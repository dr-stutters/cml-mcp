"""CML link and interface tools.

Covers the CML 2.10 link object model within a lab:
- links: list/get/create/delete, start/stop, link conditioning
  (bandwidth/latency/jitter/loss...)
- interfaces: list/get/create/delete, start/stop (interfaces are the endpoints
  links connect)
- packet capture: start/stop/status per link, plus decoded packet download

CML has no server-side pagination: list endpoints return complete arrays
(data=true for links so we get objects instead of bare UUIDs), and pagination
happens client-side before the response is enveloped.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from cml_mcp.errors import PlatformError, format_error
from cml_mcp.formatting import ResponseFormat, finalize, pagination_envelope, to_json
from cml_mcp.safety import AppContext, register_tool

_UUID_FIELD = {"min_length": 1, "max_length": 100}


class AmbiguousInterfaceLabelError(PlatformError, ValueError):
    """An abbreviated interface label matched more than one physical interface.

    A distinct type so callers can tell "abbreviation is ambiguous" (never
    guess — name the candidates) apart from "nothing matched" (match_interface
    returns None and the caller decides what to do).
    """


def _split_iface_label(label: str) -> tuple[str, str]:
    """'GigabitEthernet0/1' -> ('gigabitethernet', '0/1'); 'ens2' -> ('ens', '2')."""
    i = 0
    while i < len(label) and not label[i].isdigit():
        i += 1
    return label[:i].strip().casefold(), "".join(label[i:].split())


def match_interface(
    requested: str, ifaces: list[dict[str, Any]], node_ref: str
) -> dict[str, Any] | None:
    """Match an interface label, allowing IOS-style abbreviations ('Gi0/1').

    Pure helper (no I/O). Only PHYSICAL interfaces are considered — loopbacks
    can't carry a link. An exact casefolded label match wins outright;
    otherwise the label is split into an alpha prefix plus a numeric tail
    ("Gi0/1" -> ("gi", "0/1")) and the prefix is matched as a prefix of the
    candidate's, with the tails compared as strings (so '0/1' != '0/01').

    Returns the matching interface dict, or None when nothing matches (the
    caller decides whether that's an error). Raises
    AmbiguousInterfaceLabelError when the abbreviation matches several
    interfaces — it never guesses.
    """
    phys = [i for i in ifaces if i.get("type", "physical") == "physical"]
    req_cf = requested.strip().casefold()
    exact = [i for i in phys if str(i.get("label", "")).casefold() == req_cf]
    if exact:
        return exact[0]
    req_prefix, req_tail = _split_iface_label(requested)
    candidates = []
    for iface in phys:
        prefix, tail = _split_iface_label(str(iface.get("label", "")))
        if req_prefix and prefix.startswith(req_prefix) and tail == req_tail:
            candidates.append(iface)
    if len(candidates) > 1:
        names = ", ".join(str(i.get("label")) for i in candidates)
        raise AmbiguousInterfaceLabelError(
            f"interface label '{requested}' on node '{node_ref}' is ambiguous: "
            f"it matches {names}. Pass the full label, or the interface UUID."
        )
    return candidates[0] if candidates else None


def _links_markdown(links: list[dict[str, Any]], envelope: dict[str, Any]) -> str:
    lines = [f"# Links ({envelope['count']} shown, total {envelope['total']})", ""]
    for link in links:
        lines.append(f"- **{link.get('id', '?')}** — state: {link.get('state', '?')}")
        lines.append(
            f"  - interfaces: {link.get('interface_a', '?')} <-> {link.get('interface_b', '?')}"
        )
        if link.get("node_a") or link.get("node_b"):
            lines.append(f"  - nodes: {link.get('node_a', '?')} <-> {link.get('node_b', '?')}")
        if link.get("label"):
            lines.append(f"  - label: {link['label']}")
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _interfaces_markdown(interfaces: list[dict[str, Any]], envelope: dict[str, Any]) -> str:
    lines = [f"# Interfaces ({envelope['count']} shown, total {envelope['total']})", ""]
    for iface in interfaces:
        lines.append(f"- **{iface.get('label', '?')}** ({iface.get('id', '?')})")
        lines.append(
            f"  - node: {iface.get('node', '?')}, state: {iface.get('state', '?')}, "
            f"connected: {iface.get('is_connected', '?')}, type: {iface.get('type', '?')}"
        )
        if iface.get("mac_address"):
            lines.append(f"  - mac: {iface['mac_address']}")
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _packets_markdown(packets: list[dict[str, Any]], envelope: dict[str, Any]) -> str:
    lines = [f"# Captured packets ({envelope['count']} shown, total {envelope['total']})", ""]
    for pkt in packets:
        lines.append(
            f"- #{pkt.get('no', '?')} t={pkt.get('time', '?')}s "
            f"{pkt.get('source', '?')} -> {pkt.get('destination', '?')} "
            f"[{pkt.get('protocol', '?')}, {pkt.get('length', '?')} bytes]: "
            f"{pkt.get('info', '')}"
        )
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")
    return "\n".join(lines)


def _match_node_id(nodes: list[dict[str, Any]], node_ref: str) -> str:
    """Resolve a node reference (UUID or label) against a lab's node list."""
    for node in nodes:
        if node.get("id") == node_ref:
            return node_ref
    matches = [node for node in nodes if node.get("label") == node_ref]
    if len(matches) == 1:
        return str(matches[0].get("id"))
    if not matches:
        raise PlatformError(
            f"No node with label or ID '{node_ref}' exists in this lab. "
            "List nodes with cml_list_nodes to find the right label or UUID."
        )
    raise PlatformError(
        f"Node label '{node_ref}' matches {len(matches)} nodes in this lab — "
        "labels are ambiguous here; pass the node UUID instead."
    )


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    async def _pick_free_interface(
        lab_id: str, node_id: str, node_ref: str, used: set[str]
    ) -> str:
        """Return the first unconnected physical interface on a node.

        Raises PlatformError (rendered as 'Error: ...') when the node has no
        free physical interface left; loopbacks are skipped because they can't
        be linked.
        """
        data = await client.request_json(
            "GET", f"/labs/{lab_id}/nodes/{node_id}/interfaces", params={"data": "true"}
        )
        interfaces = data if isinstance(data, list) else []
        for iface in interfaces:
            iface_id = str(iface.get("id"))
            if iface.get("type") == "loopback" or iface.get("is_connected") or iface_id in used:
                continue
            return iface_id
        raise PlatformError(
            f"Node '{node_ref}' has no free physical interface to link. "
            "Create one with cml_create_interface (the node must be stopped), then retry."
        )

    async def _resolve_interface_label(
        lab_id: str, node_id: str, node_ref: str, label: str
    ) -> str:
        """Resolve an interface label (possibly abbreviated) on a node to its UUID.

        Raises PlatformError listing the node's physical labels when nothing
        matches, or AmbiguousInterfaceLabelError naming the candidates.
        """
        data = await client.request_json(
            "GET", f"/labs/{lab_id}/nodes/{node_id}/interfaces", params={"data": "true"}
        )
        interfaces = data if isinstance(data, list) else []
        match = match_interface(label, interfaces, node_ref)
        if match is not None:
            return str(match.get("id"))
        physical = [
            str(iface.get("label"))
            for iface in interfaces
            if iface.get("type", "physical") == "physical"
        ]
        available = ", ".join(physical) if physical else "(none)"
        raise PlatformError(
            f"Node '{node_ref}' has no physical interface matching label '{label}'. "
            f"Physical interfaces on this node: {available}. Abbreviations like "
            "'Gi0/1' are accepted; if the label you expected is missing entirely, "
            "this node definition may not produce that label; check "
            "cml_get_node_definition."
        )

    # ------------------------------------------------------------------ reads

    @register_tool(
        mcp,
        ctx,
        name="cml_list_links",
        title="List Lab Links",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_links(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
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
        """List all links (point-to-point connections between interfaces) in a lab.

        Read-only. Use this to discover link IDs before cml_get_link,
        cml_set_link_condition, or packet-capture tools. CML returns the full
        array; pagination is applied client-side.

        Returns:
            str: Markdown listing (link ID, endpoint interface/node IDs, state),
            or JSON: {"total": int, "count": int, "offset": int,
            "items": [{"id", "interface_a", "interface_b", "node_a", "node_b",
            "lab_id", "label", "state"}, ...], "has_more": bool,
            "next_offset": int|null}
            On failure: "Error: ..." (404 -> the lab_id doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET", f"/labs/{lab_id}/links", params={"data": "true"}
            )
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_links_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_link",
        title="Get Link Details",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_link(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
    ) -> str:
        """Get full details for one link: endpoint interfaces/nodes, label, state.

        Read-only. Find link IDs with cml_list_links first.

        Returns:
            str: JSON object {"id", "interface_a", "interface_b", "node_a",
            "node_b", "lab_id", "label", "state"}, or "Error: ..."
            (404 -> lab or link ID doesn't exist; check with cml_list_links).
        """
        try:
            data = await client.request_json("GET", f"/labs/{lab_id}/links/{link_id}")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_link_condition",
        title="Get Link Condition",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_link_condition(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
    ) -> str:
        """Get the conditioning (bandwidth/latency/jitter/loss...) applied to a link.

        Read-only. The platform returns {} when no conditioning has ever been
        applied; this tool reports that explicitly. Note conditioning values only
        take effect while 'enabled' is true.

        Returns:
            str: "No link conditioning is applied..." when empty, otherwise JSON
            {"bandwidth": kbps, "latency": ms, "jitter": ms, "loss": percent,
            "enabled": bool, "operational": {...}|null, ...}, or "Error: ..."
            (404 -> lab or link ID doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET", f"/labs/{lab_id}/links/{link_id}/condition"
            )
            if not data:
                return f"No link conditioning is applied to link {link_id}."
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_interfaces",
        title="List Lab Interfaces",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_interfaces(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        operational: Annotated[
            bool,
            Field(
                description="Include operational data (e.g. runtime MAC/IP details) per "
                "interface. Set false for configuration only."
            ),
        ] = True,
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
        """List all interfaces in a lab across all nodes.

        Read-only. Use this to find the two free interface IDs needed by
        cml_create_link (pick interfaces with is_connected=false). CML returns
        the full array; pagination is applied client-side.

        CML fabric rule: an interface added to an ALREADY-RUNNING node comes up
        STOPPED even though its link shows STARTED — no traffic passes and the
        device sees the port down/down. If state is STOPPED here, start it with
        cml_set_interface_state and re-check before diagnosing device config.

        Returns:
            str: Markdown listing (label, ID, node, state, connected), or JSON:
            {"total": int, "count": int, "offset": int,
            "items": [{"id", "label", "node", "lab_id", "type", "slot",
            "is_connected", "mac_address", "state", "operational"}, ...],
            "has_more": bool, "next_offset": int|null}
            On failure: "Error: ..." (404 -> the lab_id doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET",
                f"/labs/{lab_id}/interfaces",
                params={"operational": "true" if operational else "false"},
            )
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_interfaces_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_interface",
        title="Get Interface Details",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_interface(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        interface_id: Annotated[
            str,
            Field(
                description="Interface ID (UUID, e.g. '7b1c9d2e-3f4a-4b5c-8d6e-9f0a1b2c3d4e').",
                **_UUID_FIELD,
            ),
        ],
        operational: Annotated[
            bool,
            Field(description="Include operational (runtime) data. Set false for config only."),
        ] = True,
    ) -> str:
        """Get full details for one interface by ID.

        Read-only. Find interface IDs with cml_list_interfaces or from a link's
        interface_a/interface_b fields.

        Returns:
            str: JSON object {"id", "label", "node", "lab_id", "type", "slot",
            "is_connected", "mac_address", "state", "operational"}, or
            "Error: ..." (404 -> lab or interface ID doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET",
                f"/labs/{lab_id}/interfaces/{interface_id}",
                params={"operational": "true" if operational else "false"},
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_link_capture_status",
        title="Get Link Capture Status",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_link_capture_status(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
    ) -> str:
        """Get the status of the packet capture on a link.

        Read-only. starttime and packetscaptured are null when no capture is
        running. Use cml_set_link_capture (action='start') to begin one and
        cml_get_link_capture_packets to fetch the decoded packets.

        Returns:
            str: JSON {"config": {"maxpackets", "maxtime", "bpfilter", "encap"},
            "starttime": ISO datetime|null, "packetscaptured": int|null}, or
            "Error: ..." (404 -> lab or link ID doesn't exist).
        """
        try:
            data = await client.request_json(
                "GET", f"/labs/{lab_id}/links/{link_id}/capture/status"
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_link_capture_packets",
        title="Get Link Capture Packets",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_link_capture_packets(
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d'). "
                "The capture key equals the link ID; no lab_id is needed.",
                **_UUID_FIELD,
            ),
        ],
        packet_id: Annotated[
            int | None,
            Field(
                description="Numeric ID of one packet in the capture (the 'no' field from "
                "the packet list, e.g. 4712). When set, the single full packet decode is "
                "returned and limit/offset/response_format are ignored.",
                ge=1,
                le=1_000_000,
            ),
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum packets to return.", ge=1, le=500)
        ] = 50,
        offset: Annotated[
            int, Field(description="Packets to skip, for pagination.", ge=0)
        ] = 0,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Download decoded packets for a link's packet capture.

        Read-only. Requires a capture to have run on the link
        (cml_set_link_capture with action='start'); check progress with
        cml_get_link_capture_status. Without packet_id the platform returns all
        decoded packets and pagination is applied client-side. With packet_id
        the single full decode of that one packet is returned instead —
        limit/offset/response_format have no effect in that mode.

        Returns:
            str: Markdown listing (packet no, time, source, destination,
            protocol, length, info), or JSON: {"total": int, "count": int,
            "offset": int, "items": [{"no", "time", "source", "destination",
            "length", "protocol", "info"}, ...], "has_more": bool,
            "next_offset": int|null}. With packet_id: a single JSON packet
            object {"no", "time", "source", "destination", "length",
            "protocol", "info"}.
            On failure: "Error: ..." (404 -> no capture exists for this link,
            or the packet_id is not in the capture).
        """
        try:
            if packet_id is not None:
                data = await client.request_json(
                    "GET", f"/pcap/{link_id}/packet/{packet_id}"
                )
                return finalize(to_json(data), settings)
            data = await client.request_json("GET", f"/pcap/{link_id}/packets")
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_packets_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    # ----------------------------------------------------------------- writes

    @register_tool(
        mcp,
        ctx,
        name="cml_create_link",
        title="Create Link",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_create_link(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        src_int: Annotated[
            str | None,
            Field(
                description="Source interface ID (UUID) — must be unconnected "
                "(e.g. '7b1c9d2e-3f4a-4b5c-8d6e-9f0a1b2c3d4e'). Mutually exclusive with "
                "src_node/src_int_label: give exactly one of src_int or src_node.",
                **_UUID_FIELD,
            ),
        ] = None,
        dst_int: Annotated[
            str | None,
            Field(
                description="Destination interface ID (UUID) — must be unconnected and on "
                "a different node (e.g. '2e4f6a8b-1c3d-4e5f-9a7b-8c6d4e2f0a1b'). Mutually "
                "exclusive with dst_node/dst_int_label: give exactly one of dst_int or "
                "dst_node.",
                **_UUID_FIELD,
            ),
        ] = None,
        src_node: Annotated[
            str | None,
            Field(
                description="Source node label or UUID (e.g. 'R1'). Alone, the first free "
                "physical interface on that node is used; with src_int_label, that named "
                "interface is used. Provide exactly one of src_int or src_node.",
                **_UUID_FIELD,
            ),
        ] = None,
        dst_node: Annotated[
            str | None,
            Field(
                description="Destination node label or UUID (e.g. 'R2'). Alone, the first "
                "free physical interface on that node is used; with dst_int_label, that "
                "named interface is used. Provide exactly one of dst_int or dst_node.",
                **_UUID_FIELD,
            ),
        ] = None,
        src_int_label: Annotated[
            str | None,
            Field(
                description="Pin the source side to a named interface on src_node, e.g. "
                "'GigabitEthernet0/1', 'Gi0/1' or 'ens2'. IOS-style abbreviations are "
                "accepted (case-insensitive prefix + exact numeric tail). REQUIRES "
                "src_node; cannot be combined with src_int.",
                min_length=1,
                max_length=100,
            ),
        ] = None,
        dst_int_label: Annotated[
            str | None,
            Field(
                description="Pin the destination side to a named interface on dst_node, "
                "e.g. 'GigabitEthernet0/2' or 'gig0/2'. IOS-style abbreviations are "
                "accepted (case-insensitive prefix + exact numeric tail). REQUIRES "
                "dst_node; cannot be combined with dst_int.",
                min_length=1,
                max_length=100,
            ),
        ] = None,
    ) -> str:
        """Create a link between two interfaces (or nodes) in a lab's topology.

        Each side takes EITHER an explicit interface ID (src_int/dst_int) OR a
        node (src_node/dst_node, label or UUID) — mixing styles across sides is
        fine. When a node is given alone, its first unconnected PHYSICAL
        interface is picked automatically (loopbacks cannot be linked); if the
        node has no free interface, the error points at cml_create_interface.

        To pin a specific port instead, pass the interface label ALONGSIDE its
        node — e.g. src_node='R1', src_int_label='Gi0/1'. Labels are matched
        case-insensitively, exact match first, then IOS-style abbreviation
        (alpha prefix + exact numeric tail), so 'Gi0/1', 'gig0/1' and
        'GigabitEthernet0/1' all resolve; an ambiguous abbreviation is refused
        with the candidate labels rather than guessed. A label needs its node,
        so src_int_label without src_node (or with src_int) is rejected before
        any API call.

        WRITE operation — only registered when writes are enabled. Find free
        interfaces (is_connected=false) with cml_list_interfaces. The POST is
        not auto-retried, so a lost response can't silently create a duplicate
        link.

        Returns:
            str: JSON {"id": "<new link UUID>"}, or "Error: ..."
            (pre-flight -> both or neither of int/node given for a side, or a
            label passed without its node / together with an interface ID;
            no match -> the node's physical labels are listed;
            ambiguous -> the matching labels are named;
            400/422 -> an interface is already connected or IDs are invalid;
            404 -> the lab doesn't exist).
        """
        try:
            for side, int_id, node_ref, label in (
                ("src", src_int, src_node, src_int_label),
                ("dst", dst_int, dst_node, dst_int_label),
            ):
                if int_id is not None and (node_ref is not None or label is not None):
                    return (
                        f"Error: {side}_int is an interface UUID and is mutually "
                        f"exclusive with {side}_node/{side}_int_label — pass either "
                        f"{side}_int alone, or {side}_node (optionally with "
                        f"{side}_int_label)."
                    )
                if label is not None and node_ref is None:
                    return (
                        f"Error: {side}_int_label ('{label}') is only meaningful on a "
                        f"node — also pass {side}_node (e.g. {side}_node='R1', "
                        f"{side}_int_label='{label}'), or use {side}_int with the "
                        "interface UUID."
                    )
                if int_id is None and node_ref is None:
                    return (
                        f"Error: provide exactly one of {side}_int or {side}_node for "
                        f"the {'source' if side == 'src' else 'destination'} side of "
                        "the link."
                    )
            if src_node is not None or dst_node is not None:
                nodes_data = await client.request_json(
                    "GET", f"/labs/{lab_id}/nodes", params={"data": "true"}
                )
                nodes = nodes_data if isinstance(nodes_data, list) else []
                used: set[str] = set()
                if src_int is not None:
                    used.add(src_int)
                if src_node is not None:
                    src_node_id = _match_node_id(nodes, src_node)
                    if src_int_label is not None:
                        src_int = await _resolve_interface_label(
                            lab_id, src_node_id, src_node, src_int_label
                        )
                    else:
                        src_int = await _pick_free_interface(
                            lab_id, src_node_id, src_node, used
                        )
                    used.add(src_int)
                if dst_node is not None:
                    dst_node_id = _match_node_id(nodes, dst_node)
                    if dst_int_label is not None:
                        dst_int = await _resolve_interface_label(
                            lab_id, dst_node_id, dst_node, dst_int_label
                        )
                    else:
                        dst_int = await _pick_free_interface(
                            lab_id, dst_node_id, dst_node, used
                        )
            data = await client.request_json(
                "POST",
                f"/labs/{lab_id}/links",
                json_body={"src_int": src_int, "dst_int": dst_int},
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_link",
        title="Delete Link",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_link(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="ID of the link to delete (UUID, e.g. "
                "'4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
    ) -> str:
        """Delete a link, disconnecting its two interfaces.

        DESTRUCTIVE write — only registered when writes are enabled. Verify the
        target with cml_get_link before deleting.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> link doesn't
            exist; it may already have been deleted).
        """
        try:
            await client.request_json("DELETE", f"/labs/{lab_id}/links/{link_id}")
            return f"Link {link_id} deleted."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_set_link_condition",
        title="Set or Clear Link Condition",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_set_link_condition(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
        action: Annotated[
            Literal["set", "clear"],
            Field(
                description="'set' applies/modifies the provided condition fields (PATCH "
                "semantics); 'clear' removes all conditioning from the link."
            ),
        ] = "set",
        bandwidth: Annotated[
            int | None,
            Field(description="Bandwidth of the link in kbps (e.g. 1000).", ge=0, le=10_000_000),
        ] = None,
        latency: Annotated[
            int | None,
            Field(description="Delay of the link in ms (e.g. 50).", ge=0, le=10_000),
        ] = None,
        jitter: Annotated[
            int | None,
            Field(description="Jitter of the link in ms (e.g. 10).", ge=0, le=10_000),
        ] = None,
        loss: Annotated[
            float | None,
            Field(description="Packet loss in percent (e.g. 2.5).", ge=0, le=100),
        ] = None,
        loss_corr: Annotated[
            float | None,
            Field(description="Loss correlation in percent (e.g. 25).", ge=0, le=100),
        ] = None,
        delay_corr: Annotated[
            float | None,
            Field(description="Delay correlation in percent (e.g. 25).", ge=0, le=100),
        ] = None,
        limit: Annotated[
            int | None,
            Field(description="Queue limit in ms (e.g. 1000).", ge=0, le=10_000),
        ] = None,
        gap: Annotated[
            int | None,
            Field(description="Gap between packets in ms (e.g. 5).", ge=0, le=10_000),
        ] = None,
        duplicate: Annotated[
            float | None,
            Field(description="Probability of duplicates in percent (e.g. 1).", ge=0, le=100),
        ] = None,
        duplicate_corr: Annotated[
            float | None,
            Field(description="Correlation of duplicates in percent (e.g. 25).", ge=0, le=100),
        ] = None,
        reorder_prob: Annotated[
            float | None,
            Field(description="Probability of re-orders in percent (e.g. 1).", ge=0, le=100),
        ] = None,
        reorder_corr: Annotated[
            float | None,
            Field(description="Re-order correlation in percent (e.g. 25).", ge=0, le=100),
        ] = None,
        corrupt_prob: Annotated[
            float | None,
            Field(
                description="Probability of corrupted frames in percent (e.g. 0.5).",
                ge=0,
                le=100,
            ),
        ] = None,
        corrupt_corr: Annotated[
            float | None,
            Field(description="Corruption correlation in percent (e.g. 25).", ge=0, le=100),
        ] = None,
        enabled: Annotated[
            bool | None,
            Field(
                description="Whether conditioning is active (e.g. true). Conditioning values "
                "only take effect while enabled=true — set it explicitly when applying them."
            ),
        ] = None,
    ) -> str:
        """Apply, modify, or clear link conditioning: bandwidth, latency, jitter, loss...

        WRITE operation — only registered when writes are enabled. With
        action='set' (the default), only the fields you provide are sent (PATCH
        semantics) and at least one condition field is required; pass
        enabled=true to activate the conditioning, otherwise values are stored
        but inactive. With action='clear', all conditioning is removed and the
        link returns to normal behavior (the link itself is untouched — only
        the artificial shaping is deleted).

        Returns:
            str: For 'set': JSON of the applied condition (same fields plus
            "operational"). For 'clear': confirmation message. On failure:
            "Error: ..." (pre-flight -> action='set' with no condition fields;
            404 -> lab or link ID doesn't exist; 400/422 -> a value is out of
            range).
        """
        try:
            if action == "clear":
                await client.request_json(
                    "DELETE", f"/labs/{lab_id}/links/{link_id}/condition"
                )
                return (
                    f"Link conditioning cleared on link {link_id}; "
                    "normal link behavior restored."
                )
            body: dict[str, Any] = {}
            fields = {
                "bandwidth": bandwidth,
                "latency": latency,
                "jitter": jitter,
                "loss": loss,
                "loss_corr": loss_corr,
                "delay_corr": delay_corr,
                "limit": limit,
                "gap": gap,
                "duplicate": duplicate,
                "duplicate_corr": duplicate_corr,
                "reorder_prob": reorder_prob,
                "reorder_corr": reorder_corr,
                "corrupt_prob": corrupt_prob,
                "corrupt_corr": corrupt_corr,
                "enabled": enabled,
            }
            for key, value in fields.items():
                if value is not None:
                    body[key] = value
            if not body:
                return (
                    "Error: provide at least one condition field (bandwidth, latency, "
                    "jitter, loss, enabled, ...) with action='set', or use "
                    "action='clear' to remove conditioning."
                )
            data = await client.request_json(
                "PATCH", f"/labs/{lab_id}/links/{link_id}/condition", json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_set_link_capture",
        title="Start or Stop Link Packet Capture",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_set_link_capture(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
        action: Annotated[
            Literal["start", "stop"],
            Field(
                description="'start' begins a packet capture on the link; 'stop' ends the "
                "running one. maxpackets/maxtime/bpfilter/encap apply to 'start' only."
            ),
        ],
        maxpackets: Annotated[
            int | None,
            Field(
                description="Maximum number of packets to capture (e.g. 1000). "
                "action='start' only; at least one of maxpackets/maxtime must be provided.",
                ge=1,
                le=1_000_000,
            ),
        ] = None,
        maxtime: Annotated[
            int | None,
            Field(
                description="Maximum capture duration in seconds (e.g. 300). "
                "action='start' only; at least one of maxpackets/maxtime must be provided.",
                ge=1,
                le=86_400,
            ),
        ] = None,
        bpfilter: Annotated[
            str | None,
            Field(
                description="Berkeley packet filter expression (e.g. 'icmp or arp'). "
                "action='start' only.",
                max_length=128,
            ),
        ] = None,
        encap: Annotated[
            Literal[
                "ethernet",
                "frelay",
                "ppp",
                "ppp_hdlc",
                "pppoe",
                "c_hdlc",
                "slip",
                "ax25",
                "ieee802_11",
                "radiotap",
            ]
            | None,
            Field(
                description="Link encapsulation for decoding (e.g. 'ethernet'). "
                "action='start' only."
            ),
        ] = None,
    ) -> str:
        """Start or stop a packet capture on a link.

        WRITE operation — only registered when writes are enabled. For
        action='start' the link must be STARTED and at least one of maxpackets
        or maxtime is REQUIRED (the platform rejects a capture with no stop
        condition). For action='stop' the capture parameters must be omitted;
        captured packets remain downloadable via cml_get_link_capture_packets
        after stopping.

        Returns:
            str: For 'start': JSON capture status {"config": {...},
            "starttime", "packetscaptured"}. For 'stop': confirmation message.
            On failure: "Error: ..." (pre-flight -> missing stop condition for
            'start', or capture params passed with 'stop'; 404 -> lab or link
            ID doesn't exist, or no capture is running; 400 -> a capture may
            already be running, or the link is not started).
        """
        try:
            if action == "stop":
                extras = {
                    "maxpackets": maxpackets,
                    "maxtime": maxtime,
                    "bpfilter": bpfilter,
                    "encap": encap,
                }
                given = [key for key, value in extras.items() if value is not None]
                if given:
                    return (
                        f"Error: {', '.join(given)} only apply to action='start' — "
                        "omit them when stopping a capture."
                    )
                await client.request_json(
                    "PUT", f"/labs/{lab_id}/links/{link_id}/capture/stop"
                )
                return f"Packet capture stopped on link {link_id}."
            if maxpackets is None and maxtime is None:
                return (
                    "Error: provide at least one of maxpackets or maxtime — the "
                    "platform requires a stop condition for packet captures."
                )
            body: dict[str, Any] = {}
            if maxpackets is not None:
                body["maxpackets"] = maxpackets
            if maxtime is not None:
                body["maxtime"] = maxtime
            if bpfilter is not None:
                body["bpfilter"] = bpfilter
            if encap is not None:
                body["encap"] = encap
            data = await client.request_json(
                "PUT", f"/labs/{lab_id}/links/{link_id}/capture/start", json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_create_interface",
        title="Create Node Interface",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_create_interface(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        node_id: Annotated[
            str,
            Field(
                description="ID of the node to add the interface to (UUID).",
                **_UUID_FIELD,
            ),
        ],
        slot: Annotated[
            int | None,
            Field(
                description="Target slot number (e.g. 3). When given, CML bulk-creates "
                "interfaces for every slot from 0 up to this one; when omitted, one new "
                "interface is appended after the node's current interfaces.",
                ge=0,
                le=128,
            ),
        ] = None,
        mac_address: Annotated[
            str | None,
            Field(
                description="Optional MAC address in Linux format "
                "(e.g. '52:54:00:12:34:56').",
                pattern=r"^[a-fA-F\d]{2}(:[a-fA-F\d]{2}){5}$",
            ),
        ] = None,
    ) -> str:
        """Create one or more interfaces on a node (usually before linking it).

        WRITE operation — only registered when writes are enabled. Needed only
        when a node was added with populate_interfaces=false or has run out of
        free interfaces for new links; the node must be stopped. The POST is
        not auto-retried, so a lost response can't silently create duplicates.

        Returns:
            str: JSON of the created interface object, or an array when slot
            triggers bulk creation. On failure: "Error: ..." (404 -> lab or
            node ID doesn't exist; 400 -> node started or slot invalid for
            this node definition).
        """
        try:
            body: dict[str, Any] = {"node": node_id}
            if slot is not None:
                body["slot"] = slot
            if mac_address is not None:
                body["mac_address"] = mac_address
            data = await client.request_json(
                "POST", f"/labs/{lab_id}/interfaces", json_body=body
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_set_interface_state",
        title="Set Interface State",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_set_interface_state(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        interface_id: Annotated[
            str,
            Field(
                description="Interface ID (UUID, e.g. '7b1c9d2e-3f4a-4b5c-8d6e-9f0a1b2c3d4e').",
                **_UUID_FIELD,
            ),
        ],
        action: Annotated[
            Literal["start", "stop"],
            Field(
                description="'start' brings the interface up; 'stop' shuts it down "
                "(single-ended failure)."
            ),
        ],
    ) -> str:
        """Start or stop one interface — single-ended failure injection.

        Unlike cml_set_link_state (which drops BOTH ends of a link, like a
        cable pull), stopping one interface takes down only that side, so the
        neighbor sees a one-way failure — ideal for testing routing protocol
        dead timers and asymmetric failure handling. Pairs well with
        cml_set_link_condition for combined impairment testing. Idempotent:
        repeating the same action is harmless.

        WRITE operation — only registered when writes are enabled. Find
        interface IDs with cml_list_interfaces or cml_get_node_interfaces.

        CML fabric rule: an interface added to an ALREADY-RUNNING node comes up
        STOPPED even though its link shows STARTED — no traffic passes and the
        device sees the port down/down. Start it here and re-check the
        interface state before diagnosing device config.

        Returns:
            str: Confirmation message, or "Error: ..." (400 -> lab or
            interface ID doesn't exist; check with cml_list_interfaces).
        """
        try:
            await client.request_json(
                "PUT", f"/labs/{lab_id}/interfaces/{interface_id}/state/{action}"
            )
            if action == "start":
                return f"Interface {interface_id} started (brought up)."
            return (
                f"Interface {interface_id} stopped (shut down). The far end of any "
                "connected link stays up; use action='start' to restore it."
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_interface",
        title="Delete Interface",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_interface(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        interface_id: Annotated[
            str,
            Field(
                description="ID of the interface to delete (UUID, e.g. "
                "'7b1c9d2e-3f4a-4b5c-8d6e-9f0a1b2c3d4e').",
                **_UUID_FIELD,
            ),
        ],
    ) -> str:
        """Delete an interface from a node in the lab topology.

        DESTRUCTIVE write — only registered when writes are enabled. Verify the
        target with cml_get_interface first; if the interface is connected
        (is_connected=true), delete its link with cml_delete_link before
        removing the interface, and the node should be stopped.

        Returns:
            str: Confirmation message, or "Error: ..." (400 -> lab or
            interface ID doesn't exist, the interface is still connected, or
            the node is running).
        """
        try:
            await client.request_json(
                "DELETE", f"/labs/{lab_id}/interfaces/{interface_id}"
            )
            return f"Interface {interface_id} deleted."
        except Exception as e:
            return format_error(e)

    # -------------------------------------------- link state & pcap download

    @register_tool(
        mcp,
        ctx,
        name="cml_set_link_state",
        title="Set Link State",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_set_link_state(
        lab_id: Annotated[
            str,
            Field(
                description="Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385').",
                **_UUID_FIELD,
            ),
        ],
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d').",
                **_UUID_FIELD,
            ),
        ],
        action: Annotated[
            Literal["start", "stop"],
            Field(
                description="'start' re-enables connectivity on a stopped link; 'stop' "
                "takes the link down (simulated cable pull) without deleting it."
            ),
        ],
    ) -> str:
        """Start or stop a link (both ends), without changing the topology.

        WRITE operation — only registered when writes are enabled. 'stop'
        simulates a cable pull: the link and its endpoint interfaces remain in
        the topology, traffic simply stops flowing until 'start' brings it back
        up. For a single-ended failure (one side only), use
        cml_set_interface_state instead. Idempotent: repeating the same action
        is harmless. To remove the link entirely, use cml_delete_link. Check
        the current state with cml_get_link.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> lab or link ID
            doesn't exist; check with cml_list_links).
        """
        try:
            await client.request_json(
                "PUT", f"/labs/{lab_id}/links/{link_id}/state/{action}"
            )
            if action == "start":
                return f"Link {link_id} started; connectivity re-enabled."
            return (
                f"Link {link_id} stopped (simulated cable pull); traffic no longer "
                "passes. Use action='start' to restore connectivity."
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_download_link_pcap",
        title="Download Link PCAP File",
        read_only=True,
        idempotent=True,
    )
    async def cml_download_link_pcap(
        link_id: Annotated[
            str,
            Field(
                description="Link ID (UUID, e.g. '4d3a2b1c-0e9f-4a8b-9c7d-6e5f4a3b2c1d'). "
                "The capture key equals the link ID; no lab_id is needed.",
                **_UUID_FIELD,
            ),
        ],
        output_path: Annotated[
            str | None,
            Field(
                description="Local file path to save the pcap to (e.g. "
                "'/home/user/capture.pcap'). Defaults to cml-capture-<link_id>.pcap "
                "in the system temp directory.",
                min_length=1,
                max_length=4096,
            ),
        ] = None,
    ) -> str:
        """Download the raw PCAP file for a link's packet capture to a local file.

        Read-only. Requires a capture to have run on the link
        (cml_set_link_capture with action='start'). The platform returns binary
        pcap data, which is written to disk rather than into the conversation;
        for a human-readable decode use cml_get_link_capture_packets instead.

        Returns:
            str: Confirmation with the saved file path and byte size, plus a
            note that the file opens in Wireshark. On failure: "Error: ..."
            (404 -> no capture exists for this link; an empty pcap body means
            no capture ran on that link — start one first).
        """
        try:
            response = await client.request("GET", f"/pcap/{link_id}")
            content = response.content
            if not content:
                return (
                    f"Error: the platform returned an empty pcap for link {link_id} "
                    "— no capture ran on that link. Start one with "
                    "cml_set_link_capture (action='start'; the link must be started), "
                    "wait for packets via cml_get_link_capture_status, then download "
                    "again."
                )
            if output_path:
                path = Path(output_path)
            else:
                path = Path(tempfile.gettempdir()) / f"cml-capture-{link_id}.pcap"
            path.write_bytes(content)
            return (
                f"Saved pcap for link {link_id} to {path} ({len(content)} bytes). "
                "The file opens in Wireshark (or any pcap-aware tool) for full "
                "packet analysis."
            )
        except Exception as e:
            return format_error(e)
