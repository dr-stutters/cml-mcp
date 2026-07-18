---
id: observability/syslog-sources
category: observability
agent: splunk-engineer
human: gui
requires: [splunk.inputs, fabric.overlay, ise.reachable, ftd.acp]
provides: [telemetry.syslog]
params: []
est: 15m
---

# observability/syslog-sources

> Point each device's syslog at Splunk (switches → 514, FTD → 5514, ISE remote-logging-target → 20514).

## Preflight — assert `requires`
- [ ] `splunk.inputs`
- [ ] `fabric.overlay`
- [ ] `ise.reachable`
- [ ] `ftd.acp`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Events landing per source in the right index.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: gui`)
**ISE remote-logging-target is a GUI-only step** (Administration → System → Logging) and its name must have NO hyphens/special chars. Switch + FTD syslog are agent-automatable.

## Gotchas
- _none banked yet_
