---
id: fabric/sda-underlay
category: fabric
agent: catalyst-engineer
human: none
requires: [lab.up]
provides: [fabric.underlay]
params: [underlay.igp, loopbacks]
est: 15m
---

# fabric/sda-underlay

> IGP underlay, loopbacks, p2p links across the fabric nodes.

## Preflight — assert `requires`
- [ ] `lab.up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Underlay adjacencies up; loopbacks reachable.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
