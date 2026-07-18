---
id: firewall/ftd-register
category: firewall
agent: firewall-engineer
human: none
requires: [fmc.api]
provides: [ftd.registered]
params: [ftd.mgmt_ip, reg.key]
est: 15m
---

# firewall/ftd-register

> Register the FTDv to FMC (day-0 mode fixed up front).

## Preflight — assert `requires`
- [ ] `fmc.api`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Device healthy/Managed in FMC.

## Rollback
_TODO_

## Gotchas
- Gate registration on TCP 8305, not the API surface.
