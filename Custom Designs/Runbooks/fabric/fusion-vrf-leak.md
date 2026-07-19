---
id: fabric/fusion-vrf-leak
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.handoff]
provides: [fusion.leak]
params: [vrf_leak]
est: 10m
---

# fabric/fusion-vrf-leak

> Fusion router VRF route-leak (fabric VN ↔ shared services / mgmt).

## Preflight — assert `requires`
- [ ] `fabric.handoff`

## Steps
1. **FUSION handoff + eBGP** — the fusion side of the Border↔FUSION /30, eBGP AS65000 ↔ AS65001, receiving
   the VN prefix and advertising a default (`default-originate`) back to the border so the fabric gets a default route.
2. **NAT overload** — `ip nat` overload the fabric pool `172.16.10.0/24` toward shared services / the mgmt
   net, so fabric hosts reach ISE / DC / Splunk (198.18.x) with a routable source.
3. **Static back-route to the fabric pool** — `ip route 172.16.10.0/24 10.1.24.1` on FUSION so return
   traffic finds the border.

## Verify — prove `provides`
Fabric host ↔ shared services both directions — e.g. HOST1 `ping 198.18.134.35` (ISE) **4/4, 0% loss** (proven 2026-07-18).

## Rollback
Remove the NAT, the static route, and the eBGP on FUSION.

## Gotchas
- **FUSION needs the static back-route** to the fabric pool (`172.16.10.0/24 → 10.1.24.1`), or replies from
  shared services have no path back into the fabric.
