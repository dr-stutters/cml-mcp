"""System tools end-to-end through MCPServer (schema validation included)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from cml_mcp import tools as tools_registry
from cml_mcp.server import build_server
from cml_mcp.tools import system as system_module
from tests.conftest import BASE_URL, call_tool_text


@pytest.fixture(autouse=True)
def _include_system_module(monkeypatch):
    """Register this module's tools even before tools/__init__.py lists it.

    Integration of ALL_MODULES happens in a separate change; the guard makes
    this fixture a no-op once the module is wired in there.
    """
    if system_module not in tools_registry.ALL_MODULES:
        monkeypatch.setattr(
            tools_registry, "ALL_MODULES", [*tools_registry.ALL_MODULES, system_module]
        )


@pytest.fixture
def mcp(make_settings):
    return build_server(make_settings(enable_writes=True))


NODE_DEFINITIONS = [
    {
        "id": "iosv",
        "general": {"nature": "router", "description": "Cisco IOSv router"},
        "ui": {"label": "IOSv"},
        "image_definitions": ["iosv-159-3-m6"],
    },
    {
        "id": "iosvl2",
        "general": {"nature": "switch", "description": "Cisco IOSv layer-2 switch"},
        "ui": {"label": "IOSvL2"},
    },
    {
        "id": "server",
        "general": {"nature": "server", "description": "Tiny Core Linux server"},
        "ui": {"label": "Server"},
    },
]

UUID_A = "90f84e38-a71c-4d57-8d90-00fa8a197385"
UUID_B = "60f84e39-ffff-4d99-8a78-00fa8aaf5666"


@respx.mock
async def test_get_system_information(mcp):
    route = respx.get(f"{BASE_URL}/system_information").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": "2.10.0",
                "ready": True,
                "allow_ssh_pubkey_auth": False,
                "oui": "52:54:00:00:00:00",
            },
        )
    )
    text = await call_tool_text(mcp, "cml_get_system_information", {})
    data = json.loads(text)
    assert data["version"] == "2.10.0"
    assert data["ready"] is True
    assert not dict(route.calls[0].request.url.params)


@respx.mock
async def test_get_system_information_error(mcp):
    respx.get(f"{BASE_URL}/system_information").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_get_system_information", {})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_get_system_health(mcp):
    respx.get(f"{BASE_URL}/system_health").mock(
        return_value=httpx.Response(
            200,
            json={
                "valid": True,
                "is_licensed": True,
                "is_enterprise": False,
                "controller": {"valid": True, "nodes_loaded": True, "images_loaded": True},
                "computes": {UUID_A: {"valid": True}},
            },
        )
    )
    respx.get(f"{BASE_URL}/system/maintenance_mode").mock(
        return_value=httpx.Response(200, json={"maintenance_mode": False, "notice": None})
    )
    respx.get(f"{BASE_URL}/system/notices").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": UUID_B,
                    "level": "WARNING",
                    "label": "Controller reboot scheduled 17:00 UTC",
                    "content": "The controller reboots at 17:00 UTC.",
                    "acknowledged": {},
                    "enabled": True,
                }
            ],
        )
    )
    text = await call_tool_text(
        mcp, "cml_get_system_health", {"response_format": "json"}
    )
    data = json.loads(text)
    assert data["valid"] is True
    assert data["computes"][UUID_A]["valid"] is True
    assert data["maintenance_mode"]["maintenance_mode"] is False
    assert data["notices"][0]["level"] == "WARNING"


@respx.mock
async def test_get_system_health_markdown_flags_maintenance_and_notices(mcp):
    respx.get(f"{BASE_URL}/system_health").mock(
        return_value=httpx.Response(200, json={"valid": True, "computes": {}})
    )
    respx.get(f"{BASE_URL}/system/maintenance_mode").mock(
        return_value=httpx.Response(200, json={"maintenance_mode": True, "notice": None})
    )
    respx.get(f"{BASE_URL}/system/notices").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": UUID_B, "level": "ERROR", "label": "Disk almost full",
                   "content": "Controller disk at 95%.", "acknowledged": {},
                   "enabled": True}],
        )
    )
    text = await call_tool_text(mcp, "cml_get_system_health", {})
    assert "Maintenance mode: on" in text
    assert "Disk almost full" in text


@respx.mock
async def test_get_system_stats(mcp):
    respx.get(f"{BASE_URL}/system_stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "all": {
                    "cpu": {"count": 16, "percent": 12.5},
                    "memory": {"total": 64, "used": 20},
                    "disk": {"total": 500, "used": 100},
                },
                "controller": {"disk": {"total": 500, "used": 100}},
                "computes": {UUID_A: {"stats": {"cpu": {"count": 16}}}},
            },
        )
    )
    text = await call_tool_text(mcp, "cml_get_system_stats", {})
    data = json.loads(text)
    assert data["all"]["cpu"]["count"] == 16
    assert data["controller"]["disk"]["total"] == 500


@respx.mock
async def test_list_node_definitions_markdown(mcp):
    route = respx.get(f"{BASE_URL}/node_definitions").mock(
        return_value=httpx.Response(200, json=NODE_DEFINITIONS)
    )
    text = await call_tool_text(mcp, "cml_list_node_definitions", {"limit": 2, "offset": 0})
    assert "**iosv**" in text and "Cisco IOSv router" in text
    assert "nature: router" in text
    assert "server" not in text  # third item beyond the page
    assert "offset=2" in text  # has_more hint: 2 of 3 shown
    assert not dict(route.calls[0].request.url.params)


@respx.mock
async def test_list_node_definitions_filter_and_envelope(mcp):
    respx.get(f"{BASE_URL}/node_definitions").mock(
        return_value=httpx.Response(200, json=NODE_DEFINITIONS)
    )
    text = await call_tool_text(
        mcp,
        "cml_list_node_definitions",
        {"id_filter": "ios", "limit": 1, "offset": 0, "response_format": "json"},
    )
    data = json.loads(text)
    assert data["total"] == 2  # iosv + iosvl2 match, server filtered out
    assert data["count"] == 1
    assert data["has_more"] is True
    assert data["next_offset"] == 1
    assert data["items"][0]["id"] == "iosv"


@respx.mock
async def test_get_node_definition(mcp):
    route = respx.get(f"{BASE_URL}/node_definitions/iosv").mock(
        return_value=httpx.Response(200, json=NODE_DEFINITIONS[0])
    )
    text = await call_tool_text(mcp, "cml_get_node_definition", {"def_id": "iosv"})
    assert json.loads(text)["id"] == "iosv"
    assert route.calls[0].request.url.params["json"] == "true"


@respx.mock
async def test_get_node_definition_404(mcp):
    respx.get(f"{BASE_URL}/node_definitions/nope").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_get_node_definition", {"def_id": "nope"})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_list_image_definitions_json_envelope(mcp):
    respx.get(f"{BASE_URL}/image_definitions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "iosv-159-3-m6", "node_definition_id": "iosv", "label": "IOSv 15.9(3)M6"},
                {"id": "server-tcl-15-0", "node_definition_id": "server", "label": "TCL 15.0"},
            ],
        )
    )
    text = await call_tool_text(
        mcp, "cml_list_image_definitions", {"limit": 1, "offset": 1, "response_format": "json"}
    )
    data = json.loads(text)
    assert data["total"] == 2
    assert data["count"] == 1
    assert data["has_more"] is False
    assert data["next_offset"] is None
    assert data["items"][0]["id"] == "server-tcl-15-0"


@respx.mock
async def test_list_image_definitions_markdown(mcp):
    respx.get(f"{BASE_URL}/image_definitions").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "iosv-159-3-m6", "node_definition_id": "iosv", "label": "IOSv 15.9(3)M6"}],
        )
    )
    text = await call_tool_text(mcp, "cml_list_image_definitions", {})
    assert "**iosv-159-3-m6**" in text
    assert "node_definition: iosv" in text


@respx.mock
async def test_list_external_connectors_markdown(mcp):
    respx.get(f"{BASE_URL}/system/external_connectors").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": UUID_A,
                    "label": "NAT",
                    "device_name": "virbr0",
                    "operational": "OK",
                    "tags": ["NAT"],
                    "allowed": True,
                }
            ],
        )
    )
    text = await call_tool_text(mcp, "cml_list_external_connectors", {})
    assert "**NAT**" in text and UUID_A in text
    assert "device: virbr0" in text
    assert "state: OK" in text


@respx.mock
async def test_list_external_connectors_json(mcp):
    respx.get(f"{BASE_URL}/system/external_connectors").mock(
        return_value=httpx.Response(200, json=[{"id": UUID_A, "label": "NAT"}])
    )
    text = await call_tool_text(
        mcp, "cml_list_external_connectors", {"response_format": "json"}
    )
    assert json.loads(text) == [{"id": UUID_A, "label": "NAT"}]


@respx.mock
async def test_list_users_markdown_mixed_detail(mcp):
    # Admin callers get full objects; non-admin get briefs — both may appear.
    respx.get(f"{BASE_URL}/users").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": UUID_A, "username": "admin", "admin": True, "groups": [UUID_B]},
                {"id": UUID_B, "username": "student"},  # brief: no admin/groups fields
            ],
        )
    )
    text = await call_tool_text(mcp, "cml_list_users", {})
    assert f"**admin** ({UUID_A}) — admin, groups: 1" in text
    assert f"**student** ({UUID_B})" in text


@respx.mock
async def test_list_users_json_envelope(mcp):
    respx.get(f"{BASE_URL}/users").mock(
        return_value=httpx.Response(
            200, json=[{"id": UUID_A, "username": "admin", "admin": True}]
        )
    )
    text = await call_tool_text(mcp, "cml_list_users", {"response_format": "json"})
    data = json.loads(text)
    assert data["total"] == 1
    assert data["count"] == 1
    assert data["has_more"] is False
    assert data["items"][0]["username"] == "admin"


@respx.mock
async def test_list_groups_markdown(mcp):
    respx.get(f"{BASE_URL}/groups").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": UUID_A,
                    "name": "CCNA Study Group",
                    "members": [UUID_B],
                    "description": "CCNA study group",
                },
                {"id": UUID_B, "name": "Ops"},  # brief: no members field
            ],
        )
    )
    text = await call_tool_text(mcp, "cml_list_groups", {})
    assert f"**CCNA Study Group** ({UUID_A}) — members: 1" in text
    assert "CCNA study group" in text
    assert f"**Ops** ({UUID_B})" in text


@respx.mock
async def test_list_groups_403_error(mcp):
    respx.get(f"{BASE_URL}/groups").mock(return_value=httpx.Response(403))
    text = await call_tool_text(mcp, "cml_list_groups", {})
    assert text.startswith("Error:")
    assert "403" in text


LICENSING = {
    "udi": {"hostname": "cml-controller", "product_uuid": UUID_A},
    "registration": {
        "status": "COMPLETED",
        "smart_account": "ACME Corp",
        "virtual_account": "Lab VA",
        "expires": "2027-01-15T00:00:00+00:00",
    },
    "authorization": {"status": "IN_COMPLIANCE", "expires": "2026-11-01T00:00:00+00:00"},
    "reservation_mode": False,
    "features": [
        {
            "id": "regid.2019-10.com.cisco.CML_NODE_COUNT,1.0_2607650b",
            "name": "CML - Node Count",
            "in_use": 5,
            "status": "IN_COMPLIANCE",
            "min": 0,
            "max": 20,
        }
    ],
    "product_license": {"active": "CML_Enterprise", "is_enterprise": True},
    "transport": {
        "proxy": {"server": None, "port": None},
        "ssms": None,
        "default_ssms": "https://smartreceiver.cisco.com/licservice/license",
    },
}


@respx.mock
async def test_get_licensing_markdown(mcp):
    respx.get(f"{BASE_URL}/licensing").mock(return_value=httpx.Response(200, json=LICENSING))
    text = await call_tool_text(mcp, "cml_get_licensing", {})
    assert "Registration: COMPLETED" in text
    assert "smart account: ACME Corp" in text
    assert "Authorization: IN_COMPLIANCE" in text
    assert "Product license: CML_Enterprise (enterprise: yes)" in text
    assert "Reservation mode: off" in text
    assert "## Features (1)" in text
    assert "**CML - Node Count** — in use 5 of max 20 (status: IN_COMPLIANCE)" in text


@respx.mock
async def test_get_licensing_json(mcp):
    respx.get(f"{BASE_URL}/licensing").mock(return_value=httpx.Response(200, json=LICENSING))
    text = await call_tool_text(mcp, "cml_get_licensing", {"response_format": "json"})
    data = json.loads(text)
    assert data["registration"]["status"] == "COMPLETED"
    assert data["product_license"]["is_enterprise"] is True
    assert data["features"][0]["max"] == 20


@respx.mock
async def test_get_licensing_403_error(mcp):
    respx.get(f"{BASE_URL}/licensing").mock(return_value=httpx.Response(403))
    text = await call_tool_text(mcp, "cml_get_licensing", {})
    assert text.startswith("Error:")
    assert "403" in text


@respx.mock
async def test_create_user_sends_body_and_hides_password(mcp):
    route = respx.post(f"{BASE_URL}/users").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": UUID_A,
                "username": "student1",
                "fullname": "Ada Lovelace",
                "admin": False,
                "groups": [UUID_B],
                "created": "2026-08-29T00:00:00+00:00",
                "modified": "2026-08-29T00:00:00+00:00",
            },
        )
    )
    text = await call_tool_text(
        mcp,
        "cml_create_user",
        {
            "username": "student1",
            "password": "s3cret-Pass!",
            "fullname": "Ada Lovelace",
            "email": "ada@example.com",
            "groups": [UUID_B],
        },
    )
    data = json.loads(text)
    assert data["id"] == UUID_A
    assert data["username"] == "student1"
    assert "s3cret-Pass!" not in text
    sent = json.loads(route.calls[0].request.content)
    assert sent["username"] == "student1"
    assert sent["password"] == "s3cret-Pass!"
    assert sent["admin"] is False
    assert sent["email"] == "ada@example.com"
    assert sent["groups"] == [UUID_B]
    assert "description" not in sent


@respx.mock
async def test_create_user_403_error(mcp):
    respx.post(f"{BASE_URL}/users").mock(return_value=httpx.Response(403))
    text = await call_tool_text(
        mcp, "cml_create_user", {"username": "student1", "password": "s3cret-Pass!"}
    )
    assert text.startswith("Error:")
    assert "403" in text
    assert "s3cret-Pass!" not in text


@respx.mock
async def test_delete_user(mcp):
    route = respx.delete(f"{BASE_URL}/users/{UUID_A}").mock(return_value=httpx.Response(204))
    text = await call_tool_text(mcp, "cml_delete_user", {"user_id": UUID_A})
    assert f"User {UUID_A} deleted" in text
    assert route.called


@respx.mock
async def test_delete_user_404_error(mcp):
    respx.delete(f"{BASE_URL}/users/{UUID_A}").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_delete_user", {"user_id": UUID_A})
    assert text.startswith("Error:")
    assert "404" in text


@respx.mock
async def test_create_group_sends_body(mcp):
    route = respx.post(f"{BASE_URL}/groups").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": UUID_A,
                "name": "CCNA Study Group",
                "description": "CCNA study group",
                "members": [UUID_B],
                "associations": [{"id": UUID_B, "permissions": ["lab_exec"]}],
                "created": "2026-08-29T00:00:00+00:00",
                "modified": "2026-08-29T00:00:00+00:00",
            },
        )
    )
    text = await call_tool_text(
        mcp,
        "cml_create_group",
        {
            "name": "CCNA Study Group",
            "description": "CCNA study group",
            "members": [UUID_B],
            "associations": [{"id": UUID_B, "permissions": ["lab_exec"]}],
        },
    )
    data = json.loads(text)
    assert data["id"] == UUID_A
    assert data["name"] == "CCNA Study Group"
    sent = json.loads(route.calls[0].request.content)
    assert sent == {
        "name": "CCNA Study Group",
        "description": "CCNA study group",
        "members": [UUID_B],
        "associations": [{"id": UUID_B, "permissions": ["lab_exec"]}],
    }


@respx.mock
async def test_create_group_conflict_error(mcp):
    respx.post(f"{BASE_URL}/groups").mock(
        return_value=httpx.Response(409, json={"description": "Group already exists"})
    )
    text = await call_tool_text(mcp, "cml_create_group", {"name": "CCNA Study Group"})
    assert text.startswith("Error:")
    assert "409" in text


@respx.mock
async def test_delete_group(mcp):
    route = respx.delete(f"{BASE_URL}/groups/{UUID_A}").mock(return_value=httpx.Response(204))
    text = await call_tool_text(mcp, "cml_delete_group", {"group_id": UUID_A})
    assert f"Group {UUID_A} deleted" in text
    assert route.called


@respx.mock
async def test_delete_group_404_error(mcp):
    respx.delete(f"{BASE_URL}/groups/{UUID_A}").mock(return_value=httpx.Response(404))
    text = await call_tool_text(mcp, "cml_delete_group", {"group_id": UUID_A})
    assert text.startswith("Error:")
    assert "404" in text
