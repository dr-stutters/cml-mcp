# MCP Suite — Test Report

**Run date:** 2026-07-17 · **Tester:** testing-agent (live) · **Verdict:** PASS-with-caveat

Roadmap item **C7 — Security Intelligence (SI) threat-feed blocking** on the **SD-Access
ISE Integration** lab. A sibling report to the C2/C6 rapid-threat-containment reports
([report-ANC.pdf](report-ANC.pdf), [report-C6-IPS-RTC.pdf](report-C6-IPS-RTC.pdf)) — same
lab, a **different firewall control**: SI drops traffic to a listed destination **before**
the access-control rules evaluate.

## 1. Executive summary

Live, independent re-verification of **C7**: an FMC **Security Intelligence** blocklist
entry makes the FTD drop traffic to a listed destination **pre-ACL** (ahead of the
access-control rules), while a control destination on the *same* allow rule stays
reachable. Executed as a **single reversible round-trip** (add the block → verify → remove
it) against the live FMC/FTD and the SDA fabric.

Starting from baseline (SI `networks.blocklist` = only **Global Block List**; HOST1 →
198.18.128.51 **0% loss**), the **host-splunk** Host object (198.18.128.51 — an otherwise
ACL-allowed, reachable stand-in "threat") was appended to the SI blocklist over the FMC
REST API and deployed. After deploy, **HOST1 (alice, 172.16.10.50) → 198.18.128.51 = 100%
loss (blocked)** while the control **HOST1 → 198.18.134.35 (ISE) = 0% loss (still
reachable)** — only the listed destination is dropped, and because it was ACL-allowed at
baseline, the drop is provably **pre-ACL**. Removing the host from the blocklist and
redeploying **restored 0% loss**; the lab is left at baseline.

**Result: 5 PASS · 1 partial · 0 FAIL.** The one partial is the documented **D13 telemetry
gap** (SI-005): the SI *block* security event is logged to the FMC event viewer but does
**not** reach Splunk. Notably, this run found connection events (`430002/430003`) **do** now
land in Splunk (an improvement since the C6 run), but the SI-block security event
specifically still does not — a precise narrowing of D13. This is scored **partial /
known-gap**, not a hard FAIL of C7 (the capability under test — the pre-ACL block — passed).
No built configuration was modified (read-only plus one reversible SI round-trip, fully
undone and re-verified).

## 2. Scope & systems under test

**Test plan:** Lab Designs / security-intelligence-blocking (`SI-001…006`). **Design:** C7
on the SD-Access ISE Integration lab; context module
`Custom Designs/SD-Access ISE Integration/modules/fmc-security-intelligence.md`.

**What the lab is (plain English).** A virtual **Cisco SD-Access campus fabric** — a
LISP/VXLAN overlay with a collapsed control-plane/border node **BORDER-CP** and a fabric
edge **EDGE1**, fused to the outside world by **FUSION-R1** — carrying a full identity +
security stack. **Cisco ISE 3.5** is the RADIUS/TrustSec/pxGrid policy server; **Microsoft
AD** (`mitchcloud.lab`) is the external identity store; a **Cisco Secure Firewall (FMC +
FTD)** sits inline at the fabric's external edge (traffic to outside destinations is
policy-routed from the fusion through the FTD); **Splunk** is the telemetry sink. Employee
endpoint **alice / HOST1** authenticates with 802.1X, is placed in the **Employees**
security group, and gets normal fabric access.

**What C7 adds.** A firewall control that acts **ahead of** the access-control rules.
**Security Intelligence** matches a destination against block lists (reputation / threat
feeds) at the very front of the packet path; a match is dropped as a *Security-Related
Connection → Block → IP Block*, and the AC rule that would otherwise *allow* it never runs.
The FMC REST API cannot create custom SI *list* objects (GUI-only), but it **can** add a
**Host/Network object** to the ACP's SI `networks.blocklist` — that object becomes the
"custom threat list" entry. The chain under test:

```
HOST1 (alice 172.16.10.50) -> EDGE1 -> BORDER-CP -> FUSION-R1 (PBR) -> FTDv
  FTDv Security Intelligence: dst on networks.blocklist?
     yes (host-splunk 198.18.128.51)  -> DROP pre-ACL          -> 100% loss
     no  (ISE 198.18.134.35, control) -> AC rule Allow (normal) -> 0% loss
```

### Component versions verified live this run

| Component | Version |
|---|---|
| Cisco Secure Firewall Management Center (FMC) | **10.0.1 (build 1)** |
| Cisco Secure Firewall Threat Defense (FTD) | **10.0.0** — Snort 3 |
| Cisco ISE (control dst / identity) | **3.5.0.527** |
| Fabric edge / NAD (EDGE1) | **cat9000v IOS-XE 17.18** |
| SD-Access fabric | **LISP/VXLAN, Closed Authentication** |

## 3. Test environment

**Lab:** CML "SDA-Fabric" (`77dd2fde-1fda-4cc9-9b29-48ff98bd1395`) — STARTED / converged,
all nodes BOOTED. IPs are **lab-specific**.

| Hostname | Role / node-type | Mgmt IP | Data IP(s) | VRF / VLAN |
|---|---|---|---|---|
| **HOST1 (`alice`)** | fabric endpoint (test source) · alpine | — | **172.16.10.50** · MAC 52:54:00:03:0B:0D | CAMPUS_VN |
| **EDGE1** | fabric edge / NAD · cat9000v | 198.18.128.73 | fabric-attached | CAMPUS_VN |
| **BORDER-CP** | fabric control-plane + border · cat9000v | 198.18.128.72 | LISP map-server / L3 handoff | CAMPUS_VN |
| **FUSION-R1** | fusion router (PBR → FTD inside) · cat8000v | 198.18.128.71 | inside handoff | global |
| **FTDv** | Secure Firewall TD — **SI enforcer** · ftdv | 198.18.128.81 | data/syslog src **198.18.128.82** | routed |
| **FMCv** | Mgmt Center — owns SDA-ACP + SI policy · fmcv | 198.18.128.80 | — | — |
| **host-splunk** | **listed "threat"** (test) + Splunk SIEM · splunk | — | **198.18.128.51** | — |
| **ISE 3.5 (`ise35`)** | **control dst** (same allow rule, never listed) | **198.18.134.35** | — | external VM |

The labeled C7 SI-block chain (Figure 1) is the primary figure; the CML canvas capture is
in the Appendix (§8).

Reproduce (live, requires FMC/FTD + the SDA fabric + Splunk): run the SI round-trip per §5
— GET/PUT the SI policy `…/securityintelligencepolicies/{sip}`, deploy the FTD, and observe
the block-vs-control pings from HOST1.

## 4. Results — automated gate (MCP servers)

**Not applicable to this run.** C7 acceptance is **manual-live** end-to-end against the live
FMC/FTD + SDA fabric + Splunk; there is no offline CI gate for a lab-design capability. The
underlying MCP tool health (firepower-mcp, cml-mcp, splunk-mcp) is covered by those servers'
own plans and the 2026-07-15 automated-gate report. All live surfaces answered this run:
FMC token auth + config/deployment API OK; FTDv MANAGED/DEPLOYED; HOST1 pyATS console OK;
Splunk management API + SPL search OK.

## 5. Results — lab-design acceptance

Manual-live, case-by-case. Round-trip: append **host-splunk (Host, 198.18.128.51)** to the
SI `networks.blocklist` → deploy → verify → remove → deploy → verify.

| ID | Objective | Result | Evidence |
|---|---|---|---|
| **SI-001** | Baseline (no SI block): listed + control dst reachable | **PASS** | GET SI policy → `networks.blocklist` = only **Global Block List** (SINetworkList). HOST1 eth0 172.16.10.50/24. HOST1 → **198.18.128.51 = 0% loss (4/4, ~87ms)**; → **198.18.134.35 = 0% loss (4/4, ~81ms)**. host-splunk reachable at baseline ⇒ it is ACL-allowed (so a later block is pre-ACL). |
| **SI-002** | SI REST API limits are as documented | **PASS** | `POST /object/sinetworklists` → **HTTP 405** (custom SI lists GUI-only). `Global-Block-List` (c76556bc-…) `metadata.readOnly.state=true`. SI blocklist rejects **NetworkGroup** ("not allowed in Security Intelligence Policy") → Host/Network only. host-splunk = **Host**, value 198.18.128.51. |
| **SI-003** | Apply — add the Host object to the SI blocklist | **PASS** | GET SI policy → stripped `links`/`metadata` → appended `{"network":{name:host-splunk,id:…9557,type:"Host"}}` → **PUT 200**. Read-back `networks.blocklist` = [**Global Block List**, **host-splunk (Host)**]. Deploy task **4294973908 → Deployed / SUCCEEDED**. `blocklistLogging.sendLogsToSyslogServer=true`. |
| **SI-004** | Verify pre-ACL block (listed blocked, control reachable) | **PASS** | HOST1 → **198.18.128.51 = 100% loss (0/5)** → SI-blocked. HOST1 → **198.18.134.35 = 0% loss (5/5)** → still reachable. Only the listed dst is dropped; it was ACL-allowed at baseline (SI-001) ⇒ the drop is **pre-ACL** (Security Intelligence, ahead of the AC rules). |
| **SI-005** | SI block event → Splunk (SIEM telemetry) | **PARTIAL (known gap D13)** | Msgid histogram (`index=network host=198.18.128.82 \| rex "%FTD-\d+-(?<msgid>\d+)" \| stats count by msgid`) → LINA `%FTD-*` **plus** connection events **430002/430003 (16 each)**. Connection **allow** events for the control dst and pre-block allows to .51 **are** present (improvement vs C6-era "no 430xxx"). **But** the post-block blocked pings to 198.18.128.51 produced **zero** Splunk events, and **0** events with `AccessControlRuleAction: Block` / "Security Intelligence" / 430001 in the last 45 min → the **SI block security event does not reach the SIEM** (FMC event viewer only). |
| **SI-006** | Revert — remove the SI block, restore baseline | **PASS** | GET → removed host-splunk from `networks.blocklist` → **PUT 200**; read-back = [**Global Block List**]. Deploy task **4294974162 → Deployed**; deployable devices **pending=0**. HOST1 → **198.18.128.51 = 0% loss (5/5) restored**; → 198.18.134.35 = 0% loss. End-state `networks.blocklist` = **[Global Block List]** (baseline). |

## 6. Summary statistics

| Metric | Value |
|---|---|
| Cases executed | 6 |
| PASS | **5** |
| Partial (known gap) | **1** (SI-005 / D13) |
| FAIL / Skip / Unreachable | 0 / 0 / 0 |
| Reachability flip (HOST1 → host-splunk) | 0% → **100%** → 0% loss |
| Control dst (HOST1 → ISE) | 0% loss throughout (never listed) |
| SI blocklist end-state | **Global Block List only** (baseline) |
| Deployments | 2 (apply + revert), both **Deployed/SUCCEEDED** |
| Built config modified | **None** (read-only + one reversible SI round-trip, undone + re-verified) |

## 7. Observations & defects

**Defects raised: none new.** Five cases passed and the round-trip was fully reverted;
the one partial is a **pre-existing, documented** telemetry gap (D13), carried as a
follow-up rather than a C7 failure.

Observations (operational notes; none downgrade a PASS case):

1. **D13 narrowed by this run.** The C6 report recorded "no 430xxx in Splunk". This run
   found `430002/430003` **connection** events *do* now land in Splunk (allow events for
   both the control dst and pre-block traffic to .51). What is still missing is the **SI
   *block* security event** for the blocked dst — so D13 is more precisely: *the FTD
   security-event syslog stream (SI block / 430001 intrusion / block-action connection) is
   not delivered to Splunk, even though ordinary connection events are.* This sharpens the
   remediation target (see brief below).
2. **FTDv health "yellow" (cosmetic).** The FTD reported `health=yellow` but was
   MANAGED/DEPLOYED and enforced the SI policy correctly (blocked the listed dst, passed
   the control) — consistent with the prior C6 run.
3. **The block is genuinely pre-ACL, not an ACL deny.** host-splunk pinged clean at
   baseline (SI-001) under the same allow rule that keeps the control dst reachable; only
   after adding it to the SI blocklist did it flip to 100% loss — the flip is attributable
   to Security Intelligence, which is evaluated ahead of the AC rules.

### C7 API-limit gotchas (re-confirmed this run)

- **Custom SI list/feed objects are GUI-only:** `POST /object/sinetworklists` → **405**;
  the editable `Global-Block-List` is `readOnly` over REST. Add a **Host/Network object**
  to the ACP's SI `networks.blocklist` instead — that object *is* the custom-threat entry.
- **SI blocklist rejects `NetworkGroup`** — it must be a **Host** or **Network** object.
- **`fmc_api_call` won't take a JSON-object body** for the SI PUT → use **curl** (token via
  `generatetoken`, short TTL → re-auth per call); **strip `links`/`metadata`** from the GET
  body before PUT-ing it back.

### Remediation brief — hand back to the specialists (not applied here)

- **Device group:** FTDv (`37ffcab8-8126-11f1-a47b-d7a4b50be775`) + FMCv 198.18.128.80,
  with splunk-engineer for verification. **Owner:** firewall-engineer (+ splunk-engineer).
- **Finding (D13):** FTD **security-event** syslog — SI blocks, `430001` intrusion, and
  block-action connection events — is not delivered to Splunk, though LINA `%FTD-*` and now
  ordinary `430002/430003` connection events are. The ACP SI `blocklistLogging`
  (`sendLogsToSyslogServer=true`, `sendLogsToEventViewer=true`) and IPS syslog toggles are
  already enabled; the security-event stream still does not arrive.
- **Change:** wire the FTD **security-event syslog** delivery path (FMC → *Devices →
  Platform Settings → Syslog*, and the ACP *Logging → Security-event / Intrusion* settings),
  confirming the security-event syslog egresses an interface/route that reaches Splunk
  198.18.128.51 (likely a dedicated security-event syslog config vs the LINA out-the-outside
  path used for `%FTD-*`).
- **Acceptance check:** re-run the SI round-trip; Splunk `index=network host=198.18.128.82`
  shows a **Block-action / Security-Intelligence** connection event for the blocked dst
  (and, with the C6 trigger, a `430001` intrusion event) within the block window. This one
  fix lights up **C6 IPS + C7 SI + connection-block** events in the SIEM together.

## 8. Appendix

- **Figure 1** — labeled C7 SI-block chain (`topology-C7.svg`, embedded in §3).
- **CML canvas capture** (`c7-cml-canvas.png`) — ground-truth: SDA-Fabric ON, converged.
- **`results-C7.json`** — machine-collected raw results for all six cases.
- Raw evidence transcripts (FMC REST GET/PUT of the SI policy before/after, deployment task
  polls, HOST1 pings baseline→blocked→restored, Splunk msgid histogram + SI-event search)
  captured inline in §5.

### Key raw evidence

```
SI networks.blocklist :  [Global Block List]  ->  [Global Block List, host-splunk (Host)]  ->  [Global Block List]
FMC deploy            :  task 4294973908 SUCCEEDED (apply) ; task 4294974162 Deployed (revert), pending=0

HOST1 -> 198.18.128.51 (listed) :  0% loss  ->  100% loss  ->  0% loss (restored)
HOST1 -> 198.18.134.35 (control):  0% loss  ->    0% loss  ->  0% loss   (never listed)

POST /object/sinetworklists            -> HTTP 405   (custom SI lists GUI-only)
GET  Global-Block-List                 -> metadata.readOnly.state = true
SI blocklist + NetworkGroup            -> rejected ("not allowed in Security Intelligence Policy")

Splunk (index=network host=198.18.128.82):
  msgid histogram: 110002/111001/111004/111008/111010/199017/302010/305011/305012/771002/780005  +  430002/430003
  430002/430003 events observed = AccessControlRuleAction: Allow (control + pre-block traffic)
  post-block blocked pings to 198.18.128.51           -> 0 Splunk events
  "AccessControlRuleAction: Block"/"Security Intelligence"/430001  -> 0 events (SI block event not in SIEM = D13)
```
