# ISE NAC Lab — end-to-end runbook

A repeatable build of a full **Cisco ISE Network Access Control** lab in CML: a
Catalyst 9000v access switch (the NAD) authenticating an endpoint against ISE by
**MAB, PEAP-MSCHAPv2 (against AD), and EAP-TLS**, then layering on **dynamic
authorization, TrustSec, CoA, and full CTS**. Validated end-to-end against ISE
**3.4 and 3.5**.

> **Orchestration:** the main session runs the stages below and fans work out to
> **ise-engineer** (ISE + NAD-side 802.1X), **catalyst-engineer** (switch), and
> **windows-engineer** (AD/DNS/CA). ISE, the Windows DC, and the CA are external
> VMs on the underlay; the switch + endpoints are CML nodes.

## What it builds

```
                 Windows DC / CA (mitchcloud.lab)          Cisco ISE (PAN/PSN/MnT)
                 198.18.134.11  (AD, DNS, AD CS)            198.18.134.35  (ise35)
                        │                                          │
        ┌───────────────┴──────────────  underlay 198.18.128.0/18 ─┴────────────┐
        │  (bridged via CML external connectors on the System Bridge)           │
   ┌────┴─────┐        ┌───────────────┐                                  ┌──────┴─────┐
   │ MGMT-EXT │        │   DATA-EXT     │  ← 2nd System-Bridge connector   │  (ISE/DC)  │
   └────┬─────┘        └───────┬────────┘                                  └────────────┘
   Gi0/0│(Mgmt-vrf, OOB) Gi1/0/1│(global table, VLAN100 SVI = NAD source IP)
   ┌────┴───────────────────────┴────┐
   │        SW-ISE35  (cat9000v-uadp) │  ← the NAD
   └───┬───────────────────────┬──────┘
   Gi1/0/2                  Gi1/0/3
   ┌───┴────┐              ┌───┴─────────────────┐
   │ EP-...  │ (MAB test)  │ SUP-ISE35 (net-tools │
   │ Alpine  │             │  + wpa_supplicant)   │  ← 802.1X supplicant
   └─────────┘             └──────────────────────┘
```

## Prerequisites

- **CML** with a `cat9000v-uadp` image (the ONLY CML switch that does functional
  NAC — see Gotchas), plus `alpine` and `net-tools` node types, and the **System
  Bridge** external connector bridged to the underlay `198.18.128.0/18`.
- **Cisco ISE** reachable on the underlay (patched **3.5** strongly preferred — the
  unpatched 3.4 has an MnT visibility gap; see Gotchas). ERS enabled (Admin ▸ System
  ▸ Settings ▸ API Settings). MCP: the `ise` server (and `ise35` for a 2nd box).
- **Windows Server** DC for `mitchcloud.lab` with **DNS + AD CS** (enterprise CA),
  built by the windows-engineer. MCP: the `windows` server.
- The `cml`, `ise`, and `windows` MCP servers wired into `.mcp.json`.

Lab values used below (**adjust for your environment**): ISE `198.18.134.35`
(hostname `ise35`), DC `198.18.134.11` (`mitchcloud.lab`), switch mgmt SVI
`Vlan100 = 198.18.128.66/18` (also the NAD source IP), RADIUS/CoA shared key
`ISEsecret123`, CTS device password `CTSsecret123`.

---

## Stage 0 — Windows AD / DNS / CA (backing)  → windows-engineer

Stand up the domain if it isn't already (`win_promote_to_dc`), a DHCP scope, and an
**AD CS enterprise CA** (`win_install_adcs_ca ca_type=EnterpriseRootCA`). Pre-create
DNS A records for the ISE node(s) so they're resolvable, e.g.
`win_add_dns_a_record(zone='mitchcloud.lab', name='ise35', ip='198.18.134.35')`.
Confirm a test AD user exists (e.g. `iseuser1`) for PEAP.

## Stage 1 — ISE base  → ise-engineer

1. **Confirm ISE's DNS points at the DC** (`ip name-server 198.18.134.11`,
   `ip domain-name mitchcloud.lab`) — this is a switch/ISE-CLI setting, **not**
   exposed via API, and it's the make-or-break for the AD join.
2. **Join ISE to AD** (ERS):
   - `POST /ers/config/activedirectory` `{"ERSActiveDirectory":{"name":"mitchcloud","domain":"mitchcloud.lab"}}`
   - `PUT /ers/config/activedirectory/{id}/joinAllNodes` with `OperationAdditionalData.additionalData = [{name:username,value:Administrator},{name:password,value:<pw>}]`
     — **`/joinAllNodes`, not `/join`**; **only** `username`+`password` (no `domainName`).
   - Verify: an ISE computer account appears in AD (`Get-ADComputer -Filter *`).
3. **PKI (EAP-TLS chain):**
   - CA cert → `win_get_ca_certificate` → `ise_import_trusted_cert(cert_pem,
     trust_for_ise_auth=True, trust_for_client_auth=True)`.
   - (Optional, disruptive) give ISE a CA-signed EAP cert: `ise_generate_csr`
     (used_for `EAP-AUTH`) → fetch the CSR PEM → `win_sign_csr(template='WebServer')`
     → bind: `POST /api/v1/certs/signed-certificate/bind` with the **pending CSR `id`**
     + `data` + `eap:true`. **Binding restarts ISE services ~10-20 min.**
4. **Identity source:** leave the **Dot1X** authN rule pointed at the built-in
   **`All_User_ID_Stores`** sequence — it already bundles the cert-auth profile
   (→ EAP-TLS), `All_AD_Join_Points` (→ PEAP/AD), and Internal Users. One source
   serves every method; no custom sequence needed.

## Stage 2 — Switch base (the critical part)  → catalyst-engineer

The cat9000v's OOB **Mgmt-vrf** port (Gi0/0) **cannot** carry NAC RADIUS or CoA
(see Gotchas). Give the switch a **front-panel, global-table** path to ISE:

1. Add a **2nd System-Bridge external connector** (`DATA-EXT`) and link a front-panel
   port (Gi1/0/1) to it; **start the node + the new interface** (interfaces added to
   a running node come up `STOPPED`).
2. Configure the uplink + mgmt SVI in the **global** table:
   ```
   vlan 100
    name RADIUS-UPLINK
   interface GigabitEthernet1/0/1
    switchport mode access
    switchport access vlan 100
    spanning-tree portfast
   interface Vlan100
    ip address 198.18.128.66 255.255.192.0     ! NAD source IP, on the underlay
   ```
   (Bounce the SVI if it stays `up/down` until STP forwards.)
3. **RADIUS + AAA, sourced from Vlan100 (global):**
   ```
   aaa new-model
   aaa group server radius ISE-GROUP
    server name ISE-PSN
    ip radius source-interface Vlan100      ! NOT Gi0/0 / Mgmt-vrf
   aaa authentication dot1x default group ISE-GROUP
   aaa authorization network default group ISE-GROUP
   aaa accounting dot1x default start-stop group ISE-GROUP
   radius server ISE-PSN
    address ipv4 198.18.134.35 auth-port 1812 acct-port 1813
    key ISEsecret123
   aaa server radius dynamic-author
    client 198.18.134.35 server-key ISEsecret123   ! global table — NO 'vrf Mgmt-vrf'
   dot1x system-auth-control
   ```
4. **Register the NAD in ISE** with the **Vlan100 SVI IP** and the shared key:
   `ise_create_network_device(name='SW-ISE35-DATA66', ip='198.18.128.66',
   radius_shared_secret='ISEsecret123')`.
5. Sanity: `test aaa group ISE-GROUP <user> <pw> new-code` should reach ISE
   (reject/accept), and `ping 198.18.134.35 source Vlan100` should work.

## Stage 3 — 802.1X on the access port  → catalyst-engineer + ise-engineer

1. **IBNS 2.0 port** (Gi1/0/2 or Gi1/0/3):
   ```
   policy-map type control subscriber DOT1X_MAB
    event session-started match-all
     10 class always do-until-failure
      10 authenticate using dot1x priority 10
      20 authenticate using mab priority 20
   interface GigabitEthernet1/0/3
    switchport mode access
    switchport access vlan 100
    access-session host-mode single-host
    access-session port-control auto
    dot1x pae authenticator
    mab
    service-policy type control subscriber DOT1X_MAB
   ```
2. **Baseline authZ:** add `Wired_802.1X → PermitAccess` (and `Wired_MAB →
   PermitAccess`) authZ rules to the Default policy set
   (`ise_create_authz_rule(..., condition_name='Wired_802.1X', profiles=['PermitAccess'])`).
3. **MAB:** register the endpoint MAC (`ise_create_endpoint`) → the Alpine on Gi1/0/2
   authenticates by MAC. Verify `show access-session … | mab = Authc Success`.
4. **The supplicant (SUP-ISE35):** a `net-tools` (Debian) node has `apt` + `openssl`
   but **no** `wpa_supplicant`. Give it temporary underlay access (VLAN 100 + a
   static IP + default route `198.18.128.1` + DNS `8.8.8.8`) and install it —
   pulling the `.deb`s **directly** (`apt-get update` chokes on the cat9000v
   dataplane; see Gotchas), then switch the port to dot1x.
5. **PEAP-MSCHAPv2 (against AD):** `wired-peap.conf` →
   `eap=PEAP / identity="iseuser1" / password=... / phase2="auth=MSCHAPV2" /
   key_mgmt=IEEE8021X / eapol_flags=0`; run `wpa_supplicant -D wired -i eth0 -c …`.
   Expect `CTRL-EVENT-EAP-SUCCESS`; ISE MnT shows `iseuser1` passed, method PEAP.
6. **EAP-TLS:** generate a client key+CSR on the supplicant, sign with the CA
   (`win_sign_csr(template='User')` → a clientAuth cert), install cert+key+CA, then
   `eap=TLS / client_cert / private_key / ca_cert`. Expect `CTRL-EVENT-EAP-SUCCESS`
   (mutual TLS). (A per-user cert subject needs a custom supply-in-request+clientAuth
   template — see the windows-engineer notes.)

## Verification (three-sided, every time)

| Vantage | Command / call |
|---|---|
| **Supplicant** | `grep CTRL-EVENT-EAP /tmp/wpa.log` → `…-EAP-SUCCESS` |
| **Switch** | `show access-session interface Gi1/0/3 details` → `Status: Authorized`, method, `SGT Value`, `ACS ACL`, `Vlan` |
| **ISE (MnT)** | `ise_session_by_username` / `ise_session_by_mac` → `passed:1` |

## Capability modules (layer onto the base)

- [Dynamic authorization — dACL + dynamic VLAN](modules/dynamic-authz.md)
- [TrustSec — SGT assignment + SGACL enforcement](modules/trustsec.md)
- [CoA — Change of Authorization](modules/coa.md)
- [Full CTS — switch downloads the SGACL policy from ISE](modules/cts.md)

## Teardown

Delete the ISE objects created (authZ rules/profiles, dACLs, SGACLs + egress cells,
NAD, endpoints, AD join point) via the `ise` MCP; on the switch, `default interface`
the access ports and remove the CTS/RADIUS config; in CML, stop/wipe/delete the lab
(`control_lab` → `delete_lab`). Leaving the AD join point + CA trust in place is fine
for re-runs.

## Gotchas (the expensive lessons)

- **cat9000v RADIUS *and* CoA must ride the global table, never Mgmt-vrf.** The
  auth-manager (SMD) RADIUS for MAB/dot1x silently times out over Gi0/0/Mgmt-vrf
  even though IOSd `test aaa` works there (ISE MnT shows nothing arriving). And the
  `dynamic-author` (CoA) client bound to `vrf Mgmt-vrf` makes ISE's CoA silently
  drop (`11213 No response from NAD`). Source RADIUS from a front-panel global SVI
  **and** put the CoA client in the global table. *(Open question: task #18.)*
- **Only cat9000v does functional NAC in CML.** `iosvl2` and `ioll2-xe` accept the
  `mab`/`access-session` config but never punt the endpoint frame to the
  auth-manager (`Client: none`) — no MAB/dot1x ever fires.
- **Console garbles long lines.** Moving a cert/key onto a CML node via the console:
  chunk base64 to ~700 chars and `tr -d '[:space:]'` on reassembly, or the file
  corrupts.
- **ERS `trustsecsettings` misspells fields** (`downlaodEnvironmentDataEveryXSeconds`).
- **MnT visibility:** patched 3.5 surfaces live sessions/auths in seconds; unpatched
  3.4.0.608 may not — trust the NAD session + RADIUS accept/accounting-ack as ground
  truth, check logging categories / patch level otherwise.
- **CML fabric first:** if an endpoint link passes no traffic, confirm both the
  link **and** interface state are `STARTED` before blaming device config.
