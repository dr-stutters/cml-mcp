---
id: identity/ise-deploy
category: identity
agent: ise-engineer
human: none
requires: [mcp.connected]
provides: [ise.reachable]
params: [ise.mgmt_ip, ise.admin_cred]
est: 10m
---

# identity/ise-deploy

> Bring ISE up, base network settings, enable the API surfaces (incl. ERS).

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
ise_check_surfaces all green.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
