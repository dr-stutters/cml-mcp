"""Lab tools end-to-end through MCPServer (schema validation included).

All HTTP mocked with respx against BASE_URL (which already represents the
/api/v0 base). Writes are enabled so the full tool set registers.
"""

from __future__ import annotations

import itertools
import json
from xml.etree import ElementTree

import httpx
import pytest
import respx

from cml_mcp.server import build_server
from tests.conftest import BASE_URL, call_tool_text

LAB_ID = "90f84e38-a71c-4d57-8d90-00fa8a197385"
LAB_ID_2 = "11111111-2222-4333-8444-555555555555"
NODE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

LABS = [
    {
        "id": LAB_ID,
        "lab_title": "CCNA study lab",
        "state": "STARTED",
        "node_count": 5,
        "link_count": 4,
        "owner_username": "admin",
        "created": "2021-02-28T07:33:47+00:00",
        "modified": "2021-02-28T07:33:47+00:00",
        "effective_permissions": ["lab_admin"],
    },
    {
        "id": LAB_ID_2,
        "lab_title": "BGP transit",
        "state": "STOPPED",
        "node_count": 3,
        "link_count": 2,
        "owner_username": "student",
        "created": "2021-03-01T08:00:00+00:00",
        "modified": "2021-03-01T08:00:00+00:00",
        "effective_permissions": ["lab_admin"],
    },
    {
        "id": "22222222-3333-4444-8555-666666666666",
        "lab_title": "CCNA extra practice",
        "state": "DEFINED_ON_CORE",
        "node_count": 2,
        "link_count": 1,
        "owner_username": "admin",
        "created": "2021-03-02T09:00:00+00:00",
        "modified": "2021-03-02T09:00:00+00:00",
        "effective_permissions": ["lab_admin"],
    },
]

EVENTS = [
    {
        "lab_id": LAB_ID,
        "event": "created",
        "element_type": "lab",
        "element_id": LAB_ID,
        "data": {},
        "previous": {},
        "timestamp": "2021-02-28T07:33:47+00:00",
    },
    {
        "lab_id": LAB_ID,
        "event": "modified",
        "element_type": "node",
        "element_id": NODE_ID,
        "data": {"state": "STARTED"},
        "previous": {"state": "STOPPED"},
        "timestamp": "2021-02-28T07:35:00+00:00",
    },
    {
        "lab_id": LAB_ID,
        "event": "modified",
        "element_type": "lab",
        "element_id": LAB_ID,
        "data": {"state": "STARTED"},
        "previous": {"state": "STOPPED"},
        "timestamp": "2021-02-28T07:36:00+00:00",
    },
]


NODE_ID_2 = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
NODE_ID_3 = "cccccccc-dddd-4eee-8fff-000000000000"

SAMPLE_LAB_ID = "33333333-4444-4555-8666-777777777777"

SAMPLE_LABS = [
    {
        "id": SAMPLE_LAB_ID,
        "title": "BGP transit sample",
        "description": "Two ASes exchanging routes over eBGP.",
        "name": "cml-labs",
        "node_types": ["iosv", "alpine"],
        "file_path": "bgp/transit.yaml",
    },
    {
        "id": "44444444-5555-4666-8777-888888888888",
        "title": "OSPF single area",
        "description": "Three routers in area 0.",
        "name": "cml-labs",
        "node_types": ["iosv"],
        "file_path": "ospf/single-area.yaml",
    },
]


@pytest.fixture
def mcp(make_settings):
    return build_server(make_settings(enable_writes=True))


@pytest.fixture
def fast_clock(monkeypatch):
    """Make polling.wait_until give up after a single poll, without real sleeping.

    The fake monotonic clock jumps 6s per read, so the first elapsed check
    already exceeds a 10s budget for both the 5s (converge) and 3s (stop) poll
    intervals — the wait tools hit their timeout branch after one HTTP call.
    """
    ticks = itertools.count(0.0, 6.0)
    monkeypatch.setattr("cml_mcp.polling.time.monotonic", lambda: next(ticks))

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr("cml_mcp.polling.asyncio.sleep", _instant_sleep)


# ---------------------------------------------------------------------- reads


@respx.mock
async def test_list_labs_markdown(mcp):
    route = respx.get(f"{BASE_URL}/labs").mock(return_value=httpx.Response(200, json=LABS))
    text = await call_tool_text(mcp, "cml_list_labs", {"limit": 2, "offset": 0})
    params = route.calls[0].request.url.params
    assert params["with_data"] == "true"
    assert params["show_all"] == "false"
    assert "CCNA study lab" in text and f"({LAB_ID})" in text
    assert "state STARTED" in text
    assert "5 nodes / 4 links" in text
    assert "owner admin" in text
    assert "offset=2" in text  # has_more hint: 2 of 3 shown


@respx.mock
async def test_list_labs_json_envelope_and_title_filter(mcp):
    route = respx.get(f"{BASE_URL}/labs").mock(return_value=httpx.Response(200, json=LABS))
    text = await call_tool_text(
        mcp,
        "cml_list_labs",
        {"title_filter": "ccna", "show_all": True, "response_format": "json"},
    )
    data = json.loads(text)
    assert data["total"] == 2  # filter applied client-side: 2 of 3 labs match
    assert data["count"] == 2
    assert data["has_more"] is False
    assert data["next_offset"] is None
    assert {lab["lab_title"] for lab in data["items"]} == {
        "CCNA study lab",
        "CCNA extra practice",
    }
    params = route.calls[0].request.url.params
    assert params["show_all"] == "true"
    assert "title" not in params  # no server-side filter exists


@respx.mock
async def test_get_lab(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}").mock(return_value=httpx.Response(200, json=LABS[0]))
    text = await call_tool_text(mcp, "cml_get_lab", {"lab_id": LAB_ID})
    data = json.loads(text)
    assert data["id"] == LAB_ID
    assert data["state"] == "STARTED"


@respx.mock
async def test_get_lab_404_error_is_string(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    text = await call_tool_text(mcp, "cml_get_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_lab_topology_full_returns_raw_json(mcp):
    topology = {"nodes": [{"id": NODE_ID}], "links": [], "lab": {"version": "0.2.2"}}
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(200, json=topology)
    )
    text = await call_tool_text(
        mcp,
        "cml_get_lab_topology",
        {"lab_id": LAB_ID, "detail": "full", "exclude_configurations": True},
    )
    assert route.calls[0].request.url.params["exclude_configurations"] == "true"
    assert json.loads(text)["nodes"][0]["id"] == NODE_ID
    # detail='full' must not fetch element state — it is the raw topology only.
    assert len(respx.calls) == 1


TOPOLOGY = {
    "lab": {
        "version": "0.2.2",
        "title": "CCNA study lab",
        "description": "OSPF area 0 practice",
        "owner": "admin",
    },
    "nodes": [
        {
            "id": NODE_ID,
            "label": "r1",
            "node_definition": "iosv",
            "interfaces": [{"id": "i-a", "label": "GigabitEthernet0/0"}],
        },
        {
            "id": NODE_ID_2,
            "label": "r2",
            "node_definition": "iosv",
            "interfaces": [{"id": "i-b", "label": "GigabitEthernet0/1"}],
        },
    ],
    "links": [
        {
            "id": "link-1",
            "node_a": NODE_ID,
            "node_b": NODE_ID_2,
            "interface_a": "i-a",
            "interface_b": "i-b",
        }
    ],
    "annotations": [{"id": "ann-1", "type": "text"}],
    "smart_annotations": [],
}

ELEMENT_STATE = {
    "nodes": {NODE_ID: "BOOTED", NODE_ID_2: "STOPPED"},
    "links": {"link-1": "STARTED"},
    "interfaces": {},
}


@respx.mock
async def test_get_lab_topology_summary_merges_state_into_tables(mcp):
    topology_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(200, json=TOPOLOGY)
    )
    state_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    text = await call_tool_text(mcp, "cml_get_lab_topology", {"lab_id": LAB_ID})
    # The summary always excludes configurations, whatever the other flag says.
    assert topology_route.calls[0].request.url.params["exclude_configurations"] == "true"
    assert state_route.called
    assert "# CCNA study lab" in text and LAB_ID in text
    assert "2 nodes, 1 links, 1 annotations" in text
    # Node table carries the merged runtime state.
    assert "| r1 | iosv | BOOTED |" in text
    assert "| r2 | iosv | STOPPED |" in text
    # Link table resolves node/interface UUIDs to labels.
    assert "| r1:GigabitEthernet0/0 | r2:GigabitEthernet0/1 | STARTED |" in text
    assert "detail='full'" in text  # tells the agent how to get the raw JSON


@respx.mock
async def test_get_lab_topology_summary_404_error(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    text = await call_tool_text(mcp, "cml_get_lab_topology", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_lab_element_state(mcp):
    payload = {
        "nodes": {NODE_ID: "BOOTED"},
        "links": {},
        "interfaces": {},
    }
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=payload)
    )
    text = await call_tool_text(mcp, "cml_get_lab_element_state", {"lab_id": LAB_ID})
    assert json.loads(text)["nodes"][NODE_ID] == "BOOTED"


@respx.mock
async def test_get_lab_layer3_addresses(mcp):
    payload = {
        NODE_ID: {
            "name": "desktop-1",
            "interfaces": {"52:54:00:00:00:01": {"ip4": ["192.0.2.10"], "ip6": []}},
        }
    }
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/layer3_addresses").mock(
        return_value=httpx.Response(200, json=payload)
    )
    text = await call_tool_text(mcp, "cml_get_lab_layer3_addresses", {"lab_id": LAB_ID})
    assert json.loads(text)[NODE_ID]["name"] == "desktop-1"


# ------------------------------------------------------------- SVG rendering

SVG_TOPOLOGY = {
    "lab": {"title": "CCNA study lab", "version": "0.2.2"},
    "nodes": [
        {
            "id": NODE_ID,
            "label": "r1",
            "node_definition": "iosv",
            "x": -100,
            "y": 40,
            "interfaces": [{"id": "i-a", "label": "GigabitEthernet0/0"}],
        },
        {
            "id": NODE_ID_2,
            "label": "r2",
            "node_definition": "iosv",
            "x": 260,
            "y": 320,
            "interfaces": [{"id": "i-b", "label": "GigabitEthernet0/1"}],
        },
    ],
    "links": [
        {
            "id": "link-1",
            "node_a": NODE_ID,
            "node_b": NODE_ID_2,
            "interface_a": "i-a",
            "interface_b": "i-b",
        }
    ],
    "annotations": [],
    "smart_annotations": [],
}

L3_ADDRESSES = {
    NODE_ID: {
        "name": "r1",
        "interfaces": {"52:54:00:00:00:01": {"ip4": ["192.0.2.10"], "ip6": []}},
    }
}


def _mock_render_endpoints(topology=None, *, state=True, addresses=None):
    """Mock the three endpoints the renderer composes; returns the routes."""
    topology_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(200, json=SVG_TOPOLOGY if topology is None else topology)
    )
    state_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
        if state
        else httpx.Response(503, json={"description": "Simulation engine busy"})
    )
    address_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/layer3_addresses").mock(
        return_value=httpx.Response(200, json=addresses if addresses is not None else {})
    )
    return topology_route, state_route, address_route


@respx.mock
async def test_render_topology_svg_writes_parseable_document(mcp, tmp_path):
    topology_route, state_route, address_route = _mock_render_endpoints()
    target = tmp_path / "ccna.svg"
    text = await call_tool_text(
        mcp, "cml_render_topology_svg", {"lab_id": LAB_ID, "output_path": str(target)}
    )
    assert not text.startswith("Error:")
    assert topology_route.called and state_route.called
    assert not address_route.called  # include_addresses defaults to false

    svg = target.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    root = ElementTree.fromstring(svg)  # must be well-formed XML
    assert root.tag.endswith("svg")
    texts = [el.text for el in root.iter() if el.text]
    assert "r1" in texts and "r2" in texts  # node labels
    assert "iosv" in texts  # node definition
    assert "BOOTED" in texts and "STOPPED" in texts  # state badges
    assert "GigabitEthernet0/0" in texts  # interface label near the link end
    lines = [el for el in root.iter() if el.tag.endswith("line")]
    assert len(lines) == 1  # one link
    assert len([el for el in root.iter() if el.tag.endswith("rect")]) == 3  # bg + 2 nodes

    assert str(target) in text
    assert f"({len(target.read_bytes())} bytes)" in text
    assert "2 nodes, 1 links" in text
    assert "CML's own canvas coordinates" in text
    assert "browser" in text


@respx.mock
async def test_render_topology_svg_default_path_and_addresses(mcp, tmp_path, monkeypatch):
    monkeypatch.setattr("cml_mcp.tools.labs.tempfile.gettempdir", lambda: str(tmp_path))
    _, _, address_route = _mock_render_endpoints(addresses=L3_ADDRESSES)
    text = await call_tool_text(
        mcp, "cml_render_topology_svg", {"lab_id": LAB_ID, "include_addresses": True}
    )
    assert address_route.called
    written = tmp_path / f"cml-topology-{LAB_ID}.svg"
    assert written.exists()
    assert str(written) in text
    assert "annotated under 1 node(s)" in text
    svg = written.read_text(encoding="utf-8")
    ElementTree.fromstring(svg)
    assert "192.0.2.10" in svg


@respx.mock
async def test_render_topology_svg_survives_failed_state_and_address_probes(mcp, tmp_path):
    """The L3 probe and the state probe are best-effort: the render still happens."""
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(200, json=SVG_TOPOLOGY)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(500, json={"description": "boom"})
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/layer3_addresses").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    target = tmp_path / "degraded.svg"
    text = await call_tool_text(
        mcp,
        "cml_render_topology_svg",
        {"lab_id": LAB_ID, "output_path": str(target), "include_addresses": True},
    )
    assert not text.startswith("Error:")
    assert "Runtime state was unavailable" in text
    assert "Layer-3 addresses could not be read" in text
    svg = target.read_text(encoding="utf-8")
    assert "UNKNOWN" in [el.text for el in ElementTree.fromstring(svg).iter()]


@respx.mock
async def test_render_topology_svg_empty_lab_renders(mcp, tmp_path):
    _mock_render_endpoints({"lab": {"title": "Empty lab"}, "nodes": [], "links": []})
    target = tmp_path / "empty.svg"
    text = await call_tool_text(
        mcp, "cml_render_topology_svg", {"lab_id": LAB_ID, "output_path": str(target)}
    )
    assert not text.startswith("Error:")
    assert "0 nodes, 0 links" in text
    svg = target.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    ElementTree.fromstring(svg)  # a zero-node lab is still a valid document


@respx.mock
async def test_render_topology_svg_falls_back_to_grid_without_coordinates(mcp, tmp_path):
    """Missing/identical coordinates must not collapse every node onto one point."""
    topology = json.loads(json.dumps(SVG_TOPOLOGY))
    for node in topology["nodes"]:
        node["x"] = 0
        node["y"] = 0
    _mock_render_endpoints(topology)
    target = tmp_path / "grid.svg"
    text = await call_tool_text(
        mcp, "cml_render_topology_svg", {"lab_id": LAB_ID, "output_path": str(target)}
    )
    assert "generated grid" in text
    rects = [
        el
        for el in ElementTree.fromstring(target.read_text(encoding="utf-8")).iter()
        if el.tag.endswith("rect") and el.get("rx")
    ]
    assert len({(r.get("x"), r.get("y")) for r in rects}) == 2  # distinct positions


@respx.mock
async def test_render_topology_svg_escapes_hostile_labels(mcp, tmp_path):
    topology = json.loads(json.dumps(SVG_TOPOLOGY))
    topology["nodes"][0]["label"] = "R1 & <b>"
    topology["lab"]["title"] = 'Lab "quoted" & <script>'
    _mock_render_endpoints(topology)
    target = tmp_path / "escaped.svg"
    text = await call_tool_text(
        mcp, "cml_render_topology_svg", {"lab_id": LAB_ID, "output_path": str(target)}
    )
    assert not text.startswith("Error:")
    svg = target.read_text(encoding="utf-8")
    assert "<b>" not in svg and "<script>" not in svg
    assert "&amp;" in svg and "&lt;b&gt;" in svg
    texts = [el.text for el in ElementTree.fromstring(svg).iter() if el.text]
    assert "R1 & <b>" in texts  # escaped on the wire, intact once parsed


@respx.mock
async def test_render_topology_svg_404_error_is_string(make_settings, tmp_path):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/topology").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    text = await call_tool_text(
        mcp,
        "cml_render_topology_svg",
        {"lab_id": LAB_ID, "output_path": str(tmp_path / "nope.svg")},
    )
    assert text.startswith("Error:")
    assert "404" in text
    assert not (tmp_path / "nope.svg").exists()  # nothing written on failure


@respx.mock
async def test_get_lab_events_client_side_pagination(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/events").mock(
        return_value=httpx.Response(200, json=EVENTS)
    )
    text = await call_tool_text(
        mcp,
        "cml_get_lab_events",
        {"lab_id": LAB_ID, "limit": 2, "offset": 0, "response_format": "json"},
    )
    data = json.loads(text)
    assert data["total"] == 3
    assert data["count"] == 2
    assert data["has_more"] is True
    assert data["next_offset"] == 2
    # order preserved as returned (newest-last): first page holds oldest events
    assert data["items"][0]["event"] == "created"


@respx.mock
async def test_get_lab_simulation_stats(mcp):
    payload = {"nodes": {NODE_ID: {"cpu": {"percent": 12.5}}}, "links": {}}
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/simulation_stats").mock(
        return_value=httpx.Response(200, json=payload)
    )
    text = await call_tool_text(mcp, "cml_get_lab_simulation_stats", {"lab_id": LAB_ID})
    assert json.loads(text)["nodes"][NODE_ID]["cpu"]["percent"] == 12.5


@respx.mock
async def test_export_lab_unwraps_json_encoded_yaml(mcp):
    yaml_text = "lab:\n  title: CCNA study lab\nnodes: []\nlinks: []\n"
    # CML may return the YAML as a JSON-encoded string; the tool must unwrap it.
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/download").mock(
        return_value=httpx.Response(200, json=yaml_text)
    )
    text = await call_tool_text(mcp, "cml_export_lab", {"lab_id": LAB_ID})
    assert text == yaml_text


@respx.mock
async def test_get_pyats_testbed_plain_text(mcp):
    yaml_text = "devices:\n  r1:\n    os: iosxe\ntestbed:\n  name: CCNA study lab\n"
    route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/pyats_testbed").mock(
        return_value=httpx.Response(
            200, text=yaml_text, headers={"Content-Type": "application/yaml"}
        )
    )
    text = await call_tool_text(
        mcp, "cml_get_pyats_testbed", {"lab_id": LAB_ID, "hostname": "cml.example.com"}
    )
    assert text == yaml_text
    assert route.calls[0].request.url.params["hostname"] == "cml.example.com"


# --------------------------------------------------------------------- writes


@respx.mock
async def test_create_lab_sends_only_provided_fields(mcp):
    route = respx.post(f"{BASE_URL}/labs").mock(
        return_value=httpx.Response(200, json=LABS[0])
    )
    text = await call_tool_text(
        mcp, "cml_create_lab", {"title": "CCNA study lab", "description": "OSPF practice"}
    )
    assert json.loads(text)["id"] == LAB_ID
    body = json.loads(route.calls[0].request.content)
    assert body == {"title": "CCNA study lab", "description": "OSPF practice"}


@respx.mock
async def test_update_lab_sends_only_provided_fields(mcp):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}").mock(
        return_value=httpx.Response(200, json=LABS[0])
    )
    text = await call_tool_text(
        mcp, "cml_update_lab", {"lab_id": LAB_ID, "notes": "Check R1-R2 adjacency"}
    )
    assert json.loads(text)["id"] == LAB_ID
    assert json.loads(route.calls[0].request.content) == {"notes": "Check R1-R2 adjacency"}


@respx.mock
async def test_update_lab_without_fields_is_error_without_request(mcp):
    text = await call_tool_text(mcp, "cml_update_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "at least one" in text
    assert not respx.calls  # nothing was sent to the platform


@respx.mock
async def test_import_lab_sends_parsed_topology_object(mcp):
    yaml_text = "lab:\n  version: 0.2.2\nnodes: []\nlinks: []\n"
    route = respx.post(f"{BASE_URL}/import").mock(
        return_value=httpx.Response(200, json={"id": LAB_ID, "warnings": []})
    )
    text = await call_tool_text(
        mcp,
        "cml_import_lab",
        {"topology_yaml": yaml_text, "title": "Imported CCNA lab"},
    )
    data = json.loads(text)
    assert data["id"] == LAB_ID
    request = route.calls[0].request
    assert request.url.params["title"] == "Imported CCNA lab"
    # The YAML is parsed client-side and sent as the JSON topology object.
    body = json.loads(request.content)
    assert body["lab"]["version"] == "0.2.2"
    assert body["nodes"] == [] and body["links"] == []


@respx.mock
async def test_import_lab_rejects_non_mapping_input(mcp):
    text = await call_tool_text(
        mcp, "cml_import_lab", {"topology_yaml": "just a plain sentence"}
    )
    assert text.startswith("Error:")
    assert "mapping" in text
    assert not respx.calls  # nothing was sent to the platform


@respx.mock
async def test_start_lab_without_wait_is_fire_and_forget(mcp):
    route = respx.put(f"{BASE_URL}/labs/{LAB_ID}/start").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_start_lab", {"lab_id": LAB_ID, "wait": False})
    assert route.called
    assert not text.startswith("Error:")
    assert LAB_ID in text and "start" in text.lower()
    assert len(respx.calls) == 1  # no polling at all


@respx.mock
async def test_start_lab_waits_for_convergence_and_reports_states(mcp):
    start = respx.put(f"{BASE_URL}/labs/{LAB_ID}/start").mock(
        return_value=httpx.Response(204)
    )
    converged = respx.get(f"{BASE_URL}/labs/{LAB_ID}/check_if_converged").mock(
        return_value=httpx.Response(200, json=True)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    text = await call_tool_text(mcp, "cml_start_lab", {"lab_id": LAB_ID})
    assert start.called and converged.called
    data = json.loads(text)
    assert data["lab_id"] == LAB_ID
    assert data["converged"] is True
    assert data["node_states"][NODE_ID] == "BOOTED"
    assert "note" not in data
    # Start first, then poll for convergence.
    assert respx.calls[0].request.method == "PUT"


@respx.mock
async def test_start_lab_timeout_is_not_an_error(mcp, fast_clock):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/start").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/check_if_converged").mock(
        return_value=httpx.Response(200, json=False)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    text = await call_tool_text(
        mcp, "cml_start_lab", {"lab_id": LAB_ID, "wait_timeout_seconds": 10}
    )
    assert not text.startswith("Error:")
    data = json.loads(text)
    assert data["converged"] is False
    assert data["timeout_seconds"] == 10
    assert "NOT an API failure" in data["note"]
    assert data["node_states"][NODE_ID_2] == "STOPPED"


@respx.mock
async def test_start_lab_error_is_string(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/start").mock(
        return_value=httpx.Response(400, json={"description": "Insufficient resources"})
    )
    text = await call_tool_text(mcp, "cml_start_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "400" in text
    assert len(respx.calls) == 1  # never polled after a failed start


@respx.mock
async def test_stop_lab_without_wait_is_fire_and_forget(mcp):
    route = respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_stop_lab", {"lab_id": LAB_ID, "wait": False})
    assert route.called
    assert not text.startswith("Error:")
    assert LAB_ID in text and "stop" in text.lower()
    assert len(respx.calls) == 1


@respx.mock
async def test_stop_lab_waits_for_stopped_state(mcp):
    stop = respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(
        return_value=httpx.Response(204)
    )
    state = respx.get(f"{BASE_URL}/labs/{LAB_ID}/state").mock(
        return_value=httpx.Response(200, json="STOPPED")
    )
    text = await call_tool_text(mcp, "cml_stop_lab", {"lab_id": LAB_ID})
    assert stop.called and state.called
    data = json.loads(text)
    assert data["lab_id"] == LAB_ID
    assert data["stopped"] is True
    assert data["state"] == "STOPPED"
    assert "note" not in data


@respx.mock
async def test_stop_lab_timeout_is_not_an_error(mcp, fast_clock):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/state").mock(
        return_value=httpx.Response(200, json="STARTED")
    )
    text = await call_tool_text(
        mcp, "cml_stop_lab", {"lab_id": LAB_ID, "wait_timeout_seconds": 10}
    )
    assert not text.startswith("Error:")
    data = json.loads(text)
    assert data["stopped"] is False
    assert data["state"] == "STARTED"
    assert data["timeout_seconds"] == 10
    assert "NOT an API failure" in data["note"]


@respx.mock
async def test_stop_lab_error_is_string(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    text = await call_tool_text(mcp, "cml_stop_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_wipe_lab(mcp):
    route = respx.put(f"{BASE_URL}/labs/{LAB_ID}/wipe").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_wipe_lab", {"lab_id": LAB_ID})
    assert route.called
    assert not text.startswith("Error:")
    assert LAB_ID in text and "wiped" in text


@respx.mock
async def test_wipe_lab_running_lab_error(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/wipe").mock(
        return_value=httpx.Response(
            400, json={"description": "Lab must be stopped before wiping"}
        )
    )
    text = await call_tool_text(mcp, "cml_wipe_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "400" in text
    assert "stopped" in text


@respx.mock
async def test_delete_lab(mcp):
    route = respx.delete(f"{BASE_URL}/labs/{LAB_ID}").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_delete_lab", {"lab_id": LAB_ID})
    assert route.called
    assert text == f"Lab {LAB_ID} deleted."


@respx.mock
async def test_delete_lab_force_waits_for_stop_then_wipes_then_deletes(mcp):
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/state").mock(
        side_effect=[
            httpx.Response(200, json="STARTED"),
            httpx.Response(200, json="STOPPED"),
        ]
    )
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/wipe").mock(return_value=httpx.Response(204))
    respx.delete(f"{BASE_URL}/labs/{LAB_ID}").mock(return_value=httpx.Response(204))
    text = await call_tool_text(mcp, "cml_delete_lab", {"lab_id": LAB_ID, "force": True})
    assert not text.startswith("Error:")
    assert "deleted" in text
    # Stop, WAIT for STOPPED (async stop), wipe, then delete — in that order.
    methods = [(call.request.method, call.request.url.path) for call in respx.calls]
    assert methods[0] == ("PUT", f"/labs/{LAB_ID}/stop")
    assert methods[-2] == ("PUT", f"/labs/{LAB_ID}/wipe")
    assert methods[-1] == ("DELETE", f"/labs/{LAB_ID}")
    assert ("GET", f"/labs/{LAB_ID}/state") in methods
    assert methods.index(("PUT", f"/labs/{LAB_ID}/wipe")) > methods.index(
        ("GET", f"/labs/{LAB_ID}/state")
    )


@respx.mock
async def test_delete_lab_force_errors_if_stop_times_out(mcp, monkeypatch):
    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr("cml_mcp.polling.asyncio.sleep", _instant_sleep)
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/stop").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/state").mock(
        return_value=httpx.Response(200, json="STARTED")
    )
    wipe = respx.put(f"{BASE_URL}/labs/{LAB_ID}/wipe").mock(return_value=httpx.Response(204))
    text = await call_tool_text(
        mcp, "cml_delete_lab", {"lab_id": LAB_ID, "force": True, "stop_timeout_seconds": 5}
    )
    assert text.startswith("Error:")
    assert "did not reach a stopped state" in text
    assert not wipe.called  # never wiped/deleted a lab still shutting down


# ------------------------------------------------------- clone and annotations

ANNOTATION_ID = "90f84e38-a71c-4d57-8d90-00fa8a197399"

ANNOTATIONS = [
    {
        "id": ANNOTATION_ID,
        "type": "text",
        "text_content": "Core layer",
        "x1": 100.0,
        "y1": 200.0,
        "rotation": 0,
        "z_index": 0,
    },
    {
        "id": "aaaaaaaa-bbbb-4ccc-8ddd-ffffffffffff",
        "type": "rectangle",
        "x1": 0.0,
        "y1": 0.0,
        "x2": 250.0,
        "y2": 150.0,
        "rotation": 0,
        "z_index": 0,
    },
]


@respx.mock
async def test_clone_lab_default_title_exports_then_imports(mcp):
    yaml_text = "lab:\n  version: 0.2.2\nnodes: []\nlinks: []\n"
    get_lab = respx.get(f"{BASE_URL}/labs/{LAB_ID}").mock(
        return_value=httpx.Response(200, json=LABS[0])
    )
    download = respx.get(f"{BASE_URL}/labs/{LAB_ID}/download").mock(
        return_value=httpx.Response(200, json=yaml_text)
    )
    import_route = respx.post(f"{BASE_URL}/import").mock(
        return_value=httpx.Response(200, json={"id": LAB_ID_2, "warnings": []})
    )
    text = await call_tool_text(mcp, "cml_clone_lab", {"lab_id": LAB_ID})
    assert json.loads(text)["id"] == LAB_ID_2
    assert get_lab.called and download.called
    request = import_route.calls[0].request
    # Default title comes from the source lab's metadata.
    assert request.url.params["title"] == "Copy of CCNA study lab"
    # The exported YAML is parsed client-side and sent as the JSON topology.
    body = json.loads(request.content)
    assert body["lab"]["version"] == "0.2.2"
    assert body["nodes"] == [] and body["links"] == []


@respx.mock
async def test_clone_lab_rejects_non_mapping_export(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/download").mock(
        return_value=httpx.Response(200, json="just a plain sentence")
    )
    text = await call_tool_text(
        mcp, "cml_clone_lab", {"lab_id": LAB_ID, "new_title": "Broken clone"}
    )
    assert text.startswith("Error:")
    assert "mapping" in text
    # No import was attempted with the bad payload.
    assert not any(call.request.method == "POST" for call in respx.calls)


@respx.mock
async def test_list_annotations_markdown(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/annotations").mock(
        return_value=httpx.Response(200, json=ANNOTATIONS)
    )
    text = await call_tool_text(mcp, "cml_list_annotations", {"lab_id": LAB_ID})
    assert "**text**" in text and f"({ANNOTATION_ID})" in text
    assert '"Core layer"' in text  # text content shown for text annotations
    assert "**rectangle**" in text


@respx.mock
async def test_add_annotation_text_builds_full_body(mcp):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/annotations").mock(
        return_value=httpx.Response(200, json=ANNOTATIONS[0])
    )
    text = await call_tool_text(
        mcp,
        "cml_add_annotation",
        {
            "lab_id": LAB_ID,
            "annotation_type": "text",
            "x1": 100,
            "y1": 200,
            "text_content": "Core layer",
        },
    )
    assert json.loads(text)["id"] == ANNOTATION_ID
    body = json.loads(route.calls[0].request.content)
    assert body["type"] == "text"
    assert body["text_content"] == "Core layer"
    assert body["x1"] == 100 and body["y1"] == 200
    # Spec-required fields the tool fills with defaults.
    assert body["text_unit"] == "pt" and body["text_size"] == 12
    assert body["border_style"] == "" and body["z_index"] == 0
    assert "x2" not in body  # not part of the text annotation schema


@respx.mock
async def test_add_annotation_line_omits_rotation(mcp):
    route = respx.post(f"{BASE_URL}/labs/{LAB_ID}/annotations").mock(
        return_value=httpx.Response(200, json={"id": ANNOTATION_ID, "type": "line"})
    )
    text = await call_tool_text(
        mcp,
        "cml_add_annotation",
        {
            "lab_id": LAB_ID,
            "annotation_type": "line",
            "x1": 0,
            "y1": 0,
            "x2": 50,
            "y2": 60,
            "rotation": 45,  # not supported for lines; must be ignored
        },
    )
    assert json.loads(text)["type"] == "line"
    body = json.loads(route.calls[0].request.content)
    assert body["type"] == "line"
    assert body["x2"] == 50 and body["y2"] == 60
    assert "rotation" not in body  # line annotations have no rotation field
    assert body["line_start"] is None and body["line_end"] is None


@respx.mock
async def test_add_annotation_text_without_content_is_error_without_request(mcp):
    text = await call_tool_text(
        mcp,
        "cml_add_annotation",
        {"lab_id": LAB_ID, "annotation_type": "text", "x1": 0, "y1": 0},
    )
    assert text.startswith("Error:")
    assert "text_content" in text
    assert not respx.calls  # nothing was sent to the platform


@respx.mock
async def test_delete_annotation(mcp):
    route = respx.delete(f"{BASE_URL}/labs/{LAB_ID}/annotations/{ANNOTATION_ID}").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(
        mcp,
        "cml_delete_annotation",
        {"lab_id": LAB_ID, "annotation_id": ANNOTATION_ID},
    )
    assert route.called
    assert not text.startswith("Error:")
    assert ANNOTATION_ID in text and "deleted" in text


# ------------------------------------------------------------- sample labs


@respx.mock
async def test_list_sample_labs_markdown_table(mcp):
    respx.get(f"{BASE_URL}/sample/labs").mock(
        return_value=httpx.Response(200, json=SAMPLE_LABS)
    )
    text = await call_tool_text(mcp, "cml_list_sample_labs", {})
    assert "| Title | Sample lab ID | Node types | Description |" in text
    assert f"| BGP transit sample | {SAMPLE_LAB_ID} | iosv, alpine |" in text
    assert "Two ASes exchanging routes over eBGP." in text
    assert "cml_load_sample_lab" in text  # chains to the loader


@respx.mock
async def test_list_sample_labs_json_envelope_paginates(mcp):
    respx.get(f"{BASE_URL}/sample/labs").mock(
        return_value=httpx.Response(200, json=SAMPLE_LABS)
    )
    text = await call_tool_text(
        mcp, "cml_list_sample_labs", {"limit": 1, "offset": 0, "response_format": "json"}
    )
    data = json.loads(text)
    assert data["total"] == 2 and data["count"] == 1
    assert data["has_more"] is True and data["next_offset"] == 1
    assert data["items"][0]["id"] == SAMPLE_LAB_ID


@respx.mock
async def test_list_sample_labs_error_is_string(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/sample/labs").mock(
        return_value=httpx.Response(404, json={"description": "No sample labs"})
    )
    text = await call_tool_text(mcp, "cml_list_sample_labs", {})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_load_sample_lab_returns_new_lab(mcp):
    route = respx.put(f"{BASE_URL}/sample/labs/{SAMPLE_LAB_ID}").mock(
        return_value=httpx.Response(200, json=LABS[0])
    )
    text = await call_tool_text(
        mcp, "cml_load_sample_lab", {"sample_lab_id": SAMPLE_LAB_ID}
    )
    assert route.called
    assert json.loads(text)["id"] == LAB_ID


@respx.mock
async def test_load_sample_lab_404_error(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.put(f"{BASE_URL}/sample/labs/{SAMPLE_LAB_ID}").mock(
        return_value=httpx.Response(404, json={"description": "Sample lab not found"})
    )
    text = await call_tool_text(
        mcp, "cml_load_sample_lab", {"sample_lab_id": SAMPLE_LAB_ID}
    )
    assert text.startswith("Error:")
    assert "404" in text


# ---------------------------------------------------------------- bootstrap


@respx.mock
async def test_bootstrap_lab(mcp):
    route = respx.put(f"{BASE_URL}/labs/{LAB_ID}/bootstrap").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_bootstrap_lab", {"lab_id": LAB_ID})
    assert route.called
    assert not text.startswith("Error:")
    assert LAB_ID in text and "day-0" in text


@respx.mock
async def test_bootstrap_lab_error_is_string(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.put(f"{BASE_URL}/labs/{LAB_ID}/bootstrap").mock(
        return_value=httpx.Response(400, json={"description": "Lab is running"})
    )
    text = await call_tool_text(mcp, "cml_bootstrap_lab", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "400" in text


# --------------------------------------------------------- snapshot/restore

SNAPSHOT_NODES = [
    {"id": NODE_ID, "label": "r1", "state": "BOOTED", "node_definition": "iosv"},
    {"id": NODE_ID_2, "label": "r2", "state": "STOPPED", "node_definition": "iosv"},
    {"id": NODE_ID_3, "label": "r3", "state": "BOOTED", "node_definition": "iosv"},
]

SNAPSHOT_YAML = "lab:\n  version: 0.2.2\n  title: CCNA study lab\nnodes: []\nlinks: []\n"


def _mock_snapshot_endpoints():
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(200, json=SNAPSHOT_NODES)
    )
    extract_ok = respx.put(
        f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/extract_configuration"
    ).mock(return_value=httpx.Response(200, json="ok"))
    # A per-node failure must not abort the snapshot.
    extract_fail = respx.put(
        f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID_3}/extract_configuration"
    ).mock(return_value=httpx.Response(404, json={"description": "Node not found"}))
    extract_skipped = respx.put(
        f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID_2}/extract_configuration"
    ).mock(return_value=httpx.Response(200, json="ok"))
    download = respx.get(f"{BASE_URL}/labs/{LAB_ID}/download").mock(
        return_value=httpx.Response(200, json=SNAPSHOT_YAML)
    )
    return extract_ok, extract_fail, extract_skipped, download


@respx.mock
async def test_snapshot_lab_writes_file_and_reports_per_node(mcp, tmp_path):
    extract_ok, extract_fail, extract_skipped, download = _mock_snapshot_endpoints()
    target = tmp_path / "ccna-lab.yaml"
    text = await call_tool_text(
        mcp, "cml_snapshot_lab", {"lab_id": LAB_ID, "output_path": str(target)}
    )
    assert not text.startswith("Error:")
    assert extract_ok.called and extract_fail.called and download.called
    assert not extract_skipped.called  # r2 is not BOOTED, so nothing was extracted
    assert target.read_text(encoding="utf-8") == SNAPSHOT_YAML
    assert str(target) in text
    assert "| r1 | BOOTED | extracted |" in text
    assert "| r2 | STOPPED | skipped |" in text
    assert "| r3 | BOOTED | failed |" in text
    assert "extracted from 1 of 3 nodes" in text
    assert "cml_restore_lab" in text


@respx.mock
async def test_snapshot_lab_default_path_uses_temp_dir(mcp, tmp_path, monkeypatch):
    monkeypatch.setattr("cml_mcp.tools.labs.tempfile.gettempdir", lambda: str(tmp_path))
    _mock_snapshot_endpoints()
    text = await call_tool_text(mcp, "cml_snapshot_lab", {"lab_id": LAB_ID})
    written = list(tmp_path.glob(f"cml-snapshot-{LAB_ID}-*.yaml"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == SNAPSHOT_YAML
    assert str(written[0]) in text


@respx.mock
async def test_snapshot_lab_404_error_is_string(make_settings, tmp_path):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    text = await call_tool_text(
        mcp,
        "cml_snapshot_lab",
        {"lab_id": LAB_ID, "output_path": str(tmp_path / "nope.yaml")},
    )
    assert text.startswith("Error:")
    assert "404" in text
    assert not (tmp_path / "nope.yaml").exists()  # nothing written on failure


@respx.mock
async def test_restore_lab_imports_snapshot_file(mcp, tmp_path):
    snapshot = tmp_path / "snap.yaml"
    snapshot.write_text(SNAPSHOT_YAML, encoding="utf-8")
    route = respx.post(f"{BASE_URL}/import").mock(
        return_value=httpx.Response(200, json={"id": LAB_ID_2, "warnings": []})
    )
    text = await call_tool_text(
        mcp,
        "cml_restore_lab",
        {"snapshot_path": str(snapshot), "title": "CCNA lab restored"},
    )
    assert json.loads(text)["id"] == LAB_ID_2
    request = route.calls[0].request
    assert request.url.params["title"] == "CCNA lab restored"
    body = json.loads(request.content)
    assert body["lab"]["version"] == "0.2.2"


@respx.mock
async def test_restore_lab_missing_file_is_error_without_request(mcp, tmp_path):
    text = await call_tool_text(
        mcp, "cml_restore_lab", {"snapshot_path": str(tmp_path / "absent.yaml")}
    )
    assert text.startswith("Error:")
    assert "no snapshot file" in text
    assert not respx.calls  # nothing was sent to the platform


@respx.mock
async def test_restore_lab_rejects_non_mapping_file(mcp, tmp_path):
    snapshot = tmp_path / "snap.yaml"
    snapshot.write_text("just a plain sentence", encoding="utf-8")
    text = await call_tool_text(mcp, "cml_restore_lab", {"snapshot_path": str(snapshot)})
    assert text.startswith("Error:")
    assert "mapping" in text
    assert not respx.calls


# ------------------------------------------------------------- associations

ASSOCIATIONS = {
    "groups": [{"id": "55555555-6666-4777-8888-999999999999", "permissions": ["lab_exec"]}],
    "users": [{"id": "66666666-7777-4888-8999-aaaaaaaaaaaa", "permissions": ["lab_view"]}],
}


@respx.mock
async def test_get_lab_associations(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/associations").mock(
        return_value=httpx.Response(200, json=ASSOCIATIONS)
    )
    text = await call_tool_text(mcp, "cml_get_lab_associations", {"lab_id": LAB_ID})
    data = json.loads(text)
    assert data["groups"][0]["permissions"] == ["lab_exec"]
    assert data["users"][0]["permissions"] == ["lab_view"]


@respx.mock
async def test_get_lab_associations_404_error(make_settings):
    mcp = build_server(make_settings(enable_writes=True, max_retries=0))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/associations").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    text = await call_tool_text(mcp, "cml_get_lab_associations", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_set_lab_associations_sends_only_provided_sides(mcp):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}/associations").mock(
        return_value=httpx.Response(200, json=ASSOCIATIONS)
    )
    text = await call_tool_text(
        mcp,
        "cml_set_lab_associations",
        {"lab_id": LAB_ID, "groups": ASSOCIATIONS["groups"]},
    )
    assert json.loads(text)["groups"][0]["permissions"] == ["lab_exec"]
    body = json.loads(route.calls[0].request.content)
    assert body == {"groups": ASSOCIATIONS["groups"]}  # users left untouched


@respx.mock
async def test_set_lab_associations_empty_list_revokes(mcp):
    route = respx.patch(f"{BASE_URL}/labs/{LAB_ID}/associations").mock(
        return_value=httpx.Response(200, json={"groups": [], "users": []})
    )
    text = await call_tool_text(
        mcp, "cml_set_lab_associations", {"lab_id": LAB_ID, "users": []}
    )
    assert json.loads(text)["users"] == []
    assert json.loads(route.calls[0].request.content) == {"users": []}


@respx.mock
async def test_set_lab_associations_without_fields_is_error_without_request(mcp):
    text = await call_tool_text(mcp, "cml_set_lab_associations", {"lab_id": LAB_ID})
    assert text.startswith("Error:")
    assert "Nothing to update" in text
    assert not respx.calls
