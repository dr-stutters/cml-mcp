---
id: foundation/windows-dhcp
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up]
provides: [dhcp.scopes]
params: [dhcp.scopes]
est: 5m
---

# foundation/windows-dhcp

> DHCP scopes for endpoints (optional — static host onboarding doesn't need it).

## Preflight — assert `requires`
- [ ] `ad.domain_up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Scope active; a test lease is handed out.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
