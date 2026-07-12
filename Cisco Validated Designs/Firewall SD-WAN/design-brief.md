# Firewall SD-WAN — design brief

> **Status:** skeleton. The sections below are the agent-consumable outline;
> the specifics get filled in from the CVD PDF once it's dropped in this folder.
> Items marked `TODO: from PDF` must come from the document — do not fabricate.

Distilled reference for the **firewall-engineer** agent. Source: the Cisco
Secure Firewall SD-WAN deployment guide (see [links.md](links.md)). This is
**Secure Firewall Threat Defense's own SD-WAN**, configured in FMC on the FTD —
not Cisco Catalyst SD-WAN.

## Scope & when to use

- What the design delivers (secure SD-WAN edge on Secure Firewall: multi-ISP
  WAN, application-aware path selection, direct internet access with security
  inspection). `TODO: from PDF`
- Supported FTD / FMC versions and platforms. `TODO: from PDF`
- When to reach for this vs. plain FMC-managed FTD. `TODO: from PDF`

## Topology / components

- Devices: FTDv (SD-WAN edge) + FMCv (manager); dual (or multi) ISP / WAN
  transports; inside/LAN; optional data center / hub side. `TODO: from PDF`
- CML mapping: `ftdv`, `fmcv`, external connectors / unmanaged switches for the
  WAN transports and LAN. Interface roles (WAN1/WAN2/inside). `TODO: from PDF`
- Addressing / transport plan. `TODO: from PDF`

## Config workflow (FMC-managed)

Expected building blocks (confirm/expand from the PDF):

1. **WAN interfaces** — define the WAN-facing interfaces and their zones.
   `TODO: from PDF`
2. **ECMP zones** — group WAN interfaces for load-balancing / redundancy across
   ISPs. `TODO: from PDF`
3. **Path monitoring (IP SLA)** — measure RTT / jitter / packet loss / MOS per
   WAN link for path decisions. `TODO: from PDF`
4. **Application-aware policy-based routing (PBR)** — steer applications over
   the best/allowed path; direct internet access (DIA) for selected apps.
   `TODO: from PDF`
5. **Routing & redundancy** — default/static routes with metrics, BFD, failover
   between transports. `TODO: from PDF`
6. **FMC SD-WAN wizard / summary** — the guided workflow and the objects it
   creates. `TODO: from PDF`
7. **Deploy** — push to the FTD and confirm. `TODO: from PDF`

## Verification

- `show route`, PBR / path-monitoring status and metrics on the FTD.
  `TODO: from PDF`
- FMC health / deployment success; per-application path selection behaving as
  intended; failover on transport loss. `TODO: from PDF`

## Gotchas

- `TODO: from PDF` (version requirements, interface constraints, ordering
  dependencies, licensing, anything the guide calls out).

## CML validation notes

- How to reproduce a representative slice in CML (FTDv + FMCv + two WAN
  transports via external connectors, path monitoring across them). `TODO`
- Cross-reference the firewall-engineer agent's HA and managed-mode sections for
  the FTD/FMC bring-up that precedes SD-WAN config.
