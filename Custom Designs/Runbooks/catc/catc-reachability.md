---
id: catc/catc-reachability
category: catc
agent: catalyst-center-engineer
human: none
requires: [mcp.connected]
provides: [catc.reachable]
params: [catc.url, catc.cred]
est: 2m
---

# catc/catc-reachability

> Token auth + reachability (catc_check).

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
catc_check returns version.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
