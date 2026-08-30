"""CML node tools: list/inspect nodes, lifecycle control, and node-level writes.

Nodes live inside labs (lab -> nodes -> interfaces -> links). All IDs are UUID
strings. CML has no server-side pagination: list endpoints return full arrays
(with data=true for objects instead of bare UUIDs), so pagination here is
client-side over the full result.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any, Literal

import httpx
from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cml_mcp.client import ApiClient
from cml_mcp.errors import format_error
from cml_mcp.formatting import ResponseFormat, finalize, pagination_envelope, to_json
from cml_mcp.polling import wait_until
from cml_mcp.safety import AppContext, register_tool
from cml_mcp.tools.convergence import wait_for_node_stopped

LAB_ID_DESC = "Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385')."
NODE_ID_DESC = "Node ID (UUID, e.g. '26f677f3-fcb2-47ef-9171-dc112d80b54f')."

# Node states in which interfaces are expected to be up; used to decide whether a
# stopped interface is a deliberate admin-down or just a consequence of the node.
_RUNNING_NODE_STATES = {"STARTED", "BOOTED"}

# Impairment fields of a link condition (ConditionResponse); 'enabled'/'operational'
# are metadata, not impairments.
_CONDITION_FIELDS = (
    "bandwidth",
    "latency",
    "jitter",
    "loss",
    "loss_corr",
    "delay_corr",
    "limit",
    "gap",
    "duplicate",
    "duplicate_corr",
    "reorder_prob",
    "reorder_corr",
    "corrupt_prob",
    "corrupt_corr",
)

# Console tail pulled into the diagnostic report — enough to see the last boot
# messages or a stuck prompt without flooding the agent's context.
_DIAGNOSTIC_CONSOLE_LINES = 25

_DIAGNOSTIC_TRUNCATION_HINT = (
    "Set include_configuration=false to drop stored configs, or "
    "include_diagnostics=false for the plain node object."
)

_NOT_CONVERGED_NOTE = (
    "Not converged yet — the timeout elapsed while the node was still "
    "transitioning. This is NOT an API failure: the start/stop was accepted. "
    "Call cml_wait_for_node_converged (or this tool again) to keep waiting, or "
    "inspect progress with cml_get_node_console_log."
)


def _unwrap_text(response: httpx.Response) -> str:
    """Return the body as plain text, unwrapping a JSON-encoded string if needed."""
    text = response.text
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return parsed if isinstance(parsed, str) else text


def _nodes_markdown(nodes: list[dict], envelope: dict) -> str:
    lines = [f"# Nodes ({envelope['count']} shown, total {envelope['total']})", ""]
    for n in nodes:
        lines.append(f"- **{n.get('label', '?')}** ({n.get('id', '?')})")
        details = [f"definition: {n.get('node_definition', '?')}", f"state: {n.get('state', '?')}"]
        if n.get("cpus") is not None:
            details.append(f"cpus: {n['cpus']}")
        if n.get("ram") is not None:
            details.append(f"ram: {n['ram']} MB")
        lines.append(f"  - {', '.join(details)}")
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _probe_value(result: Any) -> Any | None:
    """Unwrap one asyncio.gather(return_exceptions=True) result (None when it failed)."""
    return None if isinstance(result, BaseException) else result


def _active_conditions(condition: Any) -> dict[str, Any]:
    """Impairment fields actually set on a link condition ({} when none or unfetchable).

    CML returns {} for links that were never conditioned, and zero/None for
    fields that impose no impairment.
    """
    if not isinstance(condition, dict):
        return {}
    return {
        field: condition[field]
        for field in _CONDITION_FIELDS
        if condition.get(field) not in (None, 0)
    }


def _node_summary_lines(node: dict) -> list[str]:
    operational = node.get("operational") if isinstance(node.get("operational"), dict) else {}
    cpus = node.get("cpus", operational.get("cpus"))
    ram = node.get("ram", operational.get("ram"))
    lines = [
        f"# Node diagnostic: {node.get('label', '?')} ({node.get('id', '?')})",
        "",
        f"- State: **{node.get('state', '?')}**"
        + (f" (boot progress: {node['boot_progress']})" if node.get("boot_progress") else ""),
        f"- Definition: {node.get('node_definition', '?')}"
        + (f", image: {node['image_definition']}" if node.get("image_definition") else ""),
        f"- CPUs: {cpus if cpus is not None else 'default'}"
        + (f" (limit {node['cpu_limit']}%)" if node.get("cpu_limit") else "")
        + f", RAM: {ram if ram is not None else 'default'} MB",
    ]
    if node.get("tags"):
        lines.append(f"- Tags: {', '.join(str(t) for t in node['tags'])}")
    return lines


def _interface_lines(interfaces: Any, node_state: str) -> list[str]:
    lines = ["", "## Interfaces"]
    if not isinstance(interfaces, list):
        lines.append("_Interfaces could not be read (the probe failed)._")
        return lines
    if not interfaces:
        lines.append("_This node has no interfaces._")
        return lines
    lines += [
        "",
        "| Interface | Type | State | Connected | MAC | Flags |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    flagged: list[str] = []
    for iface in interfaces:
        label = iface.get("label", "?")
        state = str(iface.get("state", "?"))
        itype = str(iface.get("type", "?"))
        connected = bool(iface.get("is_connected"))
        flags = []
        if node_state in _RUNNING_NODE_STATES and state != "STARTED":
            flags.append("ADMIN-DOWN")
        if not connected and itype != "loopback":
            flags.append("UNCONNECTED")
        if flags:
            flagged.append(f"{label} ({', '.join(flags)})")
        lines.append(
            f"| {label} | {itype} | {state} | {'yes' if connected else 'no'} | "
            f"{iface.get('mac_address') or '-'} | {', '.join(flags) or '-'} |"
        )
    if flagged:
        lines += [
            "",
            "Needs attention: " + "; ".join(flagged) + ". ADMIN-DOWN interfaces were "
            "stopped with cml_set_interface_state; UNCONNECTED physical interfaces "
            "have no link (create one with cml_create_link).",
        ]
    return lines


def _link_lines(
    links: list[tuple[dict, Any]], node_id: str, node_labels: dict[str, str] | None = None
) -> list[str]:
    lines = ["", "## Attached links"]
    if not links:
        lines.append("_No links are attached to this node._")
        return lines
    labels = node_labels or {}
    for link, condition in links:
        far_end = link.get("node_b") if link.get("node_a") == node_id else link.get("node_a")
        # Show the peer's label when we could resolve it — a bare UUID makes the
        # agent do another lookup just to read its own diagnostic report.
        peer = f"{labels[far_end]} ({far_end})" if far_end in labels else (far_end or "?")
        lines.append(
            f"- **{link.get('label', link.get('id', '?'))}** ({link.get('id', '?')}) — "
            f"state: {link.get('state', '?')}, peer node: {peer}"
        )
        active = _active_conditions(condition)
        if not active:
            continue
        enabled = bool(condition.get("enabled")) if isinstance(condition, dict) else False
        detail = ", ".join(f"{k}={v}" for k, v in active.items())
        if enabled:
            lines.append(
                f"  - **CONDITIONING ACTIVE** ({detail}) — this link is deliberately "
                "impaired and will look like a broken/slow network. Clear it with "
                "cml_set_link_condition action='clear'."
            )
        else:
            lines.append(
                f"  - Conditioning configured but disabled ({detail}); it is not "
                "affecting traffic right now."
            )
    return lines


def _layer3_lines(layer3: Any) -> list[str]:
    lines = ["", "## Layer 3 addresses"]
    if not isinstance(layer3, dict):
        lines.append("_Layer 3 addresses could not be read (the probe failed)._")
        return lines
    interfaces = layer3.get("interfaces") or {}
    if not interfaces:
        lines.append(
            "_None reported. CML only sees addresses on nodes attached to an "
            "external connector that used DHCP._"
        )
        return lines
    for mac, entry in interfaces.items():
        entry = entry if isinstance(entry, dict) else {}
        addresses = list(entry.get("ip4") or []) + list(entry.get("ip6") or [])
        lines.append(
            f"- {entry.get('label', '?')} ({mac}): {', '.join(addresses) or 'no addresses'}"
        )
    return lines


def _console_lines(console_text: Any) -> list[str]:
    lines = ["", f"## Console log (last {_DIAGNOSTIC_CONSOLE_LINES} lines)"]
    if not isinstance(console_text, str) or not console_text.strip():
        lines.append(
            "_No console output available — the node may never have booted. "
            "Read the full log with cml_get_node_console_log._"
        )
        return lines
    lines += ["", "```", console_text.strip(), "```"]
    return lines


def _node_diagnostic_markdown(
    node: dict,
    interfaces: Any,
    links: list[tuple[dict, Any]],
    layer3: Any,
    console_text: Any,
    node_labels: dict[str, str] | None = None,
) -> str:
    """Render one markdown report from the node detail plus its best-effort probes."""
    node_state = str(node.get("state", ""))
    lines = _node_summary_lines(node)
    lines += _interface_lines(interfaces, node_state)
    lines += _link_lines(links, str(node.get("id", "")), node_labels)
    lines += _layer3_lines(layer3)
    lines += _console_lines(console_text)
    return "\n".join(lines)


async def _collect_node_diagnostics(
    client: ApiClient, lab_id: str, node_id: str, node_params: dict[str, Any]
) -> str:
    """Fan out the diagnostic probes and render the report.

    Every probe except the node itself is best-effort: one failure (e.g. the
    console log 404s on a node that never booted) must not sink the report.
    """
    node, interfaces, links, layer3, console, siblings = await asyncio.gather(
        client.request_json("GET", f"/labs/{lab_id}/nodes/{node_id}", params=node_params),
        client.request_json(
            "GET",
            f"/labs/{lab_id}/nodes/{node_id}/interfaces",
            params={"data": True, "operational": True},
        ),
        client.request_json("GET", f"/labs/{lab_id}/links", params={"data": True}),
        client.request_json("GET", f"/labs/{lab_id}/nodes/{node_id}/layer3_addresses"),
        client.request(
            "GET",
            f"/labs/{lab_id}/nodes/{node_id}/consoles/0/log",
            params={"lines": _DIAGNOSTIC_CONSOLE_LINES},
        ),
        # Sibling nodes only to resolve peer UUIDs to labels in the link table.
        client.request_json("GET", f"/labs/{lab_id}/nodes", params={"data": True}),
        return_exceptions=True,
    )
    if isinstance(node, BaseException):
        raise node  # the node itself must be readable; everything else is optional

    all_links = _probe_value(links)
    attached = [
        link
        for link in (all_links if isinstance(all_links, list) else [])
        if isinstance(link, dict) and node_id in (link.get("node_a"), link.get("node_b"))
    ]
    conditions = await asyncio.gather(
        *(
            client.request_json("GET", f"/labs/{lab_id}/links/{link.get('id')}/condition")
            for link in attached
        ),
        return_exceptions=True,
    )
    console_response = _probe_value(console)
    console_text = (
        _unwrap_text(console_response) if isinstance(console_response, httpx.Response) else None
    )
    sibling_nodes = _probe_value(siblings)
    node_labels = {
        n["id"]: str(n.get("label", "?"))
        for n in (sibling_nodes if isinstance(sibling_nodes, list) else [])
        if isinstance(n, dict) and n.get("id")
    }
    return _node_diagnostic_markdown(
        node if isinstance(node, dict) else {},
        _probe_value(interfaces),
        list(zip(attached, [_probe_value(c) for c in conditions], strict=True)),
        _probe_value(layer3),
        console_text,
        node_labels,
    )


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    @register_tool(
        mcp,
        ctx,
        name="cml_list_nodes",
        title="List Lab Nodes",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_nodes(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        operational: Annotated[
            bool,
            Field(
                description="Include runtime/operational data for each node (e.g. true). "
                "Set false for topology-only data."
            ),
        ] = True,
        include_configurations: Annotated[
            bool,
            Field(
                description="Include each node's stored configuration files (e.g. false). "
                "Configurations can be large; keep false unless you need them."
            ),
        ] = False,
        label_filter: Annotated[
            str | None,
            Field(
                description="Case-insensitive substring to filter node labels (e.g. 'rtr').",
                max_length=200,
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
        """List all nodes in a lab, with optional label filtering and pagination.

        Read-only. Use this to discover node IDs and states before acting on a
        node (cml_get_node, cml_set_node_state, ...). Not for interface or link
        detail — use cml_get_node_interfaces for that. Pagination is client-side
        (CML returns the full array); limit/offset just window the result.

        Returns:
            str: Markdown listing (label, id, node_definition, state, cpus/ram),
            or JSON:
            {"total": int, "count": int, "offset": int,
             "items": [<node objects>], "has_more": bool, "next_offset": int|null}
            On failure: "Error: <actionable message>"
            (404 -> the lab_id doesn't exist; list labs to check it).
        """
        try:
            params = {
                "data": True,
                "operational": operational,
                "exclude_configurations": not include_configurations,
            }
            nodes = await client.request_json("GET", f"/labs/{lab_id}/nodes", params=params)
            nodes = nodes or []
            if label_filter:
                needle = label_filter.lower()
                nodes = [n for n in nodes if needle in str(n.get("label", "")).lower()]
            page = nodes[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(nodes), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_nodes_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_node",
        title="Get Node Details",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_node(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        operational: Annotated[
            bool,
            Field(
                description="Include runtime/operational data for the node (e.g. true)."
            ),
        ] = True,
        include_configuration: Annotated[
            bool,
            Field(
                description="Include the node's stored configuration files (e.g. true). "
                "Set false to keep the response small."
            ),
        ] = True,
        include_diagnostics: Annotated[
            bool,
            Field(
                description="Return a troubleshooting report instead of the raw node "
                "object (e.g. true): interfaces, attached links and their conditioning, "
                "L3 addresses, and the console tail, gathered in one call."
            ),
        ] = False,
    ) -> str:
        """Get full details for one node in a lab, or a full troubleshooting report.

        Read-only. Find node IDs with cml_list_nodes first. By default returns
        the raw node object: position, node_definition, state, resources
        (cpus/ram), tags, and (by default) the stored configuration and
        operational data.

        Set include_diagnostics=true when a node "isn't working" and you don't
        know why: it fans out to the node's interfaces, the lab's links (only
        those touching this node) with each link's conditioning, the node's L3
        addresses, and the last console lines, then renders one markdown report.
        It explicitly flags admin-down/unconnected interfaces and any ACTIVE
        link conditioning — a classic silent cause of "the network is broken".
        Each extra probe is best-effort: if one fails (e.g. no console log on a
        node that never booted) the rest of the report is still returned.

        Returns:
            str: With include_diagnostics=false (default) the JSON node object
            with all fields. With include_diagnostics=true a markdown report:
            state/boot progress/CPU/RAM, an interface table with a Flags column
            (ADMIN-DOWN, UNCONNECTED), attached links with conditioning called
            out, layer 3 addresses, and the console tail.
            On failure: "Error: ..." (404 -> the lab_id or node_id doesn't
            exist; check with cml_list_nodes).
        """
        try:
            params = {
                "operational": operational,
                "exclude_configurations": not include_configuration,
            }
            if include_diagnostics:
                report = await _collect_node_diagnostics(client, lab_id, node_id, params)
                return finalize(report, settings, _DIAGNOSTIC_TRUNCATION_HINT)
            data = await client.request_json(
                "GET", f"/labs/{lab_id}/nodes/{node_id}", params=params
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_node_interfaces",
        title="Get Node Interfaces",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_node_interfaces(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        operational: Annotated[
            bool,
            Field(
                description="Include runtime/operational data for each interface "
                "(e.g. true)."
            ),
        ] = True,
    ) -> str:
        """Get all interfaces of a node (full objects, not just UUIDs).

        Read-only. Use this to find interface IDs/labels, MAC addresses,
        connection status, and link state before creating links between nodes.
        For allocated IP addresses use cml_get_node_layer3_addresses instead.

        Returns:
            str: JSON array of interface objects
            [{"id": str, "label": str, "node": str, "type": "physical"|"loopback",
              "mac_address": str|null, "is_connected": bool, "state": str, ...}, ...]
            On failure: "Error: ..." (404 -> lab_id or node_id doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET",
                f"/labs/{lab_id}/nodes/{node_id}/interfaces",
                params={"data": True, "operational": operational},
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_node_layer3_addresses",
        title="Get Node Layer 3 Addresses",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_node_layer3_addresses(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
    ) -> str:
        """Get the L3 (IP) addresses CML has observed for a running node.

        Read-only. Only reports addresses when the node is connected to an
        external connector and acquired addresses via DHCP; other nodes return
        an empty interfaces map. Use it to find how to reach a node from
        outside the lab.

        Returns:
            str: JSON {"name": str, "interfaces": {"<mac>": {<address data>}, ...}},
            or "Error: ..." (404 -> lab_id or node_id doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET", f"/labs/{lab_id}/nodes/{node_id}/layer3_addresses"
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_node_console_log",
        title="Get Node Console Log",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_node_console_log(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        console_id: Annotated[
            int,
            Field(description="Console line number on the node (e.g. 0).", ge=0, le=64),
        ] = 0,
        lines: Annotated[
            int | None,
            Field(
                description="Return only the last N lines of the log (e.g. 100). "
                "Omit for the entire log.",
                ge=1,
            ),
        ] = None,
    ) -> str:
        """Get the console (boot/serial) log of a node.

        Read-only. Use this to check boot progress or diagnose a node that is
        not coming up. Most nodes use console 0. Prefer passing lines (e.g. 100)
        to avoid pulling a huge log into context.

        Returns:
            str: The raw console log text, or "Error: ..." on failure
            (404 -> lab/node/console doesn't exist, or the node has never run).
        """
        try:
            params: dict[str, Any] = {}
            if lines is not None:
                params["lines"] = lines
            response = await client.request(
                "GET",
                f"/labs/{lab_id}/nodes/{node_id}/consoles/{console_id}/log",
                params=params or None,
            )
            return finalize(_unwrap_text(response), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_add_node",
        title="Add Node to Lab",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_add_node(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        label: Annotated[
            str,
            Field(description="Label for the new node (e.g. 'rtr-1').", min_length=1,
                  max_length=128),
        ],
        node_definition: Annotated[
            str,
            Field(
                description="Node definition ID (e.g. 'iosv', 'server').",
                min_length=1,
                max_length=250,
            ),
        ],
        x: Annotated[
            int, Field(description="Topology X coordinate (e.g. 0).", ge=-15000, le=15000)
        ] = 0,
        y: Annotated[
            int, Field(description="Topology Y coordinate (e.g. 0).", ge=-15000, le=15000)
        ] = 0,
        configuration: Annotated[
            str | None,
            Field(description="Initial device configuration text (e.g. 'hostname rtr-1')."),
        ] = None,
        image_definition: Annotated[
            str | None,
            Field(
                description="Image definition ID to run (e.g. 'iosv-159-3-m8'). "
                "Omit to use the node definition's default image.",
                max_length=250,
            ),
        ] = None,
        ram: Annotated[
            int | None,
            Field(description="RAM in MB (e.g. 2048). Omit for the definition default.",
                  ge=1, le=1048576),
        ] = None,
        cpus: Annotated[
            int | None,
            Field(description="Number of CPUs (e.g. 2). Omit for the definition default.",
                  ge=1, le=128),
        ] = None,
        cpu_limit: Annotated[
            int | None,
            Field(description="CPU usage limit percentage (e.g. 80).", ge=20, le=100),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Tags for the node (e.g. ['core', 'site-a'])."),
        ] = None,
        populate_interfaces: Annotated[
            bool,
            Field(
                description="Automatically create the node definition's predefined "
                "interfaces (e.g. true). Set false only to control slots yourself "
                "afterwards via cml_create_interface."
            ),
        ] = True,
    ) -> str:
        """Add a new node to a lab.

        WRITE operation — only registered when writes are enabled. The POST is
        not auto-retried, so a lost response can't silently create a duplicate
        node. The node is created in DEFINED_ON_CORE state; start it with
        cml_set_node_state action='start'. Discover valid node_definition IDs
        via the system/definition tools.

        Returns:
            str: JSON {"id": "<new node UUID>"}, or "Error: ..."
            (404 -> lab_id doesn't exist; 400/422 -> unknown node_definition or
            invalid field values).
        """
        try:
            body: dict[str, Any] = {
                "label": label,
                "node_definition": node_definition,
                "x": x,
                "y": y,
            }
            if configuration is not None:
                body["configuration"] = configuration
            if image_definition is not None:
                body["image_definition"] = image_definition
            if ram is not None:
                body["ram"] = ram
            if cpus is not None:
                body["cpus"] = cpus
            if cpu_limit is not None:
                body["cpu_limit"] = cpu_limit
            if tags is not None:
                body["tags"] = tags
            data = await client.request_json(
                "POST",
                f"/labs/{lab_id}/nodes",
                params={"populate_interfaces": populate_interfaces},
                json_body=body,
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_update_node",
        title="Update Node",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_update_node(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        label: Annotated[
            str | None,
            Field(description="New node label (e.g. 'rtr-1-renamed').", min_length=1,
                  max_length=128),
        ] = None,
        x: Annotated[
            int | None,
            Field(description="New topology X coordinate (e.g. 150).", ge=-15000, le=15000),
        ] = None,
        y: Annotated[
            int | None,
            Field(description="New topology Y coordinate (e.g. -80).", ge=-15000, le=15000),
        ] = None,
        configuration: Annotated[
            str | None,
            Field(description="Replacement stored configuration text (e.g. 'hostname rtr-1')."),
        ] = None,
        ram: Annotated[
            int | None, Field(description="New RAM in MB (e.g. 4096).", ge=1, le=1048576)
        ] = None,
        cpus: Annotated[
            int | None, Field(description="New number of CPUs (e.g. 4).", ge=1, le=128)
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Replacement tag list (e.g. ['edge']); replaces all tags."),
        ] = None,
    ) -> str:
        """Update properties of an existing node. Only provided fields are changed.

        WRITE operation — only registered when writes are enabled. Most changes
        (configuration, ram, cpus) require the node to be STOPPED first
        (cml_set_node_state action='stop'); label and x/y position can change
        anytime. This does NOT touch the running device — a changed configuration applies on the
        next wipe+start.

        Returns:
            str: Confirmation with the node ID, or "Error: ..."
            (404 -> lab_id or node_id doesn't exist; 400 -> a change is not
            allowed in the node's current state — stop the node first).
        """
        try:
            body: dict[str, Any] = {}
            if label is not None:
                body["label"] = label
            if x is not None:
                body["x"] = x
            if y is not None:
                body["y"] = y
            if configuration is not None:
                body["configuration"] = configuration
            if ram is not None:
                body["ram"] = ram
            if cpus is not None:
                body["cpus"] = cpus
            if tags is not None:
                body["tags"] = tags
            if not body:
                return (
                    "Error: No fields to update. Provide at least one of label, x, y, "
                    "configuration, ram, cpus, tags."
                )
            await client.request_json(
                "PATCH", f"/labs/{lab_id}/nodes/{node_id}", json_body=body
            )
            return f"Node {node_id} updated ({', '.join(sorted(body))})."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_set_node_state",
        title="Start or Stop Node",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_set_node_state(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        action: Annotated[
            Literal["start", "stop"],
            Field(
                description="'start' boots the node; 'stop' powers it off "
                "(the disk state survives until wiped)."
            ),
        ],
        wait: Annotated[
            bool,
            Field(
                description="Block until the node finishes the transition (e.g. true). "
                "CML's start/stop are asynchronous; with wait=false the tool returns "
                "as soon as the request is accepted."
            ),
        ] = True,
        wait_timeout_seconds: Annotated[
            int,
            Field(
                description="With wait=true, maximum seconds to wait before returning a "
                "not-converged-yet summary (e.g. 240). An IOS node can take minutes to "
                "boot.",
                ge=10,
                le=900,
            ),
        ] = 240,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Start (boot) or stop (power off) one node in a lab, optionally waiting.

        WRITE operation — only registered when writes are enabled. Idempotent:
        starting a started node (or stopping a stopped one) is harmless.

        Both transitions are ASYNCHRONOUS on CML. With the default wait=true
        this tool polls server-side and returns only once the node has settled,
        so you do NOT need a follow-up cml_wait_for_node_converged or a
        cml_get_node poll loop. Use wait=false to fire-and-forget (e.g. when
        starting several nodes back to back), then call
        cml_wait_for_node_converged once at the end.

        A timeout is NOT an error: you get converged=false plus the last state,
        so you can keep waiting or investigate with cml_get_node_console_log.
        Before stopping, capture running config with
        cml_extract_node_configuration if you need it.

        Returns:
            str: With wait=false, a confirmation message. With wait=true, JSON
            {"lab_id": str, "node_id": str, "action": "start"|"stop",
             "converged": bool, "elapsed_seconds": float, "state": str,
             "progress": str|null (start only)}; when not converged also
            "timeout_seconds" and a "note" explaining it is not an API failure.
            On failure: "Error: ..." (404 -> lab_id or node_id doesn't exist;
            400 -> the node cannot change state, e.g. licensing or resource
            limits).
        """
        try:
            await client.request("PUT", f"/labs/{lab_id}/nodes/{node_id}/state/{action}")
            if not wait:
                return (
                    f"Node {node_id} {action} requested (wait=false); CML applies it "
                    "asynchronously. Call cml_wait_for_node_converged (or cml_get_node) "
                    "to see when it settles."
                )

            async def on_poll(state: Any, elapsed: float) -> None:
                try:
                    if ctx is not None:
                        await ctx.report_progress(
                            elapsed,
                            wait_timeout_seconds,
                            f"Waiting for node {node_id} to {action} "
                            f"({state}, {elapsed:.0f}s elapsed)",
                        )
                except Exception:
                    pass  # progress reporting must never break the wait

            summary: dict[str, Any] = {
                "lab_id": lab_id,
                "node_id": node_id,
                "action": action,
            }
            if action == "start":
                converged, _, elapsed = await wait_until(
                    lambda: client.request_json(
                        "GET", f"/labs/{lab_id}/nodes/{node_id}/check_if_converged"
                    ),
                    lambda done: bool(done),
                    timeout_seconds=wait_timeout_seconds,
                    interval_seconds=5.0,
                    on_poll=on_poll,
                )
                state = (
                    await client.request_json(
                        "GET", f"/labs/{lab_id}/nodes/{node_id}/state"
                    )
                ) or {}
                summary["converged"] = converged
                summary["elapsed_seconds"] = round(elapsed, 1)
                summary["state"] = state.get("state")
                summary["progress"] = state.get("progress")
            else:
                started = time.monotonic()
                converged, state_name = await wait_for_node_stopped(
                    client,
                    lab_id,
                    node_id,
                    timeout_seconds=wait_timeout_seconds,
                    on_poll=on_poll,
                )
                summary["converged"] = converged
                summary["elapsed_seconds"] = round(time.monotonic() - started, 1)
                summary["state"] = state_name
            if not converged:
                summary["timeout_seconds"] = wait_timeout_seconds
                summary["note"] = _NOT_CONVERGED_NOTE
            return finalize(to_json(summary), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_wipe_node",
        title="Wipe Node Disks",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_wipe_node(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
    ) -> str:
        """Wipe a node's persisted disk data, resetting it to a factory state.

        DESTRUCTIVE write — permanently discards all changes made on the device
        since it was created (the lab-stored configuration is kept and will be
        re-applied on next start). The node must be STOPPED first
        (cml_set_node_state action='stop'). To keep the running config, run
        cml_extract_node_configuration before stopping and wiping.

        Returns:
            str: Confirmation message, or "Error: ..."
            (404 -> lab_id or node_id doesn't exist; 400 -> node is not stopped).
        """
        try:
            await client.request("PUT", f"/labs/{lab_id}/nodes/{node_id}/wipe_disks")
            return f"Node {node_id} disks wiped. It will boot fresh on next start."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_extract_node_configuration",
        title="Extract Node Configuration",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_extract_node_configuration(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
    ) -> str:
        """Pull the device's current running configuration into the lab-stored config.

        DESTRUCTIVE write — it OVERWRITES the lab-stored configuration with
        whatever is running on the device right now; the previous stored config
        is lost. The node must be RUNNING. Read the result afterwards with
        cml_get_node (include_configuration=true).

        Returns:
            str: Confirmation with the platform's response, or "Error: ..."
            (404 -> lab_id or node_id doesn't exist; 400 -> node is not running
            or its definition doesn't support extraction).
        """
        try:
            data = await client.request_json(
                "PUT", f"/labs/{lab_id}/nodes/{node_id}/extract_configuration"
            )
            message = f"Configuration extracted for node {node_id}."
            if isinstance(data, str) and data.strip():
                message += f" Platform said: {data.strip()}"
            return finalize(message, settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_node",
        title="Delete Node",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_node(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        force: Annotated[
            bool,
            Field(
                description="Stop the node and wipe its disks before deleting "
                "(e.g. false). CML refuses to delete a node that is not stopped "
                "AND wiped; force performs those two steps first."
            ),
        ] = False,
        stop_timeout_seconds: Annotated[
            int,
            Field(
                description="With force=true, how long to wait for the node to "
                "reach STOPPED before wiping (e.g. 120).",
                ge=5,
                le=900,
            ),
        ] = 120,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Permanently delete a node (and its interfaces/links) from a lab.

        DESTRUCTIVE write — the node, its disk state, stored configuration, and
        attached links are removed and cannot be recovered. Verify the target
        with cml_get_node first. CML requires the node to be stopped AND wiped
        before deletion (verified live on 2.10) — this applies even to nodes
        that were never started. Either call cml_set_node_state action='stop'
        then cml_wipe_node (or cml_wipe_lab) first, or pass force=true to have
        this tool stop and wipe the node itself before the delete.

        Returns:
            str: Confirmation message, or "Error: ..."
            (404 -> lab_id or node_id doesn't exist; 400 "not wiped"/"still
            running" -> stop and wipe the node first, or retry with force=true).
        """
        try:
            if force:
                await client.request("PUT", f"/labs/{lab_id}/nodes/{node_id}/state/stop")

                async def on_poll(state: Any, elapsed: float) -> None:
                    try:
                        if ctx is not None:
                            await ctx.report_progress(
                                elapsed,
                                stop_timeout_seconds,
                                f"Waiting for node {node_id} to stop before wiping "
                                f"({state}, {elapsed:.0f}s elapsed)",
                            )
                    except Exception:
                        pass  # progress reporting must never break the delete

                # CML stop is async — wait for STOPPED before wiping, or the
                # wipe/delete races the shutdown and 400s.
                stopped, state = await wait_for_node_stopped(
                    client,
                    lab_id,
                    node_id,
                    timeout_seconds=stop_timeout_seconds,
                    on_poll=on_poll,
                )
                if not stopped:
                    return (
                        f"Error: node {node_id} did not reach a stopped state within "
                        f"the timeout (last state: {state}); it may still be shutting "
                        "down. Retry with force=true, or stop/wipe/delete manually."
                    )
                await client.request("PUT", f"/labs/{lab_id}/nodes/{node_id}/wipe_disks")
            await client.request("DELETE", f"/labs/{lab_id}/nodes/{node_id}")
            if force:
                return f"Node {node_id} stopped, wiped, and deleted."
            return f"Node {node_id} deleted."
        except Exception as e:
            return format_error(e)
