---
id: access/switch-radius-dot1x
category: access
agent: ise-engineer
human: none
requires: [ise.nads, ise.policy_sets, fabric.underlay]
provides: [access.dot1x]
params: [edge.ports]
est: 15m
---

# access/switch-radius-dot1x

> cat9000v edge: 802.1X/MAB, closed-auth policy-map, RADIUS to ISE over the global SVI.

## Preflight — assert `requires`
- [ ] `ise.nads`
- [ ] `ise.policy_sets`
- [ ] `fabric.underlay`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
A dot1x/MAB session authorizes against ISE.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
