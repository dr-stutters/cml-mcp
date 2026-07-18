---
id: observability/splunk-cim
category: observability
agent: splunk-engineer
human: external-download
requires: [splunk.up]
provides: [splunk.cim]
params: []
est: 5m
---

# observability/splunk-cim

> Install the Splunk CIM add-on (Splunk_SA_CIM 8.5.0) — normalization prerequisite.

## Preflight — assert `requires`
- [ ] `splunk.up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Splunk_SA_CIM present + enabled.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: external-download`)
Download CIM 8.5.0 from Splunkbase (app 1621 — login-gated) and hand it in; install via Splunk Web :8000 upload (SSH is closed on the box).

## Gotchas
- _none banked yet_
