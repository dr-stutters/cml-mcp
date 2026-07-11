"""Interface management tools."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def list_interfaces(lab_id: str, node_id: str | None = None) -> str:
        """List interfaces in a lab (all of them, or just one node's if node_id is given).

        Returns interface objects with id, label, type (physical/loopback),
        slot, connection status, and state.
        """
        if node_id:
            return dumps(await client.get(
                f"/labs/{lab_id}/nodes/{node_id}/interfaces",
                params={"data": True},
            ))
        iface_ids = await client.get(f"/labs/{lab_id}/interfaces")
        return dumps(iface_ids)

    @mcp.tool()
    async def get_interface(lab_id: str, interface_id: str) -> str:
        """Get details for one interface, including its current state."""
        info = await client.get(f"/labs/{lab_id}/interfaces/{interface_id}")
        state = await client.get(f"/labs/{lab_id}/interfaces/{interface_id}/state")
        return dumps({"interface": info, "state": state})

    @mcp.tool()
    async def create_interface(lab_id: str, node_id: str, slot: int | None = None) -> str:
        """Create a new physical interface on a node (in the given slot, or the next free slot)."""
        body: dict = {"node": node_id}
        if slot is not None:
            body["slot"] = slot
        return dumps(await client.post(f"/labs/{lab_id}/interfaces", json_body=body))

    @mcp.tool()
    async def update_interface(lab_id: str, interface_id: str, mac_address: str | None = None) -> str:
        """Update an interface (currently the API supports changing the MAC address)."""
        body = {}
        if mac_address is not None:
            body["mac_address"] = mac_address
        return dumps(await client.patch(f"/labs/{lab_id}/interfaces/{interface_id}", json_body=body))

    @mcp.tool()
    async def delete_interface(lab_id: str, interface_id: str) -> str:
        """Delete an interface from a node (also removes any link using it)."""
        return dumps(await client.delete(f"/labs/{lab_id}/interfaces/{interface_id}"))

    @mcp.tool()
    async def set_interface_state(
        lab_id: str,
        interface_id: str,
        action: Literal["start", "stop"],
    ) -> str:
        """Bring an interface up (start) or shut it down (stop) at the simulation level - like pulling the cable."""
        return dumps(await client.put(f"/labs/{lab_id}/interfaces/{interface_id}/state/{action}"))
