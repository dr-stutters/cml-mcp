"""CML system tools: platform info, health, stats, definitions, users, groups.

Visibility into the CML controller itself (as opposed to labs):
- system information / health / statistics of the controller and compute hosts
- health also surfaces maintenance mode and unacknowledged system notices
- resource pools: per-pool CPU/memory/disk/license limits vs current usage
- node and image definitions (the catalog of node types agents can instantiate)
- external connectors (bridges to the outside world): list, host rescan, update
- low-level controller diagnostics (launch queue, startup scheduler, and friends)
- licensing registration status, features, and limits
- users and groups, including admin-only create/delete writes

CML returns full collections with no server-side pagination; list tools here
fetch everything, apply any client-side filter, then page with limit/offset and
present the standard pagination envelope.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from cml_mcp.errors import format_error
from cml_mcp.formatting import ResponseFormat, finalize, pagination_envelope, to_json
from cml_mcp.safety import AppContext, register_tool

UserId = Annotated[
    str,
    Field(
        description=(
            "User ID, a UUID string (e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385'). "
            "Discover IDs with cml_list_users."
        ),
        min_length=36,
        max_length=36,
    ),
]

GroupId = Annotated[
    str,
    Field(
        description=(
            "Group ID, a UUID string (e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385'). "
            "Discover IDs with cml_list_groups."
        ),
        min_length=36,
        max_length=36,
    ),
]

ConnectorId = Annotated[
    str,
    Field(
        description=(
            "External connector ID, a UUID string (e.g. "
            "'90f84e38-a71c-4d57-8d90-00fa8a197385'). Discover IDs with "
            "cml_list_external_connectors — this is the connector's id, not its "
            "label and not the host device name such as 'bridge1'."
        ),
        min_length=36,
        max_length=36,
    ),
]


def _append_more_hint(lines: list[str], envelope: dict[str, Any]) -> None:
    if envelope["has_more"]:
        lines.append("")
        lines.append(f"More available: repeat with offset={envelope['next_offset']}.")


_CONTROLLER_SERVICES = (
    "core_connected",
    "airhandler",
    "dispatcher",
    "ipsnooper",
    "pcapdemux",
    "nodes_loaded",
    "images_loaded",
)

# (key in ResourcePoolUsageData / pool object, table column header)
_RESOURCE_COLUMNS = (
    ("cpus", "CPU shares"),
    ("ram", "RAM MB"),
    ("disk_space", "Disk GB"),
    ("licenses", "Licenses"),
)


def _bool_word(value: Any) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _unacknowledged_notices(notices: list[dict]) -> list[dict]:
    """Enabled notices that at least one targeted user has not acknowledged.

    A notice with an empty acknowledgement map is shown to everyone and counts
    as unacknowledged; one where every mapped user is True is acknowledged.
    """
    unacked = []
    for notice in notices:
        if not isinstance(notice, dict) or not notice.get("enabled"):
            continue
        acked = notice.get("acknowledged") or {}
        if acked and all(acked.values()):
            continue
        unacked.append(notice)
    return unacked


def _system_health_markdown(
    health: dict, maintenance: dict | None, notices: list[dict] | None
) -> str:
    controller = health.get("controller") or {}
    computes = health.get("computes") or {}
    lines = ["# System Health", ""]
    lines.append(f"- Overall valid: {_bool_word(health.get('valid'))}")
    lines.append(
        f"- Licensed: {_bool_word(health.get('is_licensed'))} "
        f"(enterprise: {_bool_word(health.get('is_enterprise'))})"
    )
    down = [name for name in _CONTROLLER_SERVICES if controller.get(name) is False]
    if down:
        lines.append(f"- Controller: DEGRADED — down: {', '.join(down)}")
    else:
        lines.append(f"- Controller: valid={_bool_word(controller.get('valid'))}, all services up")
    healthy = sum(1 for c in computes.values() if isinstance(c, dict) and c.get("valid"))
    lines.append(f"- Computes: {healthy} of {len(computes)} healthy")
    for compute_id, compute in computes.items():
        if isinstance(compute, dict) and not compute.get("valid"):
            lines.append(f"  - {compute_id}: UNHEALTHY")
    lines.append("")
    if maintenance is None:
        lines.append("Maintenance mode: unknown (status could not be fetched)")
    else:
        lines.append(f"Maintenance mode: {'on' if maintenance.get('maintenance_mode') else 'off'}")
    if notices is None:
        lines.append("Unacknowledged notices: unknown (could not be fetched)")
    else:
        unacked = _unacknowledged_notices(notices)
        if not unacked:
            lines.append("Unacknowledged notices: none")
        else:
            lines.append(f"Unacknowledged notices ({len(unacked)}):")
            for notice in unacked:
                line = f"- [{notice.get('level', '?')}] {notice.get('label', '?')}"
                if notice.get("activated"):
                    line += f" (activated: {notice['activated']})"
                lines.append(line)
    return "\n".join(lines)


def _merge_resource_pools(pools: list[dict], usage: list[dict]) -> list[dict]:
    """Join /resource_pools objects with /resource_pool_usage entries by pool ID."""
    by_id: dict[str, dict] = {}
    for pool in pools:
        if isinstance(pool, dict) and pool.get("id"):
            by_id[pool["id"]] = dict(pool)
    for entry in usage:
        if not (isinstance(entry, dict) and entry.get("id")):
            continue
        record = by_id.setdefault(entry["id"], {"id": entry["id"]})
        record.setdefault("label", entry.get("label"))
        record["limit"] = entry.get("limit") or {}
        record["usage"] = entry.get("usage") or {}
    return list(by_id.values())


def _usage_cell(used: Any, limit: Any) -> str:
    used_text = "0" if used is None else str(used)
    limit_text = "unlimited" if limit is None else str(limit)
    return f"{used_text} / {limit_text}"


def _resource_usage_markdown(records: list[dict], lab_id: str | None) -> str:
    scope = f" used by lab {lab_id}" if lab_id else ""
    lines = [f"# Resource Pool Usage ({len(records)} pools{scope})", ""]
    lines.append("| Pool | " + " | ".join(header for _, header in _RESOURCE_COLUMNS) + " |")
    lines.append("|---" * (len(_RESOURCE_COLUMNS) + 1) + "|")
    totals_used = dict.fromkeys((key for key, _ in _RESOURCE_COLUMNS), 0)
    totals_limit: dict[str, int | None] = dict.fromkeys((key for key, _ in _RESOURCE_COLUMNS), 0)
    for record in records:
        # Pools without a usage entry (e.g. templates) fall back to their own limits.
        limit = record.get("limit")
        if limit is None:
            limit = {key: record.get(key) for key, _ in _RESOURCE_COLUMNS}
        used = record.get("usage") or {}
        cells = []
        for key, _ in _RESOURCE_COLUMNS:
            cells.append(_usage_cell(used.get(key), limit.get(key)))
            totals_used[key] += used.get(key) or 0
            if limit.get(key) is None:
                totals_limit[key] = None  # any unlimited pool makes the total unlimited
            elif totals_limit[key] is not None:
                totals_limit[key] += limit[key]
        label = record.get("label", "?")
        lines.append(f"| **{label}** ({record['id']}) | " + " | ".join(cells) + " |")
    total_cells = [
        _usage_cell(totals_used[key], totals_limit[key]) for key, _ in _RESOURCE_COLUMNS
    ]
    lines.append("| **Totals** | " + " | ".join(total_cells) + " |")
    lines.append("")
    lines.append("CPU values are 1/100-CPU shares (100 = one full CPU).")
    return "\n".join(lines)


def _node_definitions_markdown(defs: list[dict], envelope: dict) -> str:
    lines = [f"# Node Definitions ({envelope['count']} shown, total {envelope['total']})", ""]
    for d in defs:
        general = d.get("general") or {}
        lines.append(f"- **{d.get('id', '?')}**")
        description = general.get("description") or (d.get("ui") or {}).get("description")
        if description:
            lines.append(f"  - {description}")
        if general.get("nature"):
            lines.append(f"  - nature: {general['nature']}")
    _append_more_hint(lines, envelope)
    return "\n".join(lines)


def _image_definitions_markdown(images: list[dict], envelope: dict) -> str:
    lines = [f"# Image Definitions ({envelope['count']} shown, total {envelope['total']})", ""]
    for img in images:
        lines.append(f"- **{img.get('id', '?')}** — {img.get('label', '?')}")
        lines.append(f"  - node_definition: {img.get('node_definition_id', '?')}")
        if img.get("description"):
            lines.append(f"  - {img['description']}")
    _append_more_hint(lines, envelope)
    return "\n".join(lines)


def _connectors_markdown(connectors: list[dict]) -> str:
    lines = [f"# External Connectors ({len(connectors)})", ""]
    for c in connectors:
        lines.append(f"- **{c.get('label', '?')}** ({c.get('id', '?')})")
        details = []
        if c.get("device_name"):
            details.append(f"device: {c['device_name']}")
        if c.get("operational"):
            details.append(f"state: {c['operational']}")
        if c.get("tags"):
            details.append(f"tags: {', '.join(c['tags'])}")
        if details:
            lines.append(f"  - {'; '.join(details)}")
    return "\n".join(lines)


def _users_markdown(users: list[dict], envelope: dict) -> str:
    lines = [f"# Users ({envelope['count']} shown, total {envelope['total']})", ""]
    for u in users:
        line = f"- **{u.get('username', '?')}** ({u.get('id', '?')})"
        details = []
        if u.get("admin") is not None:
            details.append("admin" if u["admin"] else "non-admin")
        if isinstance(u.get("groups"), list):
            details.append(f"groups: {len(u['groups'])}")
        if details:
            line += f" — {', '.join(details)}"
        lines.append(line)
    _append_more_hint(lines, envelope)
    return "\n".join(lines)


def _licensing_markdown(data: dict) -> str:
    registration = data.get("registration") or {}
    authorization = data.get("authorization") or {}
    product = data.get("product_license") or {}
    lines = ["# Licensing", ""]
    reg_line = f"- Registration: {registration.get('status', '?')}"
    reg_details = []
    if registration.get("smart_account"):
        reg_details.append(f"smart account: {registration['smart_account']}")
    if registration.get("virtual_account"):
        reg_details.append(f"virtual account: {registration['virtual_account']}")
    if registration.get("expires"):
        reg_details.append(f"expires: {registration['expires']}")
    if reg_details:
        reg_line += f" ({'; '.join(reg_details)})"
    lines.append(reg_line)
    auth_line = f"- Authorization: {authorization.get('status', '?')}"
    if authorization.get("expires"):
        auth_line += f" (expires: {authorization['expires']})"
    lines.append(auth_line)
    lines.append(
        f"- Product license: {product.get('active', '?')} "
        f"(enterprise: {'yes' if product.get('is_enterprise') else 'no'})"
    )
    lines.append(f"- Reservation mode: {'on' if data.get('reservation_mode') else 'off'}")
    features = data.get("features") or []
    lines.append("")
    lines.append(f"## Features ({len(features)})")
    for feat in features:
        line = (
            f"- **{feat.get('name') or feat.get('id', '?')}** — "
            f"in use {feat.get('in_use', '?')} of max {feat.get('max', '?')}"
        )
        if feat.get("status"):
            line += f" (status: {feat['status']})"
        lines.append(line)
    return "\n".join(lines)


def _groups_markdown(groups: list[dict], envelope: dict) -> str:
    lines = [f"# Groups ({envelope['count']} shown, total {envelope['total']})", ""]
    for g in groups:
        line = f"- **{g.get('name', '?')}** ({g.get('id', '?')})"
        if isinstance(g.get("members"), list):
            line += f" — members: {len(g['members'])}"
        lines.append(line)
        if g.get("description"):
            lines.append(f"  - {g['description']}")
    _append_more_hint(lines, envelope)
    return "\n".join(lines)


def _launch_queue_markdown(entries: list[dict]) -> str:
    if not entries:
        return (
            "# Node Launch Queue (0)\n\n"
            "The launch queue is empty: nothing is waiting for compute capacity, "
            "so a node still in DEFINED_ON_CORE is not queued — look at "
            "cml_get_system_health and the node's own state instead."
        )
    lines = [f"# Node Launch Queue ({len(entries)} waiting)", ""]
    for entry in entries:
        lines.append(f"- node {entry.get('node_id', '?')} (lab {entry.get('lab_id', '?')})")
        details = [f"queued_time: {entry.get('queued_time', '?')}"]
        if entry.get("priority") is not None:
            details.append(f"priority: {entry['priority']}")
        deps = entry.get("dependencies") or []
        if deps:
            details.append(f"waiting on {len(deps)} node(s)")
        req = entry.get("resource_requirements")
        if isinstance(req, dict):
            details.append(
                "needs cpus={}, ram={}".format(req.get("cpus", "?"), req.get("ram", "?"))
            )
        lines.append(f"  - {'; '.join(details)}")
    return "\n".join(lines)


def _startup_scheduler_markdown(data: dict) -> str:
    lines = [
        "# Startup Scheduler",
        "",
        f"- System ready: {_bool_word(data.get('system_ready'))}",
        f"- Core driver connected: {_bool_word(data.get('core_driver_connected'))}",
        f"- Node definitions loaded: {_bool_word(data.get('node_definitions_loaded'))}",
        f"- Licensing loaded: {_bool_word(data.get('licensing_loaded'))}",
        f"- LLD connected: {_bool_word(data.get('lld_connected'))}",
        f"- LLD synced: {_bool_word(data.get('lld_synced'))}",
    ]
    if not data.get("system_ready"):
        lines.append("")
        lines.append(
            "system_ready is not true: the controller cannot launch nodes yet, so "
            "starts will sit in DEFINED_ON_CORE regardless of the lab."
        )
    return "\n".join(lines)


def _diagnostics_markdown(category: str, data: Any) -> str:
    if category == "node_launch_queue":
        return _launch_queue_markdown([e for e in (data or []) if isinstance(e, dict)])
    if category == "startup_scheduler" and isinstance(data, dict):
        return _startup_scheduler_markdown(data)
    if isinstance(data, list):
        header = f"# Diagnostics: {category} ({len(data)} entries)"
    elif isinstance(data, dict):
        header = f"# Diagnostics: {category} ({len(data)} keys)"
    else:
        header = f"# Diagnostics: {category}"
    # No stable shape for the remaining categories: show the raw document.
    return f"{header}\n\n```json\n{to_json(data)}\n```"


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    @register_tool(
        mcp,
        ctx,
        name="cml_get_system_information",
        title="Get System Information",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_system_information() -> str:
        """Get the CML controller's version and readiness state.

        Read-only. Use this first to confirm the server is reachable, which CML
        release it runs, and whether it is ready to start nodes. Not for resource
        usage (use cml_get_system_stats) or service health (cml_get_system_health).

        Returns:
            str: JSON object:
            {"version": str (e.g. "2.10.0"), "ready": bool (at least one compute
             can start nodes), "allow_ssh_pubkey_auth": bool, "oui": str|null
             (MAC prefix, e.g. "52:54:00:00:00:00"), "features": [str, ...]}
            On failure: "Error: <actionable message>".
        """
        try:
            data = await client.request_json("GET", "/system_information")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_system_health",
        title="Get System Health",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_system_health(
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Get health status of the CML controller services and compute hosts.

        Read-only. Use when labs or nodes misbehave to check whether the platform
        itself is degraded (services down, computes offline, unlicensed, in
        maintenance mode). Also reports whether maintenance mode is on (non-admin
        access is blocked while it is) and lists unacknowledged system notices.
        Admin accounts see more detail than regular users. For CPU/memory/disk
        numbers use cml_get_system_stats instead.

        Returns:
            str: Markdown summary (overall/controller/compute health, a
            'Maintenance mode: on/off' line, and unacknowledged notice titles
            with levels/dates), or JSON object:
            {"valid": bool|null (overall health), "is_licensed": bool|null,
             "is_enterprise": bool,
             "controller": {"core_connected": bool|null, "airhandler": bool|null,
              "dispatcher": bool|null, "ipsnooper": bool|null,
              "pcapdemux": bool|null, "nodes_loaded": bool, "images_loaded": bool,
              "valid": bool},
             "computes": {"<compute-uuid>": {...per-compute health...}, ...},
             "maintenance_mode": {"maintenance_mode": bool, "notice": str|null,
              "resolved_notice": {...}|null} | null (null if it could not be
              fetched, e.g. 403 for non-admins),
             "notices": [{"id": str, "level": "INFO"|"SUCCESS"|"WARNING"|"ERROR",
              "label": str, "content": str, "enabled": bool, "activated":
              str|null, "acknowledged": {"<user-uuid>": bool, ...},
              "groups": [str, ...]}, ...] | null (null if not fetchable)}
            On failure: "Error: <actionable message>".
        """
        try:
            health, maintenance, notices = await asyncio.gather(
                client.request_json("GET", "/system_health"),
                client.request_json("GET", "/system/maintenance_mode"),
                client.request_json("GET", "/system/notices"),
                return_exceptions=True,
            )
            if isinstance(health, BaseException):
                raise health
            # The extras are best-effort context: never let them break the tool.
            maintenance_data = maintenance if isinstance(maintenance, dict) else None
            notices_data = notices if isinstance(notices, list) else None
            if response_format is ResponseFormat.JSON:
                combined = dict(health) if isinstance(health, dict) else {"health": health}
                combined["maintenance_mode"] = maintenance_data
                combined["notices"] = notices_data
                return finalize(to_json(combined), settings)
            health_dict = health if isinstance(health, dict) else {}
            return finalize(
                _system_health_markdown(health_dict, maintenance_data, notices_data), settings
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_system_stats",
        title="Get System Statistics",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_system_stats() -> str:
        """Get CPU, memory, and disk usage for the controller and compute hosts.

        Read-only. Use to check capacity before starting large labs, or to
        diagnose slow simulations (overloaded computes). For service up/down
        status use cml_get_system_health instead.

        Returns:
            str: JSON object:
            {"all": {"cpu": {...}, "memory": {...}, "disk": {...}} (aggregate),
             "controller": {"disk": {...}},
             "computes": {"<compute-uuid>": {...per-compute stats...}, ...}}
            On failure: "Error: <actionable message>".
        """
        try:
            data = await client.request_json("GET", "/system_stats")
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_node_definitions",
        title="List Node Definitions",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_node_definitions(
        id_filter: Annotated[
            str | None,
            Field(
                description=(
                    "Case-insensitive substring to filter definition IDs "
                    "(e.g. 'ios' matches 'iosv' and 'iosxrv')."
                ),
                max_length=250,
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
        """List the node definitions (node types) installed on this CML server.

        Read-only. Use BEFORE cml_add_node to find valid node_definition values
        (e.g. 'iosv', 'asav', 'server') and see what each node type is. Filtering
        and pagination are client-side (CML returns the full list).

        Returns:
            str: Markdown listing (id, description, nature per definition), or
            JSON pagination envelope:
            {"total": int, "count": int, "offset": int,
             "items": [<full NodeDefinition objects>], "has_more": bool,
             "next_offset": int|null}
            On failure: "Error: <actionable message>".
        """
        try:
            data = await client.request_json("GET", "/node_definitions")
            items = data if isinstance(data, list) else []
            if id_filter:
                needle = id_filter.lower()
                items = [d for d in items if needle in str(d.get("id", "")).lower()]
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_node_definitions_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_node_definition",
        title="Get Node Definition Details",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_node_definition(
        def_id: Annotated[
            str,
            Field(
                description="Node definition ID (e.g. 'iosv', 'asav', 'server').",
                min_length=1,
                max_length=250,
            ),
        ],
    ) -> str:
        """Get the full definition for one node type by its ID.

        Read-only. Find IDs with cml_list_node_definitions first. Includes boot
        behavior, simulation/resource parameters, interface layout, configuration
        generator, associated image_definitions, and pyATS settings.

        Returns:
            str: JSON object with all NodeDefinition fields (id, boot, sim,
            general, configuration, device, ui, image_definitions, ...), or
            "Error: ..." on failure (404 -> the definition ID doesn't exist;
            check it with cml_list_node_definitions).
        """
        try:
            data = await client.request_json(
                "GET", f"/node_definitions/{def_id}", params={"json": "true"}
            )
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_image_definitions",
        title="List Image Definitions",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_image_definitions(
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
        """List the disk-image definitions installed on this CML server.

        Read-only. Each image definition belongs to a node definition
        (node_definition_id) and represents a bootable software version; use it
        to see which images back a node type, or to pick a specific image_definition
        when creating a node. Pagination is client-side (CML returns the full list).

        Returns:
            str: Markdown listing (id, label, node_definition per image), or
            JSON pagination envelope:
            {"total": int, "count": int, "offset": int,
             "items": [<full ImageDefinition objects>], "has_more": bool,
             "next_offset": int|null}
            On failure: "Error: <actionable message>".
        """
        try:
            data = await client.request_json("GET", "/image_definitions")
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_image_definitions_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_external_connectors",
        title="List External Connectors",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_external_connectors(
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """List the external connectors configured on the CML controller.

        Read-only. External connectors are the bridges that wire lab networks to
        outside networks (e.g. NAT to the internet, or a bridged management
        segment) — an 'external_connector' node in a lab must reference one of
        these. Use this to find a connector's ID/label before adding such a node:
        pass the connector's id or label (e.g. 'NAT') as the 'configuration'
        value of the external_connector node in cml_add_node.
        Tags indicate the purpose (e.g. 'NAT', 'System Bridge'); 'operational'
        shows the device state on the controller.

        Topology note: an external_connector node has exactly ONE port. When
        several devices share the same outside segment, put an
        'unmanaged_switch' node behind the connector and attach the devices to
        that, rather than trying to add more links to the connector itself.

        OPERATIONAL GOTCHA — the one known case where CML link/interface state
        lies (live-proven on this controller):
        Running 'netplan apply' on the CML controller host rebuilds bridge0. The
        rebuilt bridge keeps its physical uplink but LOSES every lab's tap, so
        every node in EVERY lab drops off the management network at once — while
        the CML API still reports each link and interface as STARTED, so the
        usual fabric check (cml_list_links / interface state) looks perfectly
        clean. The tell is that the controller itself and non-CML hosts on the
        same subnet stay reachable while all lab nodes do not.
        Diagnose on the controller host (shell, not this API):
        'ip -br link show master bridge0' — a healthy bridge lists the lab taps
        ('lnk*' interfaces); an orphaned one shows only the uplink (e.g.
        'ens192') and no 'lnk*' entries.
        Fix without rebooting: stop and then start each lab's external_connector
        node (cml_set_node_state action='stop', then action='start'). CML
        re-attaches the tap and
        connectivity returns in seconds. Repeat for every lab that has one; live
        node state survives the bounce. Budget one connector-node bounce per lab
        immediately after any planned 'netplan apply' on the controller.

        Returns:
            str: Markdown listing (label, id, device, state, tags per connector),
            or JSON list of full ExternalConnector objects:
            [{"id": str (UUID), "label": str, "device_name": str,
              "operational": str, "tags": [str, ...], "allowed": bool,
              "snooped": bool, "protected": bool}, ...]
            On failure: "Error: <actionable message>".
        """
        try:
            data = await client.request_json("GET", "/system/external_connectors")
            items = data if isinstance(data, list) else []
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(items), settings)
            return finalize(_connectors_markdown(items), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_sync_external_connectors",
        title="Sync External Connectors",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_sync_external_connectors(
        push_configured_state: Annotated[
            bool,
            Field(
                description="true (default) pushes CML's connector configuration down "
                "onto the controller host: every bridge is set to snooped and L2 "
                "bridges are set to protected. false (e.g. false) preserves whatever "
                "the host already has and just reports it back."
            ),
        ] = True,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Rescan the controller host and refresh CML's list of external connectors.

        Write (non-destructive) — only registered when CML_MCP_ENABLE_WRITES=true.
        CML can only DISCOVER bridge devices on its own host; there is no API to
        create one. So the workflow is: an administrator creates the Linux bridge
        on the CML controller (e.g. via netplan), then you call this tool to make
        CML notice it, then cml_update_external_connector to label and tag it.
        Use this after a bridge is added, renamed, or removed on the controller,
        or when cml_list_external_connectors doesn't show a bridge you know
        exists. Do not use it to create connectivity — it only rescans.

        A newly discovered bridge appears with "interface": null when it has no
        member port. That is expected for a deliberately isolated lab-only bridge
        (no uplink means lab traffic cannot leak onto the physical network) and
        does not stop CML from using it; such a bridge also reports
        DOWN/NO-CARRIER on the host, which is likewise normal.

        Leave push_configured_state=true unless an administrator has hand-tuned
        snooping/protection on the host and you want to read that state back
        instead of overwriting it. Note that the default push marks L2 bridges
        protected, and protected filters DHCP — see
        cml_update_external_connector before relying on DHCP over a bridge.

        Returns:
            str: Markdown listing of the connectors as they are after the rescan
            (same shape as cml_list_external_connectors), or JSON list of
            ExternalConnector objects:
            [{"id": str (UUID), "label": str, "device_name": str,
              "operational": str, "tags": [str, ...], "allowed": bool,
              "snooped": bool, "protected": bool}, ...]
            On failure: "Error: ..." (403 -> the configured account is not an
            admin; this rescan is admin-only on most controllers).
        """
        try:
            data = await client.request_json(
                "PUT",
                "/system/external_connectors",
                json_body={"push_configured_state": push_configured_state},
            )
            items = data if isinstance(data, list) else []
            if response_format is ResponseFormat.JSON:
                return finalize(
                    to_json(items),
                    settings,
                    truncation_hint=(
                        "The rescan itself completed; use response_format='markdown' "
                        "for a shorter view of the result."
                    ),
                )
            return finalize(
                _connectors_markdown(items),
                settings,
                truncation_hint=(
                    "The rescan itself completed; re-read the list with "
                    "cml_list_external_connectors."
                ),
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_update_external_connector",
        title="Update External Connector",
        read_only=False,
        destructive=False,
        idempotent=True,
    )
    async def cml_update_external_connector(
        connector_id: ConnectorId,
        label: Annotated[
            str | None,
            Field(
                description="New unique, human-readable label (e.g. 'ISP1'). This is "
                "the value a lab's external_connector node references in its "
                "configuration, so pick something stable.",
                min_length=1,
                max_length=128,
            ),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(
                description="Replacement list of purpose tags (e.g. ['ISP1']). Replaces "
                "the existing tags entirely — pass the full list, not just additions."
            ),
        ] = None,
        protected: Annotated[
            bool | None,
            Field(
                description="L2 protection filtering for the segment. true FILTERS DHCP "
                "and other L2 control traffic; set false (e.g. false) on an isolated "
                "lab-only bridge that must carry DHCP."
            ),
        ] = None,
        snooped: Annotated[
            bool | None,
            Field(
                description="IP snooping for the segment (e.g. true). Snooping is how "
                "CML learns node IP addresses for display; leave unset to keep the "
                "current value."
            ),
        ] = None,
    ) -> str:
        """Set the label, tags, and L2 protection of an external connector.

        Write (non-destructive) — only registered when CML_MCP_ENABLE_WRITES=true.
        Use after cml_sync_external_connectors has discovered a new bridge, to
        give it a meaningful label and tags, and to set whether the segment is
        protected/snooped. Only the fields you pass are changed; omitted fields
        keep their current values. This tool cannot create a bridge or change the
        host device it maps to — bridges are created on the controller host and
        only discovered by CML.

        CRITICAL — protected=true FILTERS DHCP. 'protected' exists to stop a lab
        from disrupting the network OUTSIDE it, and the filtering it applies
        drops DHCP and similar L2 control traffic. On an isolated, lab-only
        bridge (one with no member port, so nothing can leak anyway) that
        filtering has nothing to protect and instead silently breaks any
        DHCP-based transport: clients simply never get an address and the
        failure looks like a topology problem. Set protected=false for those
        segments. The default sync (push_configured_state=true) marks L2 bridges
        protected, so an isolated bridge usually needs this call right after it
        is discovered.

        Returns:
            str: JSON of the updated ExternalConnector object:
            {"id": str (UUID), "label": str, "device_name": str,
             "operational": str, "tags": [str, ...], "allowed": bool,
             "snooped": bool, "protected": bool}
            On failure: "Error: ..." (404 -> connector_id doesn't exist, list
            them with cml_list_external_connectors; 403 -> the configured
            account is not an admin; 400/409 -> the label is already used by
            another connector).
        """
        try:
            body: dict[str, Any] = {}
            if label is not None:
                body["label"] = label
            if tags is not None:
                body["tags"] = tags
            if protected is not None:
                body["protected"] = protected
            if snooped is not None:
                body["snooped"] = snooped
            if not body:
                return (
                    "Error: No fields to update. Provide at least one of label, tags, "
                    "protected, snooped."
                )
            data = await client.request_json(
                "PATCH", f"/system/external_connectors/{connector_id}", json_body=body
            )
            return finalize(
                to_json(data),
                settings,
                truncation_hint="Fetch the connector with cml_list_external_connectors instead.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_users",
        title="List Users",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_users(
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
        """List user accounts on the CML server.

        Read-only. Full details (admin flag, groups, owned labs) may require
        admin rights — non-admin callers get only id and username per user. Use
        to resolve a username to its user UUID (e.g. for lab ownership or group
        membership). Pagination is client-side (CML returns the full list).

        Returns:
            str: Markdown listing (username (id), admin flag, groups count), or
            JSON pagination envelope:
            {"total": int, "count": int, "offset": int,
             "items": [<UserResponse or UserBriefResponse objects>],
             "has_more": bool, "next_offset": int|null}
            On failure: "Error: ..." (403 -> the account lacks the rights to
            list users on this server).
        """
        try:
            data = await client.request_json("GET", "/users")
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_users_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_list_groups",
        title="List Groups",
        read_only=True,
        idempotent=True,
    )
    async def cml_list_groups(
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
        """List user groups on the CML server.

        Read-only. Groups bundle users for shared lab access; full details
        (members, lab associations) may require admin rights — non-admin callers
        get only id and name per group. Use to resolve a group name to its UUID.
        Pagination is client-side (CML returns the full list).

        Returns:
            str: Markdown listing (name (id), members count, description), or
            JSON pagination envelope:
            {"total": int, "count": int, "offset": int,
             "items": [<GroupResponse or GroupBriefResponse objects>],
             "has_more": bool, "next_offset": int|null}
            On failure: "Error: ..." (403 -> the account lacks the rights to
            list groups on this server).
        """
        try:
            data = await client.request_json("GET", "/groups")
            items = data if isinstance(data, list) else []
            page = items[offset : offset + limit]
            envelope = pagination_envelope(page, total=len(items), offset=offset, limit=limit)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(envelope), settings)
            return finalize(_groups_markdown(page, envelope), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_licensing",
        title="Get Licensing Status",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_licensing(
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Get the CML controller's Smart Licensing configuration and status.

        Read-only. Use to check whether the controller is registered and
        authorized, which product license is active (and whether it includes
        enterprise features), and per-feature usage against limits (e.g. node
        count in use vs. maximum). For overall platform health use
        cml_get_system_health instead — it includes an is_licensed flag.

        Returns:
            str: Markdown summary (registration status, authorization status,
            product license, reservation mode, per-feature usage/limits), or
            JSON LicensingStatus object:
            {"udi": {"hostname": str, "product_uuid": str},
             "registration": {"status": str, "smart_account": str|null,
              "virtual_account": str|null, "register_time": {...},
              "renew_time": {...}, "expires": str|null},
             "authorization": {"status": str, "renew_time": {...},
              "expires": str|null},
             "reservation_mode": bool,
             "features": [{"id": str, "name": str, "description": str,
              "version": str, "in_use": int, "status": str, "min": int,
              "max": int, "minEndDate": str|null, "maxEndDate": str|null}, ...],
             "product_license": {"active": str, "is_enterprise": bool},
             "transport": {"proxy": {...}, "ssms": str|null,
              "default_ssms": str}}
            On failure: "Error: ..." (403 -> the account lacks the rights to
            view licensing on this server).
        """
        try:
            data = await client.request_json("GET", "/licensing")
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(data), settings)
            return finalize(_licensing_markdown(data if isinstance(data, dict) else {}), settings)
        except Exception as e:
            return format_error(e)

    # ----------------------------------------------------------------- writes

    @register_tool(
        mcp,
        ctx,
        name="cml_create_user",
        title="Create User",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_create_user(
        username: Annotated[
            str,
            Field(
                description="Login name for the new user (e.g. 'student1').",
                min_length=1,
                max_length=32,
            ),
        ],
        password: Annotated[
            str,
            Field(
                description=(
                    "Initial password for the new user. Never echoed back in "
                    "the response."
                ),
                min_length=1,
            ),
        ],
        fullname: Annotated[
            str | None,
            Field(
                description="Full display name of the user (e.g. 'Ada Lovelace').",
                max_length=128,
            ),
        ] = None,
        description: Annotated[
            str | None,
            Field(
                description="Free-form detail about the user (e.g. 'CCNA cohort 2026').",
                max_length=4096,
            ),
        ] = None,
        email: Annotated[
            str | None,
            Field(
                description="E-mail address of the user (e.g. 'ada@example.com').",
                max_length=128,
            ),
        ] = None,
        admin: Annotated[
            bool,
            Field(description="Grant administrative rights (e.g. false)."),
        ] = False,
        groups: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Group UUIDs to make the user a member of "
                    "(e.g. ['90f84e38-a71c-4d57-8d90-00fa8a197385']). "
                    "Find IDs with cml_list_groups."
                ),
            ),
        ] = None,
    ) -> str:
        """Create a new user account on the CML controller.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Requires admin rights AND a registered CML license (a CML-FREE/eval
        controller returns 400 'System is not licensed'). The POST is not
        auto-retried, so a lost response can't silently create a duplicate
        user. The password is sent to the platform but never echoed back in
        this tool's response.

        Returns:
            str: JSON UserResponse for the new user (id, username, fullname,
            admin, groups, labs, created, modified — no password field), or
            "Error: ..." (403 -> the configured account is not an admin;
            400/422 -> invalid field values, e.g. username already taken or
            password rejected by policy).
        """
        try:
            body: dict[str, Any] = {
                "username": username,
                "password": password,
                "admin": admin,
            }
            if fullname is not None:
                body["fullname"] = fullname
            if description is not None:
                body["description"] = description
            if email is not None:
                body["email"] = email
            if groups is not None:
                body["groups"] = groups
            data = await client.request_json("POST", "/users", json_body=body)
            if isinstance(data, dict):
                data.pop("password", None)  # defense-in-depth: never echo it
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_user",
        title="Delete User",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_user(user_id: UserId) -> str:
        """Permanently delete a user account from the CML controller.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        Requires admin rights. Per platform behavior this also deletes the
        labs owned by the user — verify the target (and its owned labs) with
        cml_list_users first, and export anything worth keeping with
        cml_export_lab. Deletion cannot be undone.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> user ID doesn't
            exist; 403 -> the configured account is not an admin).
        """
        try:
            await client.request_json("DELETE", f"/users/{user_id}")
            return f"User {user_id} deleted (along with any labs the user owned)."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_create_group",
        title="Create Group",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_create_group(
        name: Annotated[
            str,
            Field(
                description="Full name of the group (e.g. 'CCNA Study Group Class of 26').",
                min_length=1,
                max_length=64,
            ),
        ],
        description: Annotated[
            str | None,
            Field(
                description="Free-form detail about the group (e.g. 'CCNA study group').",
                max_length=4096,
            ),
        ] = None,
        members: Annotated[
            list[str] | None,
            Field(
                description=(
                    "User UUIDs to enroll as members "
                    "(e.g. ['90f84e38-a71c-4d57-8d90-00fa8a197385']). "
                    "Find IDs with cml_list_users."
                ),
            ),
        ] = None,
        associations: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description=(
                    "Lab associations granting the group access to labs; each item "
                    "is {'id': '<lab UUID>', 'permissions': [<'lab_admin'|'lab_edit'"
                    "|'lab_exec'|'lab_view', ...>]} "
                    "(e.g. [{'id': '90f84e38-a71c-4d57-8d90-00fa8a197385', "
                    "'permissions': ['lab_exec', 'lab_view']}])."
                ),
            ),
        ] = None,
    ) -> str:
        """Create a new user group on the CML controller.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Requires admin rights AND a registered license (CML-FREE returns 400
        'System is not licensed'). Groups bundle users for shared lab access:
        members (user UUIDs) get the lab permissions listed in associations.
        The POST is not auto-retried, so a lost response can't silently create
        a duplicate group.

        Returns:
            str: JSON GroupResponse for the new group (id, name, description,
            members, associations, created, modified), or "Error: ..."
            (403 -> the configured account is not an admin; 400/422 -> invalid
            field values, e.g. group name already taken or unknown member/lab
            UUIDs).
        """
        try:
            body: dict[str, Any] = {"name": name}
            if description is not None:
                body["description"] = description
            if members is not None:
                body["members"] = members
            if associations is not None:
                body["associations"] = associations
            data = await client.request_json("POST", "/groups", json_body=body)
            return finalize(to_json(data), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_delete_group",
        title="Delete Group",
        read_only=False,
        destructive=True,
        idempotent=True,
    )
    async def cml_delete_group(group_id: GroupId) -> str:
        """Permanently delete a user group from the CML controller.

        DESTRUCTIVE write — only registered when CML_MCP_ENABLE_WRITES=true.
        Requires admin rights. Members lose any lab access they had through
        this group's associations (the users and labs themselves are kept).
        Verify the target with cml_list_groups first — deletion cannot be
        undone.

        Returns:
            str: Confirmation message, or "Error: ..." (404 -> group ID
            doesn't exist; 403 -> the configured account is not an admin).
        """
        try:
            await client.request_json("DELETE", f"/groups/{group_id}")
            return f"Group {group_id} deleted."
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_resource_usage",
        title="Get Resource Pool Usage",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_resource_usage(
        lab_id: Annotated[
            str | None,
            Field(
                description="Optional lab ID (UUID) to scope the view to the pools "
                "that lab's nodes draw from (e.g. "
                "'90f84e38-a71c-4d57-8d90-00fa8a197385').",
                max_length=100,
            ),
        ] = None,
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for a usage table, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Show resource-pool limits versus current usage (CPU, RAM, disk, licenses).

        Read-only. Use this when a node or lab fails to start — the cause is
        often an exhausted pool quota rather than a bad topology — and before
        cloning or scaling a lab, to check there is headroom. Controllers
        without resource pools configured report that plainly; for raw
        controller CPU/memory load use cml_get_system_stats instead.

        Returns:
            str: Markdown table (one row per pool: used / limit per resource,
            plus totals), or JSON
            {"lab_id": str|null, "pools": [{"id": str, "label": str,
            "limit": {...}, "usage": {...}}, ...]}.
            On failure: "Error: ..." (404 -> lab_id doesn't exist).
        """
        try:
            if lab_id:
                pools_data, usage_data = await asyncio.gather(
                    client.request_json("GET", f"/labs/{lab_id}/resource_pools"),
                    client.request_json("GET", "/resource_pool_usage"),
                )
            else:
                pools_data, usage_data = await asyncio.gather(
                    client.request_json("GET", "/resource_pools", params={"data": True}),
                    client.request_json("GET", "/resource_pool_usage"),
                )
            pools = [p for p in (pools_data or []) if isinstance(p, dict)]
            usage = list(usage_data or [])
            if lab_id:
                # Scope usage to the pools this lab actually uses.
                lab_pool_ids = {
                    p.get("id") for p in pools if isinstance(p, dict)
                } or {p for p in (pools_data or []) if isinstance(p, str)}
                usage = [u for u in usage if isinstance(u, dict) and u.get("id") in lab_pool_ids]
            records = _merge_resource_pools(pools, usage)
            if response_format is ResponseFormat.JSON:
                return finalize(to_json({"lab_id": lab_id, "pools": records}), settings)
            return finalize(_resource_usage_markdown(records, lab_id), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_get_diagnostics",
        title="Get Controller Diagnostics",
        read_only=True,
        idempotent=True,
    )
    async def cml_get_diagnostics(
        category: Annotated[
            Literal[
                "computes",
                "labs",
                "lab_events",
                "licensing",
                "node_definitions",
                "node_launch_queue",
                "services",
                "startup_scheduler",
                "user_list",
            ],
            Field(
                description="Which diagnostic document to fetch (e.g. "
                "'node_launch_queue'). 'node_launch_queue' = nodes waiting for "
                "compute capacity; 'startup_scheduler' = controller readiness "
                "flags; 'computes' = per-compute detail; 'labs' / 'lab_events' = "
                "per-lab internal state and recent events; 'services' = internal "
                "service detail; 'licensing' = licensing internals; "
                "'node_definitions' = definition-loading detail; 'user_list' is "
                "deprecated — use cml_list_users instead."
            ),
        ],
        response_format: Annotated[
            ResponseFormat,
            Field(description="'markdown' for human-readable output, 'json' for complete data."),
        ] = ResponseFormat.MARKDOWN,
    ) -> str:
        """Get a low-level controller diagnostic document for troubleshooting.

        Read-only. This is the escalation step after cml_get_system_health,
        cml_get_system_stats, and cml_get_resource_usage: it exposes the
        controller's internal view rather than a summary. Use it when a node or
        lab misbehaves and the normal reads look clean. Do not use it for
        routine listings — cml_list_users, cml_list_node_definitions, and
        cml_list_labs return cleaner, paginated data for the same objects.

        Answering "why is a started node still DEFINED_ON_CORE?": check
        category='node_launch_queue' first. If the node's ID appears there, the
        launch is QUEUED behind other launches — either waiting on the
        'dependencies' listed in its entry, or waiting for capacity, in which
        case cml_get_resource_usage shows which pool quota (CPU/RAM/disk) is
        exhausted and cml_get_system_stats shows whether the computes are simply
        full. If the node's ID is NOT in the queue, it is not waiting: the launch
        actually failed or was never scheduled — check
        category='startup_scheduler', where system_ready=false (or
        core_driver_connected/node_definitions_loaded/licensing_loaded=false)
        means the controller cannot launch anything yet, and then the node's own
        console log (cml_get_node_console_log) for a per-node failure.

        Some categories ('labs', 'lab_events', 'computes', 'services') return
        large documents on a busy controller; the response is capped and the
        truncation note says so — narrow to a more specific category or use
        response_format='markdown' rather than re-requesting the same document.

        Returns:
            str: Markdown summary for 'node_launch_queue' (one line per queued
            node: node_id, lab_id, queued_time, priority, dependency count,
            cpus/ram required) and for 'startup_scheduler' (system_ready,
            core_driver_connected, node_definitions_loaded, licensing_loaded,
            lld_connected, lld_synced as yes/no/unknown); other categories are
            returned as the raw JSON document under a heading. With
            response_format='json', the raw document itself — its shape depends
            on the category: 'node_launch_queue' and 'node_definitions' are JSON
            arrays, 'computes', 'labs' and 'lab_events' are objects keyed by
            UUID, 'startup_scheduler', 'services' and 'licensing' are flat
            objects.
            On failure: "Error: ..." (403 -> the diagnostics endpoint is
            admin-only on most controllers, so a non-admin account cannot read
            any category — use cml_get_system_health for the non-admin view;
            404 -> the controller does not implement this category).
        """
        try:
            data = await client.request_json("GET", f"/diagnostics/{category}")
            hint = (
                "Pick a narrower category, or response_format='markdown' for a summary."
            )
            if response_format is ResponseFormat.JSON:
                return finalize(to_json(data), settings, truncation_hint=hint)
            return finalize(_diagnostics_markdown(category, data), settings, truncation_hint=hint)
        except Exception as e:
            return format_error(e)
