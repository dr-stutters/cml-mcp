---
id: observability/splunk-ise-addon
category: observability
agent: splunk-engineer
human: external-download
requires: [splunk.cim, telemetry.syslog]
provides: [splunk.ise_addon]
params: []
est: 10m
---

# observability/splunk-ise-addon

> Install the Splunk Add-on for Cisco ISE 5.0.0; index=ise CIM-parsed + its dashboards.

## Preflight — assert `requires`
- [ ] `splunk.cim`
- [ ] `telemetry.syslog`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Add-on parses cisco:ise:syslog; dashboards populate.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: external-download`)
Download ISE add-on 5.0.0 (Splunkbase app 1915 — login-gated); install via Splunk Web :8000 upload.

## Gotchas
- _none banked yet_
