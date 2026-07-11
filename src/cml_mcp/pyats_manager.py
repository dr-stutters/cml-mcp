"""pyATS session management for CML labs.

Pulls the pyATS testbed that CML generates for a lab, patches in the CML
console-server credentials, and maintains persistent unicon console
connections to lab nodes so repeated commands don't pay the connect cost.

All unicon/genie calls are blocking, so tool code runs them via
asyncio.to_thread; a per-device threading.Lock serializes access to each
console line. Connections are opened with log_stdout=False - stray stdout
would corrupt the MCP stdio transport.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import yaml

from .client import CMLClient


class PyatsManager:
    def __init__(self, client: CMLClient):
        self._client = client
        self._testbeds: dict[str, Any] = {}  # lab_id -> genie testbed
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._guard = threading.Lock()

    # -- testbed handling ------------------------------------------------

    async def get_testbed(
        self,
        lab_id: str,
        refresh: bool = False,
        device_username: str | None = None,
        device_password: str | None = None,
        enable_password: str | None = None,
    ) -> Any:
        """Return a cached genie testbed for the lab, building it on demand."""
        if not refresh and lab_id in self._testbeds and not (
            device_username or device_password or enable_password
        ):
            return self._testbeds[lab_id]

        raw = await self._client.get(f"/labs/{lab_id}/pyats_testbed")
        data = yaml.safe_load(raw)
        if not data or "devices" not in data:
            raise RuntimeError("CML returned an empty pyATS testbed for this lab")

        ts = data["devices"].get("terminal_server")
        if ts is not None:
            ts.setdefault("credentials", {})["default"] = {
                "username": self._client.settings.username,
                "password": self._client.settings.password,
            }
        for name, dev in data["devices"].items():
            if name == "terminal_server":
                continue
            creds = dev.setdefault("credentials", {})
            if device_username or device_password:
                default = creds.setdefault("default", {})
                if device_username:
                    default["username"] = device_username
                if device_password:
                    default["password"] = device_password
            if enable_password is not None:
                creds["enable"] = {"password": enable_password}

        testbed = await asyncio.to_thread(self._load_testbed, data)
        old = self._testbeds.get(lab_id)
        if old is not None:
            await asyncio.to_thread(self._disconnect_testbed, old)
        self._testbeds[lab_id] = testbed
        return testbed

    @staticmethod
    def _load_testbed(data: dict) -> Any:
        from genie.testbed import load

        return load(data)

    async def resolve_device(self, lab_id: str, node: str) -> str:
        """Map a node label or node id to a testbed device name (labels are the device names)."""
        testbed = await self.get_testbed(lab_id)
        if node in testbed.devices:
            return node
        # maybe a node id - look up its label
        try:
            info = await self._client.get(f"/labs/{lab_id}/nodes/{node}")
            label = info.get("label")
            if label and label in testbed.devices:
                return label
        except Exception:
            pass
        available = [d for d in testbed.devices if d != "terminal_server"]
        raise ValueError(
            f"Node {node!r} not found in the lab's pyATS testbed. "
            f"Console-capable devices: {available}. (External connectors and "
            "unmanaged switches have no console and are not in the testbed.)"
        )

    # -- blocking helpers (run these via asyncio.to_thread) ---------------

    def _lock_for(self, lab_id: str, device_name: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault((lab_id, device_name), threading.Lock())

    def _connect(self, device: Any, timeout: float) -> None:
        if device.is_connected():
            return
        via = next((c for c in device.connections if c != "defaults"), None)
        device.connect(
            via=via,
            log_stdout=False,
            learn_hostname=True,
            connection_timeout=timeout,
        )

    def run_execute(
        self, testbed: Any, lab_id: str, device_name: str,
        commands: list[str], timeout: float,
    ) -> dict[str, str]:
        device = testbed.devices[device_name]
        with self._lock_for(lab_id, device_name):
            self._connect(device, max(timeout, 90))
            return {cmd: device.execute(cmd, timeout=timeout) for cmd in commands}

    def run_parse(
        self, testbed: Any, lab_id: str, device_name: str,
        command: str, timeout: float,
    ) -> Any:
        device = testbed.devices[device_name]
        with self._lock_for(lab_id, device_name):
            self._connect(device, max(timeout, 90))
            return device.parse(command, timeout=timeout)

    def run_configure(
        self, testbed: Any, lab_id: str, device_name: str,
        config: str, timeout: float,
    ) -> str:
        device = testbed.devices[device_name]
        with self._lock_for(lab_id, device_name):
            self._connect(device, max(timeout, 90))
            return device.configure(config, timeout=timeout)

    def run_learn(
        self, testbed: Any, lab_id: str, device_name: str, feature: str,
    ) -> Any:
        device = testbed.devices[device_name]
        with self._lock_for(lab_id, device_name):
            self._connect(device, 90)
            result = device.learn(feature)
            return getattr(result, "info", result)

    def connection_report(self, lab_id: str) -> dict[str, Any]:
        testbed = self._testbeds.get(lab_id)
        if testbed is None:
            return {"testbed_loaded": False, "devices": {}}
        return {
            "testbed_loaded": True,
            "devices": {
                name: {"os": dev.os, "connected": dev.is_connected()}
                for name, dev in testbed.devices.items()
                if name != "terminal_server"
            },
        }

    @staticmethod
    def _disconnect_testbed(testbed: Any, only: str | None = None) -> list[str]:
        closed = []
        for name, dev in testbed.devices.items():
            if only and name != only:
                continue
            try:
                if dev.is_connected():
                    dev.disconnect()
                    closed.append(name)
            except Exception:
                pass
            try:
                dev.destroy()
            except Exception:
                pass
        return closed

    async def disconnect(self, lab_id: str, node: str | None = None) -> list[str]:
        testbed = self._testbeds.get(lab_id)
        if testbed is None:
            return []
        only = await self.resolve_device(lab_id, node) if node else None
        closed = await asyncio.to_thread(self._disconnect_testbed, testbed, only)
        if only is None:
            self._testbeds.pop(lab_id, None)
        return closed
