---
id: firewall/ftd-estreamer-client
category: firewall
agent: firewall-engineer
human: gui
requires: [fmc.api]
provides: [ftd.estreamer_client]
params: [splunk.mgmt_ip, pkcs12.pass]
est: 10m
---

# firewall/ftd-estreamer-client

> eStreamer client cert for the Splunk box (feeds splunk-security-cloud).

## Preflight — assert `requires`
- [ ] `fmc.api`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Client created; FMC:8302 open; pkcs12 exported.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: gui`)
**FMC GUI (your account):** Integrations → eStreamer → tick event types → Save → Create Client for the Splunk IP + a pkcs12 password → download the .pkcs12. Then hand the file into the session. GUI-only in FMC — no REST equivalent for client-cert export.

## Gotchas
- _none banked yet_
