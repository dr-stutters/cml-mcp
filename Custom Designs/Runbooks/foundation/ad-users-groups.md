---
id: foundation/ad-users-groups
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up]
provides: [ad.users]
params: [ad.users, ad.groups]
est: 5m
---

# foundation/ad-users-groups

> OUs, test users (alice/bob/carol), and groups (Employees…) the identity + firewall stacks key off.

## Preflight — assert `requires`
- [ ] `ad.domain_up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Users + groups queryable in AD.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
