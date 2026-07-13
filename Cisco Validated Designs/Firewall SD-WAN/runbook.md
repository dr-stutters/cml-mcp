# Firewall SD-WAN — build runbook

The repeatable, as-built companion to [design-brief.md](design-brief.md). Where the
brief is the distilled *reference design*, this is the **step-by-step build** that
was validated end-to-end in CML (FMCv managing FTDv, driven via the **FMC REST
API**) — a 6-site hub-and-spoke SD-WAN over two ISPs.

> **Orchestration:** the main session asks **cml-lab-architect** to build the
> topology + FTD day-0, then fans out to **firewall-engineer** (all FMC/FTD REST
> work). See the firewall-engineer sections *"Building SD-WAN via the FMC REST API"*
> and *"SD-WAN auto-VPN — the wizard, via API"*. FMC schemas come from the API
> Explorer spec `https://<fmc>/api/api-explorer/fmc.json` — never guess VPN/VTI JSON.
>
> **Reusable component runbooks** (in `Custom Designs/`) break out each building
> block; this runbook stitches them into the full CVD. See "Component runbooks" below.

## What it builds

```
        ISP1 172.16.1.0/24   ISP2 172.16.2.0/24      (IOL routers .254; shared switches)
              │                     │
   ┌──────────┴─────────────────────┴──────────┐   FMCv (mgmt bridged, 198.18.128.11)
   │  HUBS (each an FTD HA pair)                │   manages all FTDs
   │   NYC (primary, .21) + NNJ (secondary,.22) │
   └──────────┬─────────────────────┬───────────┘
      AUTO_VPN overlay (DVTI hubs)  iBGP AS 65070, community 1000
   ┌──────────┴──────┬───────┬──────┴──────┐
  WMA(.24)         PRI(.23) NCT(.25)     MCT(.26)     ← spokes (SVTI auto-built by FMC)
  connected         OSPF    EIGRP        eBGP         ← branch LAN protocol (one each)
  10.72/16         10.71/16 10.73/16    10.74/16
```
Hubs run **DVTI**; spokes' SVTIs are **auto-created by the FMC SD-WAN wizard**. The
overlay is **iBGP AS 65070** (a DVTI can't be static-routed) with **community 1000**
gating the overlay's outbound route-map.

## Prerequisites

- CML with **`fmcv`** (32 GB!) + **`ftdv`** images; IOL routers/unmanaged switches
  for the ISP transports; the System Bridge for mgmt.
- **Host capacity:** FMCv wants 32 GB alone; 6× FTDv (8 GB each) + HA spares is a big
  lab — check `get_system_status` before building.
- FMC reachable, **eval-licensed and then registered to a Smart Account with
  export-controlled features** — SD-WAN/auto-VPN is gated until `exportControl:true`
  on `/license/smartlicenses` (in eval the API silently drops `autoVpnSettings`).
- The `cml` + `fmc` MCP servers wired in; the firewall-engineer agent.

Lab values (**adjust**): mgmt FMC `198.18.128.11`, FTD mgmt `.21`–`.26` (+ HA spares
`.31`–`.34`); ISP1 `172.16.1.0/24`, ISP2 `172.16.2.0/24`; inside LANs NYC `10.100/16`,
NNJ `10.200/16`, PRI `10.71`, WMA `10.72`, NCT `10.73`, MCT `10.74`; overlay loopbacks
`10.255.255.x`/`10.255.254.x` (ISP1/ISP2), AS `65070`, community `1000`.

---

## Stage 1 — Topology + FTD registration  → cml-lab-architect, then firewall-engineer

1. Build the lab: FMCv + one FTDv per site, each dual-homed **Gi0/0→ISP1, Gi0/1→ISP2,
   Gi0/2→inside**; ISP transports as IOL routers on shared switches; mgmt bridged.
   **Topology-as-code:** [`topology.yaml`](topology.yaml) in this folder is the spec
   exported from the validated lab — one `build_lab_from_spec` call rebuilds the full
   25-node end-state topology (incl. the Stage-5 dual-hub + HA nodes), with FTD day-0
   FMC registration and the validated ISP/LAN router configs baked in.
2. **Register each FTDv** → see component **[FMC-Managed FTD Registration](../../Custom%20Designs/FMC-Managed%20FTD%20Registration/runbook.md)**
   (device day-0 `FmcIp`+`FmcRegKey` **and** FMC `POST /devices/devicerecords`; eval
   license → export-control). Create an access policy (e.g. `SDWAN-AC`).

## Stage 2 — Interfaces, zones, VTIs  → firewall-engineer

3. Per site, **physical interfaces + security zones** (FMC PUT physicalinterfaces):
   outside1 = Eth0/0 `172.16.1.<o>/24` zone **OUTSIDE1**, outside2 = Eth0/1
   `172.16.2.<o>/24` zone **OUTSIDE2**, inside = Eth0/2 `10.<site>.0.1/24` zone
   **INSIDE** (`<o>` = the /16 second octet). WAN + inside **must** be zoned or the
   auto-VPN won't treat them as VPN interfaces.
4. **Hubs only:** a loopback per ISP (`Lo1 10.255.255.1/32`, `Lo2 10.255.254.1/32`)
   and a **DVTI** per ISP borrowing that loopback IP
   (`ipAddressAssignmentType:"BORROW_IP_FROM_INTERFACE"`, `borrowIPfrom:{loopback}`
   — needs `name` + id). Spokes need **no** pre-created VTI — the wizard builds it.

## Stage 3 — SD-WAN auto-VPN overlay (per ISP)  → firewall-engineer

5. Build the overlay → component **[Secure Firewall SD-WAN Auto-VPN](../../Custom%20Designs/Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md)**.
   Key: `POST /policy/ftds2svpns` with **`topologyType:"AUTO_VPN"`** (NOT
   `HUB_AND_SPOKE` — it silently drops `autoVpnSettings`), `autoVpnSettings.routeSettings`
   `enableBgp:true / AS 65070 / community 1000 / distributeConnectedNetwork`. HUB
   endpoint = the DVTI + an **`IPv4AddressPool`** (`ipv4PoolsForSpokeVti`); SPOKE
   endpoint = the **physical WAN interface itself** (FMC auto-builds the spoke SVTI +
   assigns its IP from the pool via IKEv2 mode-config). Deploy hub **and** spokes.
6. **Second ISP + ECMP** → component **[FTD Dual-ISP ECMP + Failover](../../Custom%20Designs/FTD%20Dual-ISP%20ECMP%20+%20Failover/runbook.md)**:
   a 2nd `AUTO_VPN` topology over ISP2 (2nd DVTI/loopback/pool, spoke endpoint =
   Eth0/1) with **`enableMultiPath:true`** → FMC adds `maximum-paths 8` to the shared
   `router bgp 65070`; spokes get two tunnels + two iBGP sessions + ECMP.

## Stage 4 — Branch LANs + redistribution  → cml-lab-architect + firewall-engineer

7. Per spoke, add a CML **`iol-xe` LAN node** off the FW's Gi0/2 (inside), then
   redistribute its LAN into the overlay → component
   **[FTD Overlay LAN Redistribution](../../Custom%20Designs/FTD%20Overlay%20LAN%20Redistribution/runbook.md)**.
   Exercised one protocol per site: **WMA connected, PRI OSPF, NCT EIGRP, MCT eBGP**.
   The crux: a **companion `/routing/bgp` MERGES** its `redistribute` into the
   auto-VPN's `router bgp 65070`, and redistributed routes must be **tagged with
   community 1000** (via a RouteMap on the redistribute entry) to pass the auto-VPN's
   outbound filter.

## Stage 5 — Resiliency: dual-hub + HA  → firewall-engineer

8. **Second hub (NNJ)** → component **[FTD Dual-Hub Redundancy](../../Custom%20Designs/FTD%20Dual-Hub%20Redundancy/runbook.md)**:
   add NNJ as `isPrimaryHub:false` on **both** topologies (its own DVTI/loopback/pool
   per ISP, each pool on a **unique /24**); redeploy **all** spokes + both hubs. Each
   spoke now has 4 tunnels/iBGP sessions; the auto-VPN makes the hubs **route
   reflectors**.
9. **HA pairs on the hubs** → component **[FTD HA Pair (FMC)](../../Custom%20Designs/FTD%20HA%20Pair%20(FMC)/runbook.md)**:
   `POST /devicehapairs/ftddevicehapairs`. **CML can't hot-add the failover NIC to a
   booted FTD**, so retrofitting HA meant **rebuilding each hub** with a spare unit
   that has Gi0/3 from first boot (see the component runbook + firewall-engineer).

## Verification

- FMC **SD-WAN Summary** + **S2S VPN Monitoring** dashboards; `fmc_device_health`.
- On an FTD (console via pyATS): `show crypto ikev2 sa` (tunnels up), `show bgp`
  (neighbors up, `maximum-paths`, ECMP `B <lan> via` both next-hops), `show route`.
- **End-to-end pings** (the real proof): `NYC-HOST 10.100.0.100 → each branch LAN
  loopback 10.<site>.100.1` = **0% loss** across the dual-ISP overlay.
- **Failover tests:** `set_link_state stop` a spoke's ISP1 link → traffic rides ISP2
  (DPD-driven, ~40-60 s); isolate the NYC hub → traffic rides NNJ; kill an HA active
  unit → the standby takes over the hub role — all **0% loss** through the overlay.

## Component runbooks (reusable building blocks, in `Custom Designs/`)

| Component | Reuse |
|---|---|
| [FMC-Managed FTD Registration](../../Custom%20Designs/FMC-Managed%20FTD%20Registration/runbook.md) | any FMC-managed FTD lab |
| [Secure Firewall SD-WAN Auto-VPN](../../Custom%20Designs/Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md) | the SD-WAN overlay itself |
| [FTD Dual-ISP ECMP + Failover](../../Custom%20Designs/FTD%20Dual-ISP%20ECMP%20+%20Failover/runbook.md) | multi-transport WAN |
| [FTD Overlay LAN Redistribution](../../Custom%20Designs/FTD%20Overlay%20LAN%20Redistribution/runbook.md) | OSPF/EIGRP/eBGP → BGP overlay |
| [FTD Dual-Hub Redundancy](../../Custom%20Designs/FTD%20Dual-Hub%20Redundancy/runbook.md) | secondary hub / route reflectors |
| [FTD HA Pair (FMC)](../../Custom%20Designs/FTD%20HA%20Pair%20(FMC)/runbook.md) | active/standby FTD |

## Gotchas (the expensive lessons)

- **`topologyType` must be `AUTO_VPN`** — `HUB_AND_SPOKE` returns 201 but GET shows
  `autoVpnSettings:null` (silently dropped).
- **Spoke endpoint `interface` = the physical WAN interface** (only accepted under
  AUTO_VPN); do NOT pre-create a spoke SVTI or pass only `tunnelSourceInterface`.
- **Export-controlled license is mandatory** for SD-WAN/auto-VPN (`exportControl:true`).
- **Redistributed LAN routes need community 1000** or the auto-VPN OUT route-map
  silently filters them.
- **DVTI hubs don't run OSPF adjacency on virtual-access** — that's *why* the CVD
  mandates iBGP over the tunnel.
- **CML locks a node's interface set once it has booted** (only `wipe` frees it) — so
  a failover NIC can't be retrofitted onto a live FTD; rebuild the unit instead.
- **CML unmanaged switches are fixed at 8 ports** — chain a second switch when full.
- **FTD day-0 via MCP `add_node(configuration=)` double-escapes JSON** and silently
  fails provisioning — set day-0 via the CML REST API `PATCH …/nodes/{id}` in
  `DEFINED_ON_CORE` state instead.
