"""Convergence-wait tools end-to-end through MCPServer (schema validation included)."""

from __future__ import annotations

import json

import httpx
import respx

from cml_mcp.client import ApiClient
from cml_mcp.config import Settings
from cml_mcp.safety import AppContext
from cml_mcp.server import build_server, create_auth
from cml_mcp.tools import convergence
from tests.conftest import BASE_URL, call_tool_text

LAB_ID = "90f84e38-a71c-4d57-8d90-00fa8a197385"
NODE_ID = "26f677f3-fcb2-47ef-9171-dc112d80b54f"

ELEMENT_STATE = {
    "nodes": {NODE_ID: "BOOTED", "36f677f3-fcb2-47ef-9171-dc112d80b54f": "BOOTED"},
    "links": {"46f677f3-fcb2-47ef-9171-dc112d80b54f": "STARTED"},
    "interfaces": {"56f677f3-fcb2-47ef-9171-dc112d80b54f": "STARTED"},
}


async def build_convergence_server(settings: Settings):
    """build_server(), registering the convergence module directly if needed.

    tools/__init__.py (ALL_MODULES) is owned by the orchestrator; register the
    module here when it is not wired in yet so these tests pass either way.
    """
    mcp = build_server(settings)
    if all(t.name != "cml_wait_for_lab_converged" for t in await mcp.list_tools()):
        ctx = AppContext(settings=settings, client=ApiClient(settings, create_auth(settings)))
        convergence.register(mcp, ctx)
    return mcp


# ------------------------------------------------------------------ lab-level


@respx.mock
async def test_wait_for_lab_converged_polls_until_true(make_settings):
    converged_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/check_if_converged").mock(
        side_effect=[
            httpx.Response(200, json=False),
            httpx.Response(200, json=False),
            httpx.Response(200, json=True),
        ]
    )
    state_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_wait_for_lab_converged",
        {"lab_id": LAB_ID, "timeout_seconds": 30, "interval_seconds": 1},
    )
    assert converged_route.call_count == 3
    assert state_route.call_count == 1
    data = json.loads(text)
    assert data["converged"] is True
    assert data["lab_id"] == LAB_ID
    assert data["node_states"][NODE_ID] == "BOOTED"
    assert "note" not in data  # converged: no not-converged note


@respx.mock
async def test_wait_for_lab_converged_timeout_is_not_an_error(make_settings):
    # interval > timeout: wait_until gives up after a single check, so the test
    # exercises the timeout path without sleeping.
    converged_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/check_if_converged").mock(
        return_value=httpx.Response(200, json=False)
    )
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/lab_element_state").mock(
        return_value=httpx.Response(200, json=ELEMENT_STATE)
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_wait_for_lab_converged",
        {"lab_id": LAB_ID, "timeout_seconds": 10, "interval_seconds": 60},
    )
    assert converged_route.call_count == 1
    assert not text.startswith("Error:")
    data = json.loads(text)
    assert data["converged"] is False
    assert data["timeout_seconds"] == 10
    assert "Not converged yet" in data["note"]
    assert data["node_states"][NODE_ID] == "BOOTED"  # current states still reported


@respx.mock
async def test_wait_for_lab_converged_404_returns_error_string(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/check_if_converged").mock(
        return_value=httpx.Response(404, json={"description": "Lab not found"})
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(
        mcp, "cml_wait_for_lab_converged", {"lab_id": LAB_ID, "timeout_seconds": 10}
    )
    assert text.startswith("Error:")
    assert "404" in text


# ----------------------------------------------------------------- node-level


@respx.mock
async def test_wait_for_node_converged_polls_until_true(make_settings):
    converged_route = respx.get(
        f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged"
    ).mock(
        side_effect=[
            httpx.Response(200, json=False),
            httpx.Response(200, json=False),
            httpx.Response(200, json=True),
        ]
    )
    state_route = respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "BOOTED", "progress": "100%"})
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_wait_for_node_converged",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "timeout_seconds": 30, "interval_seconds": 1},
    )
    assert converged_route.call_count == 3
    assert state_route.call_count == 1
    data = json.loads(text)
    assert data["converged"] is True
    assert data["node_id"] == NODE_ID
    assert data["state"] == "BOOTED"
    assert data["progress"] == "100%"
    assert "note" not in data


@respx.mock
async def test_wait_for_node_converged_timeout_is_not_an_error(make_settings):
    converged_route = respx.get(
        f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged"
    ).mock(return_value=httpx.Response(200, json=False))
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/state").mock(
        return_value=httpx.Response(200, json={"state": "STARTED", "progress": "booting"})
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True))
    text = await call_tool_text(
        mcp,
        "cml_wait_for_node_converged",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "timeout_seconds": 10, "interval_seconds": 60},
    )
    assert converged_route.call_count == 1
    assert not text.startswith("Error:")
    data = json.loads(text)
    assert data["converged"] is False
    assert data["state"] == "STARTED"
    assert "Not converged yet" in data["note"]


@respx.mock
async def test_wait_for_node_converged_404_returns_error_string(make_settings):
    respx.get(f"{BASE_URL}/labs/{LAB_ID}/nodes/{NODE_ID}/check_if_converged").mock(
        return_value=httpx.Response(404, json={"description": "Node not found"})
    )
    mcp = await build_convergence_server(make_settings(enable_writes=True, max_retries=0))
    text = await call_tool_text(
        mcp,
        "cml_wait_for_node_converged",
        {"lab_id": LAB_ID, "node_id": NODE_ID, "timeout_seconds": 10},
    )
    assert text.startswith("Error:")
    assert "404" in text
