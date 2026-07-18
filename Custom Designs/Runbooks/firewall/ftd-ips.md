---
id: firewall/ftd-ips
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.acp]
provides: [ftd.ips]
params: [ips.policy]
est: 10m
---

# firewall/ftd-ips

> Intrusion policy (SDA-IPS) attached to the ACP.

## Preflight — assert `requires`
- [ ] `ftd.acp`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Intrusion event fires on a test trigger.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
