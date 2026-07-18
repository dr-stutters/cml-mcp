---
id: fabric/sda-border-handoff
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.overlay]
provides: [fabric.handoff]
params: [border.bgp]
est: 15m
---

# fabric/sda-border-handoff

> Border external handoff (VRF-lite/BGP) toward the fusion.

## Preflight — assert `requires`
- [ ] `fabric.overlay`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Border BGP up; fabric→outside route present.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
