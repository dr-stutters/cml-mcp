"""CML lab tools — discovery, state/telemetry reads, and lab lifecycle writes.

Read tools cover the lab collection (/labs with with_data=true), single-lab
details, topology (compact summary or raw JSON), element state, layer-3
addresses, events, simulation stats, sample labs, lab associations, and the two
YAML text exports (lab download, pyATS testbed).

Write tools cover create/update/import/restore, sample-lab loading, day-0
bootstrap, snapshotting, association changes, plus the lifecycle transitions
start/stop/wipe/delete. Wipe, delete, bootstrap and snapshot are destructive
(bootstrap overwrites day-0 configurations, snapshot extracts running
configurations over the stored ones); wipe and delete require the lab to be
stopped first.

CML's start/stop are asynchronous. cml_start_lab and cml_stop_lab therefore
wait for convergence by default (wait=true) and report MCP progress while they
poll, so an agent gets the settled state in a single tool call.

CML has no server-side pagination: list-shaped endpoints return complete
arrays, so pagination here is client-side (fetch all, filter, slice).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import yaml
from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cml_mcp.errors import format_error
from cml_mcp.formatting import ResponseFormat, finalize, pagination_envelope, to_json
from cml_mcp.polling import wait_until
from cml_mcp.safety import AppContext, register_tool
from cml_mcp.tools.convergence import wait_for_lab_stopped

LabId = Annotated[
    str,
    Field(
        description=(
            "Lab ID, a UUID string (e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385'). "
            "Discover IDs with cml_list_labs."
        ),
        min_length=36,
        max_length=36,
    ),
]

SampleLabId = Annotated[
    str,
    Field(
        description=(
            "Sample lab ID, a UUID string (e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385'). "
            "Discover IDs with cml_list_sample_labs."
        ),
        min_length=36,
        max_length=36,
    ),
]

WAIT_DESC = (
    "true (default): block until the lab settles and return its final state. "
    "false: fire-and-forget — return immediately and poll yourself with "
    "cml_wait_for_lab_converged. Example: true."
)
WAIT_TIMEOUT_DESC = (
    "Maximum seconds to wait for the lab to settle before returning a "
    "not-settled-yet summary (e.g. 240). A timeout is NOT an error. Raise it "
    "for large labs of IOS nodes."
)

_POLL_INTERVAL_SECONDS = 5.0

_NOT_CONVERGED_NOTE = (
    "Not converged yet — the timeout elapsed while nodes were still booting. "
    "This is NOT an API failure and the lab is still starting: call "
    "cml_wait_for_lab_converged to keep waiting, or inspect slow nodes with "
    "cml_get_node_console_log."
)

_NOT_STOPPED_NOTE = (
    "Not stopped yet — the timeout elapsed while nodes were still shutting "
    "down. This is NOT an API failure: call cml_wait_for_lab_converged to keep "
    "waiting before wiping or deleting the lab."
)

AnnotationId = Annotated[
    str,
    Field(
        description=(
            "Annotation ID, a UUID string (e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385'). "
            "Discover IDs with cml_list_annotations."
        ),
        min_length=36,
        max_length=36,
    ),
]


def _cell(value: Any, limit: int = 120) -> str:
    """One markdown table cell: whitespace collapsed, pipes escaped, length capped."""
    text = " ".join(str("" if value is None else value).split()).replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text or "-"


async def _report(ctx: Context | None, progress: float, total: float, message: str) -> None:
    """Best-effort MCP progress report; a broken channel must never break a tool."""
    try:
        if ctx is not None:
            await ctx.report_progress(progress, total, message)
    except Exception:
        pass  # progress reporting is advisory only


def _text_payload(response: httpx.Response) -> str:
    """Body of a text-producing endpoint; unwraps CML's JSON-encoded strings."""
    text = response.text
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return parsed if isinstance(parsed, str) else text


def _labs_markdown(labs: list[dict], envelope: dict) -> str:
    lines = [f"# Labs ({envelope['count']} shown, total {envelope['total']})", ""]
    for lab in labs:
        parts = [f"state {lab.get('state', '?')}"]
        parts.append(f"{lab.get('node_count', 0)} nodes / {lab.get('link_count', 0)} links")
        if lab.get("owner_username"):
            parts.append(f"owner {lab['owner_username']}")
        lines.append(
            f"- **{lab.get('lab_title', '?')}** ({lab.get('id', '?')}) — " + ", ".join(parts)
        )
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _events_markdown(events: list[dict], envelope: dict) -> str:
    lines = [f"# Lab Events ({envelope['count']} shown, total {envelope['total']})", ""]
    for ev in events:
        lines.append(
            f"- {ev.get('timestamp', '?')} — {ev.get('event', '?')} on "
            f"{ev.get('element_type', '?')} ({ev.get('element_id', '?')})"
        )
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _annotations_markdown(annotations: list[dict], envelope: dict) -> str:
    lines = [f"# Annotations ({envelope['count']} shown, total {envelope['total']})", ""]
    for ann in annotations:
        entry = f"- **{ann.get('type', '?')}** ({ann.get('id', '?')})"
        if ann.get("type") == "text":
            text = " ".join(str(ann.get("text_content", "")).split())
            if len(text) > 120:
                text = text[:120] + "..."
            entry += f' — "{text}"'
        lines.append(entry)
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _sample_labs_markdown(samples: list[dict], envelope: dict) -> str:
    lines = [
        f"# Sample Labs ({envelope['count']} shown, total {envelope['total']})",
        "",
        "| Title | Sample lab ID | Node types | Description |",
        "| --- | --- | --- | --- |",
    ]
    for sample in samples:
        node_types = ", ".join(str(t) for t in (sample.get("node_types") or []))
        lines.append(
            f"| {_cell(sample.get('title'), 60)} | {_cell(sample.get('id'), 40)} "
            f"| {_cell(node_types, 60)} | {_cell(sample.get('description'), 100)} |"
        )
    lines.append("")
    lines.append("Create a lab from one of these with cml_load_sample_lab(sample_lab_id=...).")
    if envelope["has_more"]:
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _topology_summary_markdown(lab_id: str, topology: dict, states: dict) -> str:
    """Compact markdown view of a lab: meta, node table, link table, annotation count."""
    lab = topology.get("lab") or {}
    nodes: list[dict] = topology.get("nodes") or []
    links: list[dict] = topology.get("links") or []
    annotations = topology.get("annotations") or []
    smart_annotations = topology.get("smart_annotations") or []
    node_states: dict = (states or {}).get("nodes") or {}
    link_states: dict = (states or {}).get("links") or {}

    node_labels = {n.get("id"): n.get("label") for n in nodes}
    interface_labels: dict[Any, Any] = {}
    for node in nodes:
        for interface in node.get("interfaces") or []:
            interface_labels[interface.get("id")] = interface.get("label")

    lines = [f"# {_cell(lab.get('title'), 64)} ({lab_id})", ""]
    meta = [f"topology version {_cell(lab.get('version'), 16)}"]
    if lab.get("owner"):
        meta.append(f"owner {_cell(lab.get('owner'), 40)}")
    meta.append(
        f"{len(nodes)} nodes, {len(links)} links, "
        f"{len(annotations) + len(smart_annotations)} annotations"
    )
    lines.append("- " + " | ".join(meta))
    if lab.get("description"):
        lines.append(f"- description: {_cell(lab.get('description'), 200)}")
    if lab.get("notes"):
        lines.append(f"- notes: {_cell(lab.get('notes'), 200)}")

    lines += [
        "",
        "## Nodes",
        "",
        "| Label | Definition | State | Node ID |",
        "| --- | --- | --- | --- |",
    ]
    for node in nodes:
        node_id = node.get("id")
        lines.append(
            f"| {_cell(node.get('label'), 60)} | {_cell(node.get('node_definition'), 40)} "
            f"| {_cell(node_states.get(node_id), 24)} | {_cell(node_id, 40)} |"
        )

    lines += [
        "",
        "## Links",
        "",
        "| A side | B side | State | Link ID |",
        "| --- | --- | --- | --- |",
    ]
    for link in links:
        a_node = node_labels.get(link.get("node_a"), link.get("node_a"))
        b_node = node_labels.get(link.get("node_b"), link.get("node_b"))
        a_iface = interface_labels.get(link.get("interface_a"), link.get("interface_a"))
        b_iface = interface_labels.get(link.get("interface_b"), link.get("interface_b"))
        link_id = link.get("id")
        lines.append(
            f"| {_cell(a_node, 40)}:{_cell(a_iface, 40)} "
            f"| {_cell(b_node, 40)}:{_cell(b_iface, 40)} "
            f"| {_cell(link_states.get(link_id), 24)} | {_cell(link_id, 40)} |"
        )

    lines += [
        "",
        f"Annotations: {len(annotations)} drawing, {len(smart_annotations)} smart "
        "(list them with cml_list_annotations).",
        "Pass detail='full' for the raw topology JSON (coordinates, node "
        "configurations, annotation geometry).",
    ]
    return "\n".join(lines)


def _snapshot_markdown(lab_id: str, path: Path, size: int, results: list[dict]) -> str:
    extracted = sum(1 for r in results if r["result"] == "extracted")
    lines = [
        f"# Lab snapshot — {lab_id}",
        "",
        f"- Topology YAML written to `{path}` ({size} bytes).",
        f"- Running configurations extracted from {extracted} of {len(results)} nodes "
        "before the export.",
        "",
        "| Node | State | Configuration extract | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| {_cell(result['label'], 60)} | {_cell(result['state'], 24)} "
            f"| {result['result']} | {_cell(result['detail'], 100)} |"
        )
    lines += [
        "",
        f"Re-create this topology as a NEW lab with cml_restore_lab(snapshot_path='{path}').",
    ]
    return "\n".join(lines)


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    # ------------------------------------------------------------------ reads

    @register_tool(
        mcp,
        ctx,
        name="cml_list_labs",
        title="List Labs",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_labs(
        show_all: Annotated[
            bool,
            Field(
                description=(
                    "false (default): only labs owned by / shared with this user. "
                    "true: all users' labs (admin accounts only). Example: false."
                ),
            ),
        ] = False,
        title_filter: Annotated[
            str | None,
            Field(
                description=(
                    "Case-insensitive substring match on the lab title, applied "
                    "client-side (e.g. 'ccna')."
                ),
                max_length=64,
            ),
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum results to return.", ge=1, le=100)
        ] = 20,
        offset: Annotated[
            int, Field(description="Results to skip, for pagination.", ge=0)
        ] = 0,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """List labs on the CML controller, with title filtering and pagination.

        Read-only; the usual first call for any lab task — use it to find the
        lab ID for every other lab tool. CML returns the full collection
        (no server-side pagination), so filtering and paging happen client-side.

        Returns:
            str: Markdown listing (title, ID, state, node/link counts, owner),
            or JSON: {"total": int, "count": int, "offset": int,
            "items": [LabResponse, ...], "has_more": bool, "next_offset": int|null}
            where LabResponse includes id, lab_title, state
            (DEFINED_ON_CORE/STOPPED/STARTED), node_count, link_count,
            owner_username, created, modified.
            On failure: "Error: ..." (403 -> show_all=true needs an admin account).
        """
        try:
            data = await client.request_json(
                "GET", "/labs", params={"show_all": show_all, "with_data": True}
            )
            labs: list[dict] = data or []
            if title_filter:
                needle = title_filter.lower()
                labs = [lab for lab in labs if needle in str(lab.get("lab_title", "")).lower()]
            page = labs[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(labs), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_labs_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab",
        title="Get Lab Details",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab(lab_id: LabId) -> str:
        """Get full details for one lab: title, state, counts, owner, metadata.

        Read-only. Use for lab metadata; for node/interface/link runtime states
        use cml_get_lab_element_state, and for the wiring use
        cml_get_lab_topology.

        Returns:
            str: JSON LabResponse (id, lab_title, lab_description, lab_notes,
            state, node_count, link_count, owner_username, created, modified,
            effective_permissions, ...), or "Error: ..." on failure
            (404 -> lab ID doesn't exist; check it with cml_list_labs).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_topology",
        title="Get Lab Topology",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_topology(
        lab_id: LabId,
        detail: Annotated[
            Literal["summary", "full"],
            Field(
                description=(
                    "'summary' (default): compact markdown — lab meta, a node table "
                    "(label/definition/state/id) and a link table (A-node:iface <-> "
                    "B-node:iface + state), with runtime state merged in. 'full': the "
                    "raw topology JSON. Example: 'summary'."
                ),
            ),
        ] = "summary",
        exclude_configurations: Annotated[
            bool,
            Field(
                description=(
                    "Only used with detail='full': true omits node configurations for a "
                    "much smaller response; false (default) includes them. Example: true. "
                    "detail='summary' never includes configurations."
                ),
            ),
        ] = False,
    ) -> str:
        """Get the topology of a lab: nodes, links, and annotations.

        Read-only. Start with the default detail='summary' — it merges the
        topology with cml_get_lab_element_state in one call and renders a
        compact wiring overview that fits an agent's context. Switch to
        detail='full' only when you need raw fields (coordinates, node
        configurations, annotation geometry); that response can be large and
        may hit the response-size cap, so pair it with
        exclude_configurations=true or fetch single elements with
        cml_get_node / cml_get_link.

        Returns:
            str: with detail='summary', markdown (lab meta; node table
            label/definition/state/id; link table A-node:iface <->
            B-node:iface with link state; annotation counts). With
            detail='full', JSON {"nodes": [...], "links": [...], "lab": {...},
            "annotations": [...], "smart_annotations": [...]}. On failure:
            "Error: ..." (404 -> lab ID doesn't exist).
        """
        try:
            if detail == "summary":
                topology, states = await asyncio.gather(
                    client.request_json(
                        "GET",
                        f"/labs/{lab_id}/topology",
                        params={"exclude_configurations": True},
                    ),
                    client.request_json("GET", f"/labs/{lab_id}/lab_element_state"),
                )
                return finalize(
                    _topology_summary_markdown(
                        lab_id,
                        topology if isinstance(topology, dict) else {},
                        states if isinstance(states, dict) else {},
                    ),
                    settings,
                    "Fetch fewer elements with cml_list_nodes/cml_list_links (limit/offset).",
                )
            data = await client.request_json(
                "GET",
                f"/labs/{lab_id}/topology",
                params={"exclude_configurations": exclude_configurations},
            )
            return finalize(
                to_json(data),
                settings,
                "Retry with detail='summary' for a compact overview, or keep "
                "detail='full' with exclude_configurations=true.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_element_state",
        title="Get Lab Element States",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_element_state(lab_id: LabId) -> str:
        """Get the runtime state of every node, interface, and link in a lab.

        Read-only. The first stop for "what's running / what's broken" — one
        call returns the state of all lab elements, keyed by element UUID.
        Cheaper than fetching nodes individually.

        Returns:
            str: JSON {"nodes": {node_id: state, ...},
            "links": {link_id: state, ...},
            "interfaces": {interface_id: state, ...}} with states like
            DEFINED_ON_CORE/STOPPED/STARTED/BOOTED, or "Error: ..." on failure
            (404 -> lab ID doesn't exist).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/lab_element_state")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_layer3_addresses",
        title="Get Lab Layer-3 Addresses",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_layer3_addresses(lab_id: LabId) -> str:
        """Get DHCP-acquired management IP addresses for the nodes in a lab.

        Read-only. Only nodes connected to an external connector (with
        addresses acquired via DHCP) appear; an empty object means the lab is
        not started or no node has an externally reachable address yet.

        Returns:
            str: JSON {node_id: {"name": str, "interfaces": {mac: {"ip4": [...],
            "ip6": [...], "label": str, ...}}}, ...}, or "Error: ..." on failure
            (404 -> lab ID doesn't exist).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/layer3_addresses")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_events",
        title="Get Lab Events",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_events(
        lab_id: LabId,
        limit: Annotated[
            int, Field(description="Maximum events to return.", ge=1, le=100)
        ] = 20,
        offset: Annotated[
            int, Field(description="Events to skip, for pagination.", ge=0)
        ] = 0,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Get the event history for a lab (state changes, element add/remove).

        Read-only. Useful for auditing what happened to a lab and when. CML
        returns the full event list newest-last; pagination is client-side and
        preserves that order, so the last page holds the most recent events.

        Returns:
            str: Markdown listing, or JSON: {"total": int, "count": int,
            "offset": int, "items": [{"lab_id": str, "event": str,
            "element_type": str, "element_id": str, "data": {...},
            "previous": {...}, "timestamp": str}, ...], "has_more": bool,
            "next_offset": int|null}. On failure: "Error: ..."
            (404 -> lab ID doesn't exist).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/events")
            events: list[dict] = data or []
            page = events[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(events), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_events_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_simulation_stats",
        title="Get Lab Simulation Stats",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_simulation_stats(lab_id: LabId) -> str:
        """Get runtime resource statistics for a running lab's nodes and links.

        Read-only. Reports per-node compute usage (CPU, memory, disk) and
        per-link counters, keyed by element UUID. Empty/sparse for labs that
        are not started.

        Returns:
            str: JSON {"nodes": {node_id: stats, ...},
            "links": {link_id: stats, ...}}, or "Error: ..." on failure
            (404 -> lab ID doesn't exist).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/simulation_stats")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_export_lab",
        title="Export Lab YAML",
        read_only=True,
        idempotent=True,
    )
    async def cml_export_lab(lab_id: LabId) -> str:
        """Download a lab as CML2 topology YAML (the lab's portable definition).

        Read-only. The returned YAML can be saved as a backup or re-created on
        any CML controller with cml_import_lab. Includes node configurations,
        so the response can be large (truncated past the size cap).

        Returns:
            str: The lab topology as YAML text, or "Error: ..." on failure
            (404 -> lab ID doesn't exist).
        """
        try:
            response = await client.request("GET", f"/labs/{lab_id}/download")
            return finalize(_text_payload(response), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_pyats_testbed",
        title="Get pyATS Testbed",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_pyats_testbed(
        lab_id: LabId,
        hostname: Annotated[
            str | None,
            Field(
                description=(
                    "Optional hostname/IP (with optional port) to use as the console "
                    "terminal-server address in the testbed (e.g. 'cml.example.com')."
                ),
                min_length=1,
                max_length=128,
            ),
        ] = None,
    ) -> str:
        """Get the pyATS testbed YAML for a lab (device connection inventory).

        Read-only. Use when driving lab devices with pyATS/Unicon or Genie: the
        testbed lists every device with console connection details, credentials,
        OS, and platform. Not useful for topology inspection — use
        cml_get_lab_topology for that.

        Returns:
            str: The pyATS testbed as YAML text (devices, testbed, topology
            sections), or "Error: ..." on failure (404 -> lab ID doesn't exist;
            400/422 -> a testbed could not be generated for this lab).
        """
        try:
            params = {"hostname": hostname} if hostname else None
            response = await client.request(
                "GET", f"/labs/{lab_id}/pyats_testbed", params=params
            )
            return finalize(_text_payload(response), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_sample_labs",
        title="List Sample Labs",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_sample_labs(
        limit: Annotated[
            int, Field(description="Maximum sample labs to return.", ge=1, le=100)
        ] = 20,
        offset: Annotated[
            int, Field(description="Sample labs to skip, for pagination.", ge=0)
        ] = 0,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """List the ready-made sample labs shipped with this CML controller.

        Read-only. Sample labs are templates, not labs: they have their own IDs
        and do not appear in cml_list_labs until you instantiate one with
        cml_load_sample_lab. Use this when the user wants a working topology
        ("give me a BGP lab") instead of building nodes and links by hand.
        The list already carries each sample's title, description and node
        types, so no per-sample fetch is needed. Pagination is client-side
        (CML returns the full list).

        Returns:
            str: Markdown table (title, sample lab ID, node types, description),
            or JSON: {"total": int, "count": int, "offset": int,
            "items": [{"id": str, "title": str, "description": str,
            "name": str (repository), "node_types": [str, ...],
            "file_path": str}, ...], "has_more": bool, "next_offset": int|null}.
            On failure: "Error: ..." (404 -> this controller ships no sample
            lab repository).
        """
        try:
            data = await client.request_json("GET", "/sample/labs")
            samples: list[dict] = data or []
            page = samples[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(samples), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(
                _sample_labs_markdown(page, envelope),
                settings,
                "Page through the samples with limit/offset.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_lab_associations",
        title="Get Lab Associations",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_lab_associations(lab_id: LabId) -> str:
        """Get the group and user access associations configured on a lab.

        Read-only. Answers "who can see or run this lab, and with what
        permission" — the lab's owner is separate (cml_get_lab). Resolve the
        returned UUIDs to names with cml_list_groups and cml_list_users. Change
        the associations with cml_set_lab_associations.

        Returns:
            str: JSON {"groups": [{"id": "<group UUID>", "permissions":
            ["lab_admin"|"lab_edit"|"lab_exec"|"lab_view", ...]}, ...],
            "users": [{"id": "<user UUID>", "permissions": [...]}, ...]}, or
            "Error: ..." (404 -> lab ID doesn't exist; 403 -> the account
            lacks the rights to view this lab's associations).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/associations")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    # ----------------------------------------------------------------- writes

    @register_tool(
        mcp,
        ctx,
        name="cml_create_lab",
        title="Create Lab",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_create_lab(
        title: Annotated[
            str,
            Field(
                description="Title of the new lab (e.g. 'CCNA study lab').",
                min_length=1,
                max_length=64,
            ),
        ],
        description: Annotated[
            str | None,
            Field(
                description="Optional free-form description (e.g. 'OSPF area 0 practice').",
                max_length=4096,
            ),
        ] = None,
        notes: Annotated[
            str | None,
            Field(
                description="Optional free-form lab notes (e.g. 'Check R1-R2 adjacency').",
                max_length=32768,
            ),
        ] = None,
    ) -> str:
        """Create a new, empty lab on the CML controller.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true. The
        lab starts with no nodes; add them with the node tools, or use
        cml_import_lab to create a fully-populated lab from topology YAML
        instead. The POST is not auto-retried, so a lost response can't
        silently create duplicate labs.

        Returns:
            str: JSON LabResponse for the new lab (including its "id" — keep it
            for all follow-up calls), or "Error: ..." on failure
            (400/422 -> check the title length, 1-64 characters).
        """
        try:
            body: dict[str, Any] = {"title": title}
            if description is not None:
                body["description"] = description
            if notes is not None:
                body["notes"] = notes
            data = await client.request_json("POST", "/labs", json_body=body)
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_update_lab",
        title="Update Lab",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_update_lab(
        lab_id: LabId,
        title: Annotated[
            str | None,
            Field(
                description="New lab title (e.g. 'CCNA study lab v2').",
                min_length=1,
                max_length=64,
            ),
        ] = None,
        description: Annotated[
            str | None,
            Field(
                description="New lab description; replaces the existing one.",
                max_length=4096,
            ),
        ] = None,
        notes: Annotated[
            str | None,
            Field(
                description="New lab notes; replaces the existing ones.",
                max_length=32768,
            ),
        ] = None,
    ) -> str:
        """Update a lab's title, description, and/or notes.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Sends a PATCH with only the fields you provide; omitted fields are left
        unchanged on the lab. Does not touch nodes, links, or lab state.

        Returns:
            str: JSON LabResponse with the updated fields, or "Error: ..."
            (404 -> lab ID doesn't exist; no fields given -> nothing to send).
        """
        try:
            body: dict[str, Any] = {}
            if title is not None:
                body["title"] = title
            if description is not None:
                body["description"] = description
            if notes is not None:
                body["notes"] = notes
            if not body:
                return (
                    "Error: Nothing to update — provide at least one of title, "
                    "description, or notes."
                )
            data = await client.request_json("PATCH", f"/labs/{lab_id}", json_body=body)
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_import_lab",
        title="Import Lab from YAML",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_import_lab(
        topology_yaml: Annotated[
            str,
            Field(
                description=(
                    "Complete lab topology in CML2 YAML format (as produced by "
                    "cml_export_lab), e.g. 'lab:\\n  version: 0.2.2\\nnodes: []\\n...'."
                ),
                min_length=1,
            ),
        ],
        title: Annotated[
            str | None,
            Field(
                description=(
                    "Optional title for the new lab (e.g. 'Imported CCNA lab'); "
                    "defaults to the title inside the YAML."
                ),
                min_length=1,
                max_length=64,
            ),
        ] = None,
    ) -> str:
        """Create a new lab from a CML2 topology YAML document.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Creates a complete lab (nodes, links, configurations, annotations) in
        one call — pair with cml_export_lab to copy or restore labs, or use it
        to author a topology from scratch instead of many create-node/
        create-link calls. The YAML (or JSON — YAML is a superset) is parsed
        client-side and sent to POST /import as the JSON topology object the
        API requires. The POST is not auto-retried, so a lost response can't
        import twice.

        Element IDs inside the document are LOCAL references, not UUIDs: node
        ids (n0, n1, ...) and interface ids (i0, i1, ...) must be unique across
        the whole document, and each link points at two of them. CML assigns
        real UUIDs on import. A minimal, complete two-node example:

            lab:
              version: 0.2.2
              title: Two-node demo
              description: R1 Gi0/0 <-> R2 Gi0/0
            nodes:
              - id: n0
                label: r1
                node_definition: iosv
                x: -100
                y: 0
                configuration: |
                  hostname r1
                interfaces:
                  - id: i0
                    type: physical
                    slot: 0
                    label: GigabitEthernet0/0
              - id: n1
                label: r2
                node_definition: iosv
                x: 100
                y: 0
                interfaces:
                  - id: i1
                    type: physical
                    slot: 0
                    label: GigabitEthernet0/0
            links:
              - id: l0
                n1: n0
                i1: i0
                n2: n1
                i2: i1

        Required keys: lab.version (a supported schema version such as
        '0.2.2'); every node needs id + node_definition; every interface needs
        id + type ('physical' or 'loopback'); every link needs id, n1, i1, n2,
        i2. Swap node_definition for one this controller actually has
        (cml_list_node_definitions) — an unknown definition fails the import.
        Loopback interfaces cannot be linked. Then boot the result with
        cml_start_lab.

        Returns:
            str: JSON {"id": "<new lab UUID>", "warnings": [str]|null}, or
            "Error: ..." (400/422 -> the topology is not a valid CML2 topology,
            or it references node/image definitions missing on this controller).
        """
        try:
            try:
                body: Any = yaml.safe_load(topology_yaml)
            except yaml.YAMLError:
                body = None
            if not isinstance(body, dict):
                return (
                    "Error: topology_yaml did not parse to a YAML/JSON mapping. "
                    "Pass a CML2 topology document, e.g. the output of cml_export_lab."
                )
            params = {"title": title} if title else None
            data = await client.request_json("POST", "/import", params=params, json_body=body)
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_restore_lab",
        title="Restore Lab from Snapshot File",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_restore_lab(
        snapshot_path: Annotated[
            str,
            Field(
                description=(
                    "Path to a CML2 topology YAML file on the machine running this "
                    "server, as written by cml_snapshot_lab (e.g. "
                    "'/tmp/cml-snapshot-90f84e38-a71c-4d57-8d90-00fa8a197385-"
                    "20260829T101500Z.yaml'). The file must already exist."
                ),
                min_length=1,
                max_length=4096,
            ),
        ],
        title: Annotated[
            str | None,
            Field(
                description=(
                    "Optional title for the restored lab (e.g. 'CCNA lab restored'); "
                    "defaults to the title inside the snapshot."
                ),
                min_length=1,
                max_length=64,
            ),
        ] = None,
    ) -> str:
        """Re-create a lab on this controller from a snapshot file on disk.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Always creates a NEW lab; it never overwrites the lab the snapshot came
        from, so restoring twice gives you two labs. Pass a path produced by
        cml_snapshot_lab (or any CML2 topology YAML file); if you have the YAML
        as text rather than a file, use cml_import_lab instead. The POST is not
        auto-retried, so a lost response can't restore twice.

        Returns:
            str: JSON {"id": "<new lab UUID>", "warnings": [str]|null} — start
            it with cml_start_lab. On failure: "Error: ..." (file not found ->
            check the path; 400/422 -> the topology is not a valid CML2
            topology, or it references node/image definitions missing on this
            controller).
        """
        try:
            path = Path(snapshot_path).expanduser()
            if not path.is_file():
                return (
                    f"Error: no snapshot file at {path}. Pass the path returned by "
                    "cml_snapshot_lab, or import YAML text with cml_import_lab."
                )
            try:
                body: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                body = None
            if not isinstance(body, dict):
                return (
                    f"Error: the file at {path} did not parse to a YAML/JSON mapping. "
                    "Pass a CML2 topology document, e.g. a file written by "
                    "cml_snapshot_lab."
                )
            params = {"title": title} if title else None
            data = await client.request_json("POST", "/import", params=params, json_body=body)
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_load_sample_lab",
        title="Load Sample Lab",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_load_sample_lab(sample_lab_id: SampleLabId) -> str:
        """Instantiate one of the controller's sample labs as a new lab.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true. The
        fastest way to get a working topology: pick a sample with
        cml_list_sample_labs, load it here, then boot it with cml_start_lab
        (wait=true) and drive the nodes with the console tools. The sample
        template is untouched — this always creates a new, independent lab, so
        loading twice gives you two labs. Not auto-retried, so a lost response
        can't create duplicates.

        Returns:
            str: JSON LabResponse for the new lab — its "id" is the lab ID to
            pass to cml_start_lab and every other lab tool. On failure:
            "Error: ..." (404 -> sample_lab_id doesn't exist on this
            controller; list them with cml_list_sample_labs).
        """
        try:
            data = await client.request_json("PUT", f"/sample/labs/{sample_lab_id}")
            if not isinstance(data, dict) or not data.get("id"):
                return (
                    f"Sample lab {sample_lab_id} loaded, but the controller returned "
                    "no lab object — find the new lab with cml_list_labs."
                )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_start_lab",
        title="Start Lab",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_start_lab(
        lab_id: LabId,
        wait: Annotated[bool, Field(description=WAIT_DESC)] = True,
        wait_timeout_seconds: Annotated[
            int, Field(description=WAIT_TIMEOUT_DESC, ge=10, le=900)
        ] = 240,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Start the simulation for a lab (boot all of its nodes).

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Idempotent PUT; starting an already-started lab is harmless. CML's
        start is ASYNCHRONOUS, so by default (wait=true) this tool then polls
        the lab's convergence server-side and returns the settled node states —
        one call instead of a poll loop, with MCP progress reported while it
        waits. Set wait=false for fire-and-forget (then use
        cml_wait_for_lab_converged yourself). Nodes usually still need extra
        time inside the guest OS after convergence; check readiness with the
        console tools.

        Reaching wait_timeout_seconds is NOT an error: the lab keeps booting
        and the response says converged=false so you can keep waiting.

        Returns:
            str: with wait=true, JSON {"lab_id": str, "converged": bool,
            "elapsed_seconds": float, "node_states": {node_id: state, ...}} and,
            when not converged, "timeout_seconds" plus a "note" explaining it
            is not an API failure. With wait=false, a confirmation message.
            On failure: "Error: ..." (404 -> lab ID doesn't exist; 400 -> the
            lab cannot start, e.g. insufficient resources).
        """
        try:
            await client.request_json("PUT", f"/labs/{lab_id}/start")
            if not wait:
                return (
                    f"Lab {lab_id} start requested. Nodes boot asynchronously — "
                    "check cml_get_lab_element_state for progress."
                )

            async def fetch() -> bool:
                data = await client.request_json("GET", f"/labs/{lab_id}/check_if_converged")
                return bool(data)

            async def on_poll(state: bool, elapsed: float) -> None:
                await _report(
                    ctx,
                    elapsed,
                    wait_timeout_seconds,
                    f"Starting lab {lab_id} (converged={state}, {elapsed:.0f}s elapsed)",
                )

            converged, _, elapsed = await wait_until(
                fetch,
                lambda done: done,
                timeout_seconds=wait_timeout_seconds,
                interval_seconds=_POLL_INTERVAL_SECONDS,
                on_poll=on_poll,
            )
            states = await client.request_json("GET", f"/labs/{lab_id}/lab_element_state")
            summary: dict[str, Any] = {
                "lab_id": lab_id,
                "converged": converged,
                "elapsed_seconds": round(elapsed, 1),
                "node_states": (states or {}).get("nodes", {}),
            }
            if not converged:
                summary["timeout_seconds"] = wait_timeout_seconds
                summary["note"] = _NOT_CONVERGED_NOTE
            return finalize(to_json(summary), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_stop_lab",
        title="Stop Lab",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_stop_lab(
        lab_id: LabId,
        wait: Annotated[bool, Field(description=WAIT_DESC)] = True,
        wait_timeout_seconds: Annotated[
            int, Field(description=WAIT_TIMEOUT_DESC, ge=10, le=900)
        ] = 240,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Stop the simulation for a lab (shut down all of its nodes).

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Idempotent PUT; stopping an already-stopped lab is harmless. Node disk
        state persists across stop/start — use cml_wipe_lab to discard it.
        CML's stop is ASYNCHRONOUS, so by default (wait=true) this tool polls
        the lab state until it is STOPPED/DEFINED_ON_CORE and reports MCP
        progress while it waits; that matters because wiping or deleting a lab
        that is still shutting down is rejected with 400. Set wait=false for
        fire-and-forget.

        Reaching wait_timeout_seconds is NOT an error: the response says
        stopped=false with the last observed state so you can keep waiting.

        Returns:
            str: with wait=true, JSON {"lab_id": str, "stopped": bool,
            "state": str} and, when not stopped, "timeout_seconds" plus a
            "note" explaining it is not an API failure. With wait=false, a
            confirmation message. On failure: "Error: ..." (404 -> lab ID
            doesn't exist).
        """
        try:
            await client.request_json("PUT", f"/labs/{lab_id}/stop")
            if not wait:
                return f"Lab {lab_id} stop requested."

            async def on_poll(state: str, elapsed: float) -> None:
                await _report(
                    ctx,
                    elapsed,
                    wait_timeout_seconds,
                    f"Stopping lab {lab_id} (state={state}, {elapsed:.0f}s elapsed)",
                )

            stopped, state = await wait_for_lab_stopped(
                client, lab_id, timeout_seconds=wait_timeout_seconds, on_poll=on_poll
            )
            summary: dict[str, Any] = {
                "lab_id": lab_id,
                "stopped": stopped,
                "state": state,
            }
            if not stopped:
                summary["timeout_seconds"] = wait_timeout_seconds
                summary["note"] = _NOT_STOPPED_NOTE
            return finalize(to_json(summary), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_bootstrap_lab",
        title="Bootstrap Lab Configurations",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_bootstrap_lab(lab_id: LabId) -> str:
        """Regenerate CML's day-0 configurations for every node in a lab.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        CML rewrites each node's stored configuration from its node definition
        (hostname, management interface, default credentials), OVERWRITING any
        configuration you or cml_snapshot_lab put there. Use it after building
        a topology by hand so nodes boot with sane defaults, or to reset a lab
        you have edited. Take a backup first with cml_snapshot_lab or
        cml_export_lab — this cannot be undone. Changes apply on the next
        boot; already-running nodes keep their current running configuration.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> lab ID doesn't
            exist; 400 -> the lab is in a state that forbids regeneration).
        """
        try:
            await client.request_json("PUT", f"/labs/{lab_id}/bootstrap")
            return (
                f"Lab {lab_id} bootstrapped: day-0 configurations regenerated for its "
                "nodes, replacing the previously stored ones. They take effect on the "
                "next start (cml_start_lab)."
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_snapshot_lab",
        title="Snapshot Lab to File",
        read_only=False,
        destructive=True,
        idempotent=False,
    )
    async def cml_snapshot_lab(
        lab_id: LabId,
        output_path: Annotated[
            str | None,
            Field(
                description=(
                    "Where to write the topology YAML on the machine running this "
                    "server (e.g. '/tmp/ccna-lab.yaml'). Defaults to the system temp "
                    "directory as 'cml-snapshot-<lab id>-<UTC timestamp>.yaml'. An "
                    "existing file at this path is overwritten."
                ),
                min_length=1,
                max_length=4096,
            ),
        ] = None,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Save a lab to a YAML file, including the running configs of booted nodes.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        It is destructive because of the first step: for every BOOTED node the
        tool calls extract_configuration, which copies the node's RUNNING
        configuration over its stored one on the controller (the same thing
        cml_extract_node_configuration does). Nodes that are not booted are
        skipped, and a per-node failure never aborts the snapshot. It then
        downloads the lab topology (GET .../download) and writes it to
        output_path, so the file contains the freshly extracted configurations.
        Progress is reported per node. Restore the file later with
        cml_restore_lab (which creates a NEW lab). For a plain export with no
        controller-side changes, use the read-only cml_export_lab instead.

        Returns:
            str: Markdown — the file path and byte count, plus a per-node table
            (label, state, extracted/skipped/failed, detail). On failure:
            "Error: ..." (404 -> lab ID doesn't exist; OSError -> output_path
            is not writable on the server).
        """
        try:
            nodes = await client.request_json(
                "GET",
                f"/labs/{lab_id}/nodes",
                params={"data": True, "operational": True, "exclude_configurations": True},
            )
            nodes = nodes or []
            results: list[dict[str, str]] = []
            for index, node in enumerate(nodes, start=1):
                node_id = str(node.get("id", ""))
                label = str(node.get("label") or node_id)
                state = str(node.get("state") or "?")
                if state.upper() != "BOOTED":
                    results.append(
                        {
                            "label": label,
                            "state": state,
                            "result": "skipped",
                            "detail": "not BOOTED — nothing to extract",
                        }
                    )
                else:
                    try:
                        await client.request(
                            "PUT", f"/labs/{lab_id}/nodes/{node_id}/extract_configuration"
                        )
                        detail, outcome = "running configuration extracted", "extracted"
                    except Exception as node_error:  # best effort: keep snapshotting
                        detail = format_error(node_error).removeprefix("Error: ")
                        outcome = "failed"
                    results.append(
                        {"label": label, "state": state, "result": outcome, "detail": detail}
                    )
                await _report(
                    ctx, index, len(nodes), f"Snapshotting lab {lab_id}: node {label}"
                )

            response = await client.request("GET", f"/labs/{lab_id}/download")
            topology_yaml = _text_payload(response)
            if output_path:
                path = Path(output_path).expanduser()
            else:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                path = Path(tempfile.gettempdir()) / f"cml-snapshot-{lab_id}-{stamp}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(topology_yaml, encoding="utf-8")
            return finalize(
                _snapshot_markdown(lab_id, path, len(topology_yaml), results),
                settings,
                f"The complete snapshot is on disk at {path}; only this summary "
                "was shortened.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_wipe_lab",
        title="Wipe Lab",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_wipe_lab(lab_id: LabId) -> str:
        """Wipe the persisted state of every node in a lab.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        Permanently discards all persisted node state (disk changes and saved
        configurations); nodes revert to their day-0 configurations on next
        start. The lab definition itself is kept. The lab MUST be stopped
        first (cml_stop_lab) or CML rejects the request.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> lab ID doesn't
            exist; 400 -> the lab is not stopped — stop it first).
        """
        try:
            await client.request_json("PUT", f"/labs/{lab_id}/wipe")
            return (
                f"Lab {lab_id} wiped: persisted node state removed; nodes will "
                "boot from their day-0 configurations on next start."
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_lab",
        title="Delete Lab",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_lab(
        lab_id: LabId,
        force: Annotated[
            bool,
            Field(
                description=(
                    "false (default): send only the DELETE; fails unless the lab is "
                    "already stopped and wiped. true: stop and wipe the lab first "
                    "(stop, wait for STOPPED, wipe, then DELETE). Example: false."
                ),
            ),
        ] = False,
        stop_timeout_seconds: Annotated[
            int,
            Field(
                description="With force=true, how long to wait for the lab to reach "
                "STOPPED before wiping (e.g. 120). Raise it for large labs.",
                ge=5,
                le=900,
            ),
        ] = 120,
    ) -> str:
        """Permanently delete a lab and its topology from the controller.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        The platform requires a lab's elements to be stopped AND wiped before
        DELETE succeeds (verified live). With force=false (default), you must
        do that yourself first (cml_stop_lab, cml_wipe_lab); with force=true,
        this tool mirrors the platform requirement by issuing stop, wipe, and
        delete in sequence. Consider cml_export_lab beforehand to keep a YAML
        backup — deletion cannot be undone. Verify the target with cml_get_lab
        before deleting.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> lab ID doesn't
            exist; 400 -> the lab is not stopped/wiped — stop and wipe it
            first, or retry with force=true).
        """
        try:
            if force:
                await client.request_json("PUT", f"/labs/{lab_id}/stop")
                # CML stop is async — wait for the lab to settle before wiping,
                # or the wipe/delete races the shutdown and 400s.
                stopped, state = await wait_for_lab_stopped(
                    client, lab_id, timeout_seconds=stop_timeout_seconds
                )
                if not stopped:
                    return (
                        f"Error: lab {lab_id} did not reach a stopped state within "
                        f"the timeout (last state: {state}); nodes may still be "
                        "shutting down. Retry with force=true, or stop/wipe/delete "
                        "manually."
                    )
                await client.request_json("PUT", f"/labs/{lab_id}/wipe")
            await client.request_json("DELETE", f"/labs/{lab_id}")
            if force:
                return f"Lab {lab_id} stopped, wiped, and deleted."
            return f"Lab {lab_id} deleted."
        except Exception as e:
            return format_error(e)

    # -------------------------------------------------- clone and annotations

    @register_tool(
        mcp,
        ctx,
        name="cml_clone_lab",
        title="Clone Lab",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_clone_lab(
        lab_id: LabId,
        new_title: Annotated[
            str | None,
            Field(
                description=(
                    "Title for the cloned lab (e.g. 'CCNA study lab copy'); defaults "
                    "to 'Copy of <source title>' (trimmed to 64 characters)."
                ),
                min_length=1,
                max_length=64,
            ),
        ] = None,
    ) -> str:
        """Clone a lab: export its topology YAML and re-import it as a new lab.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Client-side clone: downloads the source lab's CML2 topology YAML
        (GET /labs/{lab_id}/download) and re-creates it via POST /import.
        Nodes, links, configurations, and annotations are copied; runtime
        state and persisted node disks are not. The import POST is not
        auto-retried, so a lost response can't create duplicate clones.

        Returns:
            str: JSON {"id": "<new lab UUID>", "warnings": [str]|null}, or
            "Error: ..." (404 -> source lab ID doesn't exist; 400/422 -> the
            exported topology references node/image definitions missing on
            this controller).
        """
        try:
            title = new_title
            if title is None:
                source = await client.request_json("GET", f"/labs/{lab_id}")
                source_title = str((source or {}).get("lab_title", "lab"))
                title = f"Copy of {source_title}"[:64]
            response = await client.request("GET", f"/labs/{lab_id}/download")
            try:
                body: Any = yaml.safe_load(_text_payload(response))
            except yaml.YAMLError:
                body = None
            if not isinstance(body, dict):
                return (
                    "Error: the exported lab YAML did not parse to a topology "
                    "mapping, so the clone was not created. Inspect the export "
                    "with cml_export_lab."
                )
            data = await client.request_json(
                "POST", "/import", params={"title": title}, json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_annotations",
        title="List Lab Annotations",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_annotations(
        lab_id: LabId,
        limit: Annotated[
            int, Field(description="Maximum annotations to return.", ge=1, le=100)
        ] = 20,
        offset: Annotated[
            int, Field(description="Annotations to skip, for pagination.", ge=0)
        ] = 0,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """List the drawing annotations (text/rectangle/ellipse/line) on a lab canvas.

        Read-only. Annotations are cosmetic canvas elements, not lab devices —
        for nodes and links use cml_get_lab_topology. Use this to find
        annotation IDs for cml_delete_annotation. CML returns the full list
        (no server-side pagination), so paging happens client-side.

        Returns:
            str: Markdown listing (type, ID, and the text content of text
            annotations), or JSON: {"total": int, "count": int, "offset": int,
            "items": [AnnotationResponse, ...], "has_more": bool,
            "next_offset": int|null} where AnnotationResponse includes id,
            type, x1, y1, color, border_color, thickness, z_index, and the
            type-specific fields (x2/y2, text_content, ...). On failure:
            "Error: ..." (404 -> lab ID doesn't exist).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/annotations")
            annotations: list[dict] = data or []
            page = annotations[offset : offset + limit]
            envelope = pagination_envelope(
                page, total=len(annotations), offset=offset, limit=limit
            )
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_annotations_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_add_annotation",
        title="Add Lab Annotation",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_add_annotation(
        lab_id: LabId,
        annotation_type: Annotated[
            Literal["text", "rectangle", "ellipse", "line"],
            Field(
                description=(
                    "Kind of annotation to draw on the lab canvas (e.g. 'text'). "
                    "'text' requires text_content."
                ),
            ),
        ],
        x1: Annotated[
            float,
            Field(
                description="Element anchor X coordinate (e.g. 100).",
                ge=-15000,
                le=15000,
            ),
        ],
        y1: Annotated[
            float,
            Field(
                description="Element anchor Y coordinate (e.g. 200).",
                ge=-15000,
                le=15000,
            ),
        ],
        x2: Annotated[
            float | None,
            Field(
                description=(
                    "Additional X value: width for rectangle, X radius for ellipse, "
                    "end-point X for line; unused for text (e.g. 250). Default 100."
                ),
                ge=-15000,
                le=15000,
            ),
        ] = None,
        y2: Annotated[
            float | None,
            Field(
                description=(
                    "Additional Y value: height for rectangle, Y radius for ellipse, "
                    "end-point Y for line; unused for text (e.g. 150). Default 100."
                ),
                ge=-15000,
                le=15000,
            ),
        ] = None,
        text_content: Annotated[
            str | None,
            Field(
                description=(
                    "Text to display — REQUIRED for annotation_type='text', unused "
                    "otherwise (e.g. 'Core layer')."
                ),
                max_length=8192,
            ),
        ] = None,
        color: Annotated[
            str | None,
            Field(
                description=(
                    "Fill color — the text color for text annotations (e.g. '#FF00FF' "
                    "or 'rgba(255, 0, 0, 0.5)'). Defaults: '#000000FF' for text, "
                    "'#FFFFFF00' (transparent) for shapes and lines."
                ),
                max_length=32,
            ),
        ] = None,
        border_color: Annotated[
            str | None,
            Field(
                description="Border/line color (e.g. '#808080FF', the default).",
                max_length=32,
            ),
        ] = None,
        thickness: Annotated[
            int | None,
            Field(description="Border/line thickness (e.g. 2). Default 1.", ge=1, le=32),
        ] = None,
        rotation: Annotated[
            int | None,
            Field(
                description=(
                    "Rotation in degrees (e.g. 45). Default 0. Not supported for "
                    "'line' annotations (ignored)."
                ),
                ge=0,
                le=360,
            ),
        ] = None,
    ) -> str:
        """Add a drawing annotation (text, rectangle, ellipse, or line) to a lab canvas.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Annotations are cosmetic — use the node/link tools to change the
        topology itself. The API requires a complete annotation object, so
        omitted fields are sent with sensible defaults (solid border style,
        z_index 0, and for text: 12pt regular monospace). The POST is not
        auto-retried, so a lost response can't duplicate the annotation.

        Returns:
            str: JSON AnnotationResponse for the created annotation (including
            its "id" — needed for cml_delete_annotation), or "Error: ..."
            (404 -> lab ID doesn't exist; 400/422 -> a value is out of range,
            e.g. coordinates beyond +/-15000).
        """
        try:
            if annotation_type == "text" and text_content is None:
                return (
                    "Error: text_content is required for annotation_type='text' — "
                    "provide the text to display."
                )
            body: dict[str, Any] = {
                "type": annotation_type,
                "x1": x1,
                "y1": y1,
                "border_color": border_color if border_color is not None else "#808080FF",
                "border_style": "",
                "thickness": thickness if thickness is not None else 1,
                "z_index": 0,
            }
            if annotation_type == "text":
                body["color"] = color if color is not None else "#000000FF"
                body["rotation"] = rotation if rotation is not None else 0
                body.update(
                    {
                        "text_bold": False,
                        "text_content": text_content,
                        "text_font": "monospace",
                        "text_italic": False,
                        "text_size": 12,
                        "text_unit": "pt",
                    }
                )
            else:
                body["color"] = color if color is not None else "#FFFFFF00"
                body["x2"] = x2 if x2 is not None else 100.0
                body["y2"] = y2 if y2 is not None else 100.0
                if annotation_type == "line":
                    body["line_start"] = None
                    body["line_end"] = None
                else:
                    body["rotation"] = rotation if rotation is not None else 0
                    if annotation_type == "rectangle":
                        body["border_radius"] = 0
            data = await client.request_json(
                "POST", f"/labs/{lab_id}/annotations", json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_annotation",
        title="Delete Lab Annotation",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_annotation(lab_id: LabId, annotation_id: AnnotationId) -> str:
        """Delete one drawing annotation from a lab canvas.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        Removes only the cosmetic canvas element; nodes, links, and lab state
        are untouched. Find annotation IDs with cml_list_annotations. Deletion
        cannot be undone (re-create with cml_add_annotation if needed).

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> lab or
            annotation ID doesn't exist; it may already have been deleted).
        """
        try:
            await client.request_json(
                "DELETE", f"/labs/{lab_id}/annotations/{annotation_id}"
            )
            return f"Annotation {annotation_id} deleted from lab {lab_id}."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_set_lab_associations",
        title="Set Lab Associations",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_set_lab_associations(
        lab_id: LabId,
        groups: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    "Complete list of group associations for this lab; each item is "
                    "{'id': '<group UUID>', 'permissions': [<'lab_admin'|'lab_edit'|"
                    "'lab_exec'|'lab_view', ...>]} (e.g. [{'id': "
                    "'90f84e38-a71c-4d57-8d90-00fa8a197385', 'permissions': "
                    "['lab_exec', 'lab_view']}]). Pass [] to remove all group access. "
                    "Find group IDs with cml_list_groups. Omit to leave groups alone."
                ),
            ),
        ] = None,
        users: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    "Complete list of user associations for this lab; each item is "
                    "{'id': '<user UUID>', 'permissions': [<'lab_admin'|'lab_edit'|"
                    "'lab_exec'|'lab_view', ...>]} (e.g. [{'id': "
                    "'26f677f3-fcb2-47ef-9171-dc112d80b54f', 'permissions': "
                    "['lab_view']}]). Pass [] to remove all user access. Find user IDs "
                    "with cml_list_users. Omit to leave users alone."
                ),
            ),
        ] = None,
    ) -> str:
        """Set which groups and users may access a lab, and with what permission.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Each list you pass REPLACES the stored list wholesale — it is not a
        merge — so read the current state with cml_get_lab_associations first
        and send the full desired set (omitting a key leaves that side
        untouched; passing [] revokes all of it). Permissions are
        lab_admin/lab_edit/lab_exec/lab_view; resolve names to UUIDs with
        cml_list_groups and cml_list_users. This changes access only — it does
        not change the lab owner or its nodes.

        Returns:
            str: JSON {"groups": [...], "users": [...]} with the associations
            now stored, or "Error: ..." (404 -> lab ID doesn't exist; 403 ->
            the account lacks the rights to change this lab's associations;
            400/422 -> an unknown group/user UUID or permission name).
        """
        try:
            body: dict[str, Any] = {}
            if groups is not None:
                body["groups"] = groups
            if users is not None:
                body["users"] = users
            if not body:
                return (
                    "Error: Nothing to update — provide groups and/or users "
                    "(pass [] to revoke all access on that side)."
                )
            data = await client.request_json(
                "PATCH", f"/labs/{lab_id}/associations", json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)
