# Test Plan — ISE NAC Lab (end-to-end acceptance)

**Plan ID prefix:** `NAC-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

End-to-end acceptance of the [ISE NAC Lab](../../Custom%20Designs/ISE%20NAC%20Lab/) design:
that a supplicant authenticating through a Catalyst NAD to ISE is authenticated by the
right method, authorized with the right result (dACL / VLAN / SGT), and that CoA and full
TrustSec CTS provisioning work. **Out of scope:** ISE/AD/CA server internals (covered by the
server test plans), scale, and non-lab identity stores.

## 2. System under test

| Item | Value |
|---|---|
| Design | ISE NAC Lab (runbook + 4 modules) |
| Verified against | ISE **3.4** and **3.5**; cat9000v NAD; `mitchcloud.lab` AD + AD CS |
| Environment | CML lab (**lab-specific** IPs) — cat9000v switch, supplicant (wpa_supplicant), ISE VMs, DC |
| Dependencies | ISE joined to AD; CA trust imported; cat9000v RADIUS uplink on a **global-table** front-panel SVI |

## 3. Test approach / levels

**Solution acceptance — Manual/Live**, driven via the `ise` + `cml` MCP tools and pyATS on
the NAD. Every case is verified **three-sided** (per the runbook): supplicant log, switch
`show access-session`, and ISE MnT session. Component detail lives in the design's
`modules/` (dynamic-authz, trustsec, coa, cts).

## 4. Preconditions & environment

- Lab booted; cat9000v NAD reachable to ISE; supplicant node ready with wpa_supplicant.
- ISE AD join point up; NAD onboarded as a RADIUS client; identity store =
  `All_User_ID_Stores` for durable authN.
- Evidence tools: `ise_session_by_username`/`_by_mac`, `ise_auth_status_by_mac`,
  `pyats_execute` on the switch, `grep CTRL-EVENT-EAP /tmp/wpa.log` on the client.

## 5. Test cases

### Authentication methods

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `NAC-001` | MAB (profiled endpoint) | Connect a non-802.1X endpoint → MAB | Switch `Authorized` via MAB; ISE MnT `passed:1` for the MAC | `manual-live` (#8/#12) |
| `NAC-002` | 802.1X PEAP-MSCHAPv2 vs AD | wpa_supplicant PEAP as an AD user | Client `EAP-SUCCESS`; ISE session shows PEAP + AD identity store; `passed:1` | `manual-live` (#4) |
| `NAC-003` | 802.1X EAP-TLS (cert) | Client presents a `win_sign_csr`-issued cert | Client `EAP-SUCCESS` via EAP-TLS; ISE session shows cert CN | `manual-live` (#5) |

### Authorization results

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `NAC-010` | Dynamic dACL push | AuthZ profile returns a dACL | Switch `show access-session … details` lists the `ACS ACL`; traffic filtered per dACL | `manual-live` (#7) |
| `NAC-011` | Dynamic VLAN assignment | AuthZ profile returns a VLAN | `show access-session` shows the assigned `Vlan`; endpoint lands in it | `manual-live` (#7) |
| `NAC-012` | TrustSec SGT assignment | AuthZ profile returns an SGT | `show access-session` shows the `SGT Value`; ISE session shows the SGT | `manual-live` (#8) |

### Enforcement, CoA, CTS

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `NAC-020` | SGACL enforcement | Traffic between two SGTs with an egress-matrix SGACL | Permitted/denied per the SGACL; switch drop counters match | `manual-live` (#8) |
| `NAC-021` | CoA (Change of Authorization) | `ise_apply_anc` / re-auth triggers CoA | Switch re-authorizes with the new result without a link bounce | `manual-live` (#9) |
| `NAC-022` | Full CTS provisioning | Switch downloads SGACL policy from ISE (`cts refresh`) | `show cts role-based permissions` shows ISE-downloaded policy | `manual-live` (#17) |

## 6. Pass/fail & exit criteria

- **Plan pass =** every case reaches its expected result, confirmed three-sided (supplicant
  + switch + ISE MnT). Any single vantage disagreeing = FAIL for that case.
- Underlying tool health is covered by the [ise-mcp](../MCP%20Servers/ise-mcp.md),
  [windows-mcp](../MCP%20Servers/windows-mcp.md), and [cml-mcp](../MCP%20Servers/cml-mcp.md)
  server plans.

## 7. Traceability matrix

| Capability | Case IDs | Backlog |
|---|---|---|
| AuthN methods (MAB/PEAP/EAP-TLS) | NAC-001…003 | #4, #5, #8, #12 |
| AuthZ results (dACL/VLAN/SGT) | NAC-010…012 | #7, #8 |
| Enforcement/CoA/CTS | NAC-020…022 | #8, #9, #17 |

All cases are manual-live acceptance (no CI gate — require the live lab).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
