# Test Plan — Wireless NAC (end-to-end acceptance)

**Plan ID prefix:** `WLNAC-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

End-to-end acceptance of the [Wireless NAC](../../Custom%20Designs/Wireless%20NAC/) design,
which proves wireless 802.1X to ISE **two separate ways** in CML: (1) the **C9800 config
path** (controller fully configured for WPA2-Enterprise to ISE, AAA reachability proven with
`test aaa`) and (2) the **live wireless path** (hostapd AP + wpa_supplicant client doing real
EAP over the shared RF medium to ISE). **Out of scope:** CAPWAP AP join to the C9800 (not
possible in CML — hostapd ≠ CAPWAP), RF performance.

## 2. System under test

| Item | Value |
|---|---|
| Design | Wireless NAC |
| Verified against | C9800-CL IOS-XE **17.18**; hostapd AP + wpa_supplicant; ISE **3.5** |
| Environment | CML lab (**lab-specific**) — C9800 `198.18.128.70`, hostapd NAS `198.18.128.71` |
| Dependencies | Two ISE NADs (C9800 + hostapd), both → ISE 3.5; external connectors STARTED |

## 3. Test approach / levels

**Solution acceptance — Manual/Live**, via the `wlc` + `ise` MCP tools and pyATS/CLI on the
hostapd + client nodes. The two paths are independent (the controller and the live client
never meet in CML).

## 4. Preconditions & environment

- C9800 mgmt IP on the **`Vlan1` SVI** (+ default route); `wlc_check` returns 200 (RESTCONF
  up — it lags the boot by minutes).
- Both NADs onboarded in ISE (different source IPs); a test identity `wifiuser` exists.
- External connectors STARTED (else no path to ISE/host).

## 5. Test cases

### Path 1 — C9800 config path

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLNAC-001` | Controller reachable via RESTCONF | `wlc_check`, `wlc_device_info` | 200; IOS-XE 17.18 reported | `manual-live` |
| `WLNAC-002` | WPA2-Enterprise WLAN present | `wlc_list_wlans` | `nac-corp` dot1x WLAN configured | `manual-live` (#19) |
| `WLNAC-003` | AAA/RADIUS → ISE wired | `wlc_list_radius_servers`, `wlc_list_aaa` | RADIUS server = ISE 3.5; AAA group + dot1x method list bound | `manual-live` |
| `WLNAC-004` | Controller onboarded as ISE NAD | `ise_list_network_devices` | `WLC-1-c9800` present as a RADIUS client | `manual-live` |
| `WLNAC-005` | Live AAA probe from the controller | `test aaa group ISE-GROUP wifiuser … new-code` (pyATS) | "User successfully authenticated" | `manual-live` (#19) |

### Path 2 — Live wireless (hostapd ↔ wpa_supplicant)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLNAC-010` | Client associates + authenticates | client `wpa_cli status` | State = `COMPLETED` (EAP over RF succeeded) | `manual-live` (#19) |
| `WLNAC-011` | Authenticator sees Access-Accept | hostapd log | `Access-Accept` / `EAP-SUCCESS` for `wifiuser` | `manual-live` |
| `WLNAC-012` | ISE recorded the wireless auth | `ise_session_by_username("wifiuser")` | ISE MnT session from the hostapd NAS, `passed:1` | `manual-live` |

## 6. Pass/fail & exit criteria

- **Path 1 pass =** WLNAC-001…005 all pass (controller fully configured + `test aaa` accept).
- **Path 2 pass =** WLNAC-010…012 all pass (client COMPLETED + ISE session recorded).
- **Plan pass =** both paths pass. (CML wireless is a 2.10 beta — Path 2 is the higher-risk
  part; Path 1 is deterministic.)
- Underlying tool health is covered by the [wlc-mcp](../MCP%20Servers/wlc-mcp.md) and
  [ise-mcp](../MCP%20Servers/ise-mcp.md) server plans.

## 7. Traceability matrix

| Capability | Case IDs | Backlog |
|---|---|---|
| C9800 config path | WLNAC-001…005 | #19 |
| Live wireless 802.1X | WLNAC-010…012 | #19 |

All cases are manual-live acceptance (no CI gate — require the live lab + RF medium).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
