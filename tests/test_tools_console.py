"""Console tools end-to-end through MCPServer (schema validation included).

No real pyATS connections: the loader and the blocking connect/execute/parse/
configure helpers are monkeypatched; all HTTP is mocked with respx. Every test
gets a fresh ConsoleSessionManager so cached sessions (and their locks) never
leak across event loops.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx
import yaml

from cml_mcp import tools as tools_registry
from cml_mcp.errors import PlatformError
from cml_mcp.server import build_server
from cml_mcp.tools import console as console_module
from tests.conftest import BASE_URL, call_tool_text


@pytest.fixture(autouse=True)
def _include_console_module(monkeypatch):
    """Register this module's tools even before tools/__init__.py lists it.

    Integration of ALL_MODULES happens in a separate change; the guard makes
    this fixture a no-op once the module is wired in there.
    """
    if console_module not in tools_registry.ALL_MODULES:
        monkeypatch.setattr(
            tools_registry, "ALL_MODULES", [*tools_registry.ALL_MODULES, console_module]
        )


@pytest.fixture(autouse=True)
async def sessions(monkeypatch):
    """Isolate the module-level session cache per test and tear it down after."""
    manager = console_module.ConsoleSessionManager()
    monkeypatch.setattr(console_module, "SESSIONS", manager)
    yield manager
    await manager.close()


@pytest.fixture
def mcp(make_settings):
    return build_server(
        make_settings(enable_writes=True, username="netadmin", password="s3cret")
    )


LAB_ID = "90f84e38-a71c-4d57-8d90-00fa8a197385"
NODE_ID = "26f677f3-fcb2-47ef-9171-dc112d80b54f"

SAMPLE_TESTBED_YAML = """\
devices:
  R1:
    connections:
      a:
        command: open /Console Lab/R1/0
        protocol: telnet
        proxy: terminal_server
      defaults:
        class: unicon.Unicon
    credentials:
      default:
        username: cisco
        password: cisco
      enable:
        password: cisco
    os: iosxe
  terminal_server:
    connections:
      cli:
        ip: cml.example.test
        protocol: ssh
    credentials:
      default:
        username: change_me
        password: change_me
    os: linux
testbed:
  name: Console Lab
"""


class FakeDevice:
    """Stand-in for a Unicon/Genie device: tracks connects, never talks SSH."""

    def __init__(self, name: str, parsed: dict | None = None) -> None:
        self.name = name
        self.connected = False
        self.connects = 0
        self.parsed = parsed

    def parse(self, command: str, output: str = ""):
        if self.parsed is None:
            raise ValueError(f"no parser for {command}")  # what Genie does on a parser miss
        return self.parsed

    def disconnect(self) -> None:
        self.connected = False


def _fake_testbed(*labels: str) -> SimpleNamespace:
    devices = {label: FakeDevice(label) for label in labels}
    devices["terminal_server"] = FakeDevice("terminal_server")
    return SimpleNamespace(devices=devices)


def _mock_nodes(*nodes: tuple[str, str]) -> None:
    """Mock GET /nodes from (label, state) pairs; defaults to a single BOOTED R1."""
    nodes = nodes or (("R1", "BOOTED"),)
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": f"{NODE_ID[:-1]}{index}",
                    "label": label,
                    "state": state,
                    "node_definition": "iosv",
                }
                for index, (label, state) in enumerate(nodes)
            ],
        )
    )


def _mock_testbed() -> None:
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/pyats_testbed").mock(
        return_value=httpx.Response(
            200, text=SAMPLE_TESTBED_YAML, headers={"Content-Type": "application/yaml"}
        )
    )


def _patch_console(monkeypatch, testbed, **overrides) -> None:
    """Wire the blocking pyATS seams to fakes: no SSH, no real loader."""

    def fake_connect(device, timeout_seconds):
        device.connects += 1
        device.connected = True

    monkeypatch.setattr(console_module, "_load_testbed", overrides.get("load", lambda p: testbed))
    monkeypatch.setattr(console_module, "_connect", overrides.get("connect", fake_connect))
    if "execute" in overrides:
        monkeypatch.setattr(console_module, "_execute_command", overrides["execute"])
    if "apply_config" in overrides:
        monkeypatch.setattr(console_module, "_apply_config", overrides["apply_config"])
    if "parse" in overrides:
        monkeypatch.setattr(console_module, "_parse_output", overrides["parse"])
    if "learn" in overrides:
        monkeypatch.setattr(console_module, "_learn_feature", overrides["learn"])


# ------------------------------------------------- credential-injection helper


def test_inject_terminal_server_credentials_replaces_placeholders():
    data = yaml.safe_load(SAMPLE_TESTBED_YAML)
    result = console_module.inject_terminal_server_credentials(data, "netadmin", "s3cret")
    assert result["devices"]["terminal_server"]["credentials"]["default"] == {
        "username": "netadmin",
        "password": "s3cret",
    }
    # Device-level credentials (from the lab's node configurations) stay untouched.
    assert result["devices"]["R1"]["credentials"]["default"]["username"] == "cisco"
    assert result["devices"]["R1"]["credentials"]["default"]["password"] == "cisco"


def test_inject_terminal_server_credentials_missing_device():
    with pytest.raises(PlatformError, match="terminal_server"):
        console_module.inject_terminal_server_credentials(
            {"devices": {"R1": {}}}, "netadmin", "s3cret"
        )


# ------------------------------------------------------- rename + tool surface


async def test_run_command_was_renamed_to_run_commands(mcp):
    names = {tool.name for tool in await mcp.list_tools()}
    assert "cml_run_commands" in names
    assert "cml_ping_matrix" in names
    assert "cml_learn_feature" in names
    assert "cml_run_command" not in names  # old singular name is gone


# ------------------------------------------------------------ cml_run_commands


@respx.mock
async def test_run_commands_rejects_config_command_preflight(mcp):
    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "commands": ["configure terminal"]},
    )
    assert text == console_module.COMMAND_REJECTED
    assert len(respx.calls) == 0  # rejected before any HTTP request


@respx.mock
async def test_run_commands_rejects_multiline_smuggling(mcp):
    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["R1"],
            "commands": ["show version", "show run\nconfigure terminal"],
        },
    )
    assert text == console_module.COMMAND_REJECTED
    assert len(respx.calls) == 0  # one bad command rejects the whole batch


@respx.mock
async def test_run_commands_multi_node_multi_command_shaping(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()
    loaded: dict = {}
    calls: list[tuple[str, str, int]] = []

    def fake_load(path: str):
        loaded["path"] = path
        data = yaml.safe_load(Path(path).read_text())
        loaded["ts_creds"] = data["devices"]["terminal_server"]["credentials"]["default"]
        return _fake_testbed("R1", "R2")

    def fake_execute(device, command, timeout_seconds):
        calls.append((device.name, command, timeout_seconds))
        return f"{device.name}: {command} output"

    _patch_console(monkeypatch, None, load=fake_load, execute=fake_execute)

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["R1", "R2"],
            "commands": ["show version", "show ip interface brief"],
            "output_format": "raw",
            "timeout_seconds": 90,
        },
    )
    assert '"R1"' in text and '"R2"' in text
    assert "R1: show version output" in text
    assert "R2: show ip interface brief output" in text
    assert sorted(calls) == [
        ("R1", "show ip interface brief", 90),
        ("R1", "show version", 90),
        ("R2", "show ip interface brief", 90),
        ("R2", "show version", 90),
    ]
    # The CML credentials were injected into the terminal_server proxy device...
    assert loaded["ts_creds"] == {"username": "netadmin", "password": "s3cret"}
    # ...and the credential-bearing temp file was removed afterwards.
    assert not os.path.exists(loaded["path"])


@respx.mock
async def test_run_commands_wildcard_expands_to_console_nodes(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"), ("R3", "STOPPED"))
    _mock_testbed()
    _patch_console(
        monkeypatch,
        _fake_testbed("R1", "R2", "R3"),
        execute=lambda device, command, timeout: f"{device.name} ok",
    )

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["*"],
            "commands": ["show version"],
            "output_format": "raw",
        },
    )
    assert "R1 ok" in text and "R2 ok" in text
    assert "terminal_server" not in text  # the SSH proxy is never a target
    assert "STOPPED" in text and '"R3"' in text  # not-booted node is an inline error


@respx.mock
async def test_run_commands_parse_falls_back_to_raw(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()
    testbed = _fake_testbed("R1", "R2")
    testbed.devices["R1"].parsed = {"version": {"version_short": "17.9"}}
    _patch_console(
        monkeypatch,
        testbed,
        execute=lambda device, command, timeout: "Cisco IOS XE Software, Version 17.09.01",
    )

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2"], "commands": ["show version"]},
    )
    assert '"version_short": "17.9"' in text  # R1 parsed by Genie
    assert console_module.PARSE_FALLBACK_NOTE in text  # R2 has no parser
    assert "Cisco IOS XE Software, Version 17.09.01" in text  # raw kept as the fallback


@respx.mock
async def test_run_commands_isolates_per_node_failure(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()

    def fake_execute(device, command, timeout_seconds):
        if device.name == "R2":
            raise RuntimeError("password=s3cret leaked in a pyATS log line")
        return "R1 ok"

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), execute=fake_execute)

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["R1", "R2"],
            "commands": ["show version"],
            "output_format": "raw",
        },
    )
    assert "R1 ok" in text  # the healthy node still returns output
    assert "console operation on node 'R2' failed (RuntimeError)" in text
    assert "s3cret" not in text  # exception details (may embed credentials) stay out


@respx.mock
async def test_run_commands_reuses_testbed_and_session(mcp, monkeypatch, sessions):
    _mock_nodes()
    _mock_testbed()
    testbed = _fake_testbed("R1")
    loads = 0

    def fake_load(path: str):
        nonlocal loads
        loads += 1
        return testbed

    _patch_console(
        monkeypatch,
        testbed,
        load=fake_load,
        execute=lambda device, command, timeout: "ok",
    )

    args = {
        "lab_id": LAB_ID,
        "node_labels": ["R1"],
        "commands": ["show version"],
        "output_format": "raw",
    }
    await call_tool_text(mcp, "cml_run_commands", args)
    await call_tool_text(mcp, "cml_run_commands", args)

    assert loads == 1  # testbed cached for the lab (same node set, inside the TTL)
    assert testbed.devices["R1"].connects == 1  # console session reused across calls
    assert (LAB_ID, "R1") in sessions._devices


@respx.mock
async def test_run_commands_reloads_testbed_when_node_set_changes(mcp, monkeypatch):
    _mock_testbed()
    testbed = _fake_testbed("R1", "R2")
    loads = 0

    def fake_load(path: str):
        nonlocal loads
        loads += 1
        return testbed

    _patch_console(
        monkeypatch, testbed, load=fake_load, execute=lambda d, c, t: "ok"
    )

    args = {
        "lab_id": LAB_ID,
        "node_labels": ["R1"],
        "commands": ["show version"],
        "output_format": "raw",
    }
    _mock_nodes(("R1", "BOOTED"))
    await call_tool_text(mcp, "cml_run_commands", args)
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))  # a node was added to the lab
    await call_tool_text(mcp, "cml_run_commands", args)

    assert loads == 2  # cache invalidated by the changed node set
    assert testbed.devices["R1"].connects == 2  # and the stale session was dropped


@respx.mock
async def test_run_commands_unknown_label(mcp, monkeypatch):
    _mock_nodes(("R2", "BOOTED"))
    _mock_testbed()
    _patch_console(monkeypatch, _fake_testbed("R2"))
    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "commands": ["show version"]},
    )
    assert "no node labeled 'R1'" in text


@respx.mock
async def test_run_commands_testbed_fetch_404(mcp):
    _mock_nodes()
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/pyats_testbed").mock(
        return_value=httpx.Response(404)
    )
    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "commands": ["show version"]},
    )
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_run_commands_without_console_credentials(make_settings):
    mcp = build_server(make_settings(enable_writes=True))  # api_token only
    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "commands": ["show version"]},
    )
    assert text == console_module.MISSING_CREDENTIALS
    assert len(respx.calls) == 0


@respx.mock
async def test_console_tools_report_missing_pyats_extra(mcp, monkeypatch):
    monkeypatch.setattr(console_module, "_pyats_available", lambda: False)
    for name, args in (
        (
            "cml_run_commands",
            {"lab_id": LAB_ID, "node_labels": ["R1"], "commands": ["show version"]},
        ),
        (
            "cml_send_config",
            {"lab_id": LAB_ID, "node_labels": ["R1"], "config_lines": "no ip http"},
        ),
        ("cml_ping_matrix", {"lab_id": LAB_ID}),
        (
            "cml_learn_feature",
            {"lab_id": LAB_ID, "node_labels": ["R1"], "feature": "ospf"},
        ),
    ):
        text = await call_tool_text(mcp, name, args)
        assert text == console_module.PYATS_MISSING
    assert len(respx.calls) == 0


# ------------------------------------------------------------- cml_send_config


@respx.mock
async def test_send_config_multi_node_happy_path(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()
    applied: list[tuple[str, str, int]] = []

    def fake_apply(device, config_lines, timeout_seconds):
        applied.append((device.name, config_lines, timeout_seconds))
        return "Enter configuration commands, one per line."

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), apply_config=fake_apply)

    config = "interface Loopback0\nip address 10.0.0.1 255.255.255.255"
    text = await call_tool_text(
        mcp,
        "cml_send_config",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2"], "config_lines": config},
    )
    assert '"status": "applied"' in text
    assert "cml_extract_node_configuration" in text  # persistence follow-up advice kept
    assert sorted(applied) == [
        ("R1", config, console_module.CONFIG_TIMEOUT_SECONDS),
        ("R2", config, console_module.CONFIG_TIMEOUT_SECONDS),
    ]


@respx.mock
async def test_send_config_rejects_wildcard(mcp):
    text = await call_tool_text(
        mcp,
        "cml_send_config",
        {"lab_id": LAB_ID, "node_labels": ["*"], "config_lines": "no ip http server"},
    )
    assert text == console_module.CONFIG_WILDCARD_REJECTED
    assert len(respx.calls) == 0


@respx.mock
async def test_send_config_console_failure_does_not_leak_details(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()

    def fake_apply(device, config_lines, timeout_seconds):
        if device.name == "R2":
            raise RuntimeError("password=s3cret leaked in a pyATS log line")
        return "ok"

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), apply_config=fake_apply)

    text = await call_tool_text(
        mcp,
        "cml_send_config",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2"], "config_lines": "no ip http server"},
    )
    assert "console operation on node 'R2' failed (RuntimeError)" in text
    assert '"status": "applied"' in text  # R1 was still configured
    assert "s3cret" not in text


# -------------------------------------------------------------- cml_ping_matrix


PING_OK = """\
Type escape sequence to abort.
Sending 2, 100-byte ICMP Echos to 10.0.0.2, timeout is 2 seconds:
!!
Success rate is 100 percent (2/2), round-trip min/avg/max = 1/2/4 ms"""

PING_FAIL = """\
Type escape sequence to abort.
Sending 2, 100-byte ICMP Echos to 10.0.0.3, timeout is 2 seconds:
..
Success rate is 0 percent (0/2)"""


def _mock_layer3(*entries: tuple[str, str]) -> None:
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/layer3_addresses").mock(
        return_value=httpx.Response(
            200,
            json={
                f"{NODE_ID[:-1]}{index}": {
                    "name": label,
                    "interfaces": {
                        f"52:54:00:00:00:0{index}": {
                            "id": NODE_ID,
                            "label": "eth0",
                            "ip4": [address],
                            "ip6": [],
                        }
                    },
                }
                for index, (label, address) in enumerate(entries)
            },
        )
    )


@respx.mock
async def test_ping_matrix_renders_matrix_and_verdict(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()
    _mock_layer3(("R1", "10.0.0.1"), ("R2", "10.0.0.2"))

    def fake_execute(device, command, timeout_seconds):
        assert command.endswith(f"repeat {console_module.PING_REPEAT}")
        return PING_OK if device.name == "R1" else PING_FAIL

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), execute=fake_execute)

    text = await call_tool_text(mcp, "cml_ping_matrix", {"lab_id": LAB_ID})
    assert "| source \\ target | R1 (10.0.0.1) | R2 (10.0.0.2) |" in text
    assert "| R1 | - | ok |" in text  # self column skipped, R2 reachable
    assert "| R2 | FAIL | - |" in text  # regex fallback read '0 percent'
    assert "Verdict: 1/2 pairs fully reachable" in text


@respx.mock
async def test_ping_matrix_uses_genie_parser_and_explicit_targets(mcp, monkeypatch):
    _mock_nodes()
    _mock_testbed()
    testbed = _fake_testbed("R1")
    testbed.devices["R1"].parsed = {
        "ping": {"address": "8.8.8.8", "statistics": {"send": 2, "received": 1}}
    }
    _patch_console(
        monkeypatch, testbed, execute=lambda device, command, timeout: "garbled output"
    )

    text = await call_tool_text(
        mcp,
        "cml_ping_matrix",
        {"lab_id": LAB_ID, "source_nodes": ["R1"], "target_ips": ["8.8.8.8"]},
    )
    assert "| R1 | 50% loss |" in text  # 1/2 received via the Genie ping parser
    assert not respx.calls.__len__() or all(
        "layer3_addresses" not in str(call.request.url) for call in respx.calls
    )  # explicit targets skip discovery


@respx.mock
async def test_ping_matrix_caps_pair_count(mcp, monkeypatch):
    nodes = tuple((f"R{index}", "BOOTED") for index in range(12))
    _mock_nodes(*nodes)
    _mock_testbed()
    _mock_layer3(*((f"R{index}", f"10.0.0.{index}") for index in range(12)))
    _patch_console(monkeypatch, _fake_testbed(*(label for label, _ in nodes)))

    text = await call_tool_text(mcp, "cml_ping_matrix", {"lab_id": LAB_ID})
    assert text.startswith("Error: 12 sources x 12 targets = 144 pings")
    assert "source_nodes" in text and "target_ips" in text


@respx.mock
async def test_ping_matrix_without_discovered_addresses(mcp, monkeypatch):
    _mock_nodes()
    _mock_testbed()
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/layer3_addresses").mock(
        return_value=httpx.Response(200, json={})
    )
    _patch_console(monkeypatch, _fake_testbed("R1"))

    text = await call_tool_text(mcp, "cml_ping_matrix", {"lab_id": LAB_ID})
    assert text == console_module.NO_TARGETS


@respx.mock
async def test_ping_matrix_reports_node_errors_without_failing(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "STOPPED"))
    _mock_testbed()
    _mock_layer3(("R2", "10.0.0.2"))
    _patch_console(
        monkeypatch, _fake_testbed("R1", "R2"), execute=lambda d, c, t: PING_OK
    )

    text = await call_tool_text(
        mcp, "cml_ping_matrix", {"lab_id": LAB_ID, "source_nodes": ["R1", "R2"]}
    )
    assert "| R1 | ok |" in text
    assert "Node errors:" in text
    assert "R2" in text and "STOPPED" in text


# ------------------------------------------------------- session manager itself


async def test_session_manager_reaps_idle_and_closes(sessions):
    testbed = _fake_testbed("R1")
    entry = sessions.device(LAB_ID, "R1", testbed)
    entry.device.connected = True
    assert sessions.device(LAB_ID, "R1", testbed) is entry  # cached, not recreated

    reaped = await sessions.reap_idle(now=entry.last_used + console_module.SESSION_IDLE_SECONDS)
    assert reaped == 0  # not idle long enough yet

    reaped = await sessions.reap_idle(
        now=entry.last_used + console_module.SESSION_IDLE_SECONDS + 1
    )
    assert reaped == 1
    assert sessions._devices == {}

    await sessions.close()  # idempotent, and safe with nothing cached


# --------------------------------------- security & session-manager regressions


@respx.mock
async def test_ping_matrix_rejects_command_injection_in_target_ips(make_settings):
    """target_ips is interpolated into a console command: only bare IPs allowed.

    A newline would be an Enter keypress at the device prompt, turning the rest
    of the value into a second command line (config mode from a read-only tool).
    """
    # Read-only server, but with console credentials configured.
    mcp = build_server(
        make_settings(enable_writes=False, username="netadmin", password="s3cret")
    )
    text = await call_tool_text(
        mcp,
        "cml_ping_matrix",
        {
            "lab_id": LAB_ID,
            "source_nodes": ["R1"],
            "target_ips": ["1.1.1.1\nconfigure terminal\nhostname pwned\nend"],
        },
    )
    assert text.startswith("Error:")
    assert "plain IPv4/IPv6" in text
    assert not respx.calls  # rejected before any platform call


@respx.mock
async def test_ping_matrix_rejects_non_address_targets(make_settings):
    mcp = build_server(
        make_settings(enable_writes=False, username="netadmin", password="s3cret")
    )
    for bad in ["router.example.com", "10.0.0.1 repeat 9999", "10.0.0.1;reload"]:
        text = await call_tool_text(
            mcp,
            "cml_ping_matrix",
            {"lab_id": LAB_ID, "source_nodes": ["R1"], "target_ips": [bad]},
        )
        assert text.startswith("Error:"), bad


def test_ping_command_builder_refuses_unsafe_address():
    """The command-building seam validates independently of the tool boundary."""
    from cml_mcp.tools import console as console_mod

    executed: list[str] = []

    class _FakeDevice:
        is_connected = True

        def connect(self, **_kwargs):
            return None

        def execute(self, command, **_kwargs):
            executed.append(command)
            return "Success rate is 100 percent (2/2)"

    cells = console_mod._ping_targets(
        _FakeDevice(), [("bad", "1.1.1.1\nreload"), ("ok", "10.0.0.2")], 30
    )
    assert cells["bad"] is None  # never sent
    assert executed == ["ping 10.0.0.2 repeat 2"]


async def test_invalidate_waits_for_in_flight_session(monkeypatch):
    """invalidate() must not disconnect a device another call is driving."""
    from cml_mcp.tools import console as console_mod

    manager = console_mod.ConsoleSessionManager()
    device = object()
    entry = console_mod._DeviceEntry(device, asyncio.Lock(), time.monotonic())
    manager._devices[("lab", "R1")] = entry
    manager._testbeds["lab"] = console_mod._TestbedEntry(object(), frozenset({"R1"}), 0.0)

    disconnected: list[object] = []
    monkeypatch.setattr(console_mod, "_disconnect", lambda d: disconnected.append(d))

    async with entry.lock:  # simulate a tool call using the console
        task = asyncio.create_task(manager.invalidate("lab"))
        await asyncio.sleep(0)
        assert disconnected == []  # blocked while the session is busy
    await task
    assert disconnected == [device]  # torn down once the work finished


async def test_reap_expires_testbed_and_its_sessions_together(monkeypatch):
    """A stale testbed must not be dropped while its sessions stay connected."""
    from cml_mcp.tools import console as console_mod

    manager = console_mod.ConsoleSessionManager()
    device = object()
    manager._devices[("lab", "R1")] = console_mod._DeviceEntry(
        device, asyncio.Lock(), time.monotonic()
    )
    manager._testbeds["lab"] = console_mod._TestbedEntry(object(), frozenset({"R1"}), 0.0)

    disconnected: list[object] = []
    monkeypatch.setattr(console_mod, "_disconnect", lambda d: disconnected.append(d))
    monkeypatch.setattr(console_mod, "_disconnect_all", lambda ds: disconnected.extend(ds))

    # Now is past the testbed TTL but inside the session idle window.
    await manager.reap_idle(now=time.monotonic() + console_mod.TESTBED_TTL_SECONDS + 1)
    assert manager._testbeds == {}
    assert manager._devices == {}
    assert disconnected == [device]  # no orphaned console session left behind


# ----------------------------------------------------------- cml_learn_feature


class FakeLearned:
    """Stand-in for a Genie Ops object: only .info matters to the tool."""

    def __init__(self, info) -> None:
        self.info = info


@respx.mock
async def test_learn_feature_returns_documents_per_node(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()
    learned: list[tuple[str, str]] = []

    def fake_learn(device, feature):
        learned.append((device.name, feature))
        return FakeLearned({"vrf": {"default": {"instance": {"1": {"areas": {}}}}}})

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), learn=fake_learn)

    text = await call_tool_text(
        mcp,
        "cml_learn_feature",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2"], "feature": "ospf"},
    )
    assert '"R1"' in text and '"R2"' in text
    assert '"areas"' in text  # the learned document is returned verbatim
    assert sorted(learned) == [("R1", "ospf"), ("R2", "ospf")]


@respx.mock
async def test_learn_feature_connects_once_and_reuses_session(mcp, monkeypatch, sessions):
    _mock_nodes()
    _mock_testbed()
    testbed = _fake_testbed("R1")
    _patch_console(
        monkeypatch, testbed, learn=lambda device, feature: FakeLearned({"ok": True})
    )

    args = {
        "lab_id": LAB_ID,
        "node_labels": ["R1"],
        "feature": "routing",
        "timeout_seconds": 300,
    }
    await call_tool_text(mcp, "cml_learn_feature", args)
    await call_tool_text(mcp, "cml_learn_feature", args)

    assert testbed.devices["R1"].connects == 1  # cached console reused, as for run_commands
    assert (LAB_ID, "R1") in sessions._devices


@respx.mock
async def test_learn_feature_notes_unsupported_and_empty(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()

    def fake_learn(device, feature):
        if device.name == "R1":
            raise LookupError(f"Could not find a feature called '{feature}'")
        return FakeLearned({})  # feature not configured on this node

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), learn=fake_learn)

    text = await call_tool_text(
        mcp,
        "cml_learn_feature",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2"], "feature": "vxlan"},
    )
    assert console_module.LEARN_UNSUPPORTED_NOTE in text
    assert console_module.LEARN_EMPTY_NOTE in text
    assert "Error:" not in text  # neither case is a failure


@respx.mock
async def test_learn_feature_isolates_per_node_failure(mcp, monkeypatch):
    _mock_nodes(("R1", "BOOTED"), ("R2", "STOPPED"), ("R3", "BOOTED"))
    _mock_testbed()

    def fake_learn(device, feature):
        if device.name == "R3":
            raise RuntimeError("password=s3cret leaked in a pyATS log line")
        return FakeLearned({"instance": {"default": {}}})

    _patch_console(monkeypatch, _fake_testbed("R1", "R2", "R3"), learn=fake_learn)

    text = await call_tool_text(
        mcp,
        "cml_learn_feature",
        {"lab_id": LAB_ID, "node_labels": ["R1", "R2", "R3"], "feature": "bgp"},
    )
    assert '"instance"' in text  # R1 still produced its document
    assert "STOPPED" in text  # R2 pre-flight error, inline
    assert "console operation on node 'R3' failed (RuntimeError)" in text
    assert "s3cret" not in text  # pyATS exception text (may embed credentials) stays out


@respx.mock
async def test_learn_feature_rejects_unknown_feature(mcp):
    """'config' is not a Genie ops model (the old server advertised it anyway)."""
    with pytest.raises(Exception, match="literal_error") as excinfo:
        await call_tool_text(
            mcp,
            "cml_learn_feature",
            {"lab_id": LAB_ID, "node_labels": ["R1"], "feature": "config"},
        )
    assert "'ospf'" in str(excinfo.value)  # the schema lists the valid features
    assert len(respx.calls) == 0  # rejected before any HTTP call or SSH hop


@respx.mock
async def test_learn_feature_without_console_credentials(make_settings):
    mcp = build_server(make_settings())  # api_token only
    text = await call_tool_text(
        mcp,
        "cml_learn_feature",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "feature": "interface"},
    )
    assert text == console_module.MISSING_CREDENTIALS
    assert len(respx.calls) == 0


@respx.mock
async def test_learn_feature_lab_not_found(mcp, monkeypatch):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(return_value=httpx.Response(404))
    _patch_console(monkeypatch, _fake_testbed("R1"))
    text = await call_tool_text(
        mcp,
        "cml_learn_feature",
        {"lab_id": LAB_ID, "node_labels": ["R1"], "feature": "ospf"},
    )
    assert text.startswith("Error:")
    assert "404" in text


def test_learn_features_are_importable_genie_ops_models():
    """Every advertised feature must resolve to a real Genie ops model."""
    pytest.importorskip("genie.ops.utils")
    from genie.ops.utils import get_ops

    device = SimpleNamespace(os="iosxe", platform=None, model=None, custom={})
    for feature in console_module.LEARNABLE_FEATURES.__args__:
        assert get_ops(feature, device) is not None, feature


# ------------------------------------------------- device credential overrides


DEVICE_CREDS = {
    "device_username": "labadmin",
    "device_password": "day0-pass",
    "enable_password": "day0-enable",
}


def test_apply_device_credentials_patches_devices_only():
    data = yaml.safe_load(SAMPLE_TESTBED_YAML)
    console_module.apply_device_credentials(data, "labadmin", "day0-pass", "day0-enable")
    assert data["devices"]["R1"]["credentials"]["default"] == {
        "username": "labadmin",
        "password": "day0-pass",
    }
    assert data["devices"]["R1"]["credentials"]["enable"] == {"password": "day0-enable"}
    # The SSH proxy keeps the CML account; it is patched separately.
    assert data["devices"]["terminal_server"]["credentials"]["default"]["username"] == "change_me"


def test_apply_device_credentials_only_writes_configured_values():
    data = yaml.safe_load(SAMPLE_TESTBED_YAML)
    console_module.apply_device_credentials(data, enable_password="day0-enable")
    credentials = data["devices"]["R1"]["credentials"]
    assert credentials["default"] == {"username": "cisco", "password": "cisco"}  # untouched
    assert credentials["enable"] == {"password": "day0-enable"}


def test_apply_device_credentials_noop_when_all_unset():
    data = yaml.safe_load(SAMPLE_TESTBED_YAML)
    before = yaml.safe_dump(data)
    console_module.apply_device_credentials(data)
    assert yaml.safe_dump(data) == before  # CML's generated credentials survive verbatim


def test_apply_device_credentials_creates_missing_sections():
    data = {"devices": {"R1": {"os": "iosxe"}, "terminal_server": {}}}
    console_module.apply_device_credentials(data, "labadmin", "day0-pass", "day0-enable")
    assert data["devices"]["R1"]["credentials"] == {
        "default": {"username": "labadmin", "password": "day0-pass"},
        "enable": {"password": "day0-enable"},
    }
    assert data["devices"]["terminal_server"] == {}


@respx.mock
async def test_build_testbed_applies_device_credentials(make_settings, monkeypatch):
    mcp = build_server(
        make_settings(username="netadmin", password="s3cret", **DEVICE_CREDS)
    )
    _mock_nodes()
    _mock_testbed()
    loaded: dict = {}

    def fake_load(path: str):
        data = yaml.safe_load(Path(path).read_text())
        loaded["path"] = path
        loaded["mode"] = os.stat(path).st_mode & 0o777
        loaded["device"] = data["devices"]["R1"]["credentials"]
        loaded["proxy"] = data["devices"]["terminal_server"]["credentials"]["default"]
        return _fake_testbed("R1")

    _patch_console(
        monkeypatch, None, load=fake_load, execute=lambda device, command, timeout: "ok"
    )

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["R1"],
            "commands": ["show version"],
            "output_format": "raw",
        },
    )
    assert "ok" in text
    assert loaded["device"]["default"] == {"username": "labadmin", "password": "day0-pass"}
    assert loaded["device"]["enable"] == {"password": "day0-enable"}
    assert loaded["proxy"] == {"username": "netadmin", "password": "s3cret"}
    assert loaded["mode"] == 0o600  # secrets never hit a world-readable file
    assert not os.path.exists(loaded["path"])  # ...and the file is gone afterwards


@respx.mock
async def test_device_credentials_never_reach_the_agent(make_settings, monkeypatch):
    """Neither a success nor a console failure may echo the device secrets."""
    mcp = build_server(
        make_settings(username="netadmin", password="s3cret", **DEVICE_CREDS)
    )
    _mock_nodes(("R1", "BOOTED"), ("R2", "BOOTED"))
    _mock_testbed()

    def fake_execute(device, command, timeout_seconds):
        if device.name == "R2":
            raise RuntimeError("login failed for labadmin/day0-pass (enable day0-enable)")
        return "R1 ok"

    _patch_console(monkeypatch, _fake_testbed("R1", "R2"), execute=fake_execute)

    text = await call_tool_text(
        mcp,
        "cml_run_commands",
        {
            "lab_id": LAB_ID,
            "node_labels": ["R1", "R2"],
            "commands": ["show version"],
            "output_format": "raw",
        },
    )
    assert "console operation on node 'R2' failed (RuntimeError)" in text
    assert "CML_MCP_DEVICE_USERNAME" in text  # the recovery hint names the env vars...
    for secret in ("labadmin", "day0-pass", "day0-enable", "s3cret"):
        assert secret not in text  # ...but never their values
