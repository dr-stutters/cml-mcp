# Firewall SD-WAN — design brief

Distilled from *Cisco Secure Firewall Threat Defense SD-WAN Design and
Deployment Guide* (Cisco Public, Sept 2025; based on **FMC 7.6 / FTD 7.6**).
See [links.md](links.md). Agent-consumable reference for **firewall-engineer**.

This is **Secure Firewall Threat Defense's own SD-WAN**, driven entirely from
**Secure Firewall Management Center (FMC)** on the FTDs — **not** Cisco
Catalyst SD-WAN (no vManage/vSmart/vBond/cEdge).

## Scope & when to use

Build a highly available, full-service SD-WAN branch network on Secure
Firewall: route-based VPN overlay between headquarters (hubs) and branches
(spokes), application-aware path selection over multiple WAN transports, and
secure direct internet access — all as unified FMC policy. Use it when the
firewall *is* the SD-WAN edge/router (branch security + WAN in one), rather
than fronting a separate SD-WAN fabric.

Core capabilities: route-based VTI VPN tunnels (hub↔spoke); BGP/OSPF/EIGRP
over VTI; Dynamic VTI hubs; SD-WAN wizard + Summary dashboard; DIA and
application-aware PBR; ECMP across ISPs/VTIs; dual-ISP HA with app-based path
monitoring; SASE/SSE via Umbrella and Cisco Secure Access.

## Version requirements (feature → release)

- **SD-WAN Wizard: 7.6**; SD-WAN Summary dashboard 7.4 (app monitoring 7.4.1)
- PBR with identity/SGTs, PBR via HTTP path monitoring: 7.4
- Loopback for VTIs, DVTI with S2S VPN, Umbrella auto tunnel, IPv4/IPv6 BGP &
  OSPF + IPv4 EIGRP for VTIs: 7.3
- Route-based hub-and-spoke S2S VPN, PBR with (IP) path monitoring: 7.2
- S2S VPN Monitoring dashboard, DIA/PBR, ECMP zone (WAN + VTI): 7.1
- ECMP from FMC UI: 7.0; Backup VTI: 7.0; SVTI: 6.7

## Topology / components (validated design)

Hub-and-spoke overlay across **two ISPs** (ISP1, ISP2), all sites dual-homed:
- **Hubs:** NYC (primary) + Newark/NNJ (secondary), each a **Firewall 3105 HA
  pair**. Hubs use dedicated **management** interfaces to FMC and **data**
  interfaces to branches.
- **Spokes/branches:** Providence (FP1010), Worcester (FP1120), New Haven
  (FP1120 **HA pair**), Manchester (**FTDv**).
- **Management:** Secure Firewall **Management Center Virtual** manages all;
  **Security Cloud Control (SCC)** provides cloud assist / ZTP.
- Inside networks per site are distinct /16s (e.g. NYC 10.100/16, branches
  10.71–10.74/16).

**CML mapping:** `fmcv` + `ftdv` reproduce the FTDv branch + FMC roles and the
on-box SD-WAN features (VTI overlay, PBR, path monitoring, ECMP). Hardware
models (3105/1010/1120), SCC/ZTP, Umbrella, and Secure Access are cloud/HW and
are **out of scope for a pure CML lab** — substitute `ftdv` everywhere and use
external connectors for the ISP transports.

## Config workflow (FMC-managed)

1. **Onboard FTDs to FMC** — two methods:
   - *ZTP by serial number* (FP1010/1100, SF1200, FP2100 [7.4.x], SF3100 only;
     integrates FMC with SCC).
   - *Registration key* (all models incl. **FTDv**; with or without device
     templates). ← the CML-relevant path (see firewall-engineer managed mode).
2. **VTI overlay** — the tunnel interfaces that carry the overlay:
   - **SVTI** (static, 6.7+): always-on bidirectional IPsec; used on **spokes**.
   - **DVTI** (dynamic, 7.3+): point-to-multipoint via a virtual template that
     spawns a virtual-access interface per session; **spoke-initiated only**;
     used on **hubs**. VTIs are routable, carry IPv4+IPv6, support static &
     dynamic routing, **not multicast**.
3. **SD-WAN wizard (FMC, 7.6+)** — auto-builds the route-based overlay: **DVTIs
   on hubs, SVTIs on spokes, and BGP** for the overlay. This is the fast path
   to a hub-and-spoke SD-WAN.
4. **Direct Internet Access (DIA) + PBR** — branch sends app traffic straight
   to the internet (bypassing the hub tunnel) via a PBR policy on the **ingress
   (inside) interface** matching network/port/user/group/app/SGT, forwarding
   out egress ISP interfaces. Steering methods: source-IP (7.1), app-aware
   (7.1), app-aware + path monitoring (IP 7.2 / HTTP 7.4), identity-aware
   (7.4). DIA relies on: **Trusted DNS server** (DNS snooping), **VDB** (app→
   domain data), **Network Service Objects/Groups** (NSO/NSG — FMC
   auto-generates NSGs from the PBR extended ACLs).
5. **Path monitoring** — per-egress metrics drive best-path selection:
   - Metrics: **RTT, jitter, MOS, packet loss**.
   - *IP-based* (ICMP probes, 1 s interval): Path Monitoring Module (PMM)
     collects → PBR engine routes by best metric.
   - *HTTP-based* (HTTP probes, 10 s interval; on by default per interface):
     starts on DNS snoop; PMM feeds PBR every 30 s.
6. **ECMP zones** — group up to **8 interfaces** (physical or VTI) per zone for
   load-balancing/redundancy across ISPs/VTIs (FMC UI, 7.0+).
7. **Identity-aware routing** (optional, 7.4+) — PBR by AD user/group/SGT.
   Requires AD; ISE optional (local SGTs in FMC otherwise). **ISE and local
   SGTs cannot be used together.**
8. **SASE/SSE** (optional, cloud) — Umbrella **auto tunnel** (SIG) or Cisco
   **Secure Access** manual IPsec tunnel for Secure Internet Access; HA via
   active/active or active/backup tunnels (ECMP, up to 8 active + 8 backup) and
   Network Tunnel Groups; switchover via IKE DPD (static) or BGP (dynamic).

## Verification

- FMC **SD-WAN Summary** and **Site-to-Site VPN Monitoring** dashboards
  (tunnel status, application visibility, performance).
- On the FTD: routing table and PBR/path-monitoring state — confirm the
  expected egress per application and that path-monitoring metrics
  (RTT/jitter/loss/MOS) populate and drive selection; verify failover when a
  transport degrades.

## Gotchas

- **PBR sits on top of normal routing:** a route to each egress must exist on
  the device (even if not in the active table) or PBR can't use that path.
- **PBR order matters:** top-down, first match, new rules append at the bottom
  — put the most specific rules at the top; falls back to normal routing on no
  match.
- VTIs don't carry **multicast**. DVTI is **spoke-initiated only**.
- ZTP-by-serial is limited to specific hardware models; **FTDv must use the
  registration-key method**.
- HTTP path monitoring is on by default per interface; ICMP probe interval 1 s,
  HTTP 10 s (PBR refresh every 30 s).

## CML validation notes

Reproducible slice: `fmcv` + `ftdv` SD-WAN edges, ISP transports simulated
in-lab (IOL routers / switches, all RFC1918), inside hosts. Only the FMC/FTD
management is bridged out. Cloud-tied pieces (SCC/ZTP, Umbrella, Secure Access)
can't be validated in CML. Hardware models (FPR-3105/1010/1120) → all `ftdv`.

**Build order that works** (see firewall-engineer "Building SD-WAN via the FMC
REST API"): register FTDs by key (+ eval-license prereq) → physical interfaces
+ zones → loopbacks → VTIs (DVTI hub / SVTI spoke) → route-based hub-spoke VPN
topology → **iBGP AS 65070 over the tunnel** (required — a DVTI can't be
static-routed) → ACP for the tunnel zone → deploy → verify.

**Status — SD-WAN overlay VALIDATED end-to-end (2026-07-12):** 6-site topology
(2 hubs + 4 spokes, dual ISP) built and all FTDv registered. Hub NYC ↔ spoke
WMA proven working over the **SD-WAN auto-VPN**: FMC auto-built the spoke SVTI
(Tunnel1, pool IP 10.255.255.100), auto-configured **iBGP AS 65070**
(neighbor up, LANs exchanged with community 1000), and **NYC-HOST → WMA-HOST
ping is 0% loss** across the VTI overlay. **Dual-ISP ECMP done**: a 2nd
AUTO_VPN topology over ISP2 (`enableMultiPath`) gives two active tunnels + two
iBGP sessions and installs the remote LAN via both next-hops; an ISP1
link-down failover test kept the host-to-host ping at 0% loss (rode ISP2).
**All 4 spokes done** — each on the dual-ISP overlay with a different branch
LAN protocol redistributed in and reachable end-to-end (0% loss): **WMA
connected, PRI OSPF, NCT EIGRP, MCT eBGP**. The redistribution merges a
companion `router bgp` into the auto-VPN's and tags routes with the overlay
community so they pass its outbound filter (see firewall-engineer). **Dual-hub
redundancy done**: NNJ added as a secondary hub on both topologies — each spoke
builds tunnels to both hubs (the auto-VPN makes the hubs route reflectors), and
isolating the NYC primary hub kept spoke-to-spoke traffic at 0% loss via NNJ.
**Both hubs are FTD HA pairs** (NYC-FW-2/3, NNJ-FW-2/3) — each **failover-
validated** (kill the active unit → the standby takes over the hub role, DVTIs,
and inside gateway with the overlay intact). Retrofitting HA onto the live hubs
required rebuilding each hub with a spare failover NIC (CML can't hot-add one to
a booted node); see firewall-engineer for the rebuild flow. **The full CVD is
now built and validated end-to-end in CML.** See memory `firewall-sdwan-cvd-lab`.

## Roadmap / not yet done

- **Direct Internet Access (DIA) + application-aware PBR** — branch internet
  breakout via a PBR policy on the inside interface (source-IP / app-aware /
  path-monitoring steering). Not yet built in the lab; relies on Trusted DNS,
  VDB, and FMC-generated Network Service Groups (see the "Config workflow"
  section above for the FMC mechanics).

**Hard-won findings:**
- FMC VPN/VTI config is not REST-discoverable by guessing — pull exact schemas
  from the API Explorer spec `https://<fmc>/api/api-explorer/fmc.json`. VTI
  borrow-IP = `ipAddressAssignmentType:"BORROW_IP_FROM_INTERFACE"` +
  `borrowIPfrom:{loopback}`.
- **The SD-WAN wizard IS fully API-drivable** as an `AUTO_VPN` topology (see
  firewall-engineer "SD-WAN auto-VPN — the wizard, via API"). Two non-obvious
  keys: `topologyType` MUST be `"AUTO_VPN"` (with `HUB_AND_SPOKE` the FMC
  silently drops `autoVpnSettings`), and the **spoke endpoint's `interface` is
  the physical WAN interface itself** — FMC auto-creates the spoke SVTI and
  assigns its IP from the hub's `IPv4AddressPool` via IKEv2 mode-config.
- **Export-controlled Smart License features are required** for SD-WAN/auto-VPN.
  In Evaluation Mode it's gated (GUI greys out "SD-WAN Topology"; the API drops
  `autoVpnSettings`). Register the FMC to a Smart Account with an export-control
  token; verify `exportControl: true` on `/license/smartlicenses`.
