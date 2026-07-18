---
id: wireless/wlc-radius-ise
category: wireless
agent: wireless-engineer
human: none
requires: [wlc.restconf, ise.nads]
provides: [wlc.aaa]
params: []
est: 10m
---

# wireless/wlc-radius-ise

> RADIUS server + AAA group + dot1x method list to ISE; onboard the WLC as an ISE NAD.

## Preflight — assert `requires`
- [ ] `wlc.restconf`
- [ ] `ise.nads`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
RADIUS group + method list present.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
