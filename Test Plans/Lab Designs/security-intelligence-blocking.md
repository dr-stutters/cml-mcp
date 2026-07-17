# Test Plan — Security Intelligence (SI) threat-feed blocking

**Plan ID prefix:** `SI-` · **Version:** 1.0 · **Last updated:** 2026-07-17

## 1. Scope & purpose

Validates roadmap item **C7** on the **SD-Access ISE Integration** lab: an FMC
**Security Intelligence (SI)** blocklist entry makes the FTD drop traffic to a listed
destination **before** the access-control (AC) rules evaluate — reputation / threat-feed
enforcement at the front of the packet path. The capability under test is: adding a **Host
(or Network) object** to the Access Control Policy's SI `networks.blocklist` (over the FMC
REST API) → after deploy the FTD blocks that destination **pre-ACL**, while a control
destination on the *same* allow rule stays reachable.

**Explicitly out of scope:** custom SI *list/feed* objects and URL/DNS SI (GUI-only over
REST — see SI-002); load/scale testing; SI category/reputation feed accuracy; the FMC
Unified-Events GUI view (no browser in this harness — the functional block-vs-control ping
plus the SI-config read-back are the proof).

## 2. System under test

| Item | Value |
|---|---|
| Component | SD-Access ISE Integration lab (C7 capability) — FMC/FTD Security Intelligence |
| Version(s) verified against | FMC 10.0.1 (build 1) · FTD 10.0.0 (Snort 3) · ISE 3.5.0.527 · cat9000v IOS-XE 17.18 |
| Environment | CML lab **SDA-Fabric** (`77dd2fde-1fda-4cc9-9b29-48ff98bd1395`) + FMC/FTD + Splunk — IPs are **lab-specific** |
| Dependencies | C1 (FTD inline at the fusion, PBR steering); a reachable FMC with a deployable FTD; an endpoint (HOST1/alice) in a fabric VN; Splunk receiving FTD syslog (for SI-005) |

## 3. Test approach / levels

This plan is **manual/live** end-to-end acceptance (there is no offline CI gate for a
lab-design capability). It exercises the four standard levels' Manual/Live tier:

- **Manual/Live** — driven via the FMC REST API (curl, token auth), pyATS pings from the
  fabric host, and Splunk SPL search; recorded by hand with evidence.
- The MCP tool health that underpins it (firepower-mcp, cml-mcp, splunk-mcp) is covered by
  those servers' own plans and the automated-gate reports.

**Reversibility contract:** the only write is a **reversible round-trip** — add the Host
object to the SI blocklist → verify the block → remove it → verify baseline restored. No
built configuration is otherwise modified. The lab is left at baseline
(`networks.blocklist` = only `Global Block List`).

## 4. Preconditions & environment

- FMC creds in the shared `../.env` (`FMC_URL`, `FMC_USERNAME`, `FMC_PASSWORD`); token via
  `POST /api/fmc_platform/v1/auth/generatetoken` (short TTL → re-auth per call).
- The SI policy is reached at
  `…/accesspolicies/{acp}/securityintelligencepolicies/{sip}` (GET/PUT).
- A **Host object** already exists for the destination under test (`host-splunk` =
  198.18.128.51). SI blocklist accepts **Host/Network**, not `NetworkGroup`.
- Fabric booted/converged; HOST1 (alice) has a live session and IP 172.16.10.50.
- Splunk index `network` receiving FTD syslog from the FTD data interface (198.18.128.82).
- Credentials are **never** in this plan — only the `.env` variable names.

## 5. Test cases

### SI blocking (FMC/FTD pre-ACL threat-feed enforcement)

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SI-001` | Baseline (no SI block) | GET the SI policy; ping listed dst + control dst from HOST1 | `networks.blocklist` = only **Global Block List**; HOST1 → 198.18.128.51 **0% loss** (ACL-allowed) and HOST1 → 198.18.134.35 **0% loss** | `manual-live` (FMC GET; `pyats_execute` ping) |
| `SI-002` | SI REST API limits are as documented | `POST /object/sinetworklists`; GET `Global-Block-List`; recall NetworkGroup rejection | `POST` → **HTTP 405** (custom SI lists GUI-only); Global-Block-List `metadata.readOnly.state=true`; SI blocklist rejects `NetworkGroup` (Host/Network only) | `manual-live` (FMC REST negative tests) |
| `SI-003` | Apply — add a Host object to the SI blocklist | GET SI policy → strip `links`/`metadata`, append `{"network":{name,id,type:"Host"}}` to `networks.blocklist` → PUT → `fmc_deploy` FTD | PUT accepted; read-back shows **host-splunk** in `networks.blocklist`; deploy **SUCCEEDED/Deployed** | `manual-live` (FMC PUT + deployment API) |
| `SI-004` | Verify pre-ACL block (listed blocked, control reachable) | Ping listed dst + control dst from HOST1 after deploy | HOST1 → 198.18.128.51 **100% loss** (SI-blocked); HOST1 → 198.18.134.35 **0% loss** → only the listed dst is dropped, and it was ACL-allowed at baseline ⇒ the drop is **pre-ACL** | `manual-live` (`pyats_execute` ping) |
| `SI-005` | SI block event → Splunk (SIEM telemetry) | SPL: FTD msgid histogram + search for a Block/SI event on the blocked dst after the block | **Known gap (D13):** connection **allow** events (430002/430003) reach Splunk, but the **SI *block* security event** for the blocked dst does **not** (no Block-action / "Security Intelligence" / 430001 record) → logged to the FMC event viewer, not the SIEM | `manual-live` (Splunk SPL) — **partial / known gap** |
| `SI-006` | Revert — remove the SI block, restore baseline | GET SI policy → remove host-splunk from `networks.blocklist` → PUT → `fmc_deploy`; re-ping | Read-back `networks.blocklist` = only **Global Block List**; deploy **Deployed**, nothing pending; HOST1 → 198.18.128.51 **0% loss** restored | `manual-live` (FMC PUT + deploy; ping) |

## 6. Pass/fail & exit criteria

- **Manual/live gate:** SI-001, SI-003, SI-004, SI-006 reach their expected result with
  evidence; SI-002 confirms the documented API constraints. **SI-005 is a documented known
  gap (D13)** — it is recorded **partial**, not a hard FAIL of C7 (the capability under
  test is the pre-ACL block, proven by SI-004; SIEM forwarding of the SI event is a
  separate telemetry follow-up).
- **Reversibility gate:** the round-trip is undone and re-verified (SI-006) — lab left at
  baseline.
- **Plan pass =** all cases except SI-005 PASS **and** the round-trip is verified reverted.
  Verdict when SI-005 is open: **PASS-with-caveat**.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| Baseline reachability | `SI-001` | manual-live |
| SI REST API constraints | `SI-002` | manual-live (negative) |
| Apply SI blocklist entry | `SI-003` | manual-live |
| Pre-ACL block proof | `SI-004` | manual-live |
| SI event → SIEM | `SI-005` | manual-live (known gap) |
| Revert / reversibility | `SI-006` | manual-live |

Manual-only gaps (no automated coverage): all cases (lab-design acceptance is manual-live).

## 8. Execution record

Filled per run by the customer test report.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| 2026-07-17 | testing-agent (live) | 5 PASS · 1 partial (SI-005 known gap) · 0 FAIL | report-C7-SI.pdf | D13 (SI event → Splunk) — carried follow-up |
