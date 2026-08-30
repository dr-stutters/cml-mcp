"""CML console tools: run CLI commands on lab nodes via pyATS/Unicon/Genie.

CML has no REST endpoint for executing commands on a node's console; the
supported path is pyATS/Unicon over the lab's generated testbed
(GET /labs/{lab_id}/pyats_testbed). Every device in that testbed connects
through a 'terminal_server' proxy device — the CML controller itself, reached
over SSH with the configured CML username/password. The generated YAML ships
'change_me' placeholders there; this module injects the real credentials at
runtime and never logs or returns them (nor the raw testbed content).

The per-device credentials in that testbed are whatever CML generated from the
node definitions, which is wrong for any lab whose day-0 config sets its own
local user or enable secret — the console then hangs at the login prompt. The
optional CML_MCP_DEVICE_USERNAME / CML_MCP_DEVICE_PASSWORD /
CML_MCP_ENABLE_PASSWORD settings override them for every non-proxy device.
They are deliberately environment-only: device secrets must never travel as
tool arguments, where they would land in the model's context and transcripts.

The testbed is loaded with the Genie loader so every device also exposes
.parse(), turning raw CLI output into structured data when a parser exists.

Console sessions are expensive (SSH hop + console login, seconds each), so a
module-level ConsoleSessionManager caches the loaded testbed per lab and keeps
connected Unicon devices alive between tool calls, reaping idle sessions in the
background. Each device is guarded by its own asyncio.Lock — two concurrent
tool calls can never interleave on one console — and node fan-out is bounded by
a semaphore so a 40-node lab doesn't open 40 SSH sessions at once.

pyATS is the optional [console] extra (uv sync --extra console). All pyATS
imports are deferred into small helper functions so the server still runs
without the extra (the tools then return an actionable install hint) and so
tests can monkeypatch the connection machinery. pyATS calls are blocking, so
they run in a worker thread via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import ipaddress
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import yaml
from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cml_mcp.client import ApiClient
from cml_mcp.config import Settings
from cml_mcp.errors import PlatformError, format_error
from cml_mcp.formatting import finalize, to_json
from cml_mcp.safety import AppContext, register_tool

LAB_ID_DESC = "Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385')."
NODE_LABELS_DESC = (
    "Node LABELS as shown in the lab (e.g. ['R1', 'R2']) — not UUIDs. Labels are "
    "case-sensitive; discover them with cml_list_nodes."
)

ALLOWED_COMMANDS = frozenset({"show", "ping", "traceroute", "dir"})
CONFIG_TIMEOUT_SECONDS = 60
TERMINAL_SERVER = "terminal_server"

#: Max nodes worked on concurrently (each one holds an SSH hop through the controller).
MAX_CONCURRENT_NODES = 5
#: How long a loaded testbed stays usable before it is re-fetched from CML.
TESTBED_TTL_SECONDS = 120.0
#: Console sessions idle longer than this are disconnected by the reaper.
SESSION_IDLE_SECONDS = 300.0
#: How often the idle reaper wakes up.
REAPER_INTERVAL_SECONDS = 60.0
#: Ping matrix: echo count per pair and the source x target cap.
PING_REPEAT = 2
MAX_PING_PAIRS = 100

PYATS_MISSING = (
    "Error: console tools require the optional pyATS extra — "
    "install with: uv sync --extra console"
)
COMMAND_REJECTED = (
    "Error: only show/ping/traceroute/dir commands are allowed; "
    "use cml_send_config for configuration changes."
)
MISSING_CREDENTIALS = (
    "Error: console access requires CML_MCP_USERNAME and CML_MCP_PASSWORD to be "
    "configured — they authenticate the SSH hop through the CML terminal server. "
    "A static API token alone cannot open device consoles."
)
CONFIG_WILDCARD_REJECTED = (
    "Error: cml_send_config does not accept '*' — list the node labels explicitly so a "
    "configuration push can never fan out across a whole lab by accident."
)
NO_CONSOLE_NODES = (
    "Error: this lab has no console-capable nodes in its pyATS testbed, so there is "
    "nothing to connect to. Check the lab is started (cml_start_lab) and that its "
    "nodes are not all external connectors or unmanaged switches."
)
#: Deliberately plain ASCII: notes embedded in JSON responses come back through
#: json.dumps, which escapes non-ASCII punctuation into \\uXXXX noise.
PARSE_FALLBACK_NOTE = (
    "No Genie parser matched this command on this device type; raw output shown."
)
LEARN_UNSUPPORTED_NOTE = (
    "Genie has no operational model for this feature on this device's OS. Use "
    "cml_run_commands with the equivalent show command instead."
)
LEARN_EMPTY_NOTE = (
    "Genie learned this feature but the device reported no state for it, so it is "
    "most likely not configured on this node."
)
NO_OUTPUT = "(command produced no output)"

#: Genie ops models verified importable for iosxe in this environment. Exposed as
#: the cml_learn_feature Literal so an unlearnable name is rejected by the input
#: schema rather than after an SSH hop. ('config' is NOT a Genie ops feature.)
LEARNABLE_FEATURES = Literal[
    "acl",
    "arp",
    "bgp",
    "dot1x",
    "eigrp",
    "fdb",
    "hsrp",
    "igmp",
    "interface",
    "isis",
    "lag",
    "lldp",
    "mcast",
    "msdp",
    "nd",
    "ntp",
    "ospf",
    "pim",
    "platform",
    "prefix_list",
    "rip",
    "route_policy",
    "routing",
    "static_routing",
    "stp",
    "vlan",
    "vrf",
    "vxlan",
]
#: A learn issues many show commands back to back, so it needs a bigger budget
#: than a single command.
LEARN_TIMEOUT_DEFAULT = 120


def _pyats_available() -> bool:
    """True when the optional [console] extra (pyATS/Unicon/Genie) is installed."""
    try:
        import genie.testbed  # noqa: F401  # deferred: optional extra
    except ImportError:
        return False
    return True


def inject_terminal_server_credentials(
    testbed_data: dict[str, Any], username: str, password: str
) -> dict[str, Any]:
    """Replace the terminal_server placeholder credentials with the CML account.

    The generated testbed proxies every device console through a
    'terminal_server' device (the CML controller, over SSH) whose credentials
    are emitted as 'change_me'. Mutates and returns testbed_data. Device-level
    credentials (from the lab's configurations) are left untouched.
    """
    devices = testbed_data.get("devices")
    if not isinstance(devices, dict):
        raise PlatformError(
            "The generated pyATS testbed has no devices section; the lab may have no "
            "console-capable nodes."
        )
    terminal_server = devices.get(TERMINAL_SERVER)
    if not isinstance(terminal_server, dict):
        raise PlatformError(
            "The generated pyATS testbed has no terminal_server device, so console "
            "connections cannot be proxied through the CML controller."
        )
    credentials = terminal_server.setdefault("credentials", {}).setdefault("default", {})
    credentials["username"] = username
    credentials["password"] = password
    return testbed_data


def apply_device_credentials(
    testbed_data: dict[str, Any],
    username: str = "",
    password: str = "",
    enable_password: str = "",
) -> dict[str, Any]:
    """Override the per-device console credentials for every non-proxy device.

    CML emits device credentials derived from the node definition, which do not
    match a lab whose day-0 configuration defines its own local user or enable
    secret; Unicon then sits at the login prompt until the connect timeout. Only
    values that are actually configured are written, so an unset setting keeps
    CML's own value. The terminal_server proxy is never touched — it uses the
    CML account (see inject_terminal_server_credentials). Mutates and returns
    testbed_data.
    """
    if not (username or password or enable_password):
        return testbed_data
    devices = testbed_data.get("devices")
    if not isinstance(devices, dict):
        return testbed_data
    for label, device in devices.items():
        if label == TERMINAL_SERVER or not isinstance(device, dict):
            continue
        credentials = device.setdefault("credentials", {})
        if not isinstance(credentials, dict):
            continue
        if username or password:
            default = credentials.setdefault("default", {})
            if isinstance(default, dict):
                if username:
                    default["username"] = username
                if password:
                    default["password"] = password
        if enable_password:
            enable = credentials.setdefault("enable", {})
            if isinstance(enable, dict):
                enable["password"] = enable_password
    return testbed_data


def _load_testbed(path: str) -> Any:
    """Load a testbed YAML file with the Genie loader (deferred import).

    Genie's loader is used instead of the plain pyATS one because its devices
    also expose .parse(), which cml_run_commands needs for structured output.
    """
    from genie.testbed import load  # deferred: optional extra

    return load(path)


async def build_testbed(client: ApiClient, settings: Settings, lab_id: str) -> Any:
    """Fetch a lab's pyATS testbed, inject credentials, and load it.

    Two credential patches happen here: the terminal_server proxy always gets the
    CML account, and every other device gets the optional device/enable overrides
    when they are configured.

    The credential-bearing YAML only ever exists in a 0o600 temporary file that
    is deleted before returning; it is never logged or returned to the agent.
    Callers should go through ConsoleSessionManager.testbed() so the result is
    cached instead of re-fetched on every call.
    """
    response = await client.request("GET", f"/labs/{lab_id}/pyats_testbed")
    data = yaml.safe_load(response.text)
    if isinstance(data, str):  # CML sometimes JSON-wraps text payloads
        data = yaml.safe_load(data)
    if not isinstance(data, dict):
        raise PlatformError(
            "The pyATS testbed for this lab could not be parsed. The lab may be empty "
            "or its testbed generation unsupported."
        )
    inject_terminal_server_credentials(data, settings.username, settings.password)
    apply_device_credentials(
        data,
        settings.device_username,
        settings.device_password,
        settings.enable_password,
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False)
    try:
        os.fchmod(handle.fileno(), 0o600)
        yaml.safe_dump(data, handle)
        handle.close()
        return await asyncio.to_thread(_load_testbed, handle.name)
    finally:
        handle.close()
        os.unlink(handle.name)


# --------------------------------------------------------- blocking pyATS seams
# Everything below runs inside asyncio.to_thread; tests monkeypatch these.


def _connect(device: Any, timeout_seconds: int) -> None:
    """Open the console session (blocking; call via asyncio.to_thread)."""
    device.connect(
        log_stdout=False,
        learn_hostname=True,
        init_exec_commands=[],
        init_config_commands=[],
        connection_timeout=timeout_seconds,
    )


def _ensure_connected(device: Any, timeout_seconds: int) -> None:
    """Connect only if this cached device has no live console session."""
    if not getattr(device, "connected", False):
        _connect(device, timeout_seconds)


def _execute_command(device: Any, command: str, timeout_seconds: int) -> str:
    """Run one exec command on a connected device (blocking)."""
    return str(device.execute(command, timeout=timeout_seconds))


def _parse_output(device: Any, command: str, raw: str) -> Any | None:
    """Structure raw output with the Genie parser, or None when none matches.

    Genie raises for unknown commands, unsupported OS combinations and malformed
    output alike; every one of those is a parser miss for our purposes.
    """
    try:
        parsed = device.parse(command, output=raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict | list) and parsed else None


def _learn_feature(device: Any, feature: str) -> Any:
    """Learn one feature on a connected device, returning the Genie Ops object.

    The explicit get_ops() lookup makes 'this OS has no model for this feature'
    a clean LookupError before any command is sent, instead of a confusing
    failure deep inside the learn.
    """
    from genie.ops.utils import get_ops  # deferred: optional extra

    get_ops(feature, device)
    return device.learn(feature)


def _learn_node_feature(device: Any, feature: str, timeout_seconds: int) -> dict[str, Any]:
    """Connect if needed, learn a feature, and return its .info document (blocking)."""
    _ensure_connected(device, timeout_seconds)
    try:
        learned = _learn_feature(device, feature)
    except LookupError:
        return {"note": LEARN_UNSUPPORTED_NOTE}
    info = getattr(learned, "info", None)
    if isinstance(info, dict) and info:
        return info
    return {"note": LEARN_EMPTY_NOTE}


def _apply_config(device: Any, config_lines: str, timeout_seconds: int) -> str:
    """Apply configuration lines on a connected device (blocking)."""
    return str(device.configure(config_lines))


def _run_node_commands(
    device: Any, commands: list[str], output_format: str, timeout_seconds: int
) -> dict[str, Any]:
    """Run every command on ONE connection, returning {command: parsed_or_raw}."""
    _ensure_connected(device, timeout_seconds)
    results: dict[str, Any] = {}
    for command in commands:
        raw = _execute_command(device, command, timeout_seconds)
        text = raw.strip() or NO_OUTPUT
        if output_format == "parsed":
            parsed = _parse_output(device, command, raw)
            results[command] = (
                parsed if parsed is not None else {"raw": text, "note": PARSE_FALLBACK_NOTE}
            )
        else:
            results[command] = text
    return results


def _configure_node(device: Any, config_lines: str, timeout_seconds: int) -> str:
    """Connect if needed, then push configuration lines (blocking)."""
    _ensure_connected(device, timeout_seconds)
    return _apply_config(device, config_lines, timeout_seconds)


_SUCCESS_RATE_RE = re.compile(r"Success rate is (\d+) percent", re.IGNORECASE)
_PACKET_LOSS_RE = re.compile(r"([\d.]+)% packet loss", re.IGNORECASE)


def _success_rate(device: Any, command: str, raw: str) -> float | None:
    """Success percentage of a ping: Genie parser first, regex fallback second."""
    parsed = _parse_output(device, command, raw)
    if isinstance(parsed, dict):
        ping = parsed.get("ping")
        stats = ping.get("statistics", {}) if isinstance(ping, dict) else {}
        rate = stats.get("success_rate_percent")
        if isinstance(rate, int | float):
            return float(rate)
        sent, received = stats.get("send"), stats.get("received")
        if isinstance(sent, int) and sent > 0 and isinstance(received, int):
            return received / sent * 100
    match = _SUCCESS_RATE_RE.search(raw)  # IOS/IOS-XE/NX-OS
    if match:
        return float(match.group(1))
    match = _PACKET_LOSS_RE.search(raw)  # Linux/desktop nodes
    if match:
        return 100.0 - float(match.group(1))
    return None


def _valid_ip(address: str) -> str | None:
    """Return the address if it is a bare IPv4/IPv6 literal, else None.

    Ping targets are interpolated into a console command, so anything that is
    not a plain address (extra arguments, or a newline that unicon would send
    as a second command line) must never reach the device.
    """
    candidate = address.strip()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _ping_targets(
    device: Any, targets: list[tuple[str, str]], timeout_seconds: int
) -> dict[str, float | None]:
    """Ping every target from one connected device. Returns {target: success %}."""
    _ensure_connected(device, timeout_seconds)
    cells: dict[str, float | None] = {}
    for label, address in targets:
        # Defence in depth: the tool validates too, but this is the seam that
        # actually builds a command string, so it must not trust its caller.
        safe = _valid_ip(address)
        if safe is None:
            cells[label] = None
            continue
        command = f"ping {safe} repeat {PING_REPEAT}"
        raw = _execute_command(device, command, timeout_seconds)
        cells[label] = _success_rate(device, command, raw)
    return cells


def _disconnect(device: Any) -> None:
    """Best-effort console teardown; a failed disconnect must never propagate."""
    with contextlib.suppress(Exception):
        device.disconnect()


def _disconnect_all(devices: list[Any]) -> None:
    """Disconnect a batch of devices in one worker thread."""
    for device in devices:
        _disconnect(device)


# ------------------------------------------------------------ session caching


@dataclass
class _TestbedEntry:
    """A loaded testbed plus the node set and load time it is valid for."""

    testbed: Any
    node_labels: frozenset[str]
    loaded_at: float


@dataclass
class _DeviceEntry:
    """A (possibly connected) console device with its serializing lock."""

    device: Any
    lock: asyncio.Lock
    last_used: float


class ConsoleSessionManager:
    """Caches loaded testbeds per lab and live console sessions per node.

    Loading a testbed costs an API round trip plus YAML parsing; opening a
    console costs an SSH hop and a login. Both are cached so a sequence of
    console tool calls against the same lab reuses one connection per node.

    Invalidation: a testbed is re-fetched after TESTBED_TTL_SECONDS or as soon
    as the node-state pre-flight reports a different set of node labels (nodes
    added/removed/renamed), which also drops that lab's sessions. Sessions idle
    for more than SESSION_IDLE_SECONDS are disconnected by a lazily started
    background reaper, and everything is disconnected at interpreter exit.
    """

    def __init__(self) -> None:
        self._testbeds: dict[str, _TestbedEntry] = {}
        self._devices: dict[tuple[str, str], _DeviceEntry] = {}
        self._orphans: list[Any] = []
        self._reaper: asyncio.Task[None] | None = None

    async def testbed(
        self, client: ApiClient, settings: Settings, lab_id: str, node_labels: frozenset[str]
    ) -> Any:
        """Return the lab's loaded testbed, fetching it only when the cache is stale."""
        entry = self._testbeds.get(lab_id)
        now = time.monotonic()
        if (
            entry is not None
            and entry.node_labels == node_labels
            and now - entry.loaded_at < TESTBED_TTL_SECONDS
        ):
            return entry.testbed
        if entry is not None:
            await self.invalidate(lab_id)
        testbed = await build_testbed(client, settings, lab_id)
        self._testbeds[lab_id] = _TestbedEntry(testbed, node_labels, time.monotonic())
        self._ensure_reaper()
        return testbed

    def device(self, lab_id: str, node_label: str, testbed: Any) -> _DeviceEntry:
        """Return the cached device entry for a node, creating it on first use."""
        key = (lab_id, node_label)
        entry = self._devices.get(key)
        current = testbed.devices[node_label]
        if entry is None or entry.device is not current:
            if entry is not None:
                # The testbed was reloaded under us; keep the superseded device
                # so the reaper/close() can still disconnect it (never leak it).
                self._orphans.append(entry.device)
            entry = _DeviceEntry(current, asyncio.Lock(), time.monotonic())
            self._devices[key] = entry
        entry.last_used = time.monotonic()
        self._ensure_reaper()
        return entry

    async def drop(self, lab_id: str, node_label: str) -> None:
        """Forget one session (used after a failure, so the next call reconnects)."""
        entry = self._devices.pop((lab_id, node_label), None)
        if entry is not None:
            await asyncio.to_thread(_disconnect, entry.device)

    async def invalidate(self, lab_id: str) -> None:
        """Drop a lab's cached testbed and disconnect all of its sessions.

        Teardown is serialized against in-flight work: each session is closed
        while holding its own lock, so a concurrent call can never have unicon
        driving a device on one thread while this disconnects it on another.
        """
        self._testbeds.pop(lab_id, None)
        for key in [k for k in list(self._devices) if k[0] == lab_id]:
            entry = self._devices.get(key)
            if entry is None:
                continue
            async with entry.lock:
                # Re-check under the lock: another waiter may have replaced it.
                if self._devices.get(key) is entry:
                    del self._devices[key]
                    await asyncio.to_thread(_disconnect, entry.device)

    async def reap_idle(self, now: float | None = None) -> int:
        """Disconnect sessions idle past the threshold. Returns how many were closed."""
        now = time.monotonic() if now is None else now
        stale = [
            key
            for key, entry in self._devices.items()
            if now - entry.last_used > SESSION_IDLE_SECONDS and not entry.lock.locked()
        ]
        devices = [self._devices.pop(key).device for key in stale]
        if self._orphans:  # superseded sessions from a testbed reload
            devices += self._orphans
            self._orphans = []
        if devices:
            await asyncio.to_thread(_disconnect_all, devices)
        # Expire a stale testbed together with that lab's sessions. Dropping the
        # testbed alone would orphan still-connected devices: the next call
        # loads a fresh testbed, replaces the entries, and nothing would ever
        # disconnect the old ones.
        expired = [
            lab_id
            for lab_id, entry in self._testbeds.items()
            if now - entry.loaded_at > TESTBED_TTL_SECONDS
        ]
        for lab_id in expired:
            await self.invalidate(lab_id)
        return len(devices)

    def _ensure_reaper(self) -> None:
        """Start the idle reaper on first use inside a running event loop."""
        if self._reaper is not None and not self._reaper.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # no loop (e.g. imported by a sync caller) — nothing to do
            return
        self._reaper = loop.create_task(self._reap_loop())

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(REAPER_INTERVAL_SECONDS)
            with contextlib.suppress(Exception):
                await self.reap_idle()

    async def close(self) -> None:
        """Stop the reaper and disconnect every cached session (idempotent)."""
        task, self._reaper = self._reaper, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        devices = [entry.device for entry in self._devices.values()] + self._orphans
        self._devices.clear()
        self._orphans = []
        self._testbeds.clear()
        if devices:
            await asyncio.to_thread(_disconnect_all, devices)

    def close_sync(self) -> None:
        """Interpreter-exit teardown: disconnect consoles without an event loop."""
        devices = [entry.device for entry in self._devices.values()] + self._orphans
        self._devices.clear()
        self._orphans = []
        self._testbeds.clear()
        _disconnect_all(devices)


SESSIONS = ConsoleSessionManager()
atexit.register(SESSIONS.close_sync)


# ------------------------------------------------------------- shared helpers


async def _fetch_node_states(client: ApiClient, lab_id: str) -> dict[str, str]:
    """Map node label -> state for a lab (also the testbed cache key)."""
    nodes = await client.request_json(
        "GET",
        f"/labs/{lab_id}/nodes",
        params={"data": True, "operational": True, "exclude_configurations": True},
    )
    return {
        node["label"]: node.get("state") or "UNKNOWN"
        for node in nodes or []
        if isinstance(node, dict) and node.get("label")
    }


def _node_not_ready(
    node_label: str, states: dict[str, str], console_labels: set[str]
) -> str | None:
    """Pre-flight one node: known label, BOOTED, and console-capable. None when ready."""
    if node_label not in states:
        return (
            f"Error: no node labeled '{node_label}' in this lab. Labels are case-sensitive; "
            "list them with cml_list_nodes."
        )
    state = states[node_label]
    if state != "BOOTED":
        return (
            f"Error: node '{node_label}' is in state {state}; it must be BOOTED before "
            "console access works. Start it with cml_set_node_state(action='start') and "
            "wait for boot to finish (cml_wait_for_node_converged)."
        )
    if node_label not in console_labels:
        return (
            f"Error: node '{node_label}' has no console device in the pyATS testbed; "
            "its node type may not support console access."
        )
    return None


async def _prepare(
    client: ApiClient, settings: Settings, lab_id: str, requested: list[str]
) -> tuple[Any, list[str], dict[str, str]]:
    """Resolve requested labels against the lab: (testbed, ready labels, per-node errors).

    '*' expands to every console-capable device in the testbed except the
    terminal_server proxy. Nodes that are missing, not BOOTED or console-less
    become inline errors instead of failing the whole call.
    """
    states = await _fetch_node_states(client, lab_id)
    testbed = await SESSIONS.testbed(client, settings, lab_id, frozenset(states))
    console_labels = {
        label for label in getattr(testbed, "devices", {}) if label != TERMINAL_SERVER
    }
    if "*" in requested:
        labels = sorted(console_labels & set(states))
    else:
        labels = list(dict.fromkeys(requested))
    ready: list[str] = []
    errors: dict[str, str] = {}
    for label in labels:
        error = _node_not_ready(label, states, console_labels)
        if error:
            errors[label] = error
        else:
            ready.append(label)
    return testbed, ready, errors


async def _report(ctx: Context | None, done: int, total: int, message: str) -> None:
    """Best-effort MCP progress; a broken progress channel must never fail a call."""
    try:
        if ctx is not None:
            await ctx.report_progress(done, total, message)
    except Exception:
        pass  # progress reporting is advisory only


def _console_error(node_label: str, e: Exception) -> str:
    """Console failures without leaking pyATS logs (which can embed credentials)."""
    return (
        f"Error: console operation on node '{node_label}' failed ({type(e).__name__}). "
        "Check that the node has fully finished booting (cml_get_node_console_log) and "
        "retry with a larger timeout. If it is stuck at a login or enable prompt, the "
        "device credentials CML generated do not match the lab's day-0 configuration: "
        "set CML_MCP_DEVICE_USERNAME / CML_MCP_DEVICE_PASSWORD / CML_MCP_ENABLE_PASSWORD "
        "on the server and retry."
    )


async def _run_on_nodes(
    lab_id: str,
    testbed: Any,
    labels: list[str],
    work: Callable[[str, Any], Any],
    *,
    ctx: Context | None,
    progress_label: str,
) -> dict[str, tuple[Any, str | None]]:
    """Run blocking work(label, device) on each node, bounded and failure-isolated.

    Nodes are worked in parallel up to MAX_CONCURRENT_NODES; each node's device
    is held under its own lock so concurrent tool calls can't interleave on one
    console. A per-node exception becomes (None, "Error: ...") and drops that
    cached session — it never fails the whole call.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_NODES)
    results: dict[str, tuple[Any, str | None]] = {}
    completed = 0

    async def run_one(label: str) -> None:
        nonlocal completed
        async with semaphore:
            entry = SESSIONS.device(lab_id, label, testbed)
            async with entry.lock:
                try:
                    results[label] = (await asyncio.to_thread(work, label, entry.device), None)
                except Exception as e:
                    results[label] = (None, _console_error(label, e))
                    await SESSIONS.drop(lab_id, label)
                entry.last_used = time.monotonic()
        completed += 1
        await _report(
            ctx, completed, len(labels), f"{progress_label}: {completed}/{len(labels)} nodes done"
        )

    await asyncio.gather(*(run_one(label) for label in labels))
    return results


def _cell(rate: float | None) -> str:
    """Render one ping-matrix cell: 'ok', 'FAIL', 'N% loss' or '?' (unparsed)."""
    if rate is None:
        return "?"
    if rate >= 100:
        return "ok"
    if rate <= 0:
        return "FAIL"
    return f"{100 - rate:g}% loss"


def _render_matrix(
    lab_id: str,
    sources: list[str],
    targets: list[tuple[str, str]],
    cells: dict[str, dict[str, str]],
    node_errors: dict[str, str],
) -> str:
    """Build the compact matrix table, legend and one-line verdict."""
    header = [f"{label} ({address})" for label, address in targets]
    lines = [
        f"Ping matrix for lab {lab_id} — 'ping <ip> repeat {PING_REPEAT}' from each source.",
        "",
        "| source \\ target | " + " | ".join(header) + " |",
        "| --- |" + " --- |" * len(targets),
    ]
    counts = {"ok": 0, "loss": 0, "FAIL": 0, "?": 0, "ERR": 0}
    for source in sources:
        row = []
        for label, _ in targets:
            value = cells.get(source, {}).get(label, "-")
            row.append(value)
            if value in counts:
                counts[value] += 1
            elif value.endswith("% loss"):
                counts["loss"] += 1
        lines.append(f"| {source} | " + " | ".join(row) + " |")
    lines += [
        "",
        "Legend: ok = 100% success, FAIL = 0%, 'N% loss' = partial, '-' = self/not run, "
        "'?' = ping output not understood, ERR = console failure (see node errors).",
    ]
    tested = counts["ok"] + counts["loss"] + counts["FAIL"] + counts["?"] + counts["ERR"]
    if tested and counts["ok"] == tested:
        verdict = f"Verdict: all {tested} pairs fully reachable."
    else:
        broken = counts["FAIL"] + counts["loss"]
        verdict = (
            f"Verdict: {counts['ok']}/{tested} pairs fully reachable — "
            f"{counts['FAIL']} failed, {counts['loss']} partial, "
            f"{counts['?']} unclear, {counts['ERR']} console errors"
            f"{'; investigate the failing rows' if broken else ''}."
        )
    lines.append(verdict)
    if node_errors:
        lines.append("")
        lines.append("Node errors:")
        lines += [f"- {label}: {message}" for label, message in sorted(node_errors.items())]
    return "\n".join(lines)


def _primary_ipv4(node: dict[str, Any]) -> str | None:
    """First non-loopback IPv4 CML discovered for a node, or None."""
    interfaces = node.get("interfaces")
    if not isinstance(interfaces, dict):
        return None
    for interface in interfaces.values():
        if not isinstance(interface, dict):
            continue
        for address in interface.get("ip4") or []:
            if isinstance(address, str) and address and not address.startswith("127."):
                return address
    return None


async def _discover_target_ips(client: ApiClient, lab_id: str) -> dict[str, str]:
    """Map node label -> primary IPv4 from GET /labs/{lab_id}/layer3_addresses."""
    data = await client.request_json("GET", f"/labs/{lab_id}/layer3_addresses")
    addresses: dict[str, str] = {}
    for node in (data or {}).values():
        if not isinstance(node, dict):
            continue
        label, address = node.get("name"), _primary_ipv4(node)
        if label and address:
            addresses[label] = address
    return addresses


NO_TARGETS = (
    "Error: CML reported no IPv4 addresses for this lab's nodes, so there is nothing to "
    "ping. CML only discovers addresses for nodes reached through an L2 external "
    "connector (DHCP snooping) — pass target_ips explicitly (e.g. ['10.0.0.2']) or read "
    "them from the devices with cml_run_commands(commands=['show ip interface brief'])."
)


def _validate_commands(commands: list[str]) -> list[str] | None:
    """Strip and allow-list every command. None when any one is rejected."""
    cleaned: list[str] = []
    for command in commands:
        stripped = command.strip()
        if (
            not stripped
            or "\n" in stripped
            or "\r" in stripped
            or stripped.split()[0].lower() not in ALLOWED_COMMANDS
        ):
            return None
        cleaned.append(stripped)
    return cleaned


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    @register_tool(
        mcp,
        ctx,
        name="cml_run_commands",
        title="Run Console Commands",
        read_only=True,
        idempotent=True,
    )
    async def cml_run_commands(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_labels: Annotated[
            list[str],
            Field(
                description=NODE_LABELS_DESC + " Use ['*'] for every console-capable node "
                "in the lab (the terminal server proxy is always excluded).",
                min_length=1,
                max_length=64,
            ),
        ],
        commands: Annotated[
            list[str],
            Field(
                description="CLI commands to run on every selected node, in order "
                "(e.g. ['show version', 'show ip interface brief']). Each command's first "
                "word must be show/ping/traceroute/dir.",
                min_length=1,
                max_length=20,
            ),
        ],
        output_format: Annotated[
            Literal["parsed", "raw"],
            Field(
                description="'parsed' runs the Genie parser over each command's output and "
                "returns structured data (falling back to raw text when no parser matches); "
                "'raw' returns the device text verbatim — use it for exact CLI wording."
            ),
        ] = "parsed",
        timeout_seconds: Annotated[
            int,
            Field(
                description="Connect/command timeout in seconds (e.g. 60). "
                "Raise it for slow commands like large pings or traceroutes.",
                ge=5,
                le=300,
            ),
        ] = 60,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Run read-only CLI commands on one or many booted lab nodes' consoles.

        Read-only. Opens each node's serial console through the CML terminal
        server (pyATS/Unicon over SSH), runs every command over ONE connection
        per node, and fans out across nodes in parallel (5 at a time). Console
        sessions are cached and reused by later calls, so batching commands
        here is much cheaper than repeated single-command calls.

        Only show/ping/traceroute/dir commands are allowed — for configuration
        changes use cml_send_config. Nodes must be BOOTED (cml_set_node_state
        then cml_wait_for_node_converged). Requires the optional pyATS extra
        (uv sync --extra console) and configured CML username/password. If a node
        fails at a login or enable prompt, the lab's day-0 config uses
        credentials CML did not generate — set CML_MCP_DEVICE_USERNAME,
        CML_MCP_DEVICE_PASSWORD and/or CML_MCP_ENABLE_PASSWORD on the server
        (they are environment-only; never pass device secrets as arguments).
        Consoles are slow (seconds, not milliseconds); prefer the REST read
        tools when they can answer the question, and cml_ping_matrix for
        reachability sweeps.

        Args:
            lab_id: Lab UUID.
            node_labels: Node labels, or ['*'] for every console-capable node.
            commands: Allow-listed commands, run in order on each node.
            output_format: 'parsed' (Genie structured data) or 'raw' text.
            timeout_seconds: Per-connect/per-command timeout.

        Returns:
            str: JSON {node_label: {command: parsed_object_or_raw_text}}. A node
            that is missing, not BOOTED or whose console fails contributes
            {"error": "Error: ..."} instead — one bad node never fails the call.
            A command with no Genie parser yields {"raw": ..., "note": ...}.
            On failure: "Error: ..." (404 -> lab_id doesn't exist; rejected
            command -> a non-allow-listed first word).
        """
        cleaned = _validate_commands(commands)
        if cleaned is None:
            return COMMAND_REJECTED
        if not _pyats_available():
            return PYATS_MISSING
        if not (settings.username and settings.password):
            return MISSING_CREDENTIALS
        try:
            testbed, ready, errors = await _prepare(client, settings, lab_id, node_labels)
            if not ready and not errors:
                return NO_CONSOLE_NODES

            def work(label: str, device: Any) -> dict[str, Any]:
                return _run_node_commands(device, cleaned, output_format, timeout_seconds)

            outcomes = await _run_on_nodes(
                lab_id,
                testbed,
                ready,
                work,
                ctx=ctx,
                progress_label=f"Running {len(cleaned)} command(s)",
            )
            results: dict[str, Any] = {
                label: {"error": message} for label, message in errors.items()
            }
            for label, (value, error) in outcomes.items():
                results[label] = {"error": error} if error else value
            ordered = {label: results[label] for label in sorted(results)}
            return finalize(
                to_json(ordered),
                settings,
                truncation_hint=(
                    "Ask for fewer node_labels or commands per call, or use "
                    "output_format='parsed' for a more compact result."
                ),
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_send_config",
        title="Send Configuration to Nodes",
        read_only=False,
        destructive=False,
        idempotent=False,
    )
    async def cml_send_config(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_labels: Annotated[
            list[str],
            Field(
                description=NODE_LABELS_DESC + " '*' is NOT accepted here — list every "
                "target node explicitly.",
                min_length=1,
                max_length=32,
            ),
        ],
        config_lines: Annotated[
            str,
            Field(
                description=(
                    "Newline-separated configuration lines to apply in config mode on each "
                    "node (e.g. 'interface Loopback0\\nip address 10.0.0.1 255.255.255.255')."
                ),
                min_length=1,
                max_length=16384,
            ),
        ],
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Push the same configuration lines to one or more booted lab nodes.

        WRITE operation — only registered when CML_MCP_ENABLE_WRITES=true.
        Enters configuration mode on each live device (pyATS device.configure)
        over the cached console sessions, up to 5 nodes in parallel, and applies
        the lines. This changes the nodes' RUNNING config only: the change is
        NOT persisted in the lab store and is lost on wipe. Run
        cml_extract_node_configuration afterwards to persist it.

        Nodes must be BOOTED. Requires the optional pyATS extra
        (uv sync --extra console) and configured CML username/password. If a node
        fails at a login or enable prompt, set CML_MCP_DEVICE_USERNAME,
        CML_MCP_DEVICE_PASSWORD and/or CML_MCP_ENABLE_PASSWORD on the server to
        match the lab's day-0 credentials. Send identical lines to a group in one
        call; for per-node differences call once per node. For read-only checks
        use cml_run_commands.

        Args:
            lab_id: Lab UUID.
            node_labels: Explicit node labels (no '*' wildcard).
            config_lines: Newline-separated configuration lines.

        Returns:
            str: JSON {node_label: {"status": "applied", "output": "..."} or
            {"error": "Error: ..."}} plus a "_note" reminding you to persist the
            change with cml_extract_node_configuration. A per-node failure is
            reported inline; the other nodes still get configured.
            On failure: "Error: ..." (404 -> lab_id doesn't exist).
        """
        if "*" in node_labels:
            return CONFIG_WILDCARD_REJECTED
        if not _pyats_available():
            return PYATS_MISSING
        if not (settings.username and settings.password):
            return MISSING_CREDENTIALS
        try:
            testbed, ready, errors = await _prepare(client, settings, lab_id, node_labels)

            def work(label: str, device: Any) -> str:
                return _configure_node(device, config_lines, CONFIG_TIMEOUT_SECONDS)

            outcomes = await _run_on_nodes(
                lab_id,
                testbed,
                ready,
                work,
                ctx=ctx,
                progress_label="Applying configuration",
            )
            results: dict[str, Any] = {
                label: {"error": message} for label, message in errors.items()
            }
            for label, (value, error) in outcomes.items():
                results[label] = (
                    {"error": error}
                    if error
                    else {"status": "applied", "output": str(value).strip() or NO_OUTPUT}
                )
            summary = {label: results[label] for label in sorted(results)}
            summary["_note"] = (
                "Applied to the RUNNING config only, not yet saved in the lab store. "
                "Run cml_extract_node_configuration per node to persist it."
            )
            return finalize(
                to_json(summary),
                settings,
                truncation_hint="Configure fewer node_labels per call.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_ping_matrix",
        title="Ping Reachability Matrix",
        read_only=True,
        idempotent=True,
        open_world=True,
    )
    async def cml_ping_matrix(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        source_nodes: Annotated[
            list[str],
            Field(
                description="Node LABELS to ping FROM (e.g. ['R1', 'R2']), or ['*'] for "
                "every console-capable node in the lab.",
                min_length=1,
                max_length=32,
            ),
        ] = ["*"],  # noqa: B006  # read-only default surfaced in the tool schema
        target_ips: Annotated[
            list[str] | None,
            Field(
                description="IPv4 addresses to ping (e.g. ['10.0.0.2', '8.8.8.8']). Omit to "
                "target every OTHER node's primary IPv4 as discovered by CML "
                "(GET /labs/{id}/layer3_addresses).",
                max_length=32,
            ),
        ] = None,
        timeout_seconds: Annotated[
            int,
            Field(
                description="Per-ping timeout in seconds (e.g. 60). Raise it for slow or "
                "heavily loaded consoles.",
                ge=5,
                le=300,
            ),
        ] = 60,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Ping every source node against every target and return a reachability matrix.

        Read-only (it only sends ICMP echoes). Answers "which nodes can reach
        which?" in one call instead of many cml_run_commands round trips: from
        each source node's console it runs 'ping <ip> repeat 2' per target over
        the cached console session, reads the success rate with the Genie ping
        parser (regex fallback), and renders a compact matrix plus a verdict.

        Sources must be BOOTED; non-ready nodes are listed under "Node errors"
        instead of failing the call. Source x target pairs are capped at 100 —
        scope bigger labs with source_nodes/target_ips and run several calls.
        Requires the optional pyATS extra (uv sync --extra console) and
        configured CML username/password; a source stuck at a login or enable
        prompt means CML_MCP_DEVICE_USERNAME, CML_MCP_DEVICE_PASSWORD and/or
        CML_MCP_ENABLE_PASSWORD need setting on the server. Note this pings from
        the device's default VRF; for VRF-aware or extended pings use
        cml_run_commands.

        Args:
            lab_id: Lab UUID.
            source_nodes: Labels to ping from, or ['*'] for all.
            target_ips: Explicit targets; omit to use each other node's CML-discovered IPv4.
            timeout_seconds: Per-ping timeout.

        Returns:
            str: A markdown matrix (rows = source, columns = target) whose cells
            are 'ok' (100%), 'FAIL' (0%), 'N% loss', '?' (output not parsed),
            'ERR' (console failure) or '-' (self), followed by a legend, a
            one-line verdict and any per-node errors. On failure: "Error: ..."
            (404 -> lab_id doesn't exist; over the pair cap -> scope the request).
        """
        if not _pyats_available():
            return PYATS_MISSING
        if not (settings.username and settings.password):
            return MISSING_CREDENTIALS
        try:
            explicit_targets: list[tuple[str, str]] = []
            if target_ips:
                for address in dict.fromkeys(target_ips):
                    safe = _valid_ip(address)
                    if safe is None:
                        return (
                            "Error: target_ips entries must be plain IPv4/IPv6 addresses "
                            f"(got {address!r}). Hostnames, extra ping arguments, and "
                            "multi-line values are rejected."
                        )
                    explicit_targets.append((safe, safe))
            testbed, ready, errors = await _prepare(client, settings, lab_id, source_nodes)
            if not ready and not errors:
                return NO_CONSOLE_NODES
            if target_ips:
                targets = explicit_targets
            else:
                discovered = await _discover_target_ips(client, lab_id)
                targets = sorted(discovered.items())
            if not targets:
                return NO_TARGETS
            pairs = len(ready) * len(targets)
            if pairs > MAX_PING_PAIRS:
                return (
                    f"Error: {len(ready)} sources x {len(targets)} targets = {pairs} pings "
                    f"exceeds the {MAX_PING_PAIRS}-pair cap (each ping is a console round "
                    "trip). Scope the request — pass a shorter source_nodes list and/or "
                    "explicit target_ips — and repeat for the other slices."
                )

            def work(label: str, device: Any) -> dict[str, float | None]:
                return _ping_targets(
                    device, [t for t in targets if t[0] != label], timeout_seconds
                )

            outcomes = await _run_on_nodes(
                lab_id, testbed, ready, work, ctx=ctx, progress_label="Pinging"
            )
            node_errors = dict(errors)
            cells: dict[str, dict[str, str]] = {}
            for label, (value, error) in outcomes.items():
                if error:
                    node_errors[label] = error
                    cells[label] = {target: "ERR" for target, _ in targets}
                else:
                    cells[label] = {
                        target: _cell(rate) for target, rate in (value or {}).items()
                    }
            sources = sorted(set(ready) | set(errors))
            for label in errors:
                cells.setdefault(label, {target: "ERR" for target, _ in targets})
            return finalize(
                _render_matrix(lab_id, sources, targets, cells, node_errors),
                settings,
                truncation_hint="Scope the sweep with source_nodes and/or target_ips.",
            )
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_learn_feature",
        title="Learn Feature State",
        read_only=True,
        idempotent=True,
        open_world=True,
    )
    async def cml_learn_feature(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_labels: Annotated[
            list[str],
            Field(
                description=NODE_LABELS_DESC + " Use ['*'] for every console-capable node "
                "in the lab (the terminal server proxy is always excluded). Learning is "
                "slow, so keep this list to the nodes you actually need.",
                min_length=1,
                max_length=32,
            ),
        ],
        feature: Annotated[
            LEARNABLE_FEATURES,
            Field(
                description="Genie operational model to learn (e.g. 'ospf'). Each one runs "
                "the whole set of show commands behind that protocol and returns one "
                "structured document: 'bgp'/'ospf'/'eigrp'/'isis'/'rip' for routing "
                "protocol neighbours and databases, 'routing' for the RIB, "
                "'interface'/'arp'/'nd'/'lag' for L3 edge state, 'vlan'/'stp'/'fdb' for L2, "
                "'vrf'/'acl'/'prefix_list'/'route_policy'/'static_routing' for policy, "
                "'hsrp' for first-hop redundancy, 'igmp'/'pim'/'mcast'/'msdp' for "
                "multicast, 'platform' for hardware/software inventory."
            ),
        ],
        timeout_seconds: Annotated[
            int,
            Field(
                description="Console connect timeout in seconds (e.g. 120). A learn issues "
                "many show commands in a row, so give slow or busy consoles a large value.",
                ge=30,
                le=600,
            ),
        ] = LEARN_TIMEOUT_DEFAULT,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Learn one protocol's complete operational state from booted lab nodes.

        Read-only. Runs Genie's operational model for a feature (device.learn)
        over each node's console: it issues every show command that feature needs
        and merges the parsed output into ONE structured document — neighbours,
        timers, databases, counters and the interfaces they run on — instead of
        you guessing which show commands to chain together.

        Use this to answer "what is the state of <protocol> here?" and to compare
        the same document across nodes or before/after a change. Use
        cml_run_commands instead when you need one specific command, exact CLI
        wording, or a command outside the learnable feature list; use
        cml_ping_matrix for plain reachability. A learn is much slower than a
        single command (many round trips per node), so scope node_labels
        tightly. Sessions are cached and shared with the other console tools.

        Nodes must be BOOTED (cml_set_node_state then
        cml_wait_for_node_converged). Requires the optional pyATS extra
        (uv sync --extra console) and configured CML username/password. If a node
        fails at a login or enable prompt, the lab's day-0 config uses
        credentials CML did not generate — set CML_MCP_DEVICE_USERNAME,
        CML_MCP_DEVICE_PASSWORD and/or CML_MCP_ENABLE_PASSWORD on the server.

        Args:
            lab_id: Lab UUID.
            node_labels: Node labels, or ['*'] for every console-capable node.
            feature: Genie ops model to learn (see the enumerated values).
            timeout_seconds: Console connect timeout.

        Returns:
            str: JSON {node_label: <learned document>}. A node whose device OS
            has no model for the feature, or that has nothing configured for it,
            yields {"note": "..."} instead; a node that is missing, not BOOTED or
            whose console fails yields {"error": "Error: ..."} — one bad node
            never fails the call. These documents are large, so the response may
            be truncated. On failure: "Error: ..." (404 -> lab_id doesn't exist).
        """
        if not _pyats_available():
            return PYATS_MISSING
        if not (settings.username and settings.password):
            return MISSING_CREDENTIALS
        try:
            testbed, ready, errors = await _prepare(client, settings, lab_id, node_labels)
            if not ready and not errors:
                return NO_CONSOLE_NODES

            def work(label: str, device: Any) -> dict[str, Any]:
                return _learn_node_feature(device, feature, timeout_seconds)

            outcomes = await _run_on_nodes(
                lab_id,
                testbed,
                ready,
                work,
                ctx=ctx,
                progress_label=f"Learning {feature}",
            )
            results: dict[str, Any] = {
                label: {"error": message} for label, message in errors.items()
            }
            for label, (value, error) in outcomes.items():
                results[label] = {"error": error} if error else value
            ordered = {label: results[label] for label in sorted(results)}
            return finalize(
                to_json(ordered),
                settings,
                truncation_hint=(
                    "Learned documents are large — ask for one node at a time, or use "
                    "cml_run_commands with the specific show command you need."
                ),
            )
        except Exception as e:
            return format_error(e)
