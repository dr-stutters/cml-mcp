"""CML-free unit tests for the client + the two tools fixed this session.

No live CML needed - httpx.MockTransport supplies canned responses, and the tools
are exercised through a FastMCP server with a mocked client. Run: `uv run pytest`.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from cml_mcp.client import CMLAPIError, CMLClient
from cml_mcp.config import Settings
from cml_mcp.tools import links as links_tools
from cml_mcp.tools import raw as raw_tools


def run(coro):
    return asyncio.run(coro)


def _settings() -> Settings:
    return Settings(base_url="https://cml.example.com", username="a", password="b",
                    verify_ssl=False, timeout=5)


def _client(handler) -> CMLClient:
    c = CMLClient(_settings())
    c._http = httpx.AsyncClient(base_url=c.settings.api_url, transport=httpx.MockTransport(handler))
    c._token = "testtoken"  # pre-set so we skip the auth round-trip
    return c


# --------------------------------------------------------------------------
# client: json_body vs content dispatch, 401 re-auth, error extraction, 204
# --------------------------------------------------------------------------
def test_request_sends_json_body():
    seen = {}

    def handler(req):
        seen["body"], seen["ct"] = req.content, req.headers.get("content-type", "")
        return httpx.Response(200, json={"ok": True})

    r = run(_client(handler).post("/labs", json_body={"a": 1}))
    assert json.loads(seen["body"]) == {"a": 1} and "application/json" in seen["ct"]
    assert r == {"ok": True}


def test_request_sends_text_content():
    seen = {}

    def handler(req):
        seen["body"] = req.content
        return httpx.Response(204)

    run(_client(handler).post("/import", content="version: 1"))
    assert seen["body"] == b"version: 1"


def test_401_triggers_reauth_then_retries():
    state = {"n": 0}

    def handler(req):
        if req.url.path.endswith("/authenticate"):
            return httpx.Response(200, json="newtoken")
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(401, json={"description": "token expired"})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler)
    c._token = "old"
    assert run(c.get("/labs")) == {"ok": True} and state["n"] == 2


def test_error_extraction_uses_description():
    def handler(_req):
        return httpx.Response(400, json={"description": "bad lab id"})
    with pytest.raises(CMLAPIError) as ei:
        run(_client(handler).get("/labs/x"))
    assert ei.value.status_code == 400 and "bad lab id" in str(ei.value)


def test_204_returns_none():
    assert run(_client(lambda _r: httpx.Response(204)).delete("/labs/x")) is None


# --------------------------------------------------------------------------
# tool: cml_api_call body coercion (regression - dict/list direct, str parsed/text)
# --------------------------------------------------------------------------
def _mcp(store) -> FastMCP:
    def handler(req):
        store["method"], store["path"] = req.method, req.url.path
        store["body"] = req.content.decode() if req.content else ""
        store["ct"] = req.headers.get("content-type", "")
        return httpx.Response(200, json={"ok": True})
    m = FastMCP("t")
    c = _client(handler)
    raw_tools.register(m, c)
    links_tools.register(m, c)
    return m


def test_cml_api_call_dict_body_sent_as_json():
    store = {}
    run(_mcp(store).call_tool("cml_api_call", {"method": "POST", "path": "/labs", "body": {"title": "x"}}))
    assert json.loads(store["body"]) == {"title": "x"} and "application/json" in store["ct"]


def test_cml_api_call_list_body_sent_as_json():
    store = {}
    run(_mcp(store).call_tool("cml_api_call", {"method": "POST", "path": "/x", "body": [1, 2, 3]}))
    assert json.loads(store["body"]) == [1, 2, 3]


def test_cml_api_call_json_string_is_parsed():
    store = {}
    run(_mcp(store).call_tool("cml_api_call", {"method": "POST", "path": "/labs", "body": '{"title": "y"}'}))
    assert json.loads(store["body"]) == {"title": "y"}


def test_cml_api_call_plain_string_sent_as_text():
    store = {}
    run(_mcp(store).call_tool("cml_api_call", {"method": "PUT", "path": "/x", "body": "just text"}))
    assert store["body"] == "just text"


# --------------------------------------------------------------------------
# tool: manage_packet_capture start body (regression - PCAPStart schema fields)
# --------------------------------------------------------------------------
def test_pcap_start_sends_maxtime_and_bpfilter():
    store = {}
    run(_mcp(store).call_tool("manage_packet_capture", {
        "lab_id": "L", "link_id": "K", "action": "start", "max_time": 30, "bpfilter": "udp port 1812"}))
    body = json.loads(store["body"])
    assert store["path"].endswith("/labs/L/links/K/capture/start")
    assert body["maxtime"] == 30 and body["bpfilter"] == "udp port 1812" and "maxpackets" not in body


def test_pcap_start_defaults_maxtime_and_includes_maxpackets():
    store = {}
    run(_mcp(store).call_tool("manage_packet_capture", {
        "lab_id": "L", "link_id": "K", "action": "start", "max_packets": 100}))
    body = json.loads(store["body"])
    assert body["maxtime"] == 60 and body["maxpackets"] == 100 and "bpfilter" not in body
