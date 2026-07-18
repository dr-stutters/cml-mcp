# Test Plan — Secure Firewall depth + Cisco Security Cloud observability

**Plan ID prefix:** `SFW-` · **Version:** 1.0 · **Last updated:** 2026-07-18

## 1. Scope & purpose

Validates the **firewall-depth** and **observability** roadmap items built on the
**SD-Access ISE Integration** lab (context modules
`Custom Designs/SD-Access ISE Integration/modules/splunk-security-cloud.md` and
`fmc-firewall-depth.md`). Two capability groups:

- **Observability (V6–V8):** Cisco's **Cisco Security Cloud** Splunk app (4.0) drives the
  **Secure Firewall dashboard** from real FTD telemetry — first via **FTD syslog** (UDP 5514
  → `cisco:ftd:*`), then via the app's **eStreamer** input pulling Connection / Intrusion /
  File / Malware events straight from FMC over TCP 8302 (`cisco:sfw:estreamer`) into the
  `Cisco_Security` data model.
- **Firewall depth (C6/C9/C12–C16):** exercised deep-inspection controls on the FTD —
  a real **IPS** intrusion event, real **malware** (EICAR) file detection, **URL** category
  block, **application (AVC)** block, **Encrypted Visibility Engine (EVE)**, **geolocation**
  block, and a selective **TLS-decryption bypass** — each present on `SDA-ACP`/`SDA-Decrypt`
  and **deployed** to the FTD.

**Explicitly out of scope:** live external Internet hits for the URL/geo blocks (HOST1 has
no Internet — those cases are validated config-present + deployed, not live external
traffic); load/scale testing; dashboard pixel rendering (validated by the data-model
`tstats` counts the panels consume, not a browser screenshot); the FMC GUI-only eStreamer
client-cert enrolment steps (validated by the resulting Splunk input + live events).

## 2. System under test

| Item | Value |
|---|---|
| Component | SD-Access ISE Integration lab — FMC/FTD deep inspection + Splunk Cisco Security Cloud |
| Version(s) verified against | FMC 10.0.1 (build 1) · FTD 10.0.0 (Snort 3.9.3.1) · Splunk 10.4.0 · Cisco Security Cloud app 4.0.0 · ISE 3.5.0.527 · cat9000v IOS-XE 17.18 |
| Environment | CML lab **SDA-Fabric** (`77dd2fde-1fda-4cc9-9b29-48ff98bd1395`) + FMC/FTD + Splunk — IPs are **lab-specific** |
| Dependencies | FTD inline (fusion PBR steering); reachable FMC with a deployable FTD; Splunk `.51` receiving FTD syslog + reachable from FMC eStreamer; a live fabric endpoint (HOST1/alice) for traffic generation |

## 3. Test approach / levels

This plan is **manual/live** end-to-end acceptance plus the suite's **offline automated
gate** for the MCP servers that underpin it:

- **Automated (offline)** — `ruff` + `pytest` across the six MCP repos via
  `Test Reports/run_report.py` (records the firepower-mcp / splunk-mcp / cml-mcp unit gate).
- **Manual/Live** — FMC REST GETs (read-only), Splunk REST + SPL search, CML reads; recorded
  by hand with evidence.

**Reversibility contract:** this run is **read-only** on built configuration — every FMC and
Splunk call is a GET/search. No writes, no round-trips required. (The firewall-depth objects
and the Splunk inputs under test were built in prior sessions; this plan *verifies* them.)

## 4. Preconditions & environment

- FMC creds in the shared `../.env` (`FMC_URL`, `FMC_USERNAME`=`admin`, `FMC_PASSWORD`) — the
  REST admin, distinct from the GUI operator `admin1`.
- Splunk creds in `../.env` (`SPLUNK_HOST`=198.18.128.51, `SPLUNK_USERNAME`, `SPLUNK_PASSWORD`).
- ACP **SDA-ACP** `5254002E-0748-0ed3-0000-004294968720`; decryption policy **SDA-Decrypt**
  `b10b55fe-81ed-11f1-ab09-ebb47983003b`; FTD device `37ffcab8-8126-11f1-a47b-d7a4b50be775`.
- Fabric booted/converged; EDGE1 edge-auth healthy so HOST1 traffic flows through the FTD.
- Credentials are **never** in this plan — only the `.env` variable names.

## 5. Test cases

### Observability — Cisco Security Cloud + telemetry (V6–V8)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SFW-001` | V6 — Cisco Security Cloud app installed/enabled; data model + dashboard present | GET `/services/apps/local/CiscoSecurityCloud`; GET `…/data/models/Cisco_Security`; GET `…/data/ui/views/secure_firewall_dashboard` | app **4.0.0**, `disabled=false`, `visible=true`; `Cisco_Security` data model registered (`Secure_Firewall_Dataset` + child datasets); `secure_firewall_dashboard` view exists | `manual-live` (Splunk REST) |
| `SFW-002` | V7 — Secure Firewall dashboard via FTD syslog | List Splunk inputs; GET FMC platform-settings syslog server; SPL `index=network sourcetype=cisco:ftd:*` | dedicated **UDP 5514** input (`sourcetype cisco:ftd:syslog`, `index network`, `connection_host=ip`) enabled; FTD syslog server on **5514**; `cisco:ftd:*` events present + recent (index-time sub-classified to `cisco:ftd:connection` etc.) | `manual-live` (Splunk REST + SPL) |
| `SFW-003` | NAC fix — EDGE1 reload cleared the wedged edge-auth; HOST1 traffic restored | SPL `index=network host=198.18.128.82 sourcetype=cisco:ftd:*` for recent connection events | live FTD connection/syslog events from the FTD data IP **198.18.128.82** present and **recent** (≤ a few min old) ⇒ fabric east-west path up, HOST1 services flowing through the FTD | `manual-live` (Splunk SPL) |
| `SFW-004` | V8 — eStreamer input enabled; real FMC events flowing; child datasets populated | GET `CiscoSecurityCloud_sbg_fw_estreamer_input`; SPL by `EventType`; `tstats` over `Secure_Firewall_Dataset.{Connection,Intrusion,File,Malware}_Events` | input **SDA_FMC_eStreamer** `disabled=false`, `fmc_host=198.18.128.80`, `fmc_port=8302`, `sourcetype cisco:sfw:estreamer`, `index network`; real events **ConnectionEvent/IntrusionEvent/FileEvent**; all four child datasets `count > 0` | `manual-live` (Splunk REST + SPL/tstats) |

### Firewall depth — deep inspection (C6/C9/C12–C16)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SFW-005` | C6 — real IPS intrusion event | SPL `sourcetype=cisco:sfw:estreamer EventType=IntrusionEvent` by signature | signature **`LOCAL C6 RTC test trigger`** present (real `IntrusionEvent`, count > 0) | `manual-live` (Splunk SPL) |
| `SFW-006` | C9 — real malware (EICAR) file event | SPL `sourcetype=cisco:sfw:estreamer EventType=FileEvent` by `FileName` | **`eicar.com`** with **`SHA_Disposition=Malware`**, **`ThreatName=EICAR`** (real `FileEvent`) → File + Malware datasets | `manual-live` (Splunk SPL) |
| `SFW-007` | C12 — URL-category block rule present + deployed | FMC GET `SDA-ACP/accessrules` (expanded) | `C12-Block-Malware-URL` — **BLOCK**, `urls.urlCategoriesWithReputation` = **Malware Sites**, src `net-campus10`; enabled | `manual-live` (FMC GET) — config-only (HOST1 has no Internet) |
| `SFW-008` | C13 — application/AVC block rule present + deployed | FMC GET `SDA-ACP/accessrules` (expanded) | `C13-Block-HTTP-App` — **BLOCK**, application **HTTP (id 676)**, src `net-campus10` → `host-splunk`; enabled (proven earlier: HOST1 `wget http://198.18.128.51:8000/` times out) | `manual-live` (FMC GET) |
| `SFW-009` | C14 — Encrypted Visibility Engine enabled | FMC GET `SDA-ACP/evesettings/{id}` | `enabled=true`, `mode=MONITOR_TRAFFIC` | `manual-live` (FMC GET) |
| `SFW-010` | C15 — geolocation/country block rule present + deployed | FMC GET `SDA-ACP/accessrules` (expanded) | `C15-Block-Country-China` — **BLOCK**, dst **Country China (id 156)**, src `net-campus10`; enabled | `manual-live` (FMC GET) — config-only (no Internet) |
| `SFW-011` | C16 — selective TLS-decryption bypass above the resign rule | FMC GET `SDA-Decrypt/decryptionpolicyrules` (expanded) | `C16-DND-ISE` — **DO_NOT_DECRYPT**, src `net-campus10` → dst `net-ise`, at **ruleIndex 1**, above `Decrypt-CAMPUS-443` (DECRYPT_RESIGN, index 2) — proven earlier: `openssl s_client` to ISE:443 shows real issuer `CN=Mitchcloud-Lab-Root-CA` (bypassed) | `manual-live` (FMC GET) |
| `SFW-012` | Deployment hygiene — nothing pending | FMC `fmc_deployable_devices`; FTD device record | `deployable_devices` **empty**; FTD `deploymentStatus=DEPLOYED`, `managementState=MANAGED`, `isConnected=true` | `manual-live` (FMC GET) |

### Automated gate (MCP servers underpinning the above)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SFW-013` | Offline gate — server code green | `Test Reports/run_report.py` (ruff + pytest, six repos) | ruff clean on all six; **134 unit pass / 0 fail** (incl. firepower-mcp, splunk-mcp, cml-mcp) | `unit` (`run_report.py`) |

## 6. Pass/fail & exit criteria

- **Automated gate:** `ruff` + `pytest` green across the six repos (SFW-013).
- **Manual/live gate:** every case reaches its expected result with evidence. C12/C15
  (SFW-007/010) are **config-present + deployed** validations (HOST1 has no Internet, by
  design) — deployed rule read-back is the pass criterion, not a live external hit.
- **Read-only gate:** no built configuration modified (all FMC/Splunk calls are GET/search).
- **Plan pass =** all cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| Cisco Security Cloud app + model + view | `SFW-001` | manual-live (Splunk REST) |
| Secure Firewall dashboard via syslog | `SFW-002` | manual-live |
| NAC fix — live traffic restored | `SFW-003` | manual-live |
| eStreamer real data + data model | `SFW-004` | manual-live |
| C6 real intrusion | `SFW-005` | manual-live |
| C9 real malware | `SFW-006` | manual-live |
| C12 URL / C13 AVC / C15 geo access rules | `SFW-007`,`SFW-008`,`SFW-010` | manual-live (FMC GET) |
| C14 EVE setting | `SFW-009` | manual-live |
| C16 decryption bypass | `SFW-011` | manual-live |
| Deployment hygiene | `SFW-012` | manual-live |
| MCP server offline gate | `SFW-013` | unit |

Manual-only gaps (no automated coverage): all live cases (lab-design acceptance is
manual-live); C12/C15 external-traffic proof deferred (no Internet in the lab).

## 8. Execution record

Filled per run by the customer test report.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| 2026-07-18 | testing-agent (live) | 13 PASS · 0 FAIL · 0 SKIP | report.pdf | O1 FTDv health yellow (cosmetic Cloud Connector); O2 run_report.py smoke-timeout handler bug |
