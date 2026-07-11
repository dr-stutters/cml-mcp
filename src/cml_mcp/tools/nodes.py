"""Node management tools: CRUD, lifecycle, consoles, and configuration."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def list_nodes(
        lab_id: str,
        operational: bool = False,
        exclude_configurations: bool = True,
    ) -> str:
        """List all nodes in a lab with their properties (label, node_definition, state, position).

        Args:
            operational: Include operational/runtime data (compute host, resources).
            exclude_configurations: Omit node configurations to keep output small
                (set False to include startup configs).
        """
        return dumps(await client.get(
            f"/labs/{lab_id}/nodes",
            params={
                "data": True,
                "operational": operational,
                "exclude_configurations": exclude_configurations,
            },
        ))

    @mcp.tool()
    async def get_node(lab_id: str, node_id: str, operational: bool = True) -> str:
        """Get full details for one node, including its state and (with operational=True) runtime data."""
        return dumps(await client.get(
            f"/labs/{lab_id}/nodes/{node_id}",
            params={"operational": operational},
        ))

    @mcp.tool()
    async def add_node(
        lab_id: str,
        label: str,
        node_definition: str,
        x: int = 0,
        y: int = 0,
        configuration: str | None = None,
        image_definition: str | None = None,
        ram: int | None = None,
        cpus: int | None = None,
        tags: list[str] | None = None,
        populate_interfaces: bool = True,
    ) -> str:
        """Add a node to a lab. Returns the new node object (its 'id' is the node_id).

        Args:
            lab_id: Lab to add the node to.
            label: Display name, e.g. 'R1'.
            node_definition: Node type id, e.g. 'iosv', 'cat8000v', 'external_connector',
                'unmanaged_switch' (see list_node_definitions).
            x, y: Canvas position in pixels (space nodes ~100-200 apart).
            configuration: Startup/day-0 configuration text.
            image_definition: Specific image to run (defaults to the node definition's default).
            ram: RAM override in MB. cpus: vCPU override.
            tags: Tags for grouping/smart annotations.
            populate_interfaces: Pre-create the default set of interfaces (recommended).
        """
        body: dict = {"label": label, "node_definition": node_definition, "x": x, "y": y}
        if configuration is not None:
            body["configuration"] = configuration
        if image_definition is not None:
            body["image_definition"] = image_definition
        if ram is not None:
            body["ram"] = ram
        if cpus is not None:
            body["cpus"] = cpus
        if tags is not None:
            body["tags"] = tags
        return dumps(await client.post(
            f"/labs/{lab_id}/nodes",
            json_body=body,
            params={"populate_interfaces": populate_interfaces},
        ))

    @mcp.tool()
    async def update_node(
        lab_id: str,
        node_id: str,
        label: str | None = None,
        x: int | None = None,
        y: int | None = None,
        configuration: str | None = None,
        image_definition: str | None = None,
        ram: int | None = None,
        cpus: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Update a node's properties (label, position, configuration, image, resources, tags).

        Most properties can only be changed while the node is stopped/wiped.
        """
        body = {k: v for k, v in {
            "label": label, "x": x, "y": y, "configuration": configuration,
            "image_definition": image_definition, "ram": ram, "cpus": cpus, "tags": tags,
        }.items() if v is not None}
        return dumps(await client.patch(f"/labs/{lab_id}/nodes/{node_id}", json_body=body))

    @mcp.tool()
    async def delete_node(lab_id: str, node_id: str) -> str:
        """Delete a node (and its interfaces/links) from a lab. The node should be stopped and wiped first."""
        return dumps(await client.delete(f"/labs/{lab_id}/nodes/{node_id}"))

    @mcp.tool()
    async def control_node(
        lab_id: str,
        node_id: str,
        action: Literal["start", "stop", "wipe"],
    ) -> str:
        """Start, stop, or wipe a single node.

        wipe discards the node's disk/runtime state; the node must be stopped first.
        """
        if action == "wipe":
            return dumps(await client.put(f"/labs/{lab_id}/nodes/{node_id}/wipe_disks"))
        return dumps(await client.put(f"/labs/{lab_id}/nodes/{node_id}/state/{action}"))

    @mcp.tool()
    async def get_node_state(lab_id: str, node_id: str) -> str:
        """Get a node's state (DEFINED_ON_CORE / STOPPED / STARTED / BOOTED) and whether it has converged."""
        state = await client.get(f"/labs/{lab_id}/nodes/{node_id}/state")
        converged = await client.get(f"/labs/{lab_id}/nodes/{node_id}/check_if_converged")
        return dumps({"state": state, "converged": converged})

    @mcp.tool()
    async def extract_node_configuration(lab_id: str, node_id: str) -> str:
        """Extract the running configuration from a booted node and save it into the node's stored configuration.

        The node must be running and its type must support config extraction.
        Extracted configs survive a wipe.
        """
        return dumps(await client.put(f"/labs/{lab_id}/nodes/{node_id}/extract_configuration"))

    @mcp.tool()
    async def get_node_console_log(
        lab_id: str,
        node_id: str,
        console_id: int = 0,
        lines: int | None = 200,
    ) -> str:
        """Get the console output log of a node (boot messages and console activity).

        Args:
            console_id: Console index, usually 0.
            lines: Number of trailing lines to return (None for the full log).
        """
        return dumps(await client.get(
            f"/labs/{lab_id}/nodes/{node_id}/consoles/{console_id}/log",
            params={"lines": lines},
        ))

    @mcp.tool()
    async def get_node_console_key(
        lab_id: str,
        node_id: str,
        kind: Literal["console", "vnc"] = "console",
    ) -> str:
        """Get the console (or VNC) key for a running node.

        The key is used for terminal access, e.g. 'open /{key}' on the CML
        console server (ssh -p 22 admin@<cml-host> console access).
        """
        return dumps(await client.get(f"/labs/{lab_id}/nodes/{node_id}/keys/{kind}"))

    @mcp.tool()
    async def list_all_running_nodes(exclude_configurations: bool = True) -> str:
        """List nodes across ALL labs on the server with operational data (admin view; useful for capacity review)."""
        return dumps(await client.get(
            "/nodes",
            params={"operational": True, "exclude_configurations": exclude_configurations},
        ))
