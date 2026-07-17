# MCP Suite — Test Report: Rapid Threat Containment (C2 Stage A)

**Run date:** 2026-07-17 · **Tester:** main session (live, user-approved) · **Verdict:** PASS-with-caveat

## 1. Executive summary

Live acceptance of **C2 Rapid Threat Containment — Stage A** (the containment loop) against the
[rapid-threat-containment test plan](../../Test%20Plans/Lab%20Designs/rapid-threat-containment.md)
on the SD-Access ISE Integration lab. A single ISE **ANC quarantine** applied to a live,
already-authenticated 802.1X endpoint (`alice`/HOST1) fired a **RADIUS CoA** that bounced her
fabric session and **fully isolated her** — verified by a reachability flip on the *same host,
same permit rule* (0% → 100% loss to two destinations) and by the ISE session record naming
**ANC** as the CoA source — and clearing the quarantine **restored full access**. Result:
**6/7 cases PASS, 1 partial** (the soft SGT/SGACL re-admission path was configured but not
exercised because the quarantine CoA *terminated* the session rather than re-admitting it —
a stronger containment, recorded as a caveat, not a defect). **Stage B** (an FMC correlation
rule auto-invoking this ANC) is out of scope for this report; its feasibility was confirmed
(FMC ships the *pxGrid ANC Policy Assignment* remediation module) and it is tracked separately.

## 2. Scope & systems under test

- **Test plan:** [Lab Designs / rapid-threat-containment](../../Test%20Plans/Lab%20Designs/rapid-threat-containment.md) (`RTC-001…007`).
- **Design:** C2 Rapid Threat Containment, **Stage A only** (ISE-driven ANC→CoA containment).
  The FMC-correlation auto-trigger (Stage B) is **not** executed here.
- Not the standard 6-repo automated gate — a focused lab-design acceptance run (like the
  2026-07-16 report). The other plans still apply to the untouched repos.
- **Versions:** ISE **3.5.0.527** (`198.18.134.35`) · cat9000v fabric edge **IOS-XE 17.18** ·
  SD-Access fabric (LISP/VXLAN, closed-auth) · FMCv **10.0.1** (for the Stage B feasibility check).

## 3. Test environment

| Target | Address (lab-specific) | Reachable this run? |
|---|---|---|
| ISE PSN (`ise35`) — policy decision point + CoA origin | 198.18.134.35 (CoA UDP 1700) | yes |
| EDGE1 — fabric edge / NAD (CoA client) | RADIUS id 10.1.0.3 (`EDGE1.lab.local`) | yes (pyATS) |
| HOST1 / `alice` — test subject | 172.16.10.50, MAC `52:54:00:03:0B:0D`, port Gi1/0/3 | yes (pyATS; console user `cisco`) |
| SHARED-SVC — reference dest (IOT_VN) | 172.16.20.10 | yes |
| host-splunk — reference dest | 198.18.128.51 | yes |
| CML controller | 198.18.128.10 | yes |
| FMCv (Stage B feasibility only) | 198.18.128.80 | yes (admin1 GUI) |

Reproduce: drive the `ise35` MCP (`ise_apply_anc` / `ise_clear_anc` / `ise_session_by_username`)
+ pyATS on EDGE1/HOST1 per the test plan §5; egress-cell create via `curl` to
`/ers/config/egressmatrixcell` (creds from the shared `.env`).

## 4. Results — automated gate

**Not applicable — this is a manual-live acceptance run.** RTC has no CI/unit coverage (it
requires the live ISE + SD-Access fabric); tool health for the drivers is covered by the
[ise-mcp](../../Test%20Plans/MCP%20Servers/ise-mcp.md) and [cml-mcp](../../Test%20Plans/MCP%20Servers/cml-mcp.md)
server plans. All acceptance is in §5.

## 5. Results — lab-design acceptance (RTC Stage A)

| Case | Objective | Evidence (observed 2026-07-17) | Result |
|---|---|---|---|
| `RTC-001` | Quarantine policy + enforcement objects exist | ANC `Quarantine` (action QUARANTINE); rank-0 authz rule `ANC_Quarantine` (`14dd6556…`, `Session:ANCPolicy EQUALS Quarantine` → Quarantined_Systems); egress cell `Quarantined_Systems→Shared_Services` (`f225c880…`, SGACL `Deny_IP_Log`) | **PASS** |
| `RTC-002` | Baseline access (uncontained) | EDGE1 `show access-session`: **Authorized, SGT Value 4**; HOST1 ping 172.16.20.10 **0% loss** (~170 ms), 198.18.128.51 **0% loss** (~90 ms) | **PASS** |
| `RTC-003` | ANC apply issues a CoA sourced from ANC | `ise_apply_anc(Quarantine, 52:54:00:03:0B:0D)` → ANC endpoint listed; `ise_session_by_username alice`: **`CoASourceComponent=ANC`**, **`CoAReason=Quarantine per ANC policy`**, `Device CoA type=Cisco CoA` port **1700**, `Acct-Terminate-Cause=Admin Reset` | **PASS** |
| `RTC-004` | Containment is effective | `ise_recent_authentications`: **`noOfActiveSession=0`**; EDGE1: *"No sessions match"*; HOST1 ping 172.16.20.10 **100% loss** and 198.18.128.51 **100% loss** (both were 0%) | **PASS** |
| `RTC-005` | Release restores access | `ise_clear_anc` → `sudo -n wpa_cli -i eth0 reassociate`: **EAP state=SUCCESS, suppPortStatus=Authorized**; EDGE1 back to **SGT Value 4, Authorized**; LISP EID `172.16.10.50/32` re-registered (map-server 10.1.0.2 **ACK Yes**); HOST1 ping both dests **0% loss** | **PASS** |
| `RTC-006` | Reversibility / no residual | Post-clear the endpoint authorizes under its normal `Employees_SGT` rule (SGT 4); no lingering quarantine behaviour | **PASS** |
| `RTC-007` | Soft SGT/SGACL re-admission (Quarantined_Systems 255 + deny cell) | Objects built & verified, but the quarantine CoA **terminated** the session (RTC-004) instead of re-admitting into SGT 255, and the host supplicant stayed down until release → path **configured, not exercised** | **⚠ PARTIAL** |

## 6. Summary statistics

| Metric | Value |
|---|---|
| RTC cases | **6 PASS · 1 partial · 0 FAIL** |
| Containment loop (apply→CoA→isolate→clear→restore) | verified end-to-end, reversible |
| Reachability flip (same host, same permit rule) | 0% → **100% loss** → 0% to **both** reference dests |
| CoA attribution | `CoASourceComponent=ANC`, `CoAReason=Quarantine per ANC policy` |
| Automated gate | n/a (manual-live) |

## 7. Observations & defects

**No defects raised.** The following are platform/behaviour notes (not failures):

1. **Quarantine CoA *terminated* the session** (`Acct-Terminate-Cause=Admin Reset`) rather than a
   reauth-in-place. In closed-auth this yields *full* isolation (0 sessions, 100% loss) — stronger
   than the SGACL path, and the reason `RTC-007` was a no-exercise partial.
2. **Host supplicant did not auto-re-authenticate** after termination; a switch `clear
   access-session` and a brief port flap were insufficient. **`sudo -n wpa_cli -i eth0
   reassociate`** on HOST1 (console user is `cisco`, not root) restored it cleanly. Real
   supplicants retry on their own.
3. **Post-restore LISP reconvergence** ~15–20 s — an immediate ping after re-auth can still show
   loss until the EID re-registers with the map-server.
4. **ISE `egressmatrixcell` POST** via the `ise` MCP returned `400 Resource Initialization Failed`;
   a direct `curl` to `/ers/config/egressmatrixcell` succeeded (known ise-mcp body double-encoding).
5. **Stage B feasibility (informational):** FMC's *Installed Remediation Modules* include
   **"pxGrid Adaptive Network Control (ANC) Policy Assignment"** and **"pxGrid Mitigation"** — the
   FMC→ISE auto-trigger is a supported built-in, so Stage B is viable (pending EPS-capability
   confirmation at instance-bind time).

## 8. Appendix

- **Test plan + its execution-record row:** [rapid-threat-containment.md](../../Test%20Plans/Lab%20Designs/rapid-threat-containment.md) §8 (stamped 2026-07-17).
- **Key evidence string (ISE session record, contained state):**
  `CoASourceComponent=ANC : CoAReason=Quarantine per ANC policy : Device CoA type=Cisco CoA :
  Device CoA port=1700 : Acct-Terminate-Cause=Admin Reset`.
- **Reachability matrix:** baseline `172.16.20.10` 0% / `198.18.128.51` 0% → contained both 100%
  → restored both 0%.
- `results.json` — curated machine-readable case results for this run.
- Config/recipe: [Custom Designs/SD-Access ISE Integration modules](../../Custom%20Designs/SD-Access%20ISE%20Integration/); roadmap item **C2** in [ROADMAP.md](../../Custom%20Designs/ROADMAP.md).
