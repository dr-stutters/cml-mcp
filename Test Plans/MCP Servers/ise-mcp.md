# Test Plan — ise-mcp server

**Plan ID prefix:** `ISE-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **ise-mcp** server across ISE's three REST surfaces — OpenAPI (443), ERS
(443), MnT (443) — that its tools correctly onboard NADs, manage identities/endpoints,
TrustSec, policy sets, TACACS+ device admin, posture, guest, ANC, certificates, and read
live sessions. **Out of scope:** ISE install/patching, live posture-agent enrollment
(Linux lab clients can't run Secure Client), and load testing.

## 2. System under test

| Item | Value |
|---|---|
| Component | `ise-mcp` (FastMCP + httpx), **184 tools** |
| Verified against | ISE **3.4.0.608** and **3.5.0.527** |
| Environment | Two lab ISE VMs — `198.18.134.30` (3.4), `198.18.134.35` (3.5) (**lab-specific**) |
| Dependencies | Reachable ISE with **ERS enabled** (Admin ▸ Settings ▸ API); for device-admin cases the DeviceAdmin service enabled |

## 3. Test approach / levels

All four levels. `integration_test.py --write` runs ~20 create → verify → delete
round-trips on throwaway objects against a lab ISE only.

## 4. Preconditions & environment

- `.env`: `ISE_URL`, `ISE_USERNAME`, `ISE_PASSWORD`.
- **ERS enabled** on the target (else ERS tools time out — `ise_check_surfaces` reports it).
- Live-session cases (§ MnT) need recent real authentications to return rows.
- `integration_test.py` asserts the server exposes **≥184 tools** before running.

## 5. Test cases

### Surfaces & system health

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-001` | Report reachable surfaces | `ise_check_surfaces` | OpenAPI/ERS/MnT reachability reported accurately | `smoke` |
| `ISE-002` | Version + deployment + license | `ise_version`, `ise_deployment_nodes`, `ise_license_status`, `ise_system_summary` | Version/nodes/license returned without error | `smoke` |

### Network devices (NADs)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-010` | NAD CRUD round-trip | `ise_create_network_device` → `ise_get_network_device_by_name` → `ise_delete_network_device` | NAD created, read back, deleted | `integration --write` (NAD) |
| `ISE-011` | Network device group CRUD | `ise_create_network_device_group` → list → delete | NDG created and removed | `integration --write` (NDG) |

### Identities & groups

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-020` | Internal user CRUD | `ise_create_internal_user` → get → `ise_delete_internal_user` | User created, read, deleted | `integration --write` (internal user) |
| `ISE-021` | Identity group CRUD | `ise_create_identity_group` → list → delete | Group round-trips | `integration --write` (identity group) |
| `ISE-022` | External identity sources (read) | `ise_list_active_directory`, `ise_list_external_radius_servers` | AD join + external RADIUS listed | `smoke` |

### Endpoints (incl. bulk)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-030` | Endpoint CRUD | `ise_create_endpoint` → get → delete | Endpoint round-trips | `integration --write` (endpoint) |
| `ISE-031` | Endpoint group CRUD | `ise_create_endpoint_group` → list → delete | Group round-trips | `integration --write` (endpoint group) |
| `ISE-032` | Bulk create/update/delete (async) | `ise_bulk_create_endpoints` → `ise_get_task_status` → `ise_bulk_delete_endpoints` | Bulk task submitted; status polled to success; deleted | `integration --write` (endpoint bulk) |

### TrustSec (SGT / SGACL / SXP)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-040` | SGT CRUD + update | `ise_create_sgt` → `ise_update_sgt` → delete | SGT created, PUT-updated, deleted | `integration --write` (SGT, SGT update) |
| `ISE-041` | SGACL CRUD | `ise_create_sgacl` → get → delete | SGACL round-trips | `integration --write` (SGACL) |
| `ISE-042` | Egress matrix + IP-SGT (read) | `ise_list_egress_matrix`, `ise_list_ip_sgt_mappings` | Matrix + static bindings listed | `smoke` |
| `ISE-043` | SXP connection CRUD | `ise_create_sxp_connection` → get → delete | SXP peer created, read, removed | `integration --write` (SXP connection) |

### Policy (authZ / allowed protocols / ID sequences)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-050` | Policy set + authZ rule | `ise_create_policy_set_raw` → `ise_create_authz_rule_raw` → delete set | Set + nested rule created, cleaned up | `integration --write` (policy set + authZ rule) |
| `ISE-051` | Authorization profile CRUD | `ise_create_authz_profile` → get → delete | AuthZ profile round-trips | `integration --write` (authZ profile) |
| `ISE-052` | Downloadable ACL CRUD | `ise_create_dacl` → get → delete | dACL round-trips | `integration --write` (dACL) |
| `ISE-053` | Allowed protocols CRUD | `ise_create_allowed_protocols` → get → delete | Allowed-protocols set round-trips | `integration --write` (allowed protocols) |
| `ISE-054` | Identity source sequence CRUD | `ise_create_identity_source_sequence` → get → delete | ID source sequence round-trips | `integration --write` (identity source sequence) |
| `ISE-055` | Policy read introspection | `ise_list_policy_sets`, `ise_get_authentication_rules`, `ise_get_authorization_rules` | Policy sets + rules read back | `smoke` |

### TACACS+ device administration

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-060` | Enable Device Admin service | `ise_node_services` → `ise_enable_device_admin` | DeviceAdmin listed in node services (no-op if already on) | `manual-live` |
| `ISE-061` | TACACS command set CRUD | `ise_create_tacacs_command_set` → get → delete | Command set round-trips | `integration --write` (TACACS command set) |
| `ISE-062` | TACACS profile CRUD | `ise_create_tacacs_profile` → get → delete | Shell/priv profile round-trips | `integration --write` (TACACS profile) |

### Posture, guest, ANC

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-070` | Posture condition→requirement→policy | `ise_create_posture_condition_raw` → `_requirement_raw` → `_policy_raw` → delete | Chain created and cleaned up (config-side) | `manual-live` (#25) |
| `ISE-071` | Guest / sponsor API | `ise_enable_sponsor_rest_access`, `ise_create_guest_user_raw` via sponsor creds | Guest created or documented sponsor-cred limitation | `manual-live` (#25) |
| `ISE-080` | ANC policy CRUD + apply/clear | `ise_create_anc_policy` → `ise_apply_anc` → `ise_clear_anc` → delete | Policy round-trips; quarantine apply/clear on an endpoint | `integration --write` (ANC policy) + `manual-live` (apply/clear) |

### Certificates

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-090` | Trusted-cert import round-trip | `ise_import_trusted_cert` → list → `ise_delete_trusted_cert` | CA imported into trust store, then removed | `integration --write` (trusted cert import) |
| `ISE-091` | System certs + CSR (read/generate) | `ise_list_system_certs`, `ise_list_csrs`, `ise_generate_csr` | Certs/CSRs enumerated; CSR generated for a resolvable CN | `manual-live` |

### Live sessions (MnT, read-only)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `ISE-100` | Active session inventory | `ise_active_sessions`, `ise_active_session_count`, `ise_session_counts` | Live sessions + counts returned | `smoke` |
| `ISE-101` | Session lookup by key | `ise_session_by_mac` / `_by_ip` / `_by_username`, `ise_auth_status_by_mac` | Correct session/auth status for a live endpoint | `manual-live` |
| `ISE-102` | Failure + recent-auth reporting | `ise_failure_reasons`, `ise_recent_authentications` | Failure reasons + recent auth log returned | `manual-live` |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (49 unit); `smoke_test.py` passes;
  `integration_test.py --write` against **ise35** reports no `FAIL` (version/feature `SKIP`s
  are allowed).
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| Surfaces/health | ISE-001…002 | smoke |
| NADs | ISE-010…011 | integration |
| Identities & groups | ISE-020…022 | integration + smoke |
| Endpoints (+bulk) | ISE-030…032 | integration |
| TrustSec | ISE-040…043 | integration + smoke |
| Policy | ISE-050…055 | integration + smoke |
| TACACS+ device admin | ISE-060…062 | integration + manual-live |
| Posture/guest/ANC | ISE-070…080 | integration (ANC) + manual-live |
| Certificates | ISE-090…091 | integration + manual-live |
| Live sessions (MnT) | ISE-100…102 | smoke + manual-live |

Manual-only gaps: DeviceAdmin enable, posture/guest config, ANC apply/clear, CSR/system-cert
binding, and session-by-key lookups (need live authentications).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
