---
id: identity/ise-policy-sets
category: identity
agent: ise-engineer
human: none
requires: [ise.idstores, ise.nads]
provides: [ise.policy_sets]
params: []
est: 10m
---

# identity/ise-policy-sets

> Wired/wireless policy set(s) with authN + authZ rules (incl. the ANC_Quarantine authz rule).

## Preflight — assert `requires`
- [ ] `ise.idstores`
- [ ] `ise.nads`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Policy set active; matches on a test auth.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
