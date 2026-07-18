---
id: fabric/sda-anycast-gw
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.overlay]
provides: [fabric.gateways]
params: [vns, anycast_gw]
est: 10m
---

# fabric/sda-anycast-gw

> Anycast gateway SVIs per VN/VLAN on the edges.

## Preflight — assert `requires`
- [ ] `fabric.overlay`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Anycast SVI up; gateway pings.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
