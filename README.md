# cml-mcp

MCP server for **Cisco Modeling Labs (CML 2.x)** — drive network simulation labs
(topologies, nodes, links, consoles, packet captures) from Claude or any MCP client.
Built on the official MCP Python SDK 2.x, stdio transport. Verified against the
CML 2.10 OpenAPI spec.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and network reachability to the CML server.

```bash
cd cml-mcp
uv sync
cp .env.example .env    # then edit: base URL, credentials
make test               # 107 tests, all HTTP mocked — no live CML needed
```

Hook into Claude Code (project `.mcp.json`):

```json
{
  "mcpServers": {
    "cml": {
      "command": "uv",
      "args": ["run", "--directory", "/home/reptar/MCP/cml-mcp", "cml-mcp"]
    }
  }
}
```

Configuration comes from `.env` in the working directory or the environment
(see [.env.example](.env.example)). `CML_MCP_BASE_URL` must include `/api/v0`.
CML's self-signed certificate needs `CML_MCP_VERIFY_TLS=false`.

## Safety model

**Read-only by default.** The 30 read tools are always available; the 21 write
tools (create/start/stop/wipe/delete/conditioning/captures) are not even
registered until `CML_MCP_ENABLE_WRITES=true`. Destructive operations
(wipe/delete/config-overwrite) additionally carry `destructiveHint` so clients
can prompt before running them.

## Tools

79 tools (43 read / 36 write). Highlights first — lifecycle tools **wait for
convergence by default**, so you rarely need to poll.

**Labs** — `cml_list_labs`, `cml_get_lab`, `cml_get_lab_topology`
(`detail='summary'` by default: a compact node/link digest; `'full'` for raw
JSON), `cml_get_lab_element_state`, `cml_get_lab_layer3_addresses`,
`cml_get_lab_events`, `cml_get_lab_simulation_stats`, `cml_export_lab` (YAML),
`cml_get_pyats_testbed`, `cml_get_lab_associations`, `cml_render_topology_svg` (draws the topology as an
SVG from CML's own canvas coordinates) ·
writes: `cml_create_lab`, `cml_update_lab`, `cml_import_lab` (docstring carries a
worked YAML example), `cml_clone_lab`, `cml_start_lab` / `cml_stop_lab`
(`wait=true` by default), `cml_bootstrap_lab` (auto-generate node configs),
`cml_wipe_lab`, `cml_delete_lab` (`force=true` stops+wipes first),
`cml_set_lab_associations` · annotations: `cml_list_annotations`,
`cml_add_annotation`, `cml_delete_annotation`

**Sample labs & snapshots** — `cml_list_sample_labs` + `cml_load_sample_lab`
spin up a curated topology (OSPF, BGP, …) in one call. `cml_snapshot_lab`
extracts every booted node's running config and saves the lab YAML to a file;
`cml_restore_lab` imports one back.

**Nodes** — `cml_list_nodes`, `cml_get_node` (`include_diagnostics=true` returns a
one-call troubleshooting report: state, interfaces flagged admin-down/unconnected,
attached links with **active conditioning called out**, L3 addresses, console
tail), `cml_get_node_interfaces`, `cml_get_node_layer3_addresses`,
`cml_get_node_console_log` · writes: `cml_add_node`, `cml_update_node`,
`cml_set_node_state` (`action='start'|'stop'`, waits by default), `cml_wipe_node`,
`cml_extract_node_configuration`, `cml_delete_node` (`force=true`)

**Links, interfaces & captures** — `cml_list_links`, `cml_get_link`,
`cml_get_link_condition`, `cml_list_interfaces`, `cml_get_interface`,
`cml_get_link_capture_status`, `cml_get_link_capture_packets` (pass `packet_id`
for a single full decode), `cml_download_link_pcap` (Wireshark-ready file) ·
writes: `cml_create_link` (accepts node **labels**, and interface labels with
abbreviations — `src_int_label='Gi0/1'` — or auto-picks a free physical interface), `cml_create_interface`, `cml_delete_interface`, `cml_delete_link`,
`cml_set_link_state` / `cml_set_interface_state` (`action='start'|'stop'` —
failure injection), `cml_set_link_condition` (`action='set'|'clear'`;
delay/jitter/loss/bandwidth — remember `enabled=true`), `cml_set_link_capture`
(`action='start'|'stop'`)

**System** — `cml_get_system_information`, `cml_get_system_health` (also reports
maintenance mode + unacknowledged notices), `cml_get_system_stats`,
`cml_get_resource_usage` (pool quotas vs usage — check here when a node won't
start), `cml_list_node_definitions`, `cml_get_node_definition`,
`cml_list_image_definitions`, `cml_list_external_connectors`, `cml_list_users`,
`cml_list_groups`, `cml_get_licensing`, `cml_get_diagnostics` (controller
internals — `node_launch_queue`/`startup_scheduler` explain a stuck node) ·
writes: `cml_sync_external_connectors`, `cml_update_external_connector` · admin writes: `cml_create_user`,
`cml_delete_user`, `cml_create_group`, `cml_delete_group`

**Convergence** — `cml_wait_for_lab_converged`, `cml_wait_for_node_converged` for
when you need to wait on something started earlier (or with `wait=false`). Both
report progress and treat a timeout as a status, not an error.

**Console (pyATS)** — `cml_run_commands` runs show/ping/traceroute/dir across
**several nodes and commands per call**, returning **genie-parsed JSON** by
default (`output_format='raw'` for text); `cml_send_config` pushes config lines
to one or more nodes; `cml_ping_matrix` builds a full-mesh reachability matrix; `cml_learn_feature`
returns a whole protocol's state (ospf/bgp/interface/…) via genie models.
Connections are cached and reused between calls. Requires the optional extra:
`uv sync --extra console`. These take node **labels**, not UUIDs.

**Prompts** — `cml_troubleshoot_lab`, `cml_build_topology`, `cml_capture_traffic`
are MCP prompt templates that walk an agent through those workflows.

All list tools paginate client-side (`limit`/`offset` — CML returns full
collections) and support `response_format`: `markdown` (default) or `json`.
Oversized JSON responses are truncated structurally, so they stay parseable.

## Development

`make test` (275 tests) · `make lint` · `make run` · `make inspect` (MCP Inspector) ·
`make docker-build`. Layout and conventions: see [CLAUDE.md](CLAUDE.md).

## Note on lab import

`cml_import_lab` parses your topology YAML client-side and sends the JSON
topology object the 2.10 API schema requires — so the `cml_export_lab` →
`cml_import_lab` round trip works regardless of which wire format your CML
build prefers.
