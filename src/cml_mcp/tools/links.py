"""Link management: CRUD, state, link conditioning, and packet capture."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def list_links(lab_id: str) -> str:
        """List all links in a lab with their endpoints (interface ids), nodes, label, and state."""
        link_ids = await client.get(f"/labs/{lab_id}/links")
        links = []
        for lid in link_ids:
            links.append(await client.get(f"/labs/{lab_id}/links/{lid}"))
        return dumps(links)

    @mcp.tool()
    async def get_link(lab_id: str, link_id: str) -> str:
        """Get details for one link (endpoints, state, whether it has converged)."""
        return dumps(await client.get(f"/labs/{lab_id}/links/{link_id}"))

    @mcp.tool()
    async def create_link(lab_id: str, src: str, dst: str) -> str:
        """Create a link between two endpoints.

        src and dst each accept either an interface id OR a node id - when a
        node id is given, the first free physical interface on that node is
        used automatically (a new interface is created if all are in use).
        """
        src_int = await client.resolve_node_interface(lab_id, src)
        dst_int = await client.resolve_node_interface(lab_id, dst)
        return dumps(await client.post(
            f"/labs/{lab_id}/links",
            json_body={"src_int": src_int, "dst_int": dst_int},
        ))

    @mcp.tool()
    async def delete_link(lab_id: str, link_id: str) -> str:
        """Delete a link from a lab."""
        return dumps(await client.delete(f"/labs/{lab_id}/links/{link_id}"))

    @mcp.tool()
    async def set_link_state(lab_id: str, link_id: str, action: Literal["start", "stop"]) -> str:
        """Bring a link up (start) or take it down (stop) - simulates connecting/disconnecting the cable."""
        return dumps(await client.put(f"/labs/{lab_id}/links/{link_id}/state/{action}"))

    @mcp.tool()
    async def configure_link_condition(
        lab_id: str,
        link_id: str,
        action: Literal["get", "set", "clear"] = "get",
        bandwidth: int | None = None,
        latency: int | None = None,
        jitter: int | None = None,
        loss: float | None = None,
        enabled: bool = True,
    ) -> str:
        """Get, set, or clear link conditioning (WAN emulation: bandwidth/latency/jitter/loss).

        Args:
            action: 'get' current conditioning, 'set' to apply, 'clear' to remove.
            bandwidth: Max bandwidth in kbps (e.g. 1544 for T1).
            latency: One-way delay in ms.
            jitter: Delay variation in ms.
            loss: Packet loss percentage (0-100, e.g. 0.5).
            enabled: Whether conditioning is active (set action only).
        """
        path = f"/labs/{lab_id}/links/{link_id}/condition"
        if action == "get":
            return dumps(await client.get(path))
        if action == "clear":
            return dumps(await client.delete(path))
        body: dict = {"enabled": enabled}
        if bandwidth is not None:
            body["bandwidth"] = bandwidth
        if latency is not None:
            body["latency"] = latency
        if jitter is not None:
            body["jitter"] = jitter
        if loss is not None:
            body["loss"] = loss
        return dumps(await client.patch(path, json_body=body))

    @mcp.tool()
    async def manage_packet_capture(
        lab_id: str,
        link_id: str,
        action: Literal["start", "stop", "status", "list_packets", "download"],
        save_path: str | None = None,
        bpfilter: str = "",
        max_packets: int | None = None,
        max_time: int = 60,
    ) -> str:
        """Manage packet capture on a link.

        Actions: start/stop a capture, check status, list captured packets
        (decoded summaries), or download the pcap file to a local path
        (save_path required for download). The lab must be running.

        For action='start' the CML API requires a stop condition, so at least
        one of ``max_time`` (seconds, default 60) or ``max_packets`` is always
        sent. ``bpfilter`` is an optional Berkeley packet filter (e.g.
        ``'udp port 1812 or udp port 1813'``); empty captures everything.
        """
        base = f"/labs/{lab_id}/links/{link_id}/capture"
        if action == "start":
            body: dict[str, Any] = {"maxtime": max_time}
            if max_packets is not None:
                body["maxpackets"] = max_packets
            if bpfilter:
                body["bpfilter"] = bpfilter
            return dumps(await client.put(f"{base}/start", json_body=body))
        if action == "stop":
            return dumps(await client.put(f"{base}/stop"))
        if action == "status":
            return dumps(await client.get(f"{base}/status"))
        if action == "list_packets":
            return dumps(await client.get(f"/pcap/{link_id}/packets"))
        # download
        if not save_path:
            raise ValueError("save_path is required for action='download'")
        resp = await client.get(f"/pcap/{link_id}", raw_response=True)
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return dumps(f"Saved {len(resp.content)} bytes of pcap data to {save_path}")
