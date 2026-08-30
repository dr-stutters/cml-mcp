# cml-mcp — project guide

MCP server for **Cisco Modeling Labs (CML 2.x)** only. Nothing in this repo
should reference other platforms; cross-platform notes live in
`~/MCP/PLATFORMS.md`, and the reusable template lives in `~/MCP/mcp-skeleton`.

Built on the official MCP Python SDK 2.x (`MCPServer` from
`mcp.server.mcpserver` — **not** the legacy `FastMCP`), stdio transport.

## Layout

| Path | Purpose |
|---|---|
| `src/cml_mcp/server.py` | Assembly: settings → auth → client → tools → prompts |
| `src/cml_mcp/config.py` | Env-driven settings (`CML_MCP_*`) |
| `src/cml_mcp/auth.py` | Auth strategies; CML's flow is wired in `create_auth()` |
| `src/cml_mcp/client.py` | httpx wrapper: retries, backoff, 401 re-auth, concurrency cap |
| `src/cml_mcp/safety.py` | `register_tool()` — annotations + write gating |
| `src/cml_mcp/formatting.py` | markdown/json, pagination envelope, structural truncation |
| `src/cml_mcp/polling.py` | `wait_until()` for convergence waits |
| `src/cml_mcp/prompts.py` | MCP prompt templates |
| `src/cml_mcp/tools/` | One module per API area + `console.py` (pyATS) |
| `tests/` | respx-mocked, no live network |

## Conventions (frozen — match them exactly)

- **Naming**: `cml_{action}_{resource}`. Verb pairs are merged into one tool with
  an `action` parameter (`cml_set_node_state`, `cml_set_link_state`, …).
- **Inputs**: flat `Annotated[type, Field(...)]` params with a description
  (include an example value) and constraints. Never wrap args in a single
  Pydantic model — it buries the schema behind a `$ref`.
- **Outputs**: return `str`. Lists support `response_format` (markdown default /
  json) and `pagination_envelope()`. Every return goes through `finalize()` with
  a `truncation_hint` naming that tool's narrowing parameters.
- **Errors**: never raise out of a tool — `try/except Exception` → `format_error(e)`.
  Pre-flight validation errors return `"Error: ..."` before any HTTP call.
- **Registration**: always `register_tool()`, never `@mcp.tool`. Writes get
  `read_only=False`; only delete/wipe/overwrite-stored-state get `destructive=True`.
- **Write safety on the wire**: the client auto-retries 5xx/transport errors only
  for idempotent methods (429 is always retried). Never pass `retryable=True` on
  a create.
- **Console safety**: anything interpolated into a device command must be
  validated first — a newline is an Enter keypress, i.e. arbitrary config. See
  `_valid_ip` and the command allow-list in `tools/console.py`.
- **stdio discipline**: never `print()`; log via `logging` (stderr).

## CML facts you need

`~/MCP/PLATFORMS.md` holds the full operational knowledge (boot times per node
definition, interface label schemes, the netplan "false-clean fabric" gotcha,
external-connector rules). The essentials:

- `base_url` **includes** `/api/v0`. Auth: `POST /authenticate` with a JSON
  credential body; the response body **is** the JWT.
- **No server-side pagination** — endpoints return full collections; use
  `data=true` (`with_data=true` on `GET /labs`) for objects and paginate
  client-side.
- **Ordering rules**: a node must be stopped **and wiped** before `DELETE`, even
  if never started. Lab wipe requires the lab stopped. `force=true` on the
  delete tools performs the sequence (waiting for the async stop).
- Interfaces added to an already-running node come up `STOPPED` while the link
  reports `STARTED` — check both before blaming device config.
- Loopbacks cannot be linked; only physical interfaces.
- Day-0 `configuration` is polymorphic: a string **or** a list of
  `{name, content}` files (use `config_files`).

## Working here

```bash
make test     # pytest, all HTTP mocked
make lint     # ruff
make run      # start on stdio
```

Live verification against a real controller needs `.env` (gitignored) and is the
only way to prove integration — unit tests mock every response. When you learn
something new about CML's behaviour live, write it into the relevant tool
docstring **and** `~/MCP/PLATFORMS.md`.
