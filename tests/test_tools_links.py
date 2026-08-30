"""Links/interfaces/capture tools end-to-end through MCPServer (schema included)."""

from __future__ import annotations

import json
import tempfile

import httpx
import pytest
import respx

from cml_mcp.server import build_server
from cml_mcp.tools.links import match_interface
from tests.conftest import BASE_URL, call_tool_text

LAB = "11111111-2222-4333-8444-555555555555"
LINK = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
NODE = "12121212-3434-4565-8787-909090909090"
IFACE = "99999999-8888-4777-8666-555555555555"

LINKS = [
    {
        "id": LINK,
        "interface_a": "if-a-1",
        "interface_b": "if-b-1",
        "node_a": "node-1",
        "node_b": "node-2",
        "lab_id": LAB,
        "label": "r1-to-r2",
        "state": "STARTED",
    },
    {
        "id": "link-2",
        "interface_a": "if-a-2",
        "interface_b": "if-b-2",
        "node_a": "node-2",
        "node_b": "node-3",
        "lab_id": LAB,
        "state": "DEFINED_ON_CORE",
    },
    {
        "id": "link-3",
        "interface_a": "if-a-3",
        "interface_b": "if-b-3",
        "node_a": "node-1",
        "node_b": "node-3",
        "lab_id": LAB,
        "state": "STOPPED",
    },
]

INTERFACES = [
    {
        "id": IFACE,
        "label": "GigabitEthernet0/0",
        "node": "node-1",
        "lab_id": LAB,
        "type": "physical",
        "slot": 0,
        "is_connected": True,
        "mac_address": "00:11:22:33:44:55",
        "state": "STARTED",
        "operational": None,
    },
    {
        "id": "iface-2",
        "label": "GigabitEthernet0/1",
        "node": "node-1",
        "lab_id": LAB,
        "type": "physical",
        "slot": 1,
        "is_connected": False,
        "mac_address": None,
        "state": "DEFINED_ON_CORE",
        "operational": None,
    },
]

PACKETS = [
    {
        "no": "1",
        "time": "0.000000",
        "source": "192.168.0.1",
        "destination": "192.168.0.2",
        "length": "64",
        "protocol": "ICMP",
        "info": "Echo (ping) request",
    },
    {
        "no": "2",
        "time": "0.001200",
        "source": "192.168.0.2",
        "destination": "192.168.0.1",
        "length": "64",
        "protocol": "ICMP",
        "info": "Echo (ping) reply",
    },
    {
        "no": "3",
        "time": "1.500000",
        "source": "00:11:22:33:44:55",
        "destination": "ff:ff:ff:ff:ff:ff",
        "length": "42",
        "protocol": "ARP",
        "info": "Who has 192.168.0.3?",
    },
]

CAPTURE_STATUS = {
    "config": {"maxpackets": 1000, "maxtime": 300, "bpfilter": "icmp", "encap": "ethernet"},
    "starttime": "2026-08-29T10:00:00+00:00",
    "packetscaptured": 42,
}


@pytest.fixture
def mcp(make_settings):
    return build_server(make_settings(enable_writes=True))


# ---------------------------------------------------------------------- reads


@respx.mock
async def test_list_links_markdown(mcp):
    route = respx.get(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json=LINKS)
    )
    text = await call_tool_text(mcp, "cml_list_links", {"lab_id": LAB, "limit": 2})
    assert route.calls[0].request.url.params["data"] == "true"
    assert LINK in text and "STARTED" in text
    assert "if-a-1" in text and "if-b-1" in text
    assert "node-1" in text and "node-2" in text
    assert "offset=2" in text  # has_more hint: 2 of 3 shown


@respx.mock
async def test_list_links_json_envelope(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links").mock(return_value=httpx.Response(200, json=LINKS))
    text = await call_tool_text(
        mcp, "cml_list_links", {"lab_id": LAB, "limit": 2, "response_format": "json"}
    )
    data = json.loads(text)
    assert data["total"] == 3
    assert data["count"] == 2
    assert data["has_more"] is True
    assert data["next_offset"] == 2
    assert data["items"][0]["id"] == LINK


@respx.mock
async def test_get_link(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links/{LINK}").mock(
        return_value=httpx.Response(200, json=LINKS[0])
    )
    text = await call_tool_text(mcp, "cml_get_link", {"lab_id": LAB, "link_id": LINK})
    assert json.loads(text)["interface_a"] == "if-a-1"


@respx.mock
async def test_get_link_404_error_string(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links/{LINK}").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_get_link", {"lab_id": LAB, "link_id": LINK})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_link_condition_applied(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links/{LINK}/condition").mock(
        return_value=httpx.Response(200, json={"bandwidth": 1000, "latency": 50, "enabled": True})
    )
    text = await call_tool_text(mcp, "cml_get_link_condition", {"lab_id": LAB, "link_id": LINK})
    assert json.loads(text)["bandwidth"] == 1000


@respx.mock
async def test_get_link_condition_empty_reports_none_applied(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links/{LINK}/condition").mock(
        return_value=httpx.Response(200, json={})
    )
    text = await call_tool_text(mcp, "cml_get_link_condition", {"lab_id": LAB, "link_id": LINK})
    assert "No link conditioning is applied" in text
    assert LINK in text


@respx.mock
async def test_list_interfaces_json_envelope(mcp):
    route = respx.get(f"{BASE_URL}/labs/{LAB}/interfaces").mock(
        return_value=httpx.Response(200, json=INTERFACES)
    )
    text = await call_tool_text(
        mcp, "cml_list_interfaces", {"lab_id": LAB, "limit": 1, "response_format": "json"}
    )
    assert route.calls[0].request.url.params["operational"] == "true"
    data = json.loads(text)
    assert data["total"] == 2
    assert data["count"] == 1
    assert data["has_more"] is True
    assert data["next_offset"] == 1
    assert data["items"][0]["label"] == "GigabitEthernet0/0"


@respx.mock
async def test_list_interfaces_markdown_operational_false(mcp):
    route = respx.get(f"{BASE_URL}/labs/{LAB}/interfaces").mock(
        return_value=httpx.Response(200, json=INTERFACES)
    )
    text = await call_tool_text(
        mcp, "cml_list_interfaces", {"lab_id": LAB, "operational": False}
    )
    assert route.calls[0].request.url.params["operational"] == "false"
    assert "GigabitEthernet0/0" in text and f"({IFACE})" in text
    assert "00:11:22:33:44:55" in text


@respx.mock
async def test_get_interface(mcp):
    route = respx.get(f"{BASE_URL}/labs/{LAB}/interfaces/{IFACE}").mock(
        return_value=httpx.Response(200, json=INTERFACES[0])
    )
    text = await call_tool_text(
        mcp, "cml_get_interface", {"lab_id": LAB, "interface_id": IFACE}
    )
    assert route.calls[0].request.url.params["operational"] == "true"
    assert json.loads(text)["node"] == "node-1"


@respx.mock
async def test_get_capture_status(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/links/{LINK}/capture/status").mock(
        return_value=httpx.Response(200, json=CAPTURE_STATUS)
    )
    text = await call_tool_text(
        mcp, "cml_get_link_capture_status", {"lab_id": LAB, "link_id": LINK}
    )
    data = json.loads(text)
    assert data["packetscaptured"] == 42
    assert data["config"]["bpfilter"] == "icmp"


@respx.mock
async def test_get_capture_packets_markdown(mcp):
    respx.get(f"{BASE_URL}/pcap/{LINK}/packets").mock(
        return_value=httpx.Response(200, json=PACKETS)
    )
    text = await call_tool_text(mcp, "cml_get_link_capture_packets", {"link_id": LINK})
    assert "ICMP" in text and "Echo (ping) request" in text
    assert "192.168.0.1 -> 192.168.0.2" in text


@respx.mock
async def test_get_capture_packets_json_envelope_paged(mcp):
    respx.get(f"{BASE_URL}/pcap/{LINK}/packets").mock(
        return_value=httpx.Response(200, json=PACKETS)
    )
    text = await call_tool_text(
        mcp,
        "cml_get_link_capture_packets",
        {"link_id": LINK, "limit": 2, "offset": 2, "response_format": "json"},
    )
    data = json.loads(text)
    assert data["total"] == 3
    assert data["count"] == 1
    assert data["has_more"] is False
    assert data["next_offset"] is None
    assert data["items"][0]["protocol"] == "ARP"


@respx.mock
async def test_get_capture_packets_404_error_string(mcp):
    respx.get(f"{BASE_URL}/pcap/{LINK}/packets").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_get_link_capture_packets", {"link_id": LINK})
    assert text.startswith("Error:")
    assert "404" in text


# --------------------------------------------------------------------- writes


@respx.mock
async def test_create_link(mcp):
    route = respx.post(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json={"id": LINK})
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_int": "iface-2", "dst_int": IFACE},
    )
    assert json.loads(text)["id"] == LINK
    assert json.loads(route.calls[0].request.content) == {
        "src_int": "iface-2",
        "dst_int": IFACE,
    }


@respx.mock
async def test_delete_link(mcp):
    respx.delete(f"{BASE_URL}/labs/{LAB}/links/{LINK}").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(mcp, "cml_delete_link", {"lab_id": LAB, "link_id": LINK})
    assert f"Link {LINK} deleted" in text


@respx.mock
async def test_set_link_condition_sends_only_provided_fields(mcp):
    route = respx.patch(f"{BASE_URL}/labs/{LAB}/links/{LINK}/condition").mock(
        return_value=httpx.Response(
            200, json={"bandwidth": 1000, "latency": 50, "loss": 2.5, "enabled": True}
        )
    )
    text = await call_tool_text(
        mcp,
        "cml_set_link_condition",
        {
            "lab_id": LAB,
            "link_id": LINK,
            "bandwidth": 1000,
            "latency": 50,
            "loss": 2.5,
            "enabled": True,
        },
    )
    assert json.loads(route.calls[0].request.content) == {
        "bandwidth": 1000,
        "latency": 50,
        "loss": 2.5,
        "enabled": True,
    }
    assert json.loads(text)["enabled"] is True


@respx.mock
async def test_set_link_condition_422_error_string(mcp):
    respx.patch(f"{BASE_URL}/labs/{LAB}/links/{LINK}/condition").mock(
        return_value=httpx.Response(422, json={"description": "value out of range"})
    )
    text = await call_tool_text(
        mcp, "cml_set_link_condition", {"lab_id": LAB, "link_id": LINK, "latency": 100}
    )
    assert text.startswith("Error:")
    assert "422" in text


@respx.mock
async def test_clear_link_condition(mcp):
    respx.delete(f"{BASE_URL}/labs/{LAB}/links/{LINK}/condition").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(
        mcp, "cml_set_link_condition", {"lab_id": LAB, "link_id": LINK, "action": "clear"}
    )
    assert "conditioning cleared" in text


@respx.mock
async def test_start_link_capture(mcp):
    route = respx.put(f"{BASE_URL}/labs/{LAB}/links/{LINK}/capture/start").mock(
        return_value=httpx.Response(200, json=CAPTURE_STATUS)
    )
    text = await call_tool_text(
        mcp,
        "cml_set_link_capture",
        {"lab_id": LAB, "link_id": LINK, "action": "start",
         "maxpackets": 1000, "bpfilter": "icmp"},
    )
    assert json.loads(route.calls[0].request.content) == {
        "maxpackets": 1000,
        "bpfilter": "icmp",
    }
    assert json.loads(text)["config"]["maxpackets"] == 1000


@respx.mock
async def test_stop_link_capture(mcp):
    respx.put(f"{BASE_URL}/labs/{LAB}/links/{LINK}/capture/stop").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(
        mcp, "cml_set_link_capture", {"lab_id": LAB, "link_id": LINK, "action": "stop"}
    )
    assert f"capture stopped on link {LINK}" in text


@respx.mock
async def test_start_link_capture_requires_stop_condition(mcp):
    text = await call_tool_text(
        mcp,
        "cml_set_link_capture",
        {"lab_id": LAB, "link_id": LINK, "action": "start"},
    )
    assert text.startswith("Error:")
    assert "maxpackets or maxtime" in text
    assert not respx.calls  # nothing was sent to the platform


@respx.mock
async def test_create_interface(mcp):
    route = respx.post(f"{BASE_URL}/labs/{LAB}/interfaces").mock(
        return_value=httpx.Response(
            200, json={"id": IFACE, "label": "GigabitEthernet0/3", "slot": 3}
        )
    )
    text = await call_tool_text(
        mcp,
        "cml_create_interface",
        {"lab_id": LAB, "node_id": NODE, "slot": 3},
    )
    data = json.loads(text)
    assert data["id"] == IFACE
    assert json.loads(route.calls[0].request.content) == {"node": NODE, "slot": 3}


@respx.mock
async def test_create_interface_error_path(mcp):
    respx.post(f"{BASE_URL}/labs/{LAB}/interfaces").mock(
        return_value=httpx.Response(404)
    )
    text = await call_tool_text(
        mcp, "cml_create_interface", {"lab_id": LAB, "node_id": NODE}
    )
    assert text.startswith("Error:")


# ----------------------------------------------- link state & pcap download

PCAP_BYTES = b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00" + b"\x00" * 16


@respx.mock
async def test_start_link(mcp):
    respx.put(f"{BASE_URL}/labs/{LAB}/links/{LINK}/state/start").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(
        mcp, "cml_set_link_state", {"lab_id": LAB, "link_id": LINK, "action": "start"}
    )
    assert f"Link {LINK} started" in text


@respx.mock
async def test_start_link_404_error_string(mcp):
    respx.put(f"{BASE_URL}/labs/{LAB}/links/{LINK}/state/start").mock(
        return_value=httpx.Response(404)
    )
    text = await call_tool_text(
        mcp, "cml_set_link_state", {"lab_id": LAB, "link_id": LINK, "action": "start"}
    )
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_stop_link(mcp):
    respx.put(f"{BASE_URL}/labs/{LAB}/links/{LINK}/state/stop").mock(
        return_value=httpx.Response(204)
    )
    text = await call_tool_text(
        mcp, "cml_set_link_state", {"lab_id": LAB, "link_id": LINK, "action": "stop"}
    )
    assert f"Link {LINK} stopped" in text
    assert "cable pull" in text


@respx.mock
async def test_download_link_pcap_to_output_path(mcp, tmp_path):
    respx.get(f"{BASE_URL}/pcap/{LINK}").mock(
        return_value=httpx.Response(
            200, content=PCAP_BYTES, headers={"Content-Type": "application/cap"}
        )
    )
    out = tmp_path / "capture.pcap"
    text = await call_tool_text(
        mcp, "cml_download_link_pcap", {"link_id": LINK, "output_path": str(out)}
    )
    assert out.read_bytes() == PCAP_BYTES
    assert str(out) in text
    assert f"{len(PCAP_BYTES)} bytes" in text
    assert "Wireshark" in text


@respx.mock
async def test_download_link_pcap_default_path_uses_tempdir(mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    respx.get(f"{BASE_URL}/pcap/{LINK}").mock(
        return_value=httpx.Response(200, content=PCAP_BYTES)
    )
    text = await call_tool_text(mcp, "cml_download_link_pcap", {"link_id": LINK})
    expected = tmp_path / f"cml-capture-{LINK}.pcap"
    assert expected.read_bytes() == PCAP_BYTES
    assert str(expected) in text


@respx.mock
async def test_download_link_pcap_empty_body_is_actionable_error(mcp, tmp_path):
    respx.get(f"{BASE_URL}/pcap/{LINK}").mock(
        return_value=httpx.Response(200, content=b"")
    )
    out = tmp_path / "empty.pcap"
    text = await call_tool_text(
        mcp, "cml_download_link_pcap", {"link_id": LINK, "output_path": str(out)}
    )
    assert text.startswith("Error:")
    assert "cml_set_link_capture" in text
    assert not out.exists()  # nothing written for an empty capture


# ------------------------------------------- interface-label pinning (matcher)

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


# ------------------------------------- interface-label pinning (cml_create_link)

NODE_A = "aaaa1111-2222-4333-8444-555555555555"
NODE_B = "bbbb1111-2222-4333-8444-555555555555"

NODES = [
    {"id": NODE_A, "label": "R1", "state": "STARTED"},
    {"id": NODE_B, "label": "R2", "state": "STARTED"},
]


def _node_ifaces(prefix: str) -> list[dict]:
    return [
        {
            "id": f"{prefix}-lo0",
            "label": "Loopback0",
            "type": "loopback",
            "is_connected": False,
        },
        {
            "id": f"{prefix}-gi0",
            "label": "GigabitEthernet0/0",
            "type": "physical",
            "is_connected": True,
        },
        {
            "id": f"{prefix}-gi1",
            "label": "GigabitEthernet0/1",
            "type": "physical",
            "is_connected": False,
        },
    ]


@respx.mock
async def test_create_link_by_interface_label_abbreviation(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(return_value=httpx.Response(200, json=NODES))
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_A}/interfaces").mock(
        return_value=httpx.Response(200, json=_node_ifaces("a"))
    )
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_B}/interfaces").mock(
        return_value=httpx.Response(200, json=_node_ifaces("b"))
    )
    route = respx.post(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json={"id": LINK})
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {
            "lab_id": LAB,
            "src_node": "R1",
            "src_int_label": "Gi0/1",
            "dst_node": "R2",
            "dst_int_label": "gigabitethernet0/1",
        },
    )
    assert json.loads(text)["id"] == LINK
    assert json.loads(route.calls[0].request.content) == {
        "src_int": "a-gi1",
        "dst_int": "b-gi1",
    }


@respx.mock
async def test_create_link_label_on_one_side_auto_picks_the_other(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(return_value=httpx.Response(200, json=NODES))
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_A}/interfaces").mock(
        return_value=httpx.Response(200, json=_node_ifaces("a"))
    )
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_B}/interfaces").mock(
        return_value=httpx.Response(200, json=_node_ifaces("b"))
    )
    route = respx.post(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json={"id": LINK})
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_node": "R1", "src_int_label": "Gi0/1", "dst_node": "R2"},
    )
    assert json.loads(text)["id"] == LINK
    # dst auto-pick skips the loopback and the already-connected Gi0/0.
    assert json.loads(route.calls[0].request.content) == {
        "src_int": "a-gi1",
        "dst_int": "b-gi1",
    }


@respx.mock
async def test_create_link_label_not_found_lists_labels_and_points_at_definition(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(return_value=httpx.Response(200, json=NODES))
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_A}/interfaces").mock(
        return_value=httpx.Response(200, json=_node_ifaces("a"))
    )
    post = respx.post(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json={"id": LINK})
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_node": "R1", "src_int_label": "Te0/9", "dst_int": IFACE},
    )
    assert text.startswith("Error:")
    assert "GigabitEthernet0/0, GigabitEthernet0/1" in text  # physical labels only
    assert "Loopback0" not in text
    assert text.rstrip().endswith(
        "this node definition may not produce that label; check cml_get_node_definition."
    )
    assert not post.called  # no link created on a failed resolve


@respx.mock
async def test_create_link_ambiguous_label_names_candidates(mcp):
    ifaces = [
        {"id": "a1", "label": "GigabitEthernet1", "type": "physical", "is_connected": False},
        {"id": "a2", "label": "GigE1", "type": "physical", "is_connected": False},
    ]
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(return_value=httpx.Response(200, json=NODES))
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_A}/interfaces").mock(
        return_value=httpx.Response(200, json=ifaces)
    )
    post = respx.post(f"{BASE_URL}/labs/{LAB}/links").mock(
        return_value=httpx.Response(200, json={"id": LINK})
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_node": "R1", "src_int_label": "g1", "dst_int": IFACE},
    )
    assert text.startswith("Error:")
    assert "ambiguous" in text
    assert "GigabitEthernet1" in text and "GigE1" in text
    assert not post.called


@respx.mock
async def test_create_link_label_without_node_is_preflight_error(mcp):
    nodes = respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_int_label": "Gi0/1", "dst_int": IFACE},
    )
    assert text.startswith("Error:")
    assert "src_node" in text
    assert not nodes.called  # rejected before any HTTP call


@respx.mock
async def test_create_link_int_and_label_together_is_preflight_error(mcp):
    nodes = respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {
            "lab_id": LAB,
            "src_int": "iface-2",
            "src_int_label": "Gi0/1",
            "dst_int": IFACE,
        },
    )
    assert text.startswith("Error:")
    assert "mutually exclusive" in text
    assert not nodes.called


@respx.mock
async def test_create_link_neither_int_nor_node_is_preflight_error(mcp):
    nodes = respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(
        return_value=httpx.Response(200, json=NODES)
    )
    text = await call_tool_text(mcp, "cml_create_link", {"lab_id": LAB, "src_int": "iface-2"})
    assert text.startswith("Error:")
    assert "dst_int" in text and "dst_node" in text
    assert not nodes.called


@respx.mock
async def test_create_link_label_resolve_http_error_string(mcp):
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes").mock(return_value=httpx.Response(200, json=NODES))
    respx.get(f"{BASE_URL}/labs/{LAB}/nodes/{NODE_A}/interfaces").mock(
        return_value=httpx.Response(404)
    )
    text = await call_tool_text(
        mcp,
        "cml_create_link",
        {"lab_id": LAB, "src_node": "R1", "src_int_label": "Gi0/1", "dst_int": IFACE},
    )
    assert text.startswith("Error:")
    assert "404" in text
