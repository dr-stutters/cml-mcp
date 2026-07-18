---
id: firewall/ftd-url-geo-app
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.acp]
provides: [ftd.depth]
params: []
est: 15m
---

# firewall/ftd-url-geo-app

> URL filtering (C12), application/AVC (C13), geolocation (C15) rules.

## Preflight — assert `requires`
- [ ] `ftd.acp`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
App-ID block proven; URL + geo rules deployed.

## Rollback
_TODO_

## Gotchas
- Applications endpoint ignores name filters → page it (HTTP=676, HTTPS=1122); Country China=156.
