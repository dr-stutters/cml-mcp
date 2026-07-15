# Test Plan — splunk-mcp server

**Plan ID prefix:** `SPL-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **splunk-mcp** server: that its tools correctly drive Splunk Enterprise's
REST management API (8089) and the HTTP Event Collector (HEC, 8088) to manage indexes, data
inputs (syslog), HEC tokens, run SPL, install/enable add-ons and dashboards, manage users/
roles, and generate synthetic lab telemetry. **Out of scope:** Splunk install/clustering,
premium-app licensing, and load testing.

## 2. System under test

| Item | Value |
|---|---|
| Component | `splunk-mcp` (FastMCP + httpx), **47 tools** |
| Verified against | Splunk Enterprise 10.x (**lab-specific** — ubuntu-KVM `198.18.128.51:8089`) |
| Environment | Splunk running as a CML node; Cisco/Windows add-ons installed |
| Dependencies | Mgmt API reachable; HEC enabled + a token for ingest cases |

## 3. Test approach / levels

Unit + smoke are the automated levels (the smoke test includes a live index create→delete
round-trip). Ingest/HEC/telemetry cases are exercised manual-live (they mutate data).

## 4. Preconditions & environment

- `.env`: `SPLUNK_URL` (`:8089`), `SPLUNK_USERNAME`, `SPLUNK_PASSWORD`, `SPLUNK_VERIFY_SSL`;
  optional `SPLUNK_HEC_URL` (`:8088`), `SPLUNK_HEC_TOKEN`.
- HEC enabled (`splunk_enable_hec`) with a token before HEC/telemetry cases.
- CML Docker Splunk node is capped at **1 CPU** — use the KVM box for real search load.

## 5. Test cases

### System & health

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-001` | Reachability (mgmt + HEC) | `splunk_check` | Reports 8089 + 8088 reachability | `smoke` |
| `SPL-002` | Server info / health / licensing | `splunk_server_info`, `splunk_health`, `splunk_licensing` | Version/health/license returned | `smoke` |

### Search

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-010` | One-shot SPL | `splunk_search("| rest /services/server/info")` | Results returned as JSON | `smoke` |
| `SPL-011` | Async search job | `splunk_search_job` → `_status` → `_results` | Job created, polled, results fetched | `unit` (test_client_unit) + `manual-live` |
| `SPL-012` | Saved searches | `splunk_list_saved_searches`, `splunk_create_saved_search` | Saved search created and listed | `manual-live` |

### Indexes

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-020` | Index CRUD round-trip | `splunk_create_index` → `splunk_get_index` → `splunk_delete_index` | Index created, read, deleted | `smoke` (create→delete round-trip) |
| `SPL-021` | List indexes | `splunk_list_indexes` | `cisco`/`ise`/`windows` + internal indexes listed | `smoke` |

### Ingest — inputs & HEC

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-030` | Syslog UDP/TCP input | `splunk_create_udp_input(514)` → `splunk_list_inputs` → `splunk_delete_input` | Input created feeding the target index, then removed | `manual-live` |
| `SPL-031` | HEC enable + token + event | `splunk_enable_hec` → `splunk_create_hec_token` → `splunk_send_hec_event` → search | Event lands in the index (`Authorization: Splunk <token>`) | `manual-live` |

### Apps / dashboards

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-040` | List/get apps | `splunk_list_apps`, `splunk_get_app` | Installed add-ons (Cisco ISE, Cisco Security Cloud, MS Windows) listed | `smoke` |
| `SPL-041` | Install + enable add-on | `splunk_install_app(<.tgz>)` → `splunk_enable_app` | Add-on installed and enabled | `manual-live` |
| `SPL-042` | Dashboards | `splunk_list_dashboards`, `splunk_get_dashboard` | Prebuilt dashboards enumerated | `smoke` |

### Access control

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-050` | Users / roles | `splunk_list_users`, `splunk_list_roles`, `splunk_create_user` → `splunk_delete_user` | Users/roles listed; user round-trips | `unit` + `manual-live` |

### Telemetry generator & escape hatch

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SPL-060` | List telemetry profiles | `splunk_list_telemetry_profiles` | 5 profiles (ios/ise_auth/ise_acct/asa/windows) returned | `unit` |
| `SPL-061` | Generate synthetic telemetry | `splunk_generate_telemetry(profile="ise_auth", seed=1)` → `splunk_search index=ise host=sim-*` | Backfilled `sim-` events land in the right sourcetype/index; deterministic with `seed` | `unit` (determinism) + `manual-live` (ingest) |
| `SPL-070` | REST escape hatch | `splunk_rest_call(GET,/services/server/info)` + `splunk_list_endpoints` | Passthrough returns Atom-unwrapped JSON | `unit` |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (21 unit); `smoke_test.py` passes (incl. the
  index create→delete round-trip).
- **Manual/live gate:** ingest/HEC/telemetry cases land events verifiable by SPL search.
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| System/health | SPL-001…002 | smoke |
| Search | SPL-010…012 | smoke + unit + manual-live |
| Indexes | SPL-020…021 | smoke |
| Ingest (inputs/HEC) | SPL-030…031 | manual-live |
| Apps/dashboards | SPL-040…042 | smoke + manual-live |
| Access control | SPL-050 | unit + manual-live |
| Telemetry/escape hatch | SPL-060…070 | unit + manual-live |

Manual-only gaps: syslog inputs, HEC ingest, add-on install, and live telemetry landing
(all mutate/ingest data — proven in the observability epic, not in the CI gate).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
