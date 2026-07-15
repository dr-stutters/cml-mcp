# Windows DC Foundation — runbook

**Status (2026-07-15): validated clean-room** — built from a fresh Server 2022 VM
end-to-end through the `windows` MCP off the shared master `.env`, with no pre-known
values.

A repeatable build of the **Windows Server that backs Cisco ISE**: an Active Directory
domain controller (`mitchcloud.lab`) with DNS, an **enterprise AD CS root CA**, and a
test identity — driven entirely through the `mcp__windows__*` tools. This is the
identity / PKI / DNS foundation the NAC designs build on ([ISE NAC Lab](../ISE%20NAC%20Lab/),
[Wireless NAC](../Wireless%20NAC/), [Firepower SGT Enforcement](../Firepower%20SGT%20Enforcement/)):
AD as an external identity source, the CA cert for EAP-TLS, and resolvable names for ISE
CSRs. Owned by the **windows-engineer** agent.

## Prerequisites

- A **fresh Windows Server 2022** VM, external to CML, reachable on the lab network.
- **WinRM enabled on the box first** (console/RDP, once): `Enable-PSRemoting -Force`.
  ⚠️ On a fresh, not-yet-domain-joined box the network often classifies as **Public**,
  which blocks 5985. Set it Private (or scope the rule):
  `Set-NetConnectionProfile -NetworkCategory Private` **or**
  `Set-NetFirewallRule -Name 'WINRM-HTTP-In-TCP' -RemoteAddress Any`.
- **Firewall:** on a flat lab segment only **WinRM TCP 5985** inbound is needed — the AD
  DS / DNS / DHCP / AD CS role installs open their own host-firewall rules. If ISE/clients
  sit behind a firewall from the DC, open the AD port set (DNS 53, Kerberos 88, NTP 123,
  RPC 135 + dynamic 49152-65535, LDAP 389, SMB 445, kpasswd 464, GC 3268/3269) plus
  **HTTP 80** for CRL/AIA.
- The shared master **`../.env`** filled with the connection + build params (below).
- **Reload the `windows` MCP server after editing `../.env`** — see gotcha 1.

## Master `.env` parameters

Real values are **lab-specific** (adjust for your environment); passwords live only in the
uncommitted master `../.env`, never here.

```ini
# --- WinRM connection (read by the MCP server) ---
WINRM_HOST=198.18.130.11        # the DC's IP
WINRM_USERNAME=Administrator    # local Administrator pre-domain; after promotion this
                                # same unqualified name resolves to the DOMAIN Administrator
WINRM_PASSWORD=<in ../.env>
WINRM_AUTH=ntlm
WINRM_PORT=5985

# --- AD build params (consumed by the build calls, NOT the WinRM connection) ---
AD_DOMAIN_NAME=mitchcloud.lab
AD_NETBIOS_NAME=MITCHCLOUD
AD_DSRM_PASSWORD=<in ../.env>
CA_COMMON_NAME=Mitchcloud-Lab-Root-CA
AD_TEST_USER=iseuser1
AD_TEST_USER_PASSWORD=<in ../.env>
DHCP_SCOPE_NAME=LAB-Clients
DHCP_START_RANGE=<lab-subnet range>   # NOT the 10.0.0.x template default (gotcha 4)
```

## Build — stage by stage

| # | Step | Tool | Notes |
|---|---|---|---|
| 1 | Confirm WinRM | `win_system_info` | expect `WORKGROUP` / `PartOfDomain: false` |
| 2 | **Rename → `DC01`** | `win_rename_computer("DC01")` | **before** promotion (renaming a DC later is far more involved). Reboots ~1-2 min; reconnect + confirm |
| 3 | **Promote to DC** | `win_promote_to_dc` (Install-ADDSForest) | `mitchcloud.lab` / `MITCHCLOUD`, DSRM from `AD_DSRM_PASSWORD`. Reboots + WinRM drops ~5-10 min; wait, reconnect, `win_ad_domain_info`. Post-promote `Administrator` still authenticates (gotcha 2) |
| 4 | Verify DNS | `win_list_dns_zones` | DS-integrated `mitchcloud.lab` forward zone (installed with AD DS) |
| 5a | Stage AD CS role | `win_install_feature("ADCS-Cert-Authority")` | flags `RestartNeeded` but the CA config proceeds without a reboot |
| 5b | **Configure enterprise root CA** | `win_install_adcs_ca(common_name="Mitchcloud-Lab-Root-CA", ca_type="EnterpriseRootCA")` | → `CA installed` |
| 5c | Export CA cert (for ISE) | `win_get_ca_certificate` | PEM → `ise_import_trusted_cert` (EAP-TLS / pxGrid / portals) |
| 6 | Test identity | `win_create_ad_user(AD_TEST_USER, AD_TEST_USER_PASSWORD)` | external identity for ISE |
| 7 | DHCP *(optional)* | `win_install_feature("DHCP")` + scope | set `DHCP_*` to the **lab** subnet, not the template default (gotcha 4) |

## Verification

| Check | Tool | Pass |
|---|---|---|
| Domain/forest | `win_ad_domain_info` | `mitchcloud.lab`, `DC01` sole DC, FL 2016 |
| DNS | `win_list_dns_zones` | `mitchcloud.lab` DS-integrated + `_msdcs` + reverse |
| CA | `win_adcs_ca_info` | Enterprise Root CA, cert **Valid**, CRL **published**, `certutil` rc 0 |
| CA cert | `win_get_ca_certificate` | valid PEM (2026→2031) |
| AD write | `win_create_ad_user` → `win_get_ad_user` → `win_delete_ad_user` | throwaway user round-trips |

## Teardown

Delete any test users; the box can be demoted (`Uninstall-ADDSDomainController`) or — for a
truly clean re-run — rebuilt from a fresh Server 2022 snapshot (fastest path to repeatable).

## Gotchas (the four that bit us — build these into any re-run)

1. **MCP servers cache config at startup.** After editing the master `../.env`, the
   long-running server keeps the **old** values until you reload it (`/mcp` reconnect) or
   run a fresh process. This is the classic "why is it still using the old IP" — reload
   before you trust a config change.
2. **Post-promote auth has a transient window.** For ~1 minute after the promotion reboot,
   WinRM as `Administrator` fails (`NTLM auth failed`) while AD DS / Netlogon initialize,
   then succeeds. **Wait and retry — do not switch `WINRM_USERNAME` to `MITCHCLOUD\…`**;
   the unqualified `Administrator` resolves to the domain account on a DC (there are no
   local accounts left).
3. **`certutil -CAInfo` briefly RPC-fails after the CA install** (`RPC_S_SERVER_UNAVAILABLE`)
   while `CertSvc` starts. `win_get_ca_certificate` reads the cert from the machine store
   and works immediately regardless; re-check `win_adcs_ca_info` once `CertSvc` is Running.
4. **DHCP scope template default is `10.0.0.x`** — set `DHCP_*` to the lab subnet
   (`198.18.128.0/18` here) or the scope serves nothing. DHCP is optional for the ISE
   backing and can be deferred.

Plus: **rename before promote**, and mind the **WinRM Public-profile firewall** gotcha
above on a fresh box.
