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

- [ ] **B1** Border L3 handoff, per-VN eBGP (M) — the documented "next layer"; fabric hosts reach shared services (DC01, ISE, Splunk) and beyond
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
