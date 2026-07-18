---
id: wireless/wlc-base
category: wireless
agent: wireless-engineer
human: none
requires: [mcp.connected]
provides: [wlc.restconf]
params: [wlc.mgmt_ip, wlc.cred]
est: 10m
---

# wireless/wlc-base

> C9800 RESTCONF up (aaa new-model, priv-15 user, http secure-server, restconf).

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
wlc_check green.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
