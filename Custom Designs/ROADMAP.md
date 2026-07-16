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

- [ ] **B1** Border L3 handoff, per-VN eBGP (M) — **DIAGNOSED, PAUSED (2026-07-16).** ROOT CAUSE: the node labelled `BORDER-CP` is provisioned as **`CONTROL_PLANE_NODE` only — never a border** (`catc_fabric_devices` → `["CONTROL_PLANE_NODE"]`). So there is no L3 border to hand off through; that's why external reachability never worked and why the CLI attempt's return path black-holed (a CP node has no border forwarding). Proven along the way: an eBGP+NAT handoff on a *dedicated* BORDER↔FUSION link (VLAN 999 SVI in the CAMPUS_VN VRF, cat9000v has **no L3 dot1Q subinterfaces** so use SVI-on-access-port; FUSION side plain routed + NAT overload) brings the control plane up and the **forward path works** (`ping vrf CAMPUS_VN 198.18.134.35` from the border → 100%, edge `use-petr`→border `proxy-etr` encapsulates); the return path dies on the CP-only border's `Null0`. **RESUME (disruptive):** (1) DELETE the fabric device (`017ca3de-…`, removes CP role — breaks the fabric CP + HOST1 briefly); (2) re-add via `POST /sda/fabricDevices` with `deviceRoles:["CONTROL_PLANE_NODE","BORDER_NODE"]` + `borderDeviceSettings{borderTypes:["LAYER_3"], layer3Settings{localAutonomousSystemNumber:"65001", isDefaultExit:true, importExternalRoutes:true, borderPriority:10}}` (CatC won't add the role in-place → NCHS20120 "remove and re-add"); (3) `POST /sda/fabricDevices/layer3Handoffs/ipTransits` with the existing transit `IP_Transit_Fusion` (id `4107ddd7-…`, AS **65000** = the FUSION/external side), interface Gi1/0/3, VN CAMPUS_VN, vlanId 3001, local 10.1.244.1/30 / remote 10.1.244.2/30; (4) configure FUSION Gi3 = 10.1.244.2/30 + eBGP AS 65000↔65001 + NAT overload to Gi1 + default route; (5) verify HOST1→ISE/DC/Splunk/internet. CatC then renders the *proper* border-node (route-import, correct EID forwarding) which is the return-path fix. Transit object left in place for resume; my CLI/NAT attempt fully backed out (lab clean, HOST1 works internally).
- [ ] **B2** Windows DHCP/DNS for the VN (S) → B1 — scope on DC01, `ip helper` on the anycast GW; HOST1 goes DHCP; DNS registration
- [ ] **B10** PnP zero-touch edge onboarding (L) → B2 — new cat9000v discovers CatC via DHCP option 43; day-0 fabric edge join (CML feasibility experiment)

## Wave 3 — Identity deepening
*Finish the PKI story, then richer authz. A1 → A2; A7 → A8; A4 anytime.*

- [ ] **A1** EAP-TLS client certs (M) — re-enable client-auth trust on MitchcloudCA in ISE (deferred item); AD CS user cert onto HOST1; wpa_supplicant TLS → SGT
- [ ] **A2** TEAP / EAP chaining (M) → A1 — machine + user certs in one authentication
- [ ] **A4** ISE admin RBAC via AD (S) — GUI admin login mapped to AD groups
- [ ] **A7** Endpoint profiling (M) — device sensor + RADIUS accounting → profiler policies → per-device-type authz
- [ ] **A8** Posture assessment (L) → A7 — ISE 3.5 agentless posture (SSH to endpoint); experimental in CML

## Wave 4 — Device administration
*Isolated on purpose: it touches every switch's login path (lockout risk; console recovery ready).*

- [ ] **A3** TACACS+ device admin (M) — enable ISE Device Admin, shell profiles + command sets by AD group, switches point TACACS+ at ISE; properly replaces the Phase-6 local-vty workaround

## Wave 5 — Segmentation everywhere
- [ ] **B4** Multiple VNs + inter-VN fusion routing (M) → B1 — second VN (e.g. IOT_VN), VRF leak/inspect via fusion
- [ ] **B9** Group-based access control from CatC (M) — author SGT/SGACL from CatC (GBAC over pxGrid) instead of ISE-direct
- [ ] **C5** Extend pxGrid SGT enforcement to this fabric (S) — FMC subscribes to ISE 3.5 SGTs (IoT/Shared_Services/…) for ACP use

## Wave 6 — Firewall in the fabric
*The live permit/deny packet proof virtual cat9000v couldn't give us. Check host capacity first (FMCv wants 32 GB).*

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
