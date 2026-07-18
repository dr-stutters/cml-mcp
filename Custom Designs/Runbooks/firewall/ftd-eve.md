---
id: firewall/ftd-eve
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.acp]
provides: [ftd.eve]
params: []
est: 5m
---

# firewall/ftd-eve

> Encrypted Visibility Engine (C14) — classify encrypted apps/threats without decryption.

## Preflight — assert `requires`
- [ ] `ftd.acp`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
evesettings enabled:true, mode MONITOR_TRAFFIC.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
