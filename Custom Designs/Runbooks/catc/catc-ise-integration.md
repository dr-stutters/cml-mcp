---
id: catc/catc-ise-integration
category: catc
agent: catalyst-center-engineer
human: gui
requires: [catc.reachable, ise.certs]
provides: [catc.ise_integrated]
params: []
est: 15m
---

# catc/catc-ise-integration

> CatC ↔ ISE integration (pxGrid + ERS).

## Preflight — assert `requires`
- [ ] `catc.reachable`
- [ ] `ise.certs`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
ISE shows Active in CatC.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: gui`)
**You approve the pxGrid client in the ISE GUI** (pxGrid Services → pending → Approve). No clean API alternative — pxGrid approval is GUI-gated. Watch the old-CN cert gotcha.

## Gotchas
- _none banked yet_
