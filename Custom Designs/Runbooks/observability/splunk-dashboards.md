---
id: observability/splunk-dashboards
category: observability
agent: splunk-engineer
human: none
requires: [splunk.securitycloud, telemetry.syslog]
provides: [splunk.dashboards]
params: []
est: 10m
---

# observability/splunk-dashboards

> Deploy the four committed dashboards (firewall-noc, soc-noc-overview, threat-rtc, tls-decryption).

## Preflight — assert `requires`
- [ ] `splunk.securitycloud`
- [ ] `telemetry.syslog`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
All four render with data.

## Rollback
_TODO_

## Gotchas
- XML sources are the committed dashboards/*.xml — deploy with splunk_create_dashboard.
