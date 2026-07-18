---
id: catc/catc-discovery
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.reachable, fabric.underlay]
provides: [catc.inventory]
params: [discovery.range]
est: 15m
---

# catc/catc-discovery

> SSH/SNMP discovery of the fabric nodes into inventory.

## Preflight — assert `requires`
- [ ] `catc.reachable`
- [ ] `fabric.underlay`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Devices reach Managed state.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
