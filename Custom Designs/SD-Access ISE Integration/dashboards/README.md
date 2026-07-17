# SD-Access ISE Integration — Splunk dashboards

Example **NOC / SOC dashboards** over the live telemetry the SD-Access + ISE + Firewall
stack forwards to Splunk (`198.18.128.51`). Simple XML — import via *Splunk → Search &
Reporting → Dashboards → Create → Source*, or they're already published live (created via
the `splunk` MCP `splunk_create_dashboard`).

| File | Splunk view id | What it shows |
|---|---|---|
| [`firewall-noc.xml`](firewall-noc.xml) | `sda_firewall_noc` | NGFW NOC — allow/deny volume, top talkers/destinations, access-rule hits, TrustSec SGT mix, applications, blocked-connection detail, and the **C8 TLS-decryption** detail (SSL policy/rule/version/action) |
| [`soc-noc-overview.xml`](soc-noc-overview.xml) | `sda_soc_noc_overview` | Single-pane **SOC/NOC wall board** — firewall allow/block + TLS decrypt KPIs, ISE auth passed/failed, over-time trends, blocked-connection threats, top users/NADs, fabric syslog volume, SGT mix |

## Data sources
- **`index=network`, `host=198.18.128.82`** — the **FTDv** (SDA-ACP). The rich connection
  events are `%FTD-6-430002` (connection **begin** — one per connection, carries
  `AccessControlRuleAction` Allow/**Block**, `SrcIP/DstIP`, `User`, `SourceSecurityGroup`
  (SGT), `AccessControlRuleName`) and `%FTD-6-430003` (connection **end** — allowed flows,
  adds `ApplicationProtocol`, bytes, and the **SSL** decryption fields `SSLPolicy`,
  `SSLRuleName`, `SSLActualAction: Decrypt (Resign)`, `SSLVersion`, `SSLFlowStatus`).
- **`index=network`** (all hosts) — the fabric switches' syslog (`cisco:ios`) too.
- **`index=ise`** — Cisco ISE RADIUS syslog (`CISE_Passed_Authentications` /
  `CISE_Failed_Authentications` / `CISE_RADIUS_Accounting`; `UserName=`, `NetworkDeviceName=`).

## SPL notes
- The FTD connection events are **`Key: Value`** (colon-space) formatted, which Splunk does
  **not** auto-extract → every panel uses inline **`rex`** (e.g.
  `rex "AccessControlRuleAction: (?<action>\w+)"`). Queries are **CDATA-wrapped** in the XML
  because the `(?<name>…)` capture groups contain `<`/`>`.
- **Action panels use `430002`** (both Allow and Block; block rules log at *begin* only —
  logEnd is off on the block rules, so blocks are absent from `430003`). **SSL / application
  panels use `430003`** (only they carry that detail).

## Follow-ups (roadmap V2/V3/V5)
- **V2 — Threat/RTC dashboard** needs D13 (FTD SI-block / `430001` intrusion events → Splunk);
  today threats are shown via blocked *connections* (`430002` Block).
- **V5 — Splunkbase apps** (Cisco Security Cloud / Secure Firewall, Cisco ISE add-ons) + their
  CIM-mapped prebuilt dashboards would supersede these hand-built panels; `splunk_generate_telemetry`
  can backfill demo volume.
