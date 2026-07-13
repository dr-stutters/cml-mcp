"""pyATS tools: run, parse, and apply CLI on running lab nodes via their consoles.

Connections go through the CML console server (no management network needed)
and persist between calls for speed.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from ..pyats_manager import PyatsManager
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    manager = PyatsManager(client)

    @mcp.tool()
    async def pyats_execute(
        lab_id: str,
        node: str,
        commands: list[str],
        timeout: float = 60,
        device_username: str | None = None,
        device_password: str | None = None,
        enable_password: str | None = None,
    ) -> str:
        """Run exec-mode CLI commands (e.g. show commands, ping) on a running lab node's console and return the raw output.

        The node must be BOOTED. The first call to a node opens a persistent
        console session (takes ~10-30s); later calls reuse it. Device
        credentials default to those in the CML-generated testbed (usually
        cisco/cisco); pass device_username/device_password/enable_password if
        the node's configuration uses different ones.

        Args:
            node: Node label (e.g. 'R1') or node id.
            commands: One or more commands, run in order.
        """
        if device_username or device_password or enable_password:
            testbed = await manager.get_testbed(
                lab_id, device_username=device_username,
                device_password=device_password, enable_password=enable_password,
            )
        else:
            testbed = await manager.get_testbed(lab_id)
        name = await manager.resolve_device(lab_id, node)
        result = await asyncio.to_thread(
            manager.run_execute, testbed, lab_id, name, commands, timeout
        )
        return dumps(result)

    @mcp.tool()
    async def pyats_parse(
        lab_id: str,
        node: str,
        command: str,
        timeout: float = 60,
    ) -> str:
        """Run a show command on a running node and return STRUCTURED data (Genie parser output as JSON).

        Prefer this over pyats_execute for show commands - the output is
        machine-readable (e.g. 'show ip interface brief', 'show ip route',
        'show ip ospf neighbor', 'show version'). Fails with a clear message
        if no parser exists for the command; fall back to pyats_execute then.
        """
        testbed = await manager.get_testbed(lab_id)
        name = await manager.resolve_device(lab_id, node)
        try:
            result = await asyncio.to_thread(
                manager.run_parse, testbed, lab_id, name, command, timeout
            )
        except Exception as exc:  # genie raises plain Exceptions for missing parsers
            if "Could not find parser" in str(exc):
                raise ValueError(
                    f"No Genie parser for {command!r} on this OS - "
                    "use pyats_execute for raw output instead"
                ) from exc
            raise
        return dumps(result)

    @mcp.tool()
    async def pyats_configure(
        lab_id: str,
        node: str,
        config: str,
        timeout: float = 60,
    ) -> str:
        """Apply configuration lines to a running node (enters config mode, applies, exits).

        Args:
            config: Configuration commands, one per line, e.g.
                "interface Loopback1\\n ip address 10.0.0.1 255.255.255.255".

        Note: this changes the node's RUNNING config only. To persist it into
        the lab topology (so it survives a wipe), follow up with
        extract_node_configuration.
        """
        testbed = await manager.get_testbed(lab_id)
        name = await manager.resolve_device(lab_id, node)
        result = await asyncio.to_thread(
            manager.run_configure, testbed, lab_id, name, config, timeout
        )
        return dumps(result)

    @mcp.tool()
    async def pyats_learn(lab_id: str, node: str, feature: str) -> str:
        """Learn a whole feature's operational state from a running node as structured data.

        Features include: interface, ospf, bgp, eigrp, routing, arp, vlan,
        stp, acl, vrf, platform, config. Broader than pyats_parse (which
        parses one command) but slower and more verbose.
        """
        testbed = await manager.get_testbed(lab_id)
        name = await manager.resolve_device(lab_id, node)
        result = await asyncio.to_thread(
            manager.run_learn, testbed, lab_id, name, feature
        )
        return dumps(result)

    @mcp.tool()
    async def pyats_sessions(
        lab_id: str,
        action: Literal["status", "disconnect", "refresh_testbed"] = "status",
        node: str | None = None,
    ) -> str:
        """Manage pyATS console sessions for a lab.

        - status: which devices are in the testbed and which have open console sessions.
        - disconnect: close console session(s) (one node, or all in the lab).
        - refresh_testbed: re-fetch the testbed from CML (use after adding/renaming nodes).
        """
        if action == "status":
            report = manager.connection_report(lab_id)
            if not report["testbed_loaded"]:
                await manager.get_testbed(lab_id)  # load it (side effect), then re-read
                report = manager.connection_report(lab_id)
            return dumps(report)
        if action == "disconnect":
            closed = await manager.disconnect(lab_id, node)
            return dumps({"disconnected": closed})
        await manager.get_testbed(lab_id, refresh=True)
        return dumps(manager.connection_report(lab_id))
