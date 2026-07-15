# Test Plan — firepower-mcp server

**Plan ID prefix:** `FMC-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **firepower-mcp** server: that its tools correctly drive the Cisco Secure
Firewall Management Center (FMC) REST API to register/deploy FTD devices, configure
interfaces/VTIs/loopbacks/objects, build site-to-site & SD-WAN (AUTO_VPN) topologies,
configure routing (BGP/OSPF/EIGRP), manage FTD HA pairs, and read access-control policies.
**Out of scope:** FMCv/FTDv install, Snort rule authoring, and load testing. The FMC config
API is huge and schema-driven, so the spec-search/`fmc_api_call` escape hatch is a
first-class tested capability.

## 2. System under test

| Item | Value |
|---|---|
| Component | `firepower-mcp` (FastMCP + httpx), ~50 tools |
| Verified against | FMC 10.x managing FTDv (**lab-specific** — e.g. FMC `198.18.128.13`, FTD mgmt `.27`) |
| Environment | Live FMCv + registered FTDv in CML |
| Dependencies | FMC reachable + licensed; FTD registered (TCP 8305 up) before device config |

## 3. Test approach / levels

Unit + smoke are the automated levels; **write paths are exercised manual-live** through
the `firewall-engineer` agent and the CML `firepower_e2e` suite (two-mode day-0), and are
proven end-to-end by the [Firewall SD-WAN](../Lab%20Designs/firewall-sdwan.md) and
[Firepower SGT Enforcement](../Lab%20Designs/firepower-sgt-enforcement.md) lab-design plans.

## 4. Preconditions & environment

- `.env` / env: `FMC_URL`, `FMC_USERNAME`, `FMC_PASSWORD`.
- FMC API reachable; the target FTD **registered and healthy** before interface/routing/VPN
  cases (registration gates on TCP **8305**, not the API being reachable).
- After config changes, `fmc_deploy` the affected device.

## 5. Test cases

### Connectivity & discovery

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-001` | Server reachable + version/domains | `fmc_server_version`, `fmc_domains`, `fmc_license_status` | Version/domains/license returned | `smoke` |
| `FMC-002` | Spec-driven schema discovery | `fmc_search_spec("vti")` → `fmc_get_definition` | Matching endpoints + exact model fields/enums returned | `unit` (test_client_unit) |
| `FMC-003` | Raw API escape hatch | `fmc_api_call(GET, /devicerecords)` | Passthrough returns raw JSON | `unit` |

### Devices

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-010` | List/get devices + health | `fmc_list_devices`, `fmc_get_device`, `fmc_device_health` | Devices enumerated with status | `smoke` |
| `FMC-011` | Register / delete FTD | `fmc_register_device` → poll → `fmc_delete_device` | FTD registers (gated on 8305) and can be removed | `manual-live` (firepower_e2e, firewall-engineer) |
| `FMC-012` | Deploy pending changes | `fmc_deployable_devices` → `fmc_deploy` | Deployment submitted and completes | `manual-live` |

### Interfaces & objects

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-020` | Physical interfaces read/update | `fmc_list_physical_interfaces`, `fmc_update_physical_interface` | Interfaces listed; update accepted | `manual-live` |
| `FMC-021` | VTI + loopback CRUD | `fmc_create_vti`/`fmc_create_loopback` → list → delete | VTI/loopback created and removed | `manual-live` (SD-WAN plan) |
| `FMC-022` | Network objects CRUD | `fmc_create_object` → `fmc_list_objects` → `fmc_delete_object` | Object round-trips | `manual-live` |
| `FMC-023` | Security zones (read) | `fmc_list_security_zones` | Zones enumerated | `smoke` |

### VPN / SD-WAN

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-030` | AUTO_VPN (SD-WAN) topology | `fmc_create_auto_vpn_topology` → `fmc_list_s2s_topologies` | Hub-spoke auto-VPN provisioned via REST | `manual-live` (SD-WAN plan) |
| `FMC-031` | S2S topology + endpoints | `fmc_create_s2s_topology`, `fmc_add_endpoint` → get → delete | Topology + endpoints created and removed | `manual-live` |

### Routing

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-040` | BGP enable/create/read/delete | `fmc_enable_bgp`, `fmc_create_bgp`, `fmc_get_bgp`, `fmc_delete_bgp` | iBGP overlay configured and readable | `manual-live` (SD-WAN plan) |
| `FMC-041` | OSPF / EIGRP CRUD | `fmc_create_ospf`/`fmc_create_eigrp` → get → delete | IGP config round-trips | `manual-live` |

### High availability

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-050` | Form / inspect / break HA | `fmc_form_ha` → `fmc_get_ha_pair` → `fmc_break_ha` | Active/standby pair forms, reports state, breaks cleanly | `manual-live` (firewall-engineer) |

### Access control

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `FMC-060` | Access-control policy read | `fmc_list_access_policies`, `fmc_get_access_policy` | Policies + rules returned (incl. SGT conditions) | `smoke` + `manual-live` (SGT plan) |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (6 unit); `smoke_test.py` passes.
- **Manual/live gate:** device/interface/VPN/routing/HA cases proven via the firewall-engineer
  agent and the two FTD lab-design plans, with FMC deploy succeeding and traffic/adjacency
  evidence captured.
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| Connectivity/discovery | FMC-001…003 | smoke + unit |
| Devices | FMC-010…012 | smoke + manual-live |
| Interfaces/objects | FMC-020…023 | smoke + manual-live |
| VPN/SD-WAN | FMC-030…031 | manual-live |
| Routing | FMC-040…041 | manual-live |
| HA | FMC-050 | manual-live |
| Access control | FMC-060 | smoke + manual-live |

Manual-only gaps: all write paths (register/deploy/interface/VPN/routing/HA) — no
`integration_test.py` in this repo; validated via agents + the FTD lab-design plans.

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
