---
id: firewall/ftd-acp-base
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.interfaces]
provides: [ftd.acp]
params: [objects, rules]
est: 15m
---

# firewall/ftd-acp-base

> Access-control policy + base permit/deny rules + network/host objects.

## Preflight — assert `requires`
- [ ] `ftd.interfaces`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
ACP deployed; test traffic matches expected rules.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
