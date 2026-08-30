"""Node tools end-to-end through MCPServer (schema validation included)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from cml_mcp import polling
from cml_mcp.server import build_server
from tests.conftest import BASE_URL, call_tool_text

LAB_ID = "90f84e38-a71c-4d57-8d90-00fa8a197385"
NODE_ID = "26f677f3-fcb2-47ef-9171-dc112d80b54f"
LINK_ID = "46f677f3-fcb2-47ef-9171-dc112d80b54f"
OTHER_NODE_ID = "36f677f3-fcb2-47ef-9171-dc112d80b54f"


@pytest.fixture
def instant_sleep(monkeypatch):
    """Run polling on a fake clock: sleeps return immediately but still advance
    elapsed time, so wait/timeout paths finish instantly instead of spinning."""
    clock = {"now": 0.0}

    async def _sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(polling, "asyncio", SimpleNamespace(sleep=_sleep))
    monkeypatch.setattr(polling, "time", SimpleNamespace(monotonic=lambda: clock["now"]))

NODES = [
    {
        "id": NODE_ID,
        "label": "rtr-1",
        "node_definition": "iosv",
        "state": "BOOTED",
        "cpus": 1,
        "ram": 512,
        "x": 0,
        "y": 0,
    },
    {
        "id": "36f677f3-fcb2-47ef-9171-dc112d80b54f",
        "label": "switch-1",
        "node_definition": "iosvl2",
        "state": "STOPPED",
        "cpus": None,
        "ram": None,
        "x": 100,
        "y": 0,
    },
]


# ---------------------------------------------------------------- read tools


@respx.mock
async def test_list_nodes_markdown_and_query_params(make_settings):
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_list_nodes", {"lab_id": LAB_ID})
    assert "rtr-1" in text and f"({NODE_ID})" in text
    assert "iosv" in text and "BOOTED" in text
    assert "512 MB" in text
    params = route.calls[0].request.url.params
    assert params["data"] == "true"
    assert params["operational"] == "true"
    assert params["exclude_configurations"] == "true"  # include_configurations defaults false


@respx.mock
async def test_list_nodes_json_envelope_and_client_side_paging(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_list_nodes",
        {"lab_id": LAB_ID, "limit": 1, "offset": 0, "response_format": "json"},
    )
    data = json.loads(text)
    assert data["total"] == 2
    assert data["count"] == 1
    assert data["has_more"] is True
    assert data["next_offset"] == 1
    assert data["items"][0]["label"] == "rtr-1"


@respx.mock
async def test_list_nodes_label_filter_and_include_configurations(make_settings):
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_list_nodes",
        {
            "lab_id": LAB_ID,
            "label_filter": "SWITCH",
            "include_configurations": True,
            "response_format": "json",
        },
    )
    data = json.loads(text)
    assert data["total"] == 1
    assert data["items"][0]["label"] == "switch-1"
    assert route.calls[0].request.url.params["exclude_configurations"] == "false"


@respx.mock
async def test_get_node(make_settings):
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(200, json=NODES[0])
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_get_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert json.loads(text)["label"] == "rtr-1"
    params = route.calls[0].request.url.params
    assert params["operational"] == "true"
    assert params["exclude_configurations"] == "false"  # include_configuration defaults true


@respx.mock
async def test_get_node_default_makes_no_diagnostic_probes(make_settings):
    # Default behavior must stay exactly one request for the node object.
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(200, json=NODES[0])
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_get_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert json.loads(text) == NODES[0]
    assert [c.request.url.path for c in respx.calls] == [f"/labs/{LAB_ID}/nodes/{NODE_ID}"]


def _mock_diagnostic_probes(*, condition, console=None, layer3=None):
    """Mock every include_diagnostics probe; caller varies the interesting ones."""
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(
            200, json={**NODES[0], "state": "BOOTED", "boot_progress": "Booted"}
        )
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/interfaces").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "aaaa1111-fcb2-47ef-9171-dc112d80b54f",
                    "label": "GigabitEthernet0/0",
                    "type": "physical",
                    "state": "STARTED",
                    "is_connected": True,
                    "mac_address": "52:54:00:00:00:01",
                },
                {
                    "id": "bbbb2222-fcb2-47ef-9171-dc112d80b54f",
                    "label": "GigabitEthernet0/1",
                    "type": "physical",
                    "state": "STOPPED",
                    "is_connected": False,
                    "mac_address": None,
                },
            ],
        )
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/links").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": LINK_ID,
                    "label": "rtr-1-Gi0/0<->switch-1-Gi0/1",
                    "node_a": NODE_ID,
                    "node_b": OTHER_NODE_ID,
                    "state": "STARTED",
                },
                {
                    "id": "56f677f3-fcb2-47ef-9171-dc112d80b54f",
                    "label": "unrelated-link",
                    "node_a": OTHER_NODE_ID,
                    "node_b": "66f677f3-fcb2-47ef-9171-dc112d80b54f",
                    "state": "STARTED",
                },
            ],
        )
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/links/{LINK_ID}/condition").mock(
        return_value=httpx.Response(200, json=condition)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/layer3_addresses").mock(
        return_value=layer3
        or httpx.Response(
            200,
            json={
                "name": "rtr-1",
                "interfaces": {
                    "52:54:00:00:00:01": {
                        "id": "aaaa1111-fcb2-47ef-9171-dc112d80b54f",
                        "label": "eth0",
                        "ip4": ["192.0.2.10"],
                        "ip6": [],
                    }
                },
            },
        )
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/consoles/0/log").mock(
        return_value=console or httpx.Response(200, json="last boot line\nrtr-1#")
    )
    # Sibling nodes: used only to resolve peer UUIDs to labels in the link table.
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )


@respx.mock
async def test_get_node_diagnostics_report_flags_conditioning_and_interfaces(make_settings):
    _mock_diagnostic_probes(
        condition={"bandwidth": 1000, "latency": 50, "loss": 5, "enabled": True}
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_get_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "include_diagnostics": True},
    )
    assert text.startswith(f"# Node diagnostic: rtr-1 ({NODE_ID})")
    assert "boot progress: Booted" in text
    # interface table with both problem flags
    assert "| GigabitEthernet0/0 | physical | STARTED | yes | 52:54:00:00:00:01 | - |" in text
    assert "ADMIN-DOWN" in text and "UNCONNECTED" in text
    # the impaired link is called out; the unrelated link is not in the report
    assert "CONDITIONING ACTIVE" in text
    assert "latency=50" in text and "loss=5" in text
    assert LINK_ID in text
    # The peer is named, not just a bare UUID the agent would have to look up.
    assert f"peer node: switch-1 ({OTHER_NODE_ID})" in text
    assert "unrelated-link" not in text
    assert "192.0.2.10" in text
    assert "rtr-1#" in text
    # the console probe asked for a bounded tail
    console_call = next(c for c in respx.calls if "consoles" in c.request.url.path)
    assert console_call.request.url.params["lines"] == "25"


@respx.mock
async def test_get_node_diagnostics_reports_unconditioned_links(make_settings):
    _mock_diagnostic_probes(condition={})  # CML returns {} when never conditioned
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_get_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "include_diagnostics": True},
    )
    assert "CONDITIONING ACTIVE" not in text
    assert "## Attached links" in text and LINK_ID in text


@respx.mock
async def test_get_node_diagnostics_survives_failed_probes(make_settings):
    # console log 404s on a node that never booted, L3 lookup 500s: still report.
    _mock_diagnostic_probes(
        condition={"latency": 10, "enabled": False},
        console=httpx.Response(404, json={"description": "No console log"}),
        layer3=httpx.Response(500, json={"description": "boom"}),
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(
        mcp,
        "cml_get_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "include_diagnostics": True},
    )
    assert not text.startswith("Error:")
    assert "No console output available" in text
    assert "Layer 3 addresses could not be read" in text
    assert "Conditioning configured but disabled" in text


@respx.mock
async def test_get_node_diagnostics_404_on_the_node_is_an_error(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(404, json={"description": "Node not found"})
    )
    respx.get(url__regex=rf"{BASE_URL}/labs/{LAB_ID}/.*").mock(
        return_value=httpx.Response(200, json=[])
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(
        mcp,
        "cml_get_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "include_diagnostics": True},
    )
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_node_404_returns_error_string(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(404, json={"description": "Node not found"})
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(mcp, "cml_get_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_node_interfaces(make_settings):
    interfaces = [
        {"id": "aaaa1111-fcb2-47ef-9171-dc112d80b54f", "label": "GigabitEthernet0/0",
         "node": NODE_ID, "is_connected": True, "state": "STARTED"}
    ]
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/interfaces").mock(
        return_value=httpx.Response(200, json=interfaces)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_get_node_interfaces", {"lab_id": LAB_ID, "node_id": NODE_ID}
    )
    assert json.loads(text)[0]["label"] == "GigabitEthernet0/0"
    assert route.calls[0].request.url.params["data"] == "true"


@respx.mock
async def test_get_node_layer3_addresses(make_settings):
    payload = {
        "name": "rtr-1",
        "interfaces": {"52:54:00:00:00:01": {"ip4": ["192.0.2.10"], "label": "eth0"}},
    }
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/layer3_addresses").mock(
        return_value=httpx.Response(200, json=payload)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_get_node_layer3_addresses", {"lab_id": LAB_ID, "node_id": NODE_ID}
    )
    data = json.loads(text)
    assert data["name"] == "rtr-1"
    assert "52:54:00:00:00:01" in data["interfaces"]


@respx.mock
async def test_get_node_console_log_unwraps_json_string_and_sends_lines(make_settings):
    # CML returns the log as a JSON-encoded string; the tool must unwrap it.
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/consoles/0/log").mock(
        return_value=httpx.Response(200, json="Booting...\nrtr-1 login:")
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_get_node_console_log",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "lines": 100},
    )
    assert text == "Booting...\nrtr-1 login:"
    assert route.calls[0].request.url.params["lines"] == "100"


@respx.mock
async def test_get_node_console_log_plain_text(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/consoles/1/log").mock(
        return_value=httpx.Response(200, text="plain console output")
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_get_node_console_log",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "console_id": 1},
    )
    assert text == "plain console output"


# --------------------------------------------------------------- write tools


@respx.mock
async def test_add_node_sends_only_provided_fields(make_settings):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json={"id": NODE_ID})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_add_node",
        {"lab_id": LAB_ID, "label": "rtr-1", "node_definition": "iosv", "ram": 512},
    )
    assert json.loads(text)["id"] == NODE_ID
    request = route.calls[0].request
    assert request.url.params["populate_interfaces"] == "true"
    body = json.loads(request.content)
    assert body == {"label": "rtr-1", "node_definition": "iosv", "x": 0, "y": 0, "ram": 512}


@respx.mock
async def test_add_node_optional_fields_and_populate_false(make_settings):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json={"id": NODE_ID})
    )
    mcp = build_server(make_settings(enable_writes=True))
    await call_tool_text(
        mcp,
        "cml_add_node",
        {
            "lab_id": LAB_ID,
            "label": "srv-1",
            "node_definition": "server",
            "x": 50,
            "y": -50,
            "configuration": "hostname srv-1",
            "image_definition": "server-tcl-15-0",
            "cpus": 2,
            "cpu_limit": 80,
            "tags": ["core"],
            "populate_interfaces": False,
        },
    )
    request = route.calls[0].request
    assert request.url.params["populate_interfaces"] == "false"
    body = json.loads(request.content)
    assert body["configuration"] == "hostname srv-1"
    assert body["image_definition"] == "server-tcl-15-0"
    assert body["cpus"] == 2
    assert body["cpu_limit"] == 80
    assert body["tags"] == ["core"]


@respx.mock
async def test_update_node_sends_only_provided_fields(make_settings):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(200, json=NODE_ID)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_update_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "label": "rtr-1b", "x": 25},
    )
    assert NODE_ID in text and "updated" in text
    assert json.loads(route.calls[0].request.content) == {"label": "rtr-1b", "x": 25}


async def test_update_node_no_fields_is_error_without_request(make_settings):
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_update_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert text.startswith("Error:")
    assert "at least one" in text


# ------------------------------------------- polymorphic day-0 configuration

CLOUD_INIT_FILES = [
    {"name": "user-data", "content": "#cloud-config\nhostname: srv-1\n"},
    {"name": "meta-data", "content": "instance-id: srv-1\n"},
]


@respx.mock
async def test_add_node_config_files_sent_verbatim_as_configuration(make_settings):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json={"id": NODE_ID})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_add_node",
        {
            "lab_id": LAB_ID,
            "label": "srv-1",
            "node_definition": "ubuntu",
            "config_files": CLOUD_INIT_FILES,
        },
    )
    assert json.loads(text)["id"] == NODE_ID
    body = json.loads(route.calls[0].request.content)
    # The multi-file list goes into the same polymorphic 'configuration' field.
    assert body["configuration"] == CLOUD_INIT_FILES


@respx.mock
async def test_add_node_rejects_configuration_and_config_files_together(make_settings):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json={"id": NODE_ID})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_add_node",
        {
            "lab_id": LAB_ID,
            "label": "srv-1",
            "node_definition": "ubuntu",
            "configuration": "hostname srv-1",
            "config_files": CLOUD_INIT_FILES,
        },
    )
    assert text.startswith("Error:")
    assert "not both" in text
    assert not route.called  # rejected pre-flight, nothing sent to CML


@respx.mock
@pytest.mark.parametrize(
    "config_files",
    [
        [],
        [{"name": "user-data"}],
        [{"name": "", "content": "x"}],
        [{"name": "user-data", "content": "x", "extra": "y"}],
    ],
    ids=["empty", "no-content", "empty-name", "unknown-key"],
)
async def test_add_node_rejects_malformed_config_files(make_settings, config_files):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json={"id": NODE_ID})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_add_node",
        {
            "lab_id": LAB_ID,
            "label": "srv-1",
            "node_definition": "ubuntu",
            "config_files": config_files,
        },
    )
    assert text.startswith("Error:")
    assert "config_files" in text
    assert not route.called


@respx.mock
async def test_add_node_config_files_reports_api_error(make_settings):
    respx.post(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(404, json={"description": "lab not found"})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_add_node",
        {
            "lab_id": LAB_ID,
            "label": "srv-1",
            "node_definition": "ubuntu",
            "config_files": CLOUD_INIT_FILES,
        },
    )
    assert text.startswith("Error:")


@respx.mock
async def test_update_node_config_files_replaces_file_list(make_settings):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(200, json=NODE_ID)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_update_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "config_files": CLOUD_INIT_FILES},
    )
    assert NODE_ID in text and "updated" in text
    assert json.loads(route.calls[0].request.content) == {"configuration": CLOUD_INIT_FILES}


@respx.mock
async def test_update_node_rejects_configuration_and_config_files_together(make_settings):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(200, json=NODE_ID)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_update_node",
        {
            "lab_id": LAB_ID,
            "node_id": NODE_ID,
            "configuration": "hostname rtr-1",
            "config_files": CLOUD_INIT_FILES,
        },
    )
    assert text.startswith("Error:")
    assert "not both" in text
    assert not route.called


@respx.mock
async def test_update_node_config_files_reports_api_error(make_settings):
    respx.patch(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(400, json={"description": "node is running"})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_update_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "config_files": CLOUD_INIT_FILES},
    )
    assert text.startswith("Error:")


@respx.mock
async def test_set_node_state_start_waits_for_convergence(make_settings, instant_sleep):
    start = respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/start").mock(
        return_value=httpx.Response(204)
    )
    converged = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged").mock(
        side_effect=[httpx.Response(200, json=False), httpx.Response(200, json=True)]
    )
    state = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "BOOTED", "progress": "100%"})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_set_node_state", {"lab_id": LAB_ID, "node_id": NODE_ID, "action": "start"}
    )
    assert start.called
    assert converged.call_count == 2
    assert state.call_count == 1
    data = json.loads(text)
    assert data == {
        "lab_id": LAB_ID,
        "node_id": NODE_ID,
        "action": "start",
        "converged": True,
        "elapsed_seconds": data["elapsed_seconds"],
        "state": "BOOTED",
        "progress": "100%",
    }


@respx.mock
async def test_set_node_state_start_wait_false_does_not_poll(make_settings):
    start = respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/start").mock(
        return_value=httpx.Response(204)
    )
    converged = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged").mock(
        return_value=httpx.Response(200, json=True)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_set_node_state",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "action": "start", "wait": False},
    )
    assert start.called
    assert not converged.called
    assert NODE_ID in text and "start requested" in text


@respx.mock
async def test_set_node_state_stop_waits_for_stopped(make_settings, instant_sleep):
    stop = respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/stop").mock(
        return_value=httpx.Response(204)
    )
    state = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        side_effect=[
            httpx.Response(200, json={"state": "STARTED", "progress": None}),
            httpx.Response(200, json={"state": "STOPPED", "progress": None}),
        ]
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_set_node_state", {"lab_id": LAB_ID, "node_id": NODE_ID, "action": "stop"}
    )
    assert stop.called
    assert state.call_count == 2
    data = json.loads(text)
    assert data["action"] == "stop"
    assert data["converged"] is True
    assert data["state"] == "STOPPED"
    assert "note" not in data


@respx.mock
async def test_set_node_state_stop_timeout_is_not_an_error(make_settings, instant_sleep):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/stop").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "STARTED", "progress": None})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_set_node_state",
        {
            "lab_id": LAB_ID,
            "node_id": NODE_ID,
            "action": "stop",
            "wait_timeout_seconds": 10,
        },
    )
    assert not text.startswith("Error:")
    data = json.loads(text)
    assert data["converged"] is False
    assert data["state"] == "STARTED"
    assert data["timeout_seconds"] == 10
    assert "Not converged yet" in data["note"]


@respx.mock
async def test_set_node_state_start_timeout_is_not_an_error(make_settings, instant_sleep):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/start").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged").mock(
        return_value=httpx.Response(200, json=False)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "STARTED", "progress": "booting"})
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_set_node_state",
        {
            "lab_id": LAB_ID,
            "node_id": NODE_ID,
            "action": "start",
            "wait_timeout_seconds": 10,
        },
    )
    data = json.loads(text)
    assert data["converged"] is False
    assert data["progress"] == "booting"
    assert "Not converged yet" in data["note"]


@respx.mock
async def test_set_node_state_404_returns_error_string(make_settings):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/start").mock(
        return_value=httpx.Response(404, json={"description": "Node not found"})
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(
        mcp,
        "cml_set_node_state",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "action": "start", "wait": False},
    )
    assert text.startswith("Error:")
    assert "404" in text


async def test_set_node_state_rejects_unknown_action(make_settings):
    mcp = build_server(make_settings(enable_writes=True))
    with pytest.raises(Exception, match="action"):
        await call_tool_text(
            mcp,
            "cml_set_node_state",
            {"lab_id": LAB_ID, "node_id": NODE_ID, "action": "reboot"},
        )


@respx.mock
async def test_wipe_node(make_settings):
    route = respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks").mock(
        return_value=httpx.Response(204)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_wipe_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert route.called
    assert NODE_ID in text and "wiped" in text


@respx.mock
async def test_wipe_node_400_when_running(make_settings):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks").mock(
        return_value=httpx.Response(400, json={"description": "Node is not stopped"})
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(mcp, "cml_wipe_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert text.startswith("Error:")
    assert "400" in text


@respx.mock
async def test_extract_node_configuration(make_settings):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/extract_configuration").mock(
        return_value=httpx.Response(200, json="Config extraction OK")
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_extract_node_configuration", {"lab_id": LAB_ID, "node_id": NODE_ID}
    )
    assert NODE_ID in text
    assert "Config extraction OK" in text


@respx.mock
async def test_delete_node(make_settings):
    route = respx.delete(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(204)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(mcp, "cml_delete_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert route.called
    assert text == f"Node {NODE_ID} deleted."


@respx.mock
async def test_delete_node_404_returns_error_string(make_settings):
    respx.delete(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(404)
    )
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(mcp, "cml_delete_node", {"lab_id": LAB_ID, "node_id": NODE_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_delete_node_force_waits_for_stop_then_wipes_then_deletes(
    make_settings, instant_sleep
):
    # force=true must stop, WAIT for STOPPED, wipe, then delete (stop is async).
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/stop").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        side_effect=[
            httpx.Response(200, json={"state": "STARTED", "progress": None}),
            httpx.Response(200, json={"state": "STOPPED", "progress": None}),
        ]
    )
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks").mock(
        return_value=httpx.Response(204)
    )
    respx.delete(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}").mock(
        return_value=httpx.Response(204)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp, "cml_delete_node", {"lab_id": LAB_ID, "node_id": NODE_ID, "force": True}
    )
    methods = [(c.request.method, c.request.url.path) for c in respx.calls]
    # stop, then one or more state polls, then wipe_disks, then delete — in order.
    assert methods[0] == ("PUT", f"/labs/{LAB_ID}/nodes/{NODE_ID}/state/stop")
    assert methods[-2] == ("PUT", f"/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks")
    assert methods[-1] == ("DELETE", f"/labs/{LAB_ID}/nodes/{NODE_ID}")
    assert ("GET", f"/labs/{LAB_ID}/nodes/{NODE_ID}/state") in methods
    assert methods.index(("PUT", f"/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks")) > methods.index(
        ("GET", f"/labs/{LAB_ID}/nodes/{NODE_ID}/state")
    )
    assert text == f"Node {NODE_ID} stopped, wiped, and deleted."


@respx.mock
async def test_delete_node_force_errors_if_stop_times_out(make_settings, instant_sleep):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state/stop").mock(
        return_value=httpx.Response(204)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "STARTED", "progress": None})
    )
    wipe = respx.put(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/wipe_disks").mock(
        return_value=httpx.Response(204)
    )
    mcp = build_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_delete_node",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "force": True, "stop_timeout_seconds": 5},
    )
    assert text.startswith("Error:")
    assert "did not reach a stopped state" in text
    assert not wipe.called  # never wiped or deleted a still-running node
