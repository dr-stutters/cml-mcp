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
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Cross-VRF reachability fabric↔shared-services.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
