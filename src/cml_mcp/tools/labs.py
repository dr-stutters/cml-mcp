"""Lab lifecycle, topology import/export, and lab-level data tools."""

from __future__ import annotations

import json
from typing import Any, Literal

import yaml
from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def list_labs(show_all: bool = True, with_data: bool = True) -> str:
        """List labs on the CML server.

        Args:
            show_all: Include labs owned by other users (admin only). If False,
                only labs owned by or shared with the authenticated user.
            with_data: Return full lab objects (title, state, owner, node/link
                counts). If False, return only lab ids.
        """
        return dumps(await client.get("/labs", params={"show_all": show_all, "with_data": with_data}))

    @mcp.tool()
    async def get_lab(lab_id: str) -> str:
        """Get details for one lab: title, description, state, owner, node and link counts, created/modified times."""
        return dumps(await client.get(f"/labs/{lab_id}"))

    @mcp.tool()
    async def create_lab(title: str, description: str = "", notes: str = "") -> str:
        """Create a new empty lab and return it (the returned 'id' is the lab_id used by all other lab tools)."""
        body = {"title": title, "description": description, "notes": notes}
        return dumps(await client.post("/labs", json_body=body))

    @mcp.tool()
    async def update_lab(
        lab_id: str,
        title: str | None = None,
        description: str | None = None,
        notes: str | None = None,
        owner: str | None = None,
    ) -> str:
        """Update a lab's title, description, notes, or owner (owner is a user id)."""
        body = {k: v for k, v in {
            "title": title, "description": description, "notes": notes, "owner": owner,
        }.items() if v is not None}
        return dumps(await client.patch(f"/labs/{lab_id}", json_body=body))

    @mcp.tool()
    async def delete_lab(lab_id: str) -> str:
        """Delete a lab permanently. The lab must be stopped and wiped first. This cannot be undone."""
        return dumps(await client.delete(f"/labs/{lab_id}"))

    @mcp.tool()
    async def control_lab(lab_id: str, action: Literal["start", "stop", "wipe"]) -> str:
        """Start, stop, or wipe an entire lab.

        start boots all nodes (honoring staging); stop shuts them down
        preserving disk state; wipe discards all node disk/runtime state
        (configs extracted into the topology are kept). A lab must be stopped
        before wiping, and wiped before deleting.
        """
        return dumps(await client.put(f"/labs/{lab_id}/{action}"))

    @mcp.tool()
    async def get_lab_topology(lab_id: str, exclude_configurations: bool = False) -> str:
        """Get the full lab topology (nodes, interfaces, links, annotations) as JSON.

        Args:
            exclude_configurations: Omit node startup configurations to reduce output size.
        """
        return dumps(await client.get(
            f"/labs/{lab_id}/topology",
            params={"exclude_configurations": exclude_configurations},
        ))

    @mcp.tool()
    async def export_lab(lab_id: str) -> str:
        """Export/download a lab as CML topology YAML (suitable for re-import or version control)."""
        return dumps(await client.get(f"/labs/{lab_id}/download"))

    @mcp.tool()
    async def import_lab(topology: str, title: str | None = None) -> str:
        """Import a lab from a CML topology given as YAML or JSON text.

        Accepts the format produced by export_lab (YAML) or a JSON topology
        with 'lab', 'nodes' and 'links' keys. Returns the new lab id.

        Args:
            topology: Topology document (YAML or JSON text).
            title: Optional title override for the imported lab.
        """
        try:
            data = json.loads(topology)
        except json.JSONDecodeError:
            data = yaml.safe_load(topology)
        if not isinstance(data, dict):
            raise ValueError("topology must parse to an object with lab/nodes/links keys")
        return dumps(await client.post("/import", json_body=data, params={"title": title}))

    @mcp.tool()
    async def get_lab_state(lab_id: str) -> str:
        """Get a lab's runtime state (DEFINED_ON_CORE / STOPPED / STARTED) plus whether it has converged (finished starting/stopping)."""
        state = await client.get(f"/labs/{lab_id}/state")
        converged = await client.get(f"/labs/{lab_id}/check_if_converged")
        return dumps({"state": state, "converged": converged})

    @mcp.tool()
    async def get_lab_element_state(lab_id: str) -> str:
        """Get the state of every element in a lab (all nodes, interfaces, and links) in one call."""
        return dumps(await client.get(f"/labs/{lab_id}/lab_element_state"))

    @mcp.tool()
    async def get_lab_events(lab_id: str) -> str:
        """Get the event log for a lab (state transitions, errors)."""
        return dumps(await client.get(f"/labs/{lab_id}/events"))

    @mcp.tool()
    async def get_lab_simulation_stats(lab_id: str) -> str:
        """Get runtime simulation statistics for a lab (CPU, memory, disk usage per node)."""
        return dumps(await client.get(f"/labs/{lab_id}/simulation_stats"))

    @mcp.tool()
    async def get_lab_layer3_addresses(lab_id: str, node_id: str | None = None) -> str:
        """Get discovered IP (layer-3) addresses for all nodes in a lab, or one node if node_id is given.

        Useful for finding management addresses of running nodes.
        """
        if node_id:
            return dumps(await client.get(f"/labs/{lab_id}/nodes/{node_id}/layer3_addresses"))
        return dumps(await client.get(f"/labs/{lab_id}/layer3_addresses"))

    @mcp.tool()
    async def get_pyats_testbed(lab_id: str) -> str:
        """Generate a pyATS testbed YAML for the lab (for use with pyATS/Genie network testing)."""
        return dumps(await client.get(f"/labs/{lab_id}/pyats_testbed"))

    @mcp.tool()
    async def search_lab_nodes(
        lab_id: str,
        query: str,
        by: Literal["label", "tag"] = "label",
    ) -> str:
        """Find node(s) in a lab by exact label or by tag. Returns matching node id(s)."""
        if by == "label":
            return dumps(await client.get(f"/labs/{lab_id}/find/node/label/{query}"))
        return dumps(await client.get(f"/labs/{lab_id}/find_all/node/tag/{query}"))

    @mcp.tool()
    async def manage_lab_groups(
        lab_id: str,
        action: Literal["get", "set"] = "get",
        groups: list[dict[str, Any]] | None = None,
    ) -> str:
        """Get or set which user groups a lab is shared with.

        For action='set', groups is a list of {"id": <group_id>, "permission":
        "read_only"|"read_write"} objects that replaces the current sharing.
        """
        if action == "get":
            return dumps(await client.get(f"/labs/{lab_id}/groups"))
        return dumps(await client.put(f"/labs/{lab_id}/groups", json_body=groups or []))

    @mcp.tool()
    async def sample_labs(
        action: Literal["list", "get", "load"] = "list",
        sample_lab_id: str | None = None,
    ) -> str:
        """Work with the built-in sample labs: list them, get one's details, or load one onto the server as a new lab."""
        if action == "list":
            return dumps(await client.get("/sample/labs"))
        if not sample_lab_id:
            raise ValueError("sample_lab_id is required for get/load")
        if action == "get":
            return dumps(await client.get(f"/sample/labs/{sample_lab_id}"))
        return dumps(await client.put(f"/sample/labs/{sample_lab_id}"))
