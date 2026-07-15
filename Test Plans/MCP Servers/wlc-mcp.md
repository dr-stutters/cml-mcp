# Test Plan — wlc-mcp server

**Plan ID prefix:** `WLC-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **wlc-mcp** server: that its tools correctly drive a Cisco Catalyst 9800
Wireless LAN Controller over RESTCONF (IOS-XE YANG) to manage WLANs, AAA/RADIUS to ISE,
policy/site/RF tags, and read client/AP operational state. **Out of scope:** live CAPWAP AP
join (CML's hostapd AP can't join a C9800 — see the note below), RF planning, and load
testing.

## 2. System under test

| Item | Value |
|---|---|
| Component | `wlc-mcp` (FastMCP + httpx), ~24 tools |
| Verified against | C9800-CL on IOS-XE **17.18** (CML) (**lab-specific**) |
| Environment | Live C9800 with RESTCONF up (nginx yang-management can lag boot by minutes) |
| Dependencies | `aaa new-model` + priv-15 user + `ip http secure-server` + `restconf`; mgmt IP on `Vlan1` SVI |

## 3. Test approach / levels

Unit + smoke are the automated levels. Config writes (WLAN/RADIUS/tags) are exercised
manual-live and are proven end-to-end by the
[Wireless NAC](../Lab%20Designs/wireless-nac.md) lab-design plan. **CML caveat:** the `*-oper`
client/AP tools return empty in CML (no CAPWAP join), so those are read-shape-only.

## 4. Preconditions & environment

- `.env`: `WLC_URL`, `WLC_USERNAME`, `WLC_PASSWORD`, `WLC_VERIFY_SSL`.
- `wlc_check` passes (RESTCONF answers) before any other case — nginx lags the boot.

## 5. Test cases

### System

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLC-001` | RESTCONF readiness | `wlc_check` | Reports RESTCONF up (or "not ready yet" honestly) | `smoke` |
| `WLC-002` | Device info + models | `wlc_device_info`, `wlc_list_models` | IOS-XE version + YANG module list returned | `smoke` |

### WLANs

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLC-010` | List / get WLANs | `wlc_list_wlans`, `wlc_get_wlan` | Configured WLANs enumerated with details | `smoke` |
| `WLC-011` | Create / delete dot1x WLAN | `wlc_create_wlan_dot1x("corp")` → get → `wlc_delete_wlan` | WPA2-Enterprise WLAN created and removed | `manual-live` (Wireless NAC plan) |

### AAA / RADIUS → ISE

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLC-020` | RADIUS server + AAA group | `wlc_create_radius_server` → `wlc_create_aaa_radius_group` → `wlc_list_radius_servers` | RADIUS server pointing at ISE + AAA group created | `manual-live` (Wireless NAC plan) |
| `WLC-021` | dot1x method list | `wlc_create_dot1x_method_list` → `wlc_list_aaa` | Method list bound to the AAA group | `manual-live` |

### Policy / tags

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLC-030` | Policy profile + policy tag | `wlc_create_policy_profile` → `wlc_create_policy_tag` → list → delete | Profile/tag map the WLAN to its policy | `manual-live` |
| `WLC-031` | Site / AP-join / RF tags (read) | `wlc_list_site_tags`, `wlc_list_ap_join_profiles`, `wlc_list_rf_tags` | Tag sets enumerated | `smoke` |

### Monitoring & escape hatch

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WLC-040` | Client/AP oper state (shape) | `wlc_wireless_clients`, `wlc_access_points`, `wlc_ap_radios` | Returns valid (empty in CML — no CAPWAP join) without error | `smoke` |
| `WLC-050` | RESTCONF escape hatch | `wlc_restconf_call(GET, <yang path>)`, `wlc_restconf_root` | Arbitrary YANG data node returned; error extraction correct | `unit` (test_client_unit) |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (10 unit); `smoke_test.py` passes (RESTCONF
  probe, device info, WLANs, RADIUS servers, model list).
- **Manual/live gate:** WLAN/RADIUS/tag writes proven via the Wireless NAC lab plan
  (`test aaa … new-code` returns Access-Accept from ISE).
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| System | WLC-001…002 | smoke |
| WLANs | WLC-010…011 | smoke + manual-live |
| AAA/RADIUS | WLC-020…021 | manual-live |
| Policy/tags | WLC-030…031 | smoke + manual-live |
| Monitoring/escape hatch | WLC-040…050 | smoke + unit |

Manual-only gaps: all config writes (no `integration_test.py`); live wireless client is a
separate path (hostapd ≠ CAPWAP) covered by the Wireless NAC plan.

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
