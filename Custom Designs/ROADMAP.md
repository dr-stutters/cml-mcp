# Integration roadmap — selected build program

**Chosen 2026-07-16** from the full cross-platform feature menu (28 of 41 items picked).
Sequenced into dependency-ordered waves; each wave is a working session with checkpoints,
run like the SD-Access ISE Integration build. Base state: everything in
[`SD-Access ISE Integration/runbook.md`](SD-Access%20ISE%20Integration/runbook.md) is live
(fabric + ISE 3.5 + AD + CatC ACTIVE, Closed Auth, TrustSec control-plane).

Legend: S/M/L effort · `→` = depends on

## Wave 1 — Observability foundation ✅ DONE (2026-07-16)
*Instrument first so every later wave lands in dashboards. Splunk redeployed as a CML docker node `SPLUNK` at `198.18.128.51` (8 GB) in lab SDA-Fabric; `.env` + creds updated (`Cisc0123#`).*

- [x] **D1** ISE → Splunk — Remote Logging Target `SplunkSyslog` (UDP `198.18.128.51:20514`) + Passed/Failed/Accounting categories → `index=ise` (`cisco:ise:syslog`). Verified: alice RADIUS event landed. *(GUI-only step; name must have no hyphen/special chars.)*
- [x] **D2** Fabric switch syslog → Splunk — EDGE1/BORDER-CP (`vrf Mgmt-vrf`)/FUSION → `logging host 198.18.128.51`, UDP 514 → `index=network` (`cisco:ios`). Verified.
- [x] **D3** CatC events + webhooks → Splunk — webhook dest `Splunk-HEC` + 85-event subscription `Wave1-Splunk` → HEC raw → `index=catc`.
- [x] **D8** Scheduled cross-platform health check → HEC — `/home/reptar/MCP/healthcheck.sh` (cml/ise/catc/splunk/windows/wlc/fmc) → HEC `index=health`; persistent scheduled task `lab-health-check` (~every 30 min). Dashboard `wave1_lab_overview`.

## Wave 2 — Fabric services
*Give the VN real infrastructure. Strict ordering: B1 → B2 → B10.*

- [x] **B1** Border L3 handoff, per-VN eBGP (M) — **DONE ✅ (2026-07-16)** via the *design-fix + targeted rebuild* path. ROOT CAUSE was that `BORDER-CP` had been provisioned `CONTROL_PLANE_NODE` **only — never a border**, so there was no L3 exit and the return path black-holed on `Null0`. CatC won't add the border role in-place *or* delete the only CP while an edge exists (NCHS20529), so the fix is a full fabric rebuild in dependency order: delete HOST1 port-assignment → delete EDGE1 → delete BORDER-CP → re-add **BORDER-CP as `["CONTROL_PLANE_NODE","BORDER_NODE"]`** + `borderDeviceSettings{borderTypes:["LAYER_3"], layer3Settings{localAutonomousSystemNumber:"65001", isDefaultExit:true, importExternalRoutes:true, borderPriority:1}}` → re-add EDGE1 as edge → `POST /sda/fabricDevices/layer3Handoffs/ipTransits` (transit `IP_Transit_Fusion` AS 65000, interface Gi1/0/3, VN CAMPUS_VN, vlanId 3001, 10.1.244.1/30 ↔ 10.1.244.2/30) → re-add HOST1 port-assignment → re-onboard HOST1. **Key win:** on the cat9000v CatC renders the L3 handoff as an **SVI (`Vlan3001`) on a trunk port**, *not* a dot1Q subinterface — automatically sidestepping the cat9000v's missing L3-subinterface support that blocked the earlier hand-rolled CLI attempt (that's why the CatC-driven border works where CLI couldn't). FUSION side (cat8000v): `Gi3.3001` dot1Q, eBGP 65000↔65001, `default-originate`, `ip nat inside source list NAT-FABRIC interface Gi1 overload`. **VERIFIED end-to-end:** border learns `B* 0.0.0.0/0 via FUSION` (redistributed → LISP), FUSION learns `B 172.16.10.0/24 via border`; border → ISE/Splunk/CatC 100% (src 172.16.10.1); **HOST1 (802.1X PEAP `alice` → SGT 4 Employees, Closed Auth) → ISE/Splunk 100%**, ISE MnT confirms alice's live session. **Gotchas banked** (see the runbook Gotchas + [[sda-ise-integration-lab]]): (a) re-provisioning re-applies the Network-AAA template → vty flips RADIUS-first → fix **both** `aaa authentication login VTY_authen` **and** `aaa authorization exec VTY_author` to local-first or CatC can't push (NCNP10200 / "unable to push"); (b) cat9000v `ip ssh bulk-mode` makes CatC config-push fail `ERROR-CONNECTION-CLOSED` (NCIM12018) → `no ip ssh bulk-mode`; (c) `borderPriority` must be 1–9 (10 → NCHS20300); (d) HOST1 alpine console user is `cisco` (sudoer, not root) so wpa_supplicant needs `sudo`, and its runtime IP+supplicant are lost on a plain reboot → now persisted via `/etc/local.d/sda-endpoint.start` (OpenRC `local` service); a full **wipe** still needs the wpa_supplicant reinstall (no fabric internet). **Unblocks B2/B10.**
- [x] **B2** Windows DHCP/DNS for the VN (S) → B1 — **DONE ✅ (2026-07-16).** DHCP role on DC01 (mitchcloud.lab) + scope CAMPUS_VN 172.16.10.50–200 (router/DNS/domain opts, DDNS); `ip helper-address 198.18.130.11` on the anycast SVI Vlan1021; a `route -p add 172.16.10.0/24 → FUSION .71` on the DC lets the relay OFFER (to giaddr 172.16.10.1) route back via the border. HOST1 static→**DHCP** (`udhcpc`, persisted in `/etc/local.d`) → lease 172.16.10.50, resolves `mitchcloud.lab`, ISE 100%. **Plain anycast-SVI helper worked** (no CatC/option-82 needed) across the NAT'd handoff. Gotchas: Linux-client **DDNS needs the DHCP DnsCredential** (registered the A record manually instead); renaming the alpine breaks pyATS prompt-match (disconnect+reconnect). Full: [`modules/vn-dhcp-dns.md`](SD-Access%20ISE%20Integration/modules/vn-dhcp-dns.md).
- [ ] **B10** PnP zero-touch edge onboarding (L) → B2 — new cat9000v discovers CatC via DHCP option 43; day-0 fabric edge join (CML feasibility experiment)

## Wave 3 — Identity deepening
*Finish the PKI story, then richer authz. A1 → A2; A7 → A8; A4 anytime.*

- [ ] **A1** EAP-TLS client certs (M) — **PREREQ DONE (2026-07-16):** MitchcloudCA (`Mitchcloud-Lab-Root-CA`) now **trusted for client auth** in ISE (`trustForClientAuth:true` — the long-deferred item, cleared); HOST1 has openssl 3.5.5 + a `CN=alice` CSR generated. **Remaining:** sign with a **clientAuth-EKU** cert (AD CS default templates give serverAuth-via-request `WebServer` *or* clientAuth-via-AD-subject `User`/`Machine`, not both — needs a custom template or an ISE "no EKU check" allowance); install cert+key+CA on the alpine (console/base64); ISE **Certificate Authentication Profile** (CN→AD:alice) + policy-set authN allows EAP-TLS; test wpa_supplicant EAP-TLS → SGT 4. Focused item — a boot-window squeeze isn't enough.
- [ ] **A2** TEAP / EAP chaining (M) → A1 — machine + user certs in one authentication
- [x] **A4** ISE admin RBAC via AD (S) — **DONE (2026-07-16).** AD group `ISE-Admins`→ISE `Super Admin` RBAC verified (`isExternal:true, src:mitchcloud`). netadmin can log in as Super Admin. Note the one GUI-only prereq below. Done via API/MCP: AD group `ISE-Admins` (SID `…-1110`) + user `netadmin`/`Cisco12345!` (mitchcloud.lab); `ISE-Admins` added to the ISE AD join point (4 groups now). The RBAC map (`PUT /api/v1/rbac/admin-group/Super Admin` → `isExternal:true, externalIdenSourceName:"mitchcloud", externalGroups:["mitchcloud.lab/Users/ISE-Admins"], rbacUsers:["admin"]`, exact original description) is **blocked until admin auth is external**: ISE returns *"Authentication has been set to internal by default"*. **REMAINING (GUI-only, no API):** Administration → System → Admin Access → Authentication → Authentication Method = **Password Based**, Identity Source = **mitchcloud (AD)** → Save. Then re-run the admin-group PUT and log in as `netadmin` to verify Super Admin RBAC. Body-format gotchas: `externalGroups`=array of **strings**, `rbacUsers`=array of **strings**, description must equal the system group's exact text (can't edit a system group's description).
- [ ] **A7** Endpoint profiling (M) — device sensor + RADIUS accounting → profiler policies → per-device-type authz
- [ ] **A8** Posture assessment (L) → A7 — ISE 3.5 agentless posture (SSH to endpoint); experimental in CML

## Wave 4 — Device administration
*Isolated on purpose: it touches every switch's login path (lockout risk; console recovery ready).*

- [x] **A3** TACACS+ device admin (M) — **DONE ✅ (2026-07-16).** ISE Device Admin enabled; shell profile `NetAdmin Priv15` + command set `PermitAllCommands`; NAD TACACS secrets on BORDER-CP/EDGE1; device-admin rule `SDA_NetAdmins` (AD `ISE-Admins`→priv15+permit-all). Switches: `tacacs server`/group + `ip tacacs source-interface Loopback0`; vty `login VTY_authen local group ISE_TACACS` + exec-authz local-first. **Verified:** `test aaa netadmin`→auth (both), SSH `netadmin@EDGE1`→**priv 15** live, `cisco`→local, CatC `forceSync`→isError:false (automation safe). **Local-first is the CatC-safe design** — ISE rejects the weak `cisco` password so TACACS-first would lock CatC out; but on cat9000v IOS-XE 17.x the `local` method **falls through to TACACS for unknown users**, so both work. Retires the Phase-6 workaround. Full: [`modules/tacacs-device-admin.md`](SD-Access%20ISE%20Integration/modules/tacacs-device-admin.md).

## Wave 5 — Segmentation everywhere
- [x] **B4** Multiple VNs + inter-VN fusion routing (M) → B1 — **DONE ✅ (2026-07-16).** Added `IOT_VN` (172.16.20.0/24, anycast Vlan1022) alongside CAMPUS_VN: reserved IOT-Pool, L3 VN, anycast GW, border L3 handoff (Vlan3002, 10.1.244.5/30↔.6/30), fusion Gi3.3002 + eBGP 65000↔65001 + NAT. Onboarded SHARED-SVC (EDGE1 Gi1/0/2, No-Auth) → 172.16.20.10. **Inter-VN hairpins through the fusion** (both VN subnets in its global table): SHARED-SVC↔HOST1 (IOT↔CAMPUS) **100%** (~170ms, host→edge→border→fusion→border→edge→host — the FTD insertion point for Wave 6); external from both VNs 100%. Gotchas: `tcpMssAdjustment` 500–1440; ~1min convergence after handoff; don't ping a host EID from the border via the anycast source. Full: [`SD-Access Fabric/modules/multi-vn-inter-vn.md`](SD-Access%20Fabric/modules/multi-vn-inter-vn.md).
- [ ] **B9** Group-based access control from CatC (M) — author SGT/SGACL from CatC (GBAC over pxGrid) instead of ISE-direct
- [ ] **C5** Extend pxGrid SGT enforcement to this fabric (S) — FMC subscribes to ISE 3.5 SGTs (IoT/Shared_Services/…) for ACP use

## Wave 6 — Firewall in the fabric
*The live permit/deny packet proof virtual cat9000v couldn't give us. Check host capacity first (FMCv wants 32 GB).*

> **INFRA DEPLOYED (2026-07-16):** **FMCv** (`198.18.128.80`, 32 GB) + **FTDv** (`198.18.128.81`, managed mode, day-0 `FmcIp=198.18.128.80`/`FmcRegKey=cisco123`) added to the SDA-Fabric lab, mgmt on the /18 via MGMT-SW. Host had ~89 GB free — no lab shutdown needed. **Day-0 gotcha:** FMCv `IPv4Mode` must be **`"manual"`** (not `"static"` — that silently leaves the mgmt IP blank; the console shows `Management IP: (empty)` and 8305 never opens). Corrected + rebooted → **FMCv UP + API-verified** (`admin`/`Cisc01@3` token OK, Global domain `e276abec-…`); **base ACP `SDA-ACP` created** via the API (id `5254002E-0748-0ed3-…`). `.env` FMC creds updated; the running `fmc` MCP won't hot-reload, so drive FMC via curl (or restart the MCP). **8305 (sftunnel) stayed CLOSED ~110 min in** even though the FMC web (443/302) + REST API are fully up — `sftunneld` is among the very last FMCv first-boot services and can lag the API by an hour+ on a VM; it may need more time or a **first GUI login** (`https://198.18.128.80`, admin/`Cisc01@3`) to finish initial setup before device registration opens. This is the only gate on FTD registration. **NEXT (next focused block):** wait for 8305 → add the FTDv (`198.18.128.81`, regKey `cisco123`) as a device record on the FMC → registration completes (per [[firepower-managed-mode-lab]], gate on 8305 not the API) → attach `SDA-ACP` → then C5 (pxGrid SGT ISE→FMC), D5 (FMC→Splunk), and the FTD-in-fabric insertion at the inter-VN fusion hairpin (see B4) for the live SGACL drop.

- [ ] **C1** FTD as SDA fusion firewall (L) → B1, C5 — VN handoff steered through FTDv; SGT-aware ACP; live inter-VN enforcement with hit counters
- [ ] **C3** Passive identity user-based ACP (M) → C5 — pxGrid session identity (alice/bob) driving user-based FTD rules
- [ ] **C2** Rapid threat containment (M) → C5 — FMC correlation rule → ISE ANC quarantine → CoA bounces the fabric session
- [ ] **D5** FMC/FTD → Splunk (M) — Security Cloud app; connection + IPS events
- [ ] **D7** SOAR-lite closed loop (M) → D1 — Splunk alert (e.g. brute-force pattern) → script → ISE ANC quarantine → CoA
- [ ] **C4** RA-VPN with ISE authz (L, conditional) — needs AnyConnect packages/licensing in CML; attempt last

## Wave 7 — Wireless joins the fabric
- [ ] **E1** Fabric WLC role in CatC (M) — C9800 into inventory + WIRELESS_CONTROLLER_NODE fabric role (config-path; CML CAPWAP caveat stands)
- [ ] **E3** CatC wireless design push (M) → E1 — SSID/profile/tag design objects provisioned to the C9800
- [ ] **E2** Wireless 802.1X → SGT (S) — hostapd AP + wpa_supplicant → ISE returns SGT over the RF path (Wireless NAC pattern + TrustSec authz)
- [ ] **D6** WLC → Splunk (S) — C9800 syslog/telemetry feed

## Wave 8 — Scale-out
- [ ] **B6** Fabric-in-a-box (S) — single cat9000v CP+Border+Edge (module stub exists in SD-Access Fabric)
- [ ] **B5** Second fabric site + transit (L) → B4 — IP transit between two fabric sites; capacity check first (2+ more cat9000v)

## Parked (not selected this round)
A5 guest/sponsor portal · A6 BYOD/SCEP · B3 second edge + mobility · B7 L2 flooding ·
B8 AAA-down drill · D4 AD→Splunk identity-trace dashboard · F1–F3 Crosswork (CNC onboarding,
L3VPN, L2VPN) · G1 secure-by-design audit · G2 spec export/clean-room rebuild ·
G3 compliance drift · G4 SWIM dry-run

## Standing rules for every wave
- Checkpoint at each item boundary; disruptive steps get an explicit go/no-go.
- Bank each validated wave into the matching Custom Design (new module or new design folder),
  update agents, ask before commit/push.
- Fabric-first triage on any breakage (link + interface state before device debugging).
- Capacity check before FMCv (32 GB) and before any multi-cat9000v additions.
