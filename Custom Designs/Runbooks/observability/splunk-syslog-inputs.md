---
id: observability/splunk-syslog-inputs
category: observability
agent: splunk-engineer
human: none
requires: [splunk.up]
provides: [splunk.inputs]
params: []
est: 10m
---

# observability/splunk-syslog-inputs

> UDP inputs: 514 (cisco:ios), 5514 (cisco:ftd:syslog), 20514 (cisco:ise:syslog).

## Preflight — assert `requires`
- [ ] `splunk.up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Inputs listening with the right sourcetype/index.

## Rollback
_TODO_

## Gotchas
- FTD gets its OWN 5514 input + the message_id EXTRACT + data-model acceleration.
