---
id: observability/healthcheck-cron
category: observability
agent: splunk-engineer
human: none
requires: [splunk.hec]
provides: [telemetry.health]
params: []
est: 5m
---

# observability/healthcheck-cron

> Scheduled cross-platform health check → HEC → index=health.

## Preflight — assert `requires`
- [ ] `splunk.hec`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Health events arrive ~every 30 min.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
