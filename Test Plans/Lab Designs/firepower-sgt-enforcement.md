# Test Plan — Firepower SGT Enforcement (end-to-end acceptance)

**Plan ID prefix:** `SGT-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

End-to-end acceptance of the
[Firepower SGT Enforcement](../../Custom%20Designs/Firepower%20SGT%20Enforcement/) design:
that ISE assigns an SGT at MAB, the IP→SGT binding reaches an FMC-managed FTD **via pxGrid**,
and the FTD's Snort engine enforces an SGT-based access-control policy — **permit Employees /
deny Contractors** to a server. **Out of scope:** the FlexConfig switch→FTD SXP fallback
(historical; feeds LINA only, not Snort), and load testing.

## 2. System under test

| Item | Value |
|---|---|
| Design | Firepower SGT Enforcement |
| Verified against | ISE **3.5**; FMC 10.x + FMC-managed FTDv; cat9000v NAD |
| Environment | CML lab `cb53d7fe` / spec `topology.yaml` (**lab-specific** — FMC `.13`, FTD mgmt `.27`) |
| Dependencies | FMC↔ISE **pxGrid** up (Session Directory + SXP topics); ISE SGTs + IP-SGT bindings; SGT-based ACP deployed |

## 3. Test approach / levels

**Solution acceptance — Manual/Live.** The definitive evidence is FTD `packet-tracer`
(LINA/diagnostic CLI) showing the Snort identity/firewall phases with `src sgt type: sxp`
(pxGrid-learned) and the matched ACP rule id. Supporting state via `ise_*` + `fmc_*` tools.

## 4. Preconditions & environment

- pxGrid integrated and healthy: FMC appears as **Enabled** pxGrid client(s) on ISE;
  Session Directory + **SXP** topics subscribed (SXP carries the IP-SGT bindings to Snort).
- ISE SGTs `Employees(4)` / `Contractors(5)` exist; static IP-SGT bindings map the test IPs.
- ACP deployed with distinct SGT rules; **allow ~5-6 min** for a *new* binding to reach Snort
  via the incremental SXP path (the connect-time set arrives fast via FMC bulk download).

## 5. Test cases

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SGT-001` | ISE assigns SGT at MAB | Endpoint MABs → ISE authZ returns an SGT | ISE MnT session shows the endpoint with `Employees`/`Contractors` SGT | `manual-live` (`ise_session_by_mac`) |
| `SGT-002` | IP-SGT binding reaches FTD via pxGrid | Inspect FTD Snort SGT-IP table after propagation | Binding present; learned as `src sgt type: sxp` (not inline/unknown) | `manual-live` (packet-tracer) |
| `SGT-003` | **Employees → PERMIT** | `packet-tracer input … icmp 10.40.0.10 8 0 10.60.0.10` | Phase 15 SNORT identity `src sgt: 4, type: sxp`; Phase 16 matches rule **268434434** Employees-to-SRV-PERMIT → **ALLOW** | `manual-live` |
| `SGT-004` | **Contractors → DROP** | `packet-tracer input … icmp 10.40.0.11 8 0 10.60.0.10` | `src sgt: 5, type: sxp`; matches rule **268434435** Contractors-to-SRV-DENY → **DROP** | `manual-live` |
| `SGT-005` | Unmapped → default block | packet-tracer from an unmapped source IP | `src sgt: 0` / unknown → default rule **268434432** → Block | `manual-live` |
| `SGT-006` | pxGrid client health | `ise_list_*` / ISE pxGrid Client Management | FMC + its session sub-client **Enabled**; WS_SERVER + PUBSUB healthy | `manual-live` (GUI + tools) |

## 6. Pass/fail & exit criteria

- **Plan pass =** SGT-003 ALLOW **and** SGT-004 DROP both observed, each via
  `src sgt type: sxp` (pxGrid-learned) matching **distinct** ACP rule ids, plus SGT-005
  default block. This is the whole chain: ISE SGT+binding → pxGrid SXP → FMC → FTD Snort →
  SGT-based ACP.
- Contrast the pre-pxGrid failure state where Snort saw `src sgt: 0` and everything hit the
  default BLOCK — that is a FAIL.
- Underlying tool health is covered by the [ise-mcp](../MCP%20Servers/ise-mcp.md) and
  [firepower-mcp](../MCP%20Servers/firepower-mcp.md) server plans.

## 7. Traceability matrix

| Capability | Case IDs | Backlog |
|---|---|---|
| SGT assignment + propagation | SGT-001…002, SGT-006 | #31, #32, #37 |
| Snort SGT enforcement (permit/deny) | SGT-003…005 | #37 |

All cases are manual-live acceptance (no CI gate — require the live FMC/FTD/ISE lab).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
