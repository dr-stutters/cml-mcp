# Test Plan — cml-mcp server

**Plan ID prefix:** `CML-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **cml-mcp** server: that its tools correctly drive the Cisco Modeling Labs
REST API to create/inspect/control labs, nodes, links, interfaces; run pyATS against node
consoles; and compile/round-trip declarative topology-as-code specs. **Out of scope:** the
correctness of guest-node OS configuration (covered by the lab-design plans), CML server
install, and load/scale testing.

## 2. System under test

| Item | Value |
|---|---|
| Component | `cml-mcp` (FastMCP + httpx + pyATS), ~90 tools |
| Verified against | CML 2.x controller at `198.18.128.10` (**lab-specific**) |
| Environment | Live CML controller; guest images incl. IOSv, IOL, ftdv, cat9000v |
| Dependencies | Reachable CML API; valid `CML_*` creds; images available on a compute host |

## 3. Test approach / levels

Standard four levels (see [library README](../README.md#test-levels)). CML has the richest
live coverage: unit + smoke + **three e2e suites** (no single `integration_test.py`).

## 4. Preconditions & environment

- `.env`: `CML_URL`, `CML_USERNAME`, `CML_PASSWORD` (+ `CML_VERIFY_SSL`).
- The controller has enough capacity/images for the e2e scratch labs (IOSv, ftdv).
- e2e suites **create and delete their own scratch labs** — they never touch existing labs.

## 5. Test cases

### Lab lifecycle

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `CML-001` | Create → inspect → delete a lab | `create_lab` → `get_lab` → `delete_lab` | Lab created with returned UUID; details echo title/state; delete removes it | `smoke` (smoke_test.py) |
| `CML-002` | List labs / server inventory | `list_labs`, `list_all_running_nodes` | Returns labs with ids/state without error | `smoke` |
| `CML-003` | Lab control (start/stop/wipe) | `control_lab(start)` then `stop`/`wipe` | State transitions reported via `get_lab_state`; convergence flag present | `manual-live` (pyats_e2e boots a lab) |
| `CML-004` | Export a lab to topology YAML | `export_lab` | Returns valid CML YAML for the built lab | `smoke` |

### Nodes / interfaces / links

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `CML-010` | Add nodes + link them | `add_node` ×2 → `create_link` | Two nodes + a link created; ids returned; appear in `list_nodes`/`list_links` | `smoke` (2 IOSv linked) |
| `CML-011` | Node state / boot wait | `get_node_state` until `BOOTED` | Reports DEFINED→STOPPED→STARTED→BOOTED with convergence | `manual-live` (pyats_e2e) |
| `CML-012` | Interface add + state | `create_interface`, `list_interfaces`, `set_interface_state` | Interface added; STOPPED→STARTED transition observable | `unit` (test_client_unit) + `manual-live` |
| `CML-013` | Extract running config | boot a node → `extract_node_configuration` | Running config saved back into the topology | `manual-live` (pyats_e2e) |
| `CML-014` | Console log / key | `get_node_console_log`, `get_node_console_key` | Boot log tail + console key returned | `manual-live` |

### pyATS (console automation)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `CML-020` | Exec command on a node | `pyats_execute("show version")` | Command output returned from the live console | `manual-live` (pyats_e2e) |
| `CML-021` | Parse structured output | `pyats_parse("show ip interface brief")` | Genie-parsed dict returned | `manual-live` (pyats_e2e) |
| `CML-022` | Push config | `pyats_configure` | Config applied; verifiable on re-read | `manual-live` (pyats_e2e) |
| `CML-023` | Learn a feature model | `pyats_learn("interface")` | Genie learn model returned | `manual-live` (pyats_e2e) |
| `CML-024` | Session reuse/listing | `pyats_sessions` | Open console sessions listed | `manual-live` (pyats_e2e) |

### Topology-as-code

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `CML-030` | Validate a spec (offline + live names) | `validate_lab_spec(<yaml>)` | `valid: true` for a good spec; errors listed for a bad one | `unit` (test_labspec_unit, 22) |
| `CML-031` | Build a lab from a spec | `build_lab_from_spec` | Nodes/links/annotations/briefs created in one call; lab_id returned | `manual-live` (labspec_e2e) |
| `CML-032` | Export a live lab back to a spec | `export_lab_spec` | Concise spec YAML reproduces the topology | `manual-live` (labspec_e2e) |
| `CML-033` | Spec → lab → spec → lab round-trip | build → export → rebuild → delete both | Rebuilt lab matches; both scratch labs cleaned up | `manual-live` (labspec_e2e) |

### System / definitions / raw

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `CML-040` | System status + licensing | `get_system_status`, `get_licensing_status` | Health + license state returned | `smoke` |
| `CML-041` | Node/image definitions | `list_node_definitions`, `list_image_definitions` | Definitions enumerated | `smoke` |
| `CML-042` | L3 address discovery / testbed | `get_lab_layer3_addresses`, `get_pyats_testbed` | Discovered IPs + valid pyATS testbed YAML | `manual-live` |
| `CML-043` | Raw API escape hatch | `cml_api_call(GET,/labs)` | Passthrough returns raw JSON; object-body POSTs accepted | `unit` (test_client_unit) |
| `CML-044` | Firepower two-mode day-0 | build FTD-L (ManageLocally) + FTD-M (FmcIp) | Both boot; local FDM vs FMC-managed day-0 honoured | `manual-live` (firepower_e2e) |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (33 unit tests); `smoke_test.py` prints its
  success line; the three e2e suites complete and self-clean.
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| Lab lifecycle | CML-001…004 | smoke + manual-live |
| Nodes/interfaces/links | CML-010…014 | smoke + unit + manual-live |
| pyATS | CML-020…024 | manual-live (pyats_e2e) |
| Topology-as-code | CML-030…033 | unit(22) + manual-live (labspec_e2e) |
| System/definitions/raw | CML-040…044 | smoke + unit + manual-live (firepower_e2e) |

Manual-only gaps: live pyATS/boot cases are e2e-scripted but not part of the CI gate
(require a live controller).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
