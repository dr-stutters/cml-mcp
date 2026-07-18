---
id: identity/ise-nad-onboard
category: identity
agent: ise-engineer
human: none
requires: [ise.reachable]
provides: [ise.nads]
params: [nads, radius.secret]
est: 5m
---

# identity/ise-nad-onboard

> Add the switches/WLC as RADIUS clients (NADs) + device groups.

## Preflight — assert `requires`
- [ ] `ise.reachable`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
NADs listed with the shared secret.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
