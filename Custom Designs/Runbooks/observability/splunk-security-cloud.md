---
id: observability/splunk-security-cloud
category: observability
agent: splunk-engineer
human: gui
requires: [splunk.up, ftd.estreamer_client]
provides: [splunk.securitycloud]
params: []
est: 20m
---

# observability/splunk-security-cloud

> Install Cisco Security Cloud 4.0 + wire the eStreamer input (V6/V8) → real Conn/Intrusion/File/Malware.

## Preflight — assert `requires`
- [ ] `splunk.up`
- [ ] `ftd.estreamer_client`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
eStreamer events flowing; Secure_Firewall_Dataset populated.

## Rollback
_TODO_

## Human steps (⚠ requires operator — `human: gui`)
Download the app (login-gated) + upload via Splunk Web :8000; add the eStreamer input via the app's Add-Input UI (the 4.0 REST handler rejects the `password` arg); hand in the pkcs12 from ftd-estreamer-client; index=network.

## Gotchas
- _none banked yet_
