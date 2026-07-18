---
id: fabric/sda-host-onboard
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.gateways, access.dot1x]
provides: [fabric.hosts]
params: []
est: 10m
---

# fabric/sda-host-onboard

> Onboard hosts on edge ports (static or closed-auth) into their VN.

## Preflight — assert `requires`
- [ ] `fabric.gateways`
- [ ] `access.dot1x`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Host reaches services through the fabric.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
