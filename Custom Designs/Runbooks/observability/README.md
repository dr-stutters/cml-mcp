# Observability — Splunk

Splunk base + indexes, syslog/HEC inputs, the telemetry sources, CIM, the Cisco add-ons, and the four dashboards. Driven by **splunk-engineer** (device agents point their syslog).

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`splunk-base`](splunk-base.md) | none | splunk.up, splunk.indexes | Splunk node up; indexes ise/network/catc/health created. |
| [`splunk-syslog-inputs`](splunk-syslog-inputs.md) | none | splunk.inputs | UDP inputs: 514 (cisco:ios), 5514 (cisco:ftd:syslog), 20514 (cisco:ise:syslog). |
| [`syslog-sources`](syslog-sources.md) | gui | telemetry.syslog | Point each device's syslog at Splunk (switches → 514, FTD → 5514, ISE remote-logging-target → 20514). |
| [`splunk-hec`](splunk-hec.md) | none | splunk.hec | Enable HEC + tokens (CatC webhooks, cross-platform health). |
| [`healthcheck-cron`](healthcheck-cron.md) | none | telemetry.health | Scheduled cross-platform health check → HEC → index=health. |
| [`splunk-cim`](splunk-cim.md) | external-download | splunk.cim | Install the Splunk CIM add-on (Splunk_SA_CIM 8.5.0) — normalization prerequisite. |
| [`splunk-ise-addon`](splunk-ise-addon.md) | external-download | splunk.ise_addon | Install the Splunk Add-on for Cisco ISE 5.0.0; index=ise CIM-parsed + its dashboards. |
| [`splunk-security-cloud`](splunk-security-cloud.md) | gui | splunk.securitycloud | Install Cisco Security Cloud 4.0 + wire the eStreamer input (V6/V8) → real Conn/Intrusion/File/Malware. |
| [`splunk-dashboards`](splunk-dashboards.md) | none | splunk.dashboards | Deploy the four committed dashboards (firewall-noc, soc-noc-overview, threat-rtc, tls-decryption). |

## Example prompts
- "Stand up Splunk with the ise/network/catc/health indexes and the syslog inputs"
- "Install CIM then the ISE add-on and confirm index=ise is CIM-parsed"
- "Deploy the four dashboards from the committed XML"

## Category gotchas
- CML docker Splunk is capped at 1 CPU → use an ubuntu-KVM node; SSH is closed → app installs via Splunk Web :8000 upload; env var is SPLUNK_PASSWORD.
- FTD gets its OWN 5514 input (cisco:ftd:syslog) + the message_id search-time EXTRACT + DM acceleration.
- Security Cloud 4.0 eStreamer REST handler rejects the `password` arg → use the Add-Input UI; index default cisco_secure_fw doesn't exist → use `network`.
- ISE remote-logging-target name must have NO hyphens (GUI-only step, lives in syslog-sources).

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
