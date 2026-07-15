# Test Plan — windows-mcp server

**Plan ID prefix:** `WIN-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

Validates the **windows-mcp** server: that its tools correctly drive a Windows Server over
WinRM/PowerShell remoting to manage Active Directory Domain Services (AD DS), DNS, DHCP, and
AD Certificate Services (AD CS) — the identity/PKI/DNS backing for ISE. **Out of scope:**
Windows install/patching, GPO authoring, and load testing.

## 2. System under test

| Item | Value |
|---|---|
| Component | `windows-mcp` (FastMCP + pypsrp), **37 tools** |
| Verified against | `mitchcloud.lab` domain controller (**lab-specific** — DC `198.18.134.11`) |
| Environment | Windows Server with WinRM enabled; AD DS + DNS + DHCP + AD CS roles |
| Dependencies | `Enable-PSRemoting` done; account is Domain/Enterprise Admin for AD CS ops |

## 3. Test approach / levels

Unit + smoke + **integration** (`tests/integration_test.py` — the full live pass that has
scored **34/34** functional tools against a live DC, creating and removing objects).

## 4. Preconditions & environment

- `.env`: `WINRM_HOST`, `WINRM_USERNAME`, `WINRM_PASSWORD`, `WINRM_AUTH` (ntlm), `WINRM_SSL`.
- WinRM (5985/NTLM) reachable; the box is already a promoted DC for the AD DS/DNS/DHCP cases.
- Promote-to-DC and role installs **reboot** the box (WinRM drops) — not part of the
  routine integration pass.

## 5. Test cases

### General / system

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WIN-001` | WinRM answers + system info | `win_system_info` | Hostname/OS/uptime returned over WinRM | `smoke` + `integration` |
| `WIN-002` | Features + services read | `win_list_features`, `win_get_service` | Installed roles + service state returned | `integration` |
| `WIN-003` | PowerShell escape hatches | `win_run_powershell_json`, `win_run_command` | Arbitrary PS/cmd runs; JSON parsed correctly | `unit` (test_client_unit) + `integration` |

### AD DS

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WIN-010` | Domain info | `win_ad_domain_info` | Forest/domain/DC details returned | `smoke` + `integration` |
| `WIN-011` | User lifecycle | `win_create_ad_user` → `win_get_ad_user` → `win_set_ad_user_password` → `win_delete_ad_user` | User created, read, password set, deleted | `integration` |
| `WIN-012` | Group + membership | `win_create_ad_group` → `win_add_group_member` → `win_list_ad_groups` | Group created and member added | `integration` |
| `WIN-013` | OU + computers | `win_create_ad_ou`, `win_list_ad_ous`, `win_list_ad_computers` | OU created; OUs/computers enumerated | `integration` |

### DNS

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WIN-020` | Zones read | `win_list_dns_zones`, `win_get_dns_records` | Zones + records returned | `integration` |
| `WIN-021` | A / CNAME add + remove | `win_add_dns_a_record` → `win_get_dns_records` → `win_remove_dns_record` | Record added (resolvable), then removed | `integration` (adds `mcptest-a`) |

### DHCP

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WIN-030` | Scopes read | `win_list_dhcp_scopes`, `win_list_dhcp_leases` | Scopes + leases returned | `integration` |
| `WIN-031` | Reservation add | `win_add_dhcp_reservation` | Reservation created for a MAC/IP | `integration` |

### AD CS (PKI for ISE)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `WIN-040` | CA info + templates | `win_adcs_ca_info`, `win_list_ca_templates` | Enterprise CA identified; templates listed | `integration` |
| `WIN-041` | Export CA cert (PEM) | `win_get_ca_certificate` | CA cert returned as PEM (feeds `ise_import_trusted_cert`) | `integration` |
| `WIN-042` | Sign a CSR | `win_sign_csr(csr, template=WebServer)` | Signed cert returned (feeds ISE CSR/EAP-TLS flow) | `manual-live` (ISE NAC plan) |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green (15 unit); `smoke_test.py` passes;
  `integration_test.py` prints `N PASS / 0 FAIL` (the 34/34 functional baseline).
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| General/system | WIN-001…003 | smoke + unit + integration |
| AD DS | WIN-010…013 | integration |
| DNS | WIN-020…021 | integration |
| DHCP | WIN-030…031 | integration |
| AD CS | WIN-040…042 | integration + manual-live |

Manual-only gaps: CSR signing as an EAP-TLS client cert (proven in the ISE NAC lab plan);
promote-to-DC / role installs (reboot the box, out of the routine pass).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
