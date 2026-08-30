"""Server wiring and write-safety gating across all real tool modules."""

from __future__ import annotations

from cml_mcp.server import build_instructions, build_server

# One representative read tool per module.
READ_TOOLS = {
    "cml_list_labs",
    "cml_list_nodes",
    "cml_list_links",
    "cml_get_system_information",
    "cml_list_sample_labs",
    "cml_get_lab_associations",
    "cml_get_resource_usage",
    "cml_ping_matrix",
}
# Every write tool in the server — keep in sync when adding tools.
WRITE_TOOLS = {
    "cml_create_lab",
    "cml_update_lab",
    "cml_import_lab",
    "cml_clone_lab",
    "cml_load_sample_lab",
    "cml_bootstrap_lab",
    "cml_snapshot_lab",
    "cml_restore_lab",
    "cml_set_lab_associations",
    "cml_add_annotation",
    "cml_delete_annotation",
    "cml_set_link_state",
    "cml_set_interface_state",
    "cml_delete_interface",
    "cml_create_user",
    "cml_delete_user",
    "cml_create_group",
    "cml_delete_group",
    "cml_send_config",
    "cml_start_lab",
    "cml_stop_lab",
    "cml_wipe_lab",
    "cml_delete_lab",
    "cml_add_node",
    "cml_update_node",
    "cml_set_node_state",
    "cml_wipe_node",
    "cml_extract_node_configuration",
    "cml_delete_node",
    "cml_create_link",
    "cml_create_interface",
    "cml_delete_link",
    "cml_set_link_condition",
    "cml_set_link_capture",
}


async def test_write_tools_hidden_by_default(make_settings):
    mcp = build_server(make_settings(enable_writes=False))
    names = {tool.name for tool in await mcp.list_tools()}
    assert READ_TOOLS <= names
    assert not (WRITE_TOOLS & names)


async def test_write_tools_registered_when_enabled(make_settings):
    mcp = build_server(make_settings(enable_writes=True))
    names = {tool.name for tool in await mcp.list_tools()}
    assert READ_TOOLS | WRITE_TOOLS <= names


async def test_every_tool_has_annotations(make_settings):
    mcp = build_server(make_settings(enable_writes=True))
    tools = await mcp.list_tools()
    assert len(tools) >= 50
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is not None, tool.name
        # Read tools must never carry a destructive hint.
        if tool.annotations.read_only_hint:
            assert tool.annotations.destructive_hint is False, tool.name


async def test_destructive_annotations(make_settings):
    mcp = build_server(make_settings(enable_writes=True))
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["cml_delete_lab"].annotations.destructive_hint is True
    assert tools["cml_wipe_node"].annotations.destructive_hint is True
    assert tools["cml_start_lab"].annotations.destructive_hint is False
    assert tools["cml_list_labs"].annotations.read_only_hint is True


def test_instructions_state_write_mode(make_settings):
    assert "READ-ONLY" in build_instructions(make_settings(enable_writes=False))
    assert "ENABLED" in build_instructions(make_settings(enable_writes=True))
