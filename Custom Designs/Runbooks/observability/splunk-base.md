---
id: observability/splunk-base
category: observability
agent: splunk-engineer
human: none
requires: [mcp.connected]
provides: [splunk.up, splunk.indexes]
params: [splunk.mgmt_ip, splunk.cred]
est: 15m
---

# observability/splunk-base

> Splunk node up; indexes ise/network/catc/health created.

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
splunk_check green; indexes exist.

## Rollback
_TODO_

## Gotchas
- Prefer an ubuntu-KVM node (docker Splunk is capped at 1 CPU in CML).
