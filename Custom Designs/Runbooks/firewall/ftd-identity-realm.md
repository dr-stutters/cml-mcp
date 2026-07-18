---
id: firewall/ftd-identity-realm
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.acp, ad.domain_up]
provides: [ftd.identity]
params: [realm]
est: 15m
---

# firewall/ftd-identity-realm

> FMC↔AD realm + identity policy for user-based rules.

## Preflight — assert `requires`
- [ ] `ftd.acp`
- [ ] `ad.domain_up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Realm downloads users; a user-based rule matches.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
