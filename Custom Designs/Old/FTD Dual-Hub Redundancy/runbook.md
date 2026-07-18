# Component — FTD Dual-Hub Redundancy

Add a **second hub** to an SD-WAN overlay so branches have redundant headquarters
paths. Builds on [SD-WAN Auto-VPN](../Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md)
(and [Dual-ISP ECMP](../FTD%20Dual-ISP%20ECMP%20+%20Failover/runbook.md) if two ISPs).

## Build

1. Bring up the second hub FTD (e.g. NNJ) — register it, configure WAN + inside
   interfaces/zones, a loopback + DVTI **per ISP**, and a spoke-VTI `IPv4AddressPool`
   **per ISP**.
2. **Each hub's pool must be on a unique /24** — FMC rejects two hub pools on the same
   subnet ("configure IPv4 Pools with unique subnet"). E.g. NYC ISP1 `10.255.255.0/24`
   / ISP2 `10.255.254.0/24`; NNJ ISP1 `10.255.253.0/24` / ISP2 `10.255.252.0/24`.
3. Add the new hub as an endpoint on **both** AUTO_VPN topologies with
   **`isPrimaryHub:false`** (secondary). `borrowIPfrom` on the DVTI needs `name` too,
   not just `id`.
4. **Redeploy ALL spokes + both hubs** — spokes only build tunnels to the new hub
   after a redeploy (miss this and the new tunnels stay Idle).

## Result

Each spoke now has **N_hubs × N_ISPs tunnels** (4, for 2 hubs × 2 ISPs) and that many
iBGP sessions; a remote LAN shows 4 BGP paths. The auto-VPN configures the **hubs as
route reflectors** (Cluster-list / Originator appear in the BGP table).

## Verify

```
show crypto ikev2 sa    → 4 tunnels on each spoke (NYC+NNJ × ISP1+ISP2)
show bgp <remote lan>   → 4 paths; hubs are RRs
```
**Hub failover:** isolate the primary hub (`set_link_state stop` on *both* its WAN
links) → spoke-to-spoke / spoke-to-LAN traffic stays **0% loss** via the secondary hub.
