"""CML-free unit tests for the labspec (topology-as-code) module.

Pure functions are hit directly; the build/validate/export tools run through a
FastMCP server against httpx.MockTransport. Run: `uv run pytest`.
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from cml_mcp.client import CMLClient
from cml_mcp.config import Settings
from cml_mcp.tools import labspec
from cml_mcp.tools.labspec import (
    LabSpecError,
    match_interface,
    parse_spec,
    render_briefs,
    spec_from_topology,
)


def run(coro):
    return asyncio.run(coro)


def _settings() -> Settings:
    return Settings(base_url="https://cml.example.com", username="a", password="b",
                    verify_ssl=False, timeout=5)


def _client(handler) -> CMLClient:
    c = CMLClient(_settings())
    c._http = httpx.AsyncClient(base_url=c.settings.api_url,
                                transport=httpx.MockTransport(handler))
    c._token = "testtoken"
    return c


MINIMAL = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes:
  R1:
  R2: {config: "hostname R2"}
links:
  - R1 -- R2
"""


# ---------------------------------------------------------------------------
# parse_spec
# ---------------------------------------------------------------------------

def test_parse_minimal_with_defaults():
    plan = parse_spec(MINIMAL)
    assert [n.label for n in plan.nodes] == ["R1", "R2"]
    assert all(n.definition == "iol-xe" for n in plan.nodes)
    assert plan.nodes[1].config == "hostname R2"
    # auto layout filled in
    assert all(n.x is not None and n.y is not None for n in plan.nodes)


def test_parse_accumulates_errors():
    bad = """
nodes:
  R1: {definition: iol-xe}
links:
  - R1 -- NOPE
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(bad)
    msgs = "\n".join(ei.value.errors)
    assert "lab.title" in msgs and "unknown node 'NOPE'" in msgs


def test_parse_rejects_duplicate_node_label():
    dup = """
lab: {title: T}
nodes:
  R1: {definition: iol-xe}
  R1: {definition: iosv}
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(dup)
    assert "duplicate" in ei.value.errors[0]


def test_parse_node_needs_definition_and_xy_pair():
    bad = """
lab: {title: T}
nodes:
  R1: {x: 5}
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(bad)
    msgs = "\n".join(ei.value.errors)
    assert "definition is required" in msgs and "x and y must be given together" in msgs


def test_config_json_serialized_and_mutual_exclusion():
    spec = """
lab: {title: T}
nodes:
  FTD-1:
    definition: ftdv
    config_json: {EULA: accept, AdminPassword: "x", ManageLocally: "Yes"}
"""
    plan = parse_spec(spec)
    assert json.loads(plan.nodes[0].config) == {
        "EULA": "accept", "AdminPassword": "x", "ManageLocally": "Yes"}
    both = """
lab: {title: T}
nodes:
  R1: {definition: iol-xe, config: "a", config_json: {b: 1}}
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(both)
    assert "exactly one of" in ei.value.errors[0]


def test_config_files_and_ftdv_day0_required():
    spec = """
lab: {title: T}
nodes:
  AP-1:
    definition: wireless-ap
    config_files:
      - {name: user-data, content: "#cloud-config"}
      - {name: network-config, content: "net"}
"""
    plan = parse_spec(spec)
    assert plan.nodes[0].config == [
        {"name": "user-data", "content": "#cloud-config"},
        {"name": "network-config", "content": "net"}]
    with pytest.raises(LabSpecError) as ei:
        parse_spec("lab: {title: T}\nnodes:\n  F: {definition: ftdv}\n")
    assert "requires a day-0 JSON document" in ei.value.errors[0]


def test_link_grammar_forms():
    spec = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes: {R1: , R2: , R3: }
links:
  - R1:Ethernet0/1 -- R2:e0/1
  - R2 -- R3
  - {a: "R1:e0/2", b: {node: R3, interface: Ethernet0/2}}
"""
    plan = parse_spec(spec)
    assert plan.links[0].a.interface == "Ethernet0/1"
    assert plan.links[1].a.interface is None and plan.links[1].b.interface is None
    assert plan.links[2].b.node == "R3" and plan.links[2].b.interface == "Ethernet0/2"
    with pytest.raises(LabSpecError) as ei:
        parse_spec("lab: {title: T}\nnodes: {R1: {definition: iol-xe}}\nlinks: [\"R1--R1\"]\n")
    assert "spaces around --" in ei.value.errors[0]


def test_external_connector_single_port_rule():
    spec = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes:
  R1:
  R2:
  EXT: {definition: external_connector, config: System Bridge}
links:
  - R1 -- EXT
  - R2 -- EXT
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(spec)
    assert "single-port device" in ei.value.errors[0]


def test_groups_disjoint_and_warnings():
    overlap = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes: {R1: , R2: }
groups:
  g1: {agent: catalyst-engineer, nodes: [R1], tasks: t}
  g2: {agent: catalyst-engineer, nodes: [R1], tasks: t}
"""
    with pytest.raises(LabSpecError) as ei:
        parse_spec(overlap)
    assert "must be disjoint" in "\n".join(ei.value.errors)
    ok = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes: {R1: , R2: }
groups:
  g1: {agent: catalyst-engineer, nodes: [R1]}
"""
    plan = parse_spec(ok)
    joined = "\n".join(plan.warnings)
    assert "no tasks given" in joined and "not covered by any group" in joined and "R2" in joined


def test_auto_layout_mixed_explicit():
    spec = """
lab: {title: T}
defaults: {definition: iol-xe}
nodes:
  A: {x: 500, y: 100}
  B:
  C:
"""
    plan = parse_spec(spec)
    by = {n.label: n for n in plan.nodes}
    assert (by["A"].x, by["A"].y) == (500, 100)
    assert by["B"].y >= 300 and by["C"].y >= 300  # placed below the explicit row


# ---------------------------------------------------------------------------
# interface matcher
# ---------------------------------------------------------------------------

_IFACES = [
    {"id": "i1", "label": "GigabitEthernet0/1", "type": "physical", "is_connected": False},
    {"id": "i2", "label": "GigabitEthernet0/2", "type": "physical", "is_connected": False},
    {"id": "i3", "label": "Loopback0", "type": "loopback", "is_connected": False},
]


def test_matcher_exact_and_abbreviation():
    assert match_interface("GigabitEthernet0/1", _IFACES, "R1")["id"] == "i1"
    assert match_interface("gi0/2", _IFACES, "R1")["id"] == "i2"
    assert match_interface("G0/1", _IFACES, "R1")["id"] == "i1"


def test_matcher_no_numeric_normalization_and_loopback_excluded():
    assert match_interface("Gi0/01", _IFACES, "R1") is None  # tails compared as strings
    assert match_interface("Loopback0", _IFACES, "R1") is None  # physical only


def test_matcher_ambiguous_raises():
    ifaces = [
        {"id": "a", "label": "GigabitEthernet1", "type": "physical"},
        {"id": "b", "label": "GigE1", "type": "physical"},
    ]
    with pytest.raises(ValueError) as ei:
        match_interface("g1", ifaces, "R1")
    assert "ambiguous" in str(ei.value)


def test_matcher_linux_names():
    ifaces = [{"id": "e", "label": "ens2", "type": "physical"},
              {"id": "p", "label": "port", "type": "physical"}]
    assert match_interface("ens2", ifaces, "AP")["id"] == "e"
    assert match_interface("port", ifaces, "EXT")["id"] == "p"


# ---------------------------------------------------------------------------
# briefs
# ---------------------------------------------------------------------------

def test_brief_format_matches_architect_contract():
    plan = parse_spec("""
lab: {title: T}
defaults: {definition: ioll2-xe}
nodes: {SW1: , R1: {definition: iol-xe}}
links: [SW1 -- R1]
groups:
  access:
    agent: catalyst-engineer
    nodes: [SW1]
    addressing: "SW1 Vlan10 10.0.10.1/24"
    tasks: "trunk to R1"
    acceptance: "ping 10.0.10.2"
""")
    link_report = [{"spec": "SW1 -- R1",
                    "a": {"node": "SW1", "interface": "GigabitEthernet0/1"},
                    "b": {"node": "R1", "interface": "Ethernet0/1"}}]
    brief = render_briefs(plan, "LAB1", link_report, started=False)[0]
    assert brief.splitlines() == [
        "### Brief: access -> catalyst-engineer",
        "lab_id: LAB1",
        "state: built, not started",
        "nodes: SW1 (ioll2-xe)",
        "links: SW1 GigabitEthernet0/1 <-> R1 Ethernet0/1",
        "addressing: SW1 Vlan10 10.0.10.1/24",
        "tasks: trunk to R1",
        "acceptance: ping 10.0.10.2",
    ]


# ---------------------------------------------------------------------------
# export (spec_from_topology) + round-trip
# ---------------------------------------------------------------------------

_TOPOLOGY = {
    "lab": {"title": "Exported", "description": "d", "notes": ""},
    "nodes": [
        {"id": "n1", "label": "R1", "node_definition": "iol-xe", "x": 0, "y": 0,
         "configuration": [{"name": "ios_config.txt", "content": "hostname R1"}],
         "image_definition": None, "ram": None, "cpus": None, "tags": ["core"],
         "interfaces": [
             {"id": "i1", "label": "Ethernet0/1", "type": "physical", "slot": 1},
             {"id": "i0", "label": "Loopback0", "type": "loopback"}]},
        {"id": "n2", "label": "AP-1", "node_definition": "wireless-ap", "x": 180, "y": 0,
         "configuration": [{"name": "user-data", "content": "#cloud-config\nhostname: AP-1\n"},
                           {"name": "network-config", "content": "network: {version: 2}\n"}],
         "image_definition": None, "ram": 4096, "cpus": None, "tags": [],
         "interfaces": [{"id": "i2", "label": "ens2", "type": "physical", "slot": 0}]},
        {"id": "n3", "label": "EXT", "node_definition": "external_connector", "x": 360, "y": 0,
         "configuration": [{"name": "default", "content": "System Bridge"}],
         "image_definition": None, "ram": None, "cpus": None, "tags": [],
         "interfaces": [{"id": "i3", "label": "port", "type": "physical", "slot": 0}]},
    ],
    "links": [{"id": "l1", "interface_a": "i1", "interface_b": "i3",
               "node_a": "n1", "node_b": "n3"}],
    "annotations": [{"id": "a1", "type": "text", "text_content": "hi", "x1": 5.0, "y1": 6.0,
                     "rotation": 0, "text_bold": False, "text_font": "monospace",
                     "text_italic": False, "text_size": 12, "text_unit": "pt",
                     "thickness": 1, "z_index": 0, "border_style": "",
                     "border_color": "#00000000", "color": "#000000FF"}],
}


def test_spec_from_topology_shapes():
    out = spec_from_topology(_TOPOLOGY)
    import yaml as _y
    data = _y.safe_load(out)
    assert data["lab"] == {"title": "Exported", "description": "d"}
    assert data["nodes"]["R1"]["config"] == "hostname R1"
    assert [f["name"] for f in data["nodes"]["AP-1"]["config_files"]] == [
        "user-data", "network-config"]
    assert data["nodes"]["EXT"]["config"] == "System Bridge"
    assert data["links"] == ["R1:Ethernet0/1 -- EXT:port"]
    # annotation defaults stripped, non-defaults kept
    ann = data["annotations"][0]
    assert ann["type"] == "text" and ann["text_content"] == "hi"
    assert "rotation" not in ann and "id" not in ann


def test_export_round_trips_through_parse():
    plan = parse_spec(spec_from_topology(_TOPOLOGY))
    assert [n.label for n in plan.nodes] == ["R1", "AP-1", "EXT"]
    assert plan.links[0].a.interface == "Ethernet0/1"
    assert plan.nodes[1].config[0]["name"] == "user-data"


# ---------------------------------------------------------------------------
# tools end-to-end via MockTransport
# ---------------------------------------------------------------------------

_NODE_DEFS = [{"id": "iol-xe"}, {"id": "ioll2-xe"}, {"id": "external_connector"},
              {"id": "wireless-ap"}]


def _build_handler(log, fail_on_node: str | None = None):
    """Simulate the CML endpoints build_lab_from_spec touches."""
    counters = {"node": 0, "iface": 0, "link": 0}
    node_ifaces: dict[str, list] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        log.append((method, path))
        if path.endswith("/node_definitions"):
            return httpx.Response(200, json=_NODE_DEFS)
        if path.endswith("/labs") and method == "POST":
            return httpx.Response(200, json={"id": "LAB1"})
        if path.endswith("/labs/LAB1/nodes") and method == "POST":
            body = json.loads(req.content)
            if fail_on_node and body["label"] == fail_on_node:
                return httpx.Response(400, json={"description": "boom"})
            counters["node"] += 1
            nid = f"N{counters['node']}"
            ifaces = []
            for slot in range(2):
                counters["iface"] += 1
                ifaces.append({"id": f"I{counters['iface']}",
                               "label": f"Ethernet0/{slot}", "type": "physical",
                               "slot": slot, "is_connected": False})
            node_ifaces[nid] = ifaces
            log.append(("BODY", body))
            return httpx.Response(200, json={"id": nid})
        m = re.match(r".*/labs/LAB1/nodes/(N\d+)/interfaces$", path)
        if m and method == "GET":
            return httpx.Response(200, json=node_ifaces[m.group(1)])
        if path.endswith("/labs/LAB1/interfaces") and method == "POST":
            body = json.loads(req.content)
            counters["iface"] += 1
            nid = body["node"]
            slot = len(node_ifaces[nid])
            iface = {"id": f"I{counters['iface']}", "label": f"Ethernet0/{slot}",
                     "type": "physical", "slot": slot, "is_connected": False}
            node_ifaces[nid].append(iface)
            return httpx.Response(200, json=[iface])
        if path.endswith("/labs/LAB1/links") and method == "POST":
            counters["link"] += 1
            log.append(("BODY", json.loads(req.content)))
            return httpx.Response(200, json={"id": f"L{counters['link']}"})
        if path.endswith("/labs/LAB1/annotations") and method == "POST":
            return httpx.Response(200, json={"id": "A1"})
        if path.endswith("/labs/LAB1/start"):
            return httpx.Response(200, json=None)
        if path.endswith("/labs/LAB1") and method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"description": f"unhandled {method} {path}"})

    return handler


def _mcp(handler) -> FastMCP:
    m = FastMCP("t")
    labspec.register(m, _client(handler))
    return m


BUILD_SPEC = """
lab: {title: Built}
defaults: {definition: iol-xe}
nodes:
  R1:
  R2:
  EXT: {definition: external_connector, config: System Bridge}
links:
  - R1:Ethernet0/1 -- R2:e0/1
  - R1 -- EXT
annotations:
  - {type: text, text_content: hello, x1: 1, y1: 2}
groups:
  core: {agent: catalyst-engineer, nodes: [R1, R2], tasks: ping each other}
"""


def test_build_sequence_and_report():
    log: list = []
    res = run(_mcp(_build_handler(log)).call_tool("build_lab_from_spec", {"spec": BUILD_SPEC}))
    report = json.loads(res[0][0].text)
    assert report["state"] == "built" and report["lab_id"] == "LAB1"
    assert report["nodes"] == {"R1": "N1", "R2": "N2", "EXT": "N3"}
    # pinned link resolved to real labels; auto link allocated a free interface
    assert report["links"][0]["a"] == {"node": "R1", "interface": "Ethernet0/1"}
    assert report["links"][1]["b"]["node"] == "EXT"
    assert report["annotations"] == 1
    assert "### Brief: core -> catalyst-engineer" in report["briefs"][0]
    # request ordering: lab -> 3 nodes -> links -> annotation
    paths = [p for _m, p in [e for e in log if e[0] != "BODY"]]
    assert paths.index("/api/v0/labs") < paths.index("/api/v0/labs/LAB1/nodes")
    link_bodies = [b for tag, b in log if tag == "BODY" and "src_int" in b]
    assert link_bodies[0] == {"src_int": "I2", "dst_int": "I4"}  # Ethernet0/1 on each
    ann_calls = [p for p in paths if p.endswith("/annotations")]
    assert len(ann_calls) == 1


def test_build_dry_run_makes_no_writes():
    log: list = []
    res = run(_mcp(_build_handler(log)).call_tool(
        "build_lab_from_spec", {"spec": BUILD_SPEC, "dry_run": True}))
    report = json.loads(res[0][0].text)
    assert report["dry_run"] is True and report["links"][0]["a"]["pinned"] is True
    assert "(dry run)" in report["briefs"][0]
    methods = {m for m, _p in [e for e in log if e[0] != "BODY"]}
    assert methods == {"GET"}  # only the definition check hit the wire


def test_build_partial_vs_rollback():
    log: list = []
    res = run(_mcp(_build_handler(log, fail_on_node="R2")).call_tool(
        "build_lab_from_spec", {"spec": BUILD_SPEC}))
    report = json.loads(res[0][0].text)
    assert report["state"] == "partial" and report["failed_step"] == "add node R2"
    assert report["nodes"] == {"R1": "N1"} and "boom" in report["error"]
    assert not any(m == "DELETE" for m, _p in [e for e in log if e[0] != "BODY"])

    log2: list = []
    res = run(_mcp(_build_handler(log2, fail_on_node="R2")).call_tool(
        "build_lab_from_spec", {"spec": BUILD_SPEC, "rollback_on_error": True}))
    report = json.loads(res[0][0].text)
    assert report["state"] == "rolled_back" and report["nodes"] == {}
    assert ("DELETE", "/api/v0/labs/LAB1") in [e for e in log2 if e[0] != "BODY"]


def test_validate_offline_no_http_and_live_unknown_def():
    log: list = []
    res = run(_mcp(_build_handler(log)).call_tool(
        "validate_lab_spec", {"spec": MINIMAL, "live": False}))
    assert json.loads(res[0][0].text)["valid"] is True
    assert log == []  # zero HTTP

    bad = MINIMAL.replace("iol-xe", "no-such-def")
    res = run(_mcp(_build_handler([])).call_tool("validate_lab_spec", {"spec": bad}))
    report = json.loads(res[0][0].text)
    assert report["valid"] is False and "no-such-def" in report["errors"][0]


def test_export_lab_spec_tool():
    def handler(req):
        assert req.url.path.endswith("/labs/L9/topology")
        return httpx.Response(200, json=_TOPOLOGY)
    res = run(_mcp(handler).call_tool("export_lab_spec", {"lab_id": "L9"}))
    assert "R1:Ethernet0/1 -- EXT:port" in res[0][0].text
