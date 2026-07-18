---
id: firewall/fmc-base
category: firewall
agent: firewall-engineer
human: none
requires: [mcp.connected]
provides: [fmc.api]
params: [fmc.mgmt_ip, fmc.cred]
est: 20m
---

# firewall/fmc-base

> FMCv up, licensing, domain confirmed.

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Token + fmc_server_version.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
