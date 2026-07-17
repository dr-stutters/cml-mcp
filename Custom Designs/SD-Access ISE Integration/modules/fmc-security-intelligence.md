# C7 — Security Intelligence threat-feed blocking

**Goal:** an FMC **Security Intelligence (SI)** block list drops traffic to a listed
destination **before** the access-control rules even evaluate — reputation/threat-feed
enforcement at the front of the packet path — and logs the block. Prereq: C1 (FTD inline
at the fusion). Live-proven 2026-07-17 on the SDA-Fabric lab (FTDv 198.18.128.81, ACP
`SDA-ACP`).

## What SI is and why "pre-ACL" matters
SI is evaluated **ahead of** the AC rules. A dst on the SI block list is dropped as a
**"Security-Related Connection" → Block → Reason: IP Block**, and the AC rule that would
otherwise *allow* it never runs. Proof = a listed dst blocked **and** a control dst (same
allow rule, not listed) still reachable.

## API reality (what works, what's GUI-only)
The FMC REST API is **limited** for SI:
- **Custom SI *list/feed* objects are GUI-only.** `POST /object/sinetworklists` → **405**;
  the built-in editable **`Global-Block-List` is `readOnly:true`** over REST. Uploading a
  custom `.txt` SI list or adding literals to the Global-Block-List must be done in the GUI.
- **What the API *does* allow:** add a **Host or Network object** (NOT a `NetworkGroup` —
  `"Object … (type: NetworkGroup) is not allowed in Security Intelligence Policy"`) to the
  ACP's SI **`networks.blocklist`** via
  `PUT /policy/accesspolicies/{acp}/securityintelligencepolicies/{sip}`. That host/network
  object *is* your "custom threat list" entry.

### Recipe (curl — `fmc_api_call` won't take a JSON-object body)
1. `GET …/securityintelligencepolicies` → the SI policy id (`{sip}`).
2. `GET …/securityintelligencepolicies/{sip}` → note `networks.blocklist`
   (defaults to `Global Block List`) + `networks.blocklistLogging`.
3. `PUT` it back with your **Host** object appended to `networks.blocklist`
   (`{"network":{"name":..,"id":..,"type":"Host"}}`) and
   `networks.blocklistLogging.sendLogsToSyslogServer:true`.
4. `fmc_deploy` the FTD.

## Live proof (2026-07-17)
Used **host-splunk (198.18.128.51)** as a stand-in threat — an *otherwise ACL-allowed,
reachable* dst, giving a crisp reachable→blocked flip (real deployments list actual
malicious IPs). After deploy:
- HOST1 (`alice` 172.16.10.50) → **198.18.128.51 = 100% loss** (SI-blocked);
- HOST1 → **198.18.134.35 (ISE, control, allowed, not listed) = 0% loss** — only the
  listed dst is blocked, and the block is **pre-ACL**.
- **FMC → Events & Logs → Unified Events:** Event Type **Security-Related Connection**,
  Action **Block**, Reason **IP Block**, Src 172.16.10.50 → Dst 198.18.128.51, ACP SDA-ACP,
  Device FTDv, **Security Intelligence: host-splunk** (the matched list entry).
Reversible: remove the host from `networks.blocklist`, redeploy → 0% loss restored.

## KNOWN GAP (D13) — the SI-block security event doesn't reach Splunk
Enabling the ACP security-event syslog **did** help: after
`PUT …/loggingsettings/{id}` → `syslogConfigFromPlatformSetting:true` + `enableipsSyslog:true`
(plus SI `blocklistLogging.sendLogsToSyslogServer:true`), **connection events (`430002`/`430003`)
now reach Splunk** alongside the LINA `%FTD-*` messages the D5 pipeline already carried
(`305011` NAT, `111xxx` config, `199017`). **What's still missing is specifically the SI-*block*
security event** (and the `430001` intrusion event): a message-id histogram
(`index=network host=198.18.128.82 | rex "%FTD-\d+-(?<msgid>\d+)" | stats count by msgid`) shows
**0** Block-action / Security-Intelligence / `430001` events during the block window. So the SI
block is logged to the **FMC event viewer** but not to the SIEM — a narrower gap than first
thought (the testing-agent corrected the earlier "no 430xxx at all" reading). Tracked as **D13**
(one fix would light up C6 IPS + C7 SI block events in Splunk); the logging-intent config is left
enabled on the ACP.

## Teardown / end-state
C7's SI block on host-splunk is a **test artifact** (blocking the SIEM isn't a desired
end-state) → removed after validation; baseline restored (alice→Splunk 0% loss). The
capability (add a Host object to the SI block list → pre-ACL drop) is the deliverable. The
ACP security-event-syslog toggles are left on as the intended (pending) SIEM wiring.
