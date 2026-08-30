# MCP Server Template — Specialization Playbook

This directory is a **copy-template** for building dedicated Cisco platform MCP
servers (official MCP Python SDK 2.x / `MCPServer`, stdio transport). If you are Claude and this file is
in your context, your job is to turn this template into a **complete, tested MCP
server for one platform**. Follow this playbook top to bottom.

## Step 0 — Inputs you need

Ask the user (or confirm from their request):
1. Which platform? (CML, Secure Firewall/FMC, ISE, Catalyst Center, or other)
2. Platform version if known (affects available APIs).
3. Which API areas matter most to them (e.g. "labs and nodes", "access policies",
   "network devices"). Default: comprehensive read coverage of the core object
   model, plus the obviously useful writes.

## Step 1 — Specialize the naming

From a fresh copy of this template, run:

```bash
python3 scripts/specialize.py <service>    # e.g. cml, fmc, ise, catalyst
```

This renames the package (`cml_mcp` → `<service>_mcp`), the console script,
the env prefix (`CML_MCP_` → `<SERVICE>_MCP_`), and the tool-name prefix,
across all files. Verify with `make test` — the suite must still pass after the
rename, before you change any logic.

## Step 2 — Research the platform API

Use the cheatsheet below as your starting map, but **verify against the live
platform docs** (auth endpoint paths and pagination rules occasionally change
between versions). Identify:
- auth flow (endpoint, token lifetime, refresh behavior)
- base path conventions and required headers
- pagination scheme and its limits
- the core object model (what agents will actually ask about)
- rate limits

## Step 3 — Implement auth

Edit `create_auth()` in `server.py`. The strategies in `auth.py` cover most
cases via configuration; subclass `LoginTokenAuth` only when the platform needs
extra session state. Delete the placeholder default once the real strategy is in.

## Step 4 — Implement tools

Replace `tools/example_widgets.py` with one module per API area (e.g.
`tools/devices.py`, `tools/policies.py`). Add each to `ALL_MODULES` in
`tools/__init__.py`. Non-negotiable conventions (the example module demonstrates
all of them):

- **Naming**: `{service}_{action}_{resource}` snake_case — `cml_list_labs`,
  `fmc_get_access_policy`. Action verbs: list/get/search/create/update/delete/start/stop.
- **Coverage**: prioritize comprehensive read coverage of the core object model;
  add workflow tools only where a single API call can't answer a natural request.
- **Inputs**: FLAT function parameters — every argument is
  `Annotated[type, Field(...)]` with a description (include an example value)
  and constraints (`ge`, `le`, `max_length`). Never wrap arguments in a single
  Pydantic model: it buries the schema behind a `$ref`, forces agents to nest
  arguments under one key, and turns their most common mistake (sending flat
  arguments) into a raw validation error that bypasses `format_error()`.
- **Outputs**: return `str`. List tools support `response_format`
  (markdown default / json) and the `pagination_envelope()`. Every return passes
  through `finalize()`.
- **Errors**: never raise out of a tool. Wrap the body in
  `try/except Exception` and return `format_error(e)`. Add platform-specific
  hints to `errors.py` when a status code has a platform-specific meaning
  (e.g. FMC 429 = 120 req/min limit).
- **Registration**: always through `register_tool()` (never `@mcp.tool`
  directly) so annotations and write-gating stay enforced. Writes get
  `read_only=False`; deletes/overwrites also get `destructive=True`.
- **Write safety on the wire**: ApiClient auto-retries 5xx/transport errors only
  for idempotent methods (429 is always retried). If a specific POST is safe to
  re-send on this platform, pass `retryable=True` explicitly; otherwise keep the
  default so a lost response can't duplicate a create or deployment.
- **Docstrings**: full pattern from the example module — what it does, when to
  use it (and when not to), args, return schema, error meanings.
- **Pagination**: adapt to the platform scheme (see cheatsheet) but always
  present the standard envelope to the agent.
- **stdio discipline**: never `print()`; log via `logging` (goes to stderr).

Also update `build_instructions()` in `server.py`: describe the platform, ID
conventions, and any object-model quirks the agent needs.

## Step 5 — Tests

Mirror the existing test layout; all HTTP mocked with respx, zero live network.
Required per tool: one happy-path test through `call_tool_text()` (this
validates the input schema too) and one error-path test. Keep the auth flow
tests updated for the real strategy. `make test` and `make lint` must pass.

## Step 6 — Docs and config

- `.env.example`: real variable names for this platform, with comments.
- `README.md`: platform-specific quickstart, tool list, required account
  privileges (e.g. ISE needs ERS enabled; FMC wants a dedicated API user).
- `pyproject.toml`: update `description`.

## Step 7 — Definition of done

- [ ] `make test` and `make lint` pass; server starts: `uv run <service>-mcp`
      with a configured `.env` (or fails fast with a clear config error)
- [ ] `npx @modelcontextprotocol/inspector uv run <service>-mcp` lists the tools
- [ ] every tool: register_tool + annotations + docstring + tests
- [ ] write tools invisible unless `<SERVICE>_MCP_ENABLE_WRITES=true`
- [ ] no secrets in code, logs, or error messages; no `print()` anywhere
- [ ] example_widgets module deleted

---

# Cisco Platform Cheatsheet

Working notes from prior research. **Trust but verify against the target
version's docs** — especially auth paths and pagination limits.

## Cisco Modeling Labs (CML)

- **Base**: `https://<cml>` — API lives under `/api/v0/`.
  Suggested `base_url` = host root; put `/api/v0` in tool paths.
- **Auth**: `POST /api/v0/authenticate` with JSON `{"username", "password"}` →
  response body is the JWT as a bare JSON string. Send as
  `Authorization: Bearer <token>`. Validate with `GET /api/v0/authok`.
  → `LoginTokenAuth(login_style="json", token_location="body")`.
- **Model**: labs → nodes → interfaces → links. Lab topology, node state
  (start/stop/wipe), console lines. Useful reads: `/labs`, `/labs/{id}`,
  `/labs/{id}/nodes`, node state.
- **Notes**: self-signed certs are the norm (`VERIFY_TLS=false` in labs).
  The official Python client is `virl2_client` — prefer raw REST here for
  consistency with this template.

## Cisco Secure Firewall Management Center (FMC)

- **Base**: `https://<fmc>` — config API under
  `/api/fmc_config/v1/domain/{domainUUID}/...`.
- **Auth**: `POST /api/fmc_platform/v1/auth/generatetoken` with HTTP Basic →
  tokens in **response headers** `X-auth-access-token` / `X-auth-refresh-token`;
  domain UUID(s) in the `DOMAIN_UUID`/`DOMAINS` response headers. Token lives
  ~30 min; refresh via `/auth/refreshtoken` (max 3), then re-login.
  → subclass `LoginTokenAuth(login_style="basic", token_location="header",
  token_field="X-auth-access-token", auth_header="X-auth-access-token",
  auth_scheme=None)` and capture the domain UUID in `_on_login_response()`;
  tools need it to build paths.
- **Pagination**: `?offset=&limit=` (limit ≤ 1000); response `paging` object.
  Add `?expanded=true` for full objects instead of references.
- **Rate limit**: ~120 requests/min per token → expect 429s; the client's
  backoff handles this, keep `max_concurrent_requests` low.
- **Model**: access policies → access rules; network/port objects; devices;
  NAT; deployments (deploy is a heavyweight write — mark destructive).

## Cisco Identity Services Engine (ISE)

- **ERS API**: `https://<ise>:9060/ers/config/...`, HTTP **Basic per request**
  (`BasicAuth`), needs `Accept`/`Content-Type: application/json`. ERS must be
  enabled (Administration → Settings → API Settings) and the account needs the
  ERS admin/operator role.
- **OpenAPI (ISE 3.1+)**: `https://<ise>/api/v1/...`, also Basic. Prefer it
  where it covers the resource; fall back to ERS elsewhere. Note the two APIs
  have different ports/paths — you may need two ApiClients or full URLs.
- **Pagination (ERS)**: `?page=&size=` (size ≤ 100); responses are
  `SearchResult` with `resources[]` + `nextPage` link. Filtering:
  `?filter=name.CONTAINS.foo`.
- **Model**: network devices, endpoints, identity groups, internal users,
  authorization profiles, policy sets (OpenAPI), TrustSec SGTs.

## Cisco Catalyst Center (formerly DNA Center)

- **Auth**: `POST /dna/system/api/v1/auth/token` with HTTP Basic → JSON
  `{"Token": "..."}`. Send as `X-Auth-Token` header; token lives ~1 hour.
  → `LoginTokenAuth(login_style="basic", token_location="json",
  token_field="Token", auth_header="X-Auth-Token", auth_scheme=None)`.
- **Base**: `/dna/intent/api/v1/...` for intent APIs.
- **Pagination**: `?offset=&limit=` — **offset is 1-based**, limit commonly ≤ 500.
- **Async writes**: many POST/PUT return a `taskId` → poll
  `/dna/intent/api/v1/task/{taskId}` until completion; write tools should poll
  (with a timeout) and report the final task status, not the taskId.
- **Model**: network devices, sites, clients, interfaces, templates,
  command runner (read-ish but executes on devices — gate it as a write),
  SDA fabric, assurance issues/health.
