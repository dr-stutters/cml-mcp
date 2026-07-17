# Test Plan — Rapid Threat Containment (ISE ANC quarantine → CoA)

**Plan ID prefix:** `RTC-` · **Version:** 2.0 · **Last updated:** 2026-07-17

## 1. Scope & purpose

Validate roadmap item **C2 (Rapid Threat Containment)** on the
[SD-Access ISE Integration](../../Custom%20Designs/SD-Access%20ISE%20Integration/) lab **end to end,
in both of its stages**: that a security decision can **contain a live endpoint on the SD-Access
fabric** by applying an ISE **ANC (Adaptive Network Control)** quarantine, which issues a **RADIUS
Change-of-Authorization (CoA, RFC 5176)** to the fabric edge that owns the endpoint's 802.1X session
— bouncing that session and cutting the endpoint's access — and that **clearing** the quarantine
restores it. The plan proves the containment **two ways**:

- **Stage A — ISE-driven (`RTC-001…007`).** The ANC is applied/cleared **directly via ISE's API**.
  This proves the containment primitive is sound independent of who pulls the trigger.
- **Stage B — FMC auto-trigger over pxGrid (`RTC-010…014`).** An **FMC correlation rule** fires on an
  FTD connection event and its **remediation auto-applies the same ANC over pxGrid EPS** — **no human
  in the loop** — and ISE fires the identical CoA. This is the full RTC / SOAR-style closed loop.

Out of scope: load/scale testing and endpoint posture.

> **In one sentence:** prove that either an operator flipping a switch in ISE (Stage A) **or** the
> firewall's own correlation engine reacting to a bad flow (Stage B) reaches into a *live,
> already-authenticated* fabric session and severs it in seconds — the essential primitive every
> SOAR/RTC workflow is built on — and that it is cleanly reversible.

## 2. System under test

| Item | Value |
|---|---|
| Design | C2 Rapid Threat Containment (on the SD-Access ISE Integration lab) — **Stage A + Stage B** |
| Verified against | ISE **3.5.0.527**; **FMC 10.0.1 / FTD 10.0.0 (Snort3)**; cat9000v **IOS-XE 17.18** fabric edge; SDA fabric (LISP/VXLAN, closed-auth) |
| Environment | CML lab `77dd2fde` (**lab-specific IPs** — adjust for your environment) |
| Policy decision point | ISE PSN **`198.18.134.35`** (`ise35`), CoA out UDP **1700**, **pxGrid controller** |
| NAD / enforcement point | **EDGE1** (fabric edge), RADIUS/CoA client id **`10.1.0.3`** (Loopback0), NAD name `EDGE1.lab.local` |
| Test subject | **`alice`** (AD user ∈ Employees) on **HOST1** (alpine), 802.1X wired, IP **172.16.10.50**, MAC `52:54:00:03:0B:0D`, port **Gi1/0/3** (VLAN 1021, VRF CAMPUS_VN) |
| Reference destinations | **SHARED-SVC** `172.16.20.10` (IOT_VN) and **host-splunk** `198.18.128.51` (both permitted at baseline) |
| **Stage B — firewall auto-trigger** | **FMCv** `198.18.128.80` (correlation + remediation, pxGrid consumer); **FTDv** `198.18.128.81` (`SDA-ACP` enforcer); **trigger dest host-catc** `198.18.128.5` (blocked by FTD rule `Deny-CAMPUS-to-CatC`) |
| Dependencies | Closed-auth 802.1X fabric working (Phase 6); ISE ERS enabled; SGTs incl. `Employees(4)`, `Shared_Services(200)`, `Quarantined_Systems(255)`; the `Employees→Shared_Services` permit; **(Stage B)** FMC↔ISE pxGrid up (**C5**) with the FMC client in ISE's **`ANC` pxGrid client-group**, and the active FMC correlation policy `RTC-Quarantine` |

## 3. Test approach / levels — how & why it works

**Level: Manual/Live acceptance.** Driven via the `ise35` MCP tools (`ise_apply_anc` /
`ise_clear_anc` / `ise_list_anc_endpoints` / `ise_ers_call` / `ise_session_by_username` /
`ise_auth_status_by_mac`) and **pyATS** on EDGE1 (`show access-session`) and HOST1 (`ping`, `nc`,
`wget`, `wpa_cli`). For **Stage B** the *only* action is generating **blocked** traffic HOST1→host-catc
— the ANC apply is performed **by FMC**, not the tester. The definitive evidence is the
**before/after reachability flip** on the *same host, same permit rule* plus the ISE CoA record
(MnT msg **5205** "Dynamic Authorization succeeded") — and, for Stage B, an ANC endpoint that
**appears without any tester apply**.

### How it works (the mechanism, step by step)

1. **Baseline.** `alice` completes wired 802.1X against ISE; `SDA_Wired` → `Employees_SGT` returns
   **PermitAccess + SGT 4 (Employees)**. EDGE1 authorizes the port, registers her EID in LISP.
2. **Contain.** An ANC **Quarantine** is associated with her MAC — **by the operator (Stage A)** or
   **auto-applied by FMC over pxGrid EPS after its correlation rule fires (Stage B)**. ISE originates
   a **CoA** to EDGE1 (`10.1.0.3`) on **UDP 1700** targeting her live session.
3. **Session bounce.** EDGE1 acts on the CoA. In this platform/run the CoA **terminated** the session
   (accounting **Stop**, `Acct-Terminate-Cause=Admin Reset`). Because the fabric runs **closed
   authentication**, an unauthorized port has **no data path** — the endpoint is fully isolated.
4. **Release.** `ise_clear_anc(...)` removes the quarantine flag; on the endpoint's next 802.1X auth,
   ANC no longer matches, so ISE returns `Employees_SGT` → **PermitAccess + SGT 4**; EDGE1 re-authorizes
   and re-registers the EID (~15–30 s LISP reconverge).

### Why it works (the integration chain)

- **ISE is both the policy decision point *and* the CoA originator.** The NAD is a dynamic-author
  (CoA) client, so ISE reaches back into a *live* session with no switch-side change — the essence of
  CoA/RFC 5176 and what makes containment *rapid*.
- **ANC is the abstraction on top of CoA.** "Quarantine an endpoint" is a durable ISE state keyed on
  MAC; applying/clearing it triggers the CoA. In **Stage A** ANC is invoked directly via ISE's API; in
  **Stage B** a *third party* (FMC) invokes the **same** ANC over **pxGrid EndpointProtectionService
  (EPS)** — the containment that follows is identical.
- **Stage B's unlock is a pxGrid client-group, not an FMC toggle.** FMC's remediation can only apply an
  ISE ANC policy if its pxGrid client is a member of ISE's **`ANC`** client-group (Session-Directory
  access is open; ANC needs the group). With that, the FMC remediation's ANC-policy dropdown lists
  `Quarantine` and the auto-apply works.
- **Closed-auth fabric turns "session terminated" into "fully contained."**

## 4. Preconditions & environment

- `.env` points `ISE_URL`/`ISE_USERNAME`/`ISE_PASSWORD` at the **`.35`** PSN; ERS enabled.
  Credentials are **never** in this plan — only the variable names.
- The SDA fabric is up in **closed-auth**; `alice`/HOST1 is authenticated with **baseline access** to
  SHARED-SVC and host-splunk (the access the test revokes and restores).
- ISE has SGTs `Employees(4)`, `Shared_Services(200)`, `Quarantined_Systems(255)` and the
  `Employees→Shared_Services` permit; ANC policy `Quarantine`; rank-0 authz rule `ANC_Quarantine`.
- EDGE1 is a CoA (dynamic-author) client of ISE; CoA UDP **1700** reachable ISE→EDGE1.
- **Stage B:** FMC↔ISE pxGrid session up (**C5**) and the FMC pxGrid client is in ISE's **`ANC`**
  client-group; FMC objects built — remediation instance `ISE-ANC-Quarantine`, remediation
  `Quarantine-Source` (*ANC Policy for Source* → Quarantine), correlation rule `Quarantine-on-CatC-Deny`
  (connection event, *AC Rule Name contains `Deny-CAMPUS-to-CatC`*), **active** correlation policy
  `RTC-Quarantine`; FTD ACP `SDA-ACP` has the `Deny-CAMPUS-to-CatC` BLOCK rule with `sendEventsToFMC`.

## 5. Test cases

Pass criteria include the **observed 2026-07-17 result** inline (`→ ✅ …`).

### Stage A — ISE-driven containment loop

| ID | Objective | Steps | Expected result / pass criteria |
|---|---|---|---|
| `RTC-001` | Quarantine policy + enforcement objects exist | List ANC `Quarantine`; the rank-0 authz rule `ANC_Quarantine` (`Session:ANCPolicy EQUALS Quarantine` → Quarantined_Systems); egress cell `Quarantined_Systems→Shared_Services = Deny_IP_Log` | All three present → ✅ ANC `Quarantine`, authz rule `14dd6556…` @rank 0, egress cell `f225c880…` |
| `RTC-002` | Baseline access (uncontained) | EDGE1 `show access-session mac …`; ISE `ise_session_by_username alice`; HOST1 `ping 172.16.20.10` and `198.18.128.51` | Session **Authorized, SGT 4**, rule `Employees_SGT`; both pings **0% loss** → ✅ SGT 4, PermitAccess, both 0% |
| `RTC-003` | ANC apply issues a CoA sourced from ANC | `ise_apply_anc(Quarantine, 52:54:00:03:0B:0D)`; `ise_ers_call GET ancendpoint`; `ise_auth_status_by_mac` | ANC endpoint = MAC + `Quarantine`; CoA event **msg 5205** "Dynamic Authorization succeeded" `Error-Cause=200` on UDP 1700; session → Stop → ✅ endpoint `74d844c0…`, 5205 @10:27:42 (attribution `CoASourceComponent=ANC` / `CoAReason=Quarantine per ANC policy`) |
| `RTC-004` | Containment is effective | `ise_active_session_count`; EDGE1 `show access-session mac …`; HOST1 pings both dests | **0 active sessions**; no session on EDGE1; **100% loss** to both (were 0%) → ✅ 0 sessions, 100% loss to both |
| `RTC-005` | Release restores access | `ise_clear_anc(...)`; `sudo -n wpa_cli -i eth0 reassociate`; EDGE1 session; HOST1 pings | Re-auth **EAP SUCCESS / Authorized**, back to **SGT 4**; both pings **0% loss** → ✅ SGT 4, both 0% (SHARED-SVC after ~25 s LISP reconverge) |
| `RTC-006` | Reversibility / no residual | `ise_list_anc_endpoints`; endpoint back to normal authz | No lingering ANC binding; endpoint authorizes under `Employees_SGT` → ✅ `[]`, restored to Employees |
| `RTC-007` | *(soft re-admission — partial)* Quarantined re-auth is SGACL-restricted | While flagged, force a re-auth so authz hits `ANC_Quarantine` → SGT 255; test SHARED-SVC | Endpoint re-admits as Quarantined_Systems(255) with remediation-only reach → ⚠️ **configured, not exercised** — the CoA terminated the session (RTC-004); host supplicant stayed down until release |

### Stage B — FMC correlation auto-trigger (no human in the loop)

| ID | Objective | Steps | Expected result / pass criteria |
|---|---|---|---|
| `RTC-010` | FMC correlation + remediation objects exist and are active | Confirm FTD rule `Deny-CAMPUS-to-CatC` (BLOCK, `sendEventsToFMC`); FMC objects `ISE-ANC-Quarantine` / `Quarantine-Source` / rule `Quarantine-on-CatC-Deny` / **active** policy `RTC-Quarantine` (GUI-only — not in FMC REST API; verify functionally via RTC-011…013) | Trigger rule present; correlation chain active → ✅ `Deny-CAMPUS-to-CatC` BLOCK w/ `sendEventsToFMC=true`, `logBegin=true`; chain fired automatically |
| `RTC-011` | Blocked FTD event auto-applies ANC (no human) | Reconfirm baseline; from HOST1 generate **blocked** traffic to host-catc: `ping -c5 198.18.128.5`, `for p in 443 80 22; do nc -w2 -z 198.18.128.5 $p; done`, `wget https://198.18.128.5/`; then `ise_list_anc_endpoints` + `ise_ers_call GET ancendpoint` — **without any `ise_apply_anc`** | Traffic blocked; within seconds an ANC endpoint is **auto-created** = MAC + `Quarantine` → ✅ endpoint `49356d5a…` = `52:54:00:03:0B:0D` / `Quarantine`, **no manual apply** |
| `RTC-012` | Auto-applied ANC fires a CoA vs alice's live session | `ise_auth_status_by_mac`; `ise_active_session_count`; `ise_session_by_username alice` | CoA event **msg 5205** `Error-Cause=200` against alice's audit-session; **0 active sessions** — same CoA as Stage A, automatic → ✅ 5205 @10:31:56 vs `…6F9FBCA7`, count 0 |
| `RTC-013` | Auto-containment is effective | EDGE1 `show access-session mac …`; HOST1 pings both dests | No session on EDGE1; **100% loss** to both → ✅ no session, both 100% loss |
| `RTC-014` | Release + restore after auto-containment | `ise_clear_anc(...)`; `wpa_cli reassociate`; EDGE1 session; ISE session; HOST1 pings; `ise_list_anc_endpoints` | **EAP SUCCESS / Authorized**, back to **SGT 4**, 1 active session; both pings **0%**; no ANC residual → ✅ SGT 4, count=1, both 0%, `[]` |

## 6. Pass/fail & exit criteria

- **Plan pass =** Stage A `RTC-002…006` (baseline → ANC-sourced CoA + full loss + 0 sessions → clean
  restore) **and** Stage B `RTC-011…014` (blocked FTD event auto-applies ANC → identical CoA →
  containment → restore) all observed on the **same host**. That is the complete containment→release
  loop, proven both operator-driven and firewall-auto-driven.
- The **contrast state** that would be a FAIL: applying (or auto-applying) ANC leaves the endpoint
  reachable, or the CoA is not attributable to ANC, or the endpoint cannot be restored after clear, or
  (Stage B) the blocked FTD event does **not** produce an ANC binding without a manual apply.
- `RTC-007` is a **known partial**: the soft SGT/SGACL re-admission path is built but the observed CoA
  behaviour is full session termination, recorded as ⚠️ not-a-blocker.
- **C2 status: DONE ✅ (2026-07-17) — Stage A + Stage B both proven live.** The FMC auto-trigger's
  unlock was pxGrid **EPS/ANC** client-group membership (add the FMC pxGrid client to ISE's **`ANC`**
  group); full recipe in
  [`modules/fmc-rtc-anc.md`](../../Custom%20Designs/SD-Access%20ISE%20Integration/modules/fmc-rtc-anc.md).

## 7. Traceability matrix

| Capability | Case IDs | Backlog |
|---|---|---|
| ANC quarantine + CoA containment (the C2 core) | RTC-001…006 | C2 Stage A |
| Soft SGT/SGACL re-admission | RTC-007 | C2 (partial) |
| FMC correlation → remediation → pxGrid ANC auto-trigger | RTC-010…014 | C2 Stage B |

All cases are manual-live acceptance (no CI gate — require the live ISE + SDA fabric + FMC/FTD).
Underlying tool health is covered by the [ise-mcp](../MCP%20Servers/ise-mcp.md) and
[firepower-mcp](../MCP%20Servers/firepower-mcp.md) server plans.

## 8. Execution record

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| 2026-07-17 | main session (live) | **6 PASS, 1 partial** (Stage A only: RTC-001…006 P; RTC-007 ⚠) | ISE session `CoASourceComponent=ANC`; HOST1 reach flip 0%→100%→0%; EDGE1 SGT 4→none→4; `noOfActiveSession=0` while contained | none |
| 2026-07-17 | testing-agent (live) | **12 PASS, 1 partial** (Stage A 6P+1⚠ · Stage B 5P) | Stage A: ANC endpoint `74d844c0…`=`Quarantine`, CoA msg 5205 @10:27:42, 0 sessions, 100% loss, restored SGT 4. **Stage B: ANC endpoint `49356d5a…`=`52:54:00:03:0B:0D`/`Quarantine` auto-created (no `ise_apply_anc`), CoA msg 5205 @10:31:56 vs `…6F9FBCA7`, 0 sessions, both dests 100% loss, then restored (SGT 4, count=1, `[]`).** Report: [Test Reports/2026-07-17](../../Test%20Reports/2026-07-17/report.pdf) | none |

### Notes / gotchas observed

- **The quarantine CoA *terminated* alice's session** (`Admin Reset`) in both stages — stronger than
  the SGACL path, and the reason RTC-007 stays configured-not-exercised.
- **The host supplicant did not auto-re-authenticate**; a **`sudo -n wpa_cli -i eth0 reassociate`** on
  HOST1 (console user `cisco`, use `sudo -n`) brought it back cleanly after each clear.
- **Post-restore reconvergence ~15–30 s** — the inter-VN hairpin to SHARED-SVC returns last.
- **The literal live-session `CoASourceComponent=ANC` string** is only in ISE's *active* live-session
  view; the CoA terminates the session in ~1 s, so it can roll off before sampling — the CoA is proven
  by MnT **msg 5205** + the ANC binding + active-count 0 regardless.
- **`RTC-Quarantine` correlation policy is left ACTIVE** — it re-quarantines any HOST1→host-catc
  attempt (that is the feature). Deactivate its toggle to pause.
