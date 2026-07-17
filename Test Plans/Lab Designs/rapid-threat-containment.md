# Test Plan — Rapid Threat Containment (ISE ANC quarantine → CoA)

**Plan ID prefix:** `RTC-` · **Version:** 1.0 · **Last updated:** 2026-07-17

## 1. Scope & purpose

Validate the **containment mechanism** of roadmap item **C2 (Rapid Threat Containment)** on the
[SD-Access ISE Integration](../../Custom%20Designs/SD-Access%20ISE%20Integration/) lab: that a
security decision can **contain a live endpoint on the SD-Access fabric** by applying an ISE
**ANC (Adaptive Network Control)** quarantine, which issues a **RADIUS Change-of-Authorization
(CoA, RFC 5176)** to the fabric edge that owns the endpoint's 802.1X session — bouncing that
session and cutting the endpoint's access — and that **clearing** the quarantine restores it.

This is the "back half" of C2 — *"ISE ANC quarantine → CoA bounces the fabric session"*. The
**"front half"** — an **FMC correlation rule** auto-invoking the ANC over pxGrid (Stage B) — is
**explicitly out of scope here** (it is GUI-only, tracked as a separate stage; see §6 note).
Also out of scope: load/scale testing and endpoint posture.

> **In one sentence:** prove that flipping a switch in ISE ("quarantine this endpoint") reaches
> into a *live, already-authenticated* fabric session and severs it in seconds — the essential
> primitive every SOAR/RTC workflow is built on — and that it is cleanly reversible.

## 2. System under test

| Item | Value |
|---|---|
| Design | C2 Rapid Threat Containment (on the SD-Access ISE Integration lab) |
| Verified against | ISE **3.5.0.527**; cat9000v **IOS-XE 17.18** fabric edge; SDA fabric (LISP/VXLAN, closed-auth) |
| Environment | CML lab `77dd2fde` (**lab-specific IPs** — adjust for your environment) |
| Policy decision point | ISE PSN **`198.18.134.35`** (`ise35`), CoA out UDP **1700** |
| NAD / enforcement point | **EDGE1** (fabric edge), RADIUS/CoA client id **`10.1.0.3`** (Loopback0), NAD name `EDGE1.lab.local` |
| Test subject | **`alice`** (AD user ∈ Employees) on **HOST1** (alpine), 802.1X wired, IP **172.16.10.50**, MAC `52:54:00:03:0B:0D`, port **Gi1/0/3** (VLAN 1021, VRF CAMPUS_VN) |
| Reference destinations | **SHARED-SVC** `172.16.20.10` (IOT_VN, SGT Shared_Services) and **host-splunk** `198.18.128.51` |
| Dependencies | Closed-auth 802.1X fabric working (Phase 6); ISE ERS enabled; SGTs incl. `Employees(4)`, `Shared_Services(200)`, `Quarantined_Systems(255)`; the `Employees→Shared_Services` permit that gives the baseline access this test revokes |

## 3. Test approach / levels — how & why it works

**Level: Manual/Live acceptance.** Driven from the main session via the `ise35` MCP tools
(`ise_apply_anc` / `ise_clear_anc` / `ise_session_by_username` / `ise_recent_authentications`)
and **pyATS** on EDGE1 (`show access-session`, LISP/device-tracking) and HOST1 (`ping`,
`wpa_cli`). The definitive evidence is the **before/after reachability flip** on the *same host,
same permit rule* plus the **ISE session record naming ANC as the CoA source**.

### How it works (the mechanism, step by step)

1. **Baseline.** `alice` completes wired 802.1X against ISE; the `SDA_Wired` policy set's
   `Employees_SGT` rule returns **PermitAccess + SGT 4 (Employees)**. EDGE1 authorizes the port,
   registers her EID `172.16.10.50/32` in LISP (map-server ACK), and she has normal fabric access.
2. **Contain.** `ise_apply_anc(policy="Quarantine", mac=…)` associates her MAC with the ANC
   **Quarantine** policy. ISE immediately originates a **CoA** to the NAD that owns her session
   (EDGE1, `10.1.0.3`) on **UDP 1700** — the endpoint's live session is the target, identified by
   its audit-session-id. The CoA carries `CoASourceComponent=ANC` and `CoAReason=Quarantine per
   ANC policy`.
3. **Session bounce.** EDGE1 acts on the CoA. **In this platform/run the CoA *terminated* the
   session** (RADIUS accounting **Stop**, `Acct-Terminate-Cause=Admin Reset`) rather than doing a
   reauth-in-place. Because the fabric runs **closed authentication**, an unauthorized port has
   **no data path** — so the endpoint is fully isolated (it keeps its configured IP but 0% of its
   traffic is forwarded).
4. **Release.** `ise_clear_anc(...)` removes the quarantine flag. On the endpoint's next 802.1X
   authentication, ANC no longer matches, so ISE returns to `Employees_SGT` → **PermitAccess +
   SGT 4**. EDGE1 re-authorizes the port and **re-registers the EID in LISP**; full access returns
   once the control plane reconverges (~15–20 s).

### Why it works (the integration chain)

- **ISE is both the policy decision point *and* the CoA originator.** The RADIUS relationship
  that authenticated the endpoint is bidirectional: the NAD is configured as a **dynamic-author
  (CoA) client** (`aaa server radius dynamic-author`), so ISE can reach back into a *live* session
  and change or tear it down **without any switch-side config change** — that is the whole point
  of CoA/RFC 5176 and what makes containment *rapid*.
- **ANC is the abstraction on top of CoA.** "Quarantine an endpoint" is a durable ISE state keyed
  on MAC; applying/clearing it is what triggers the CoA. Here ANC is invoked **directly via ISE's
  API** (ERS/MnT). In the full RTC flow (**Stage B**) a *third party* — FMC — invokes the same ANC
  over **pxGrid EndpointProtectionService (EPS)**; the containment that follows is identical. This
  test proves the containment half is sound independent of who pulls the trigger.
- **Closed-auth fabric turns "session terminated" into "fully contained."** Because Phase 6 put
  the fabric in closed auth, there is no fallback/guest path — losing the session means losing all
  access, which is the desired quarantine outcome.
- **The Quarantined_Systems SGT + deny SGACL is the *soft* re-admission policy.** A rank-0 authz
  rule (`ANCPolicy EQUALS Quarantine → Quarantined_Systems`) plus an egress cell
  `Quarantined_Systems→Shared_Services = Deny_IP_Log` are configured so that a quarantined endpoint
  which *does* re-authenticate while still flagged is re-admitted into SGT 255 with only remediation
  reach. In this run the CoA **terminated** the session (and the host supplicant stayed down until
  release), so this softer path was **configured but not exercised** — noted honestly in §5/§8.

## 4. Preconditions & environment

- `.env` (or env vars) point `ISE_URL`/`ISE_USERNAME`/`ISE_PASSWORD` at the **`.35`** PSN; ERS
  enabled. Credentials are **never** in this plan — only the variable names.
- The SDA fabric is up in **closed-auth**; `alice`/HOST1 is authenticated with **baseline access**
  to SHARED-SVC and host-splunk (this is the access the test revokes and restores).
- ISE has SGTs `Employees(4)`, `Shared_Services(200)`, `Quarantined_Systems(255)` and the
  `Employees→Shared_Services` permit (`SDA_Web_Permit`) in the egress matrix.
- EDGE1 is a CoA (dynamic-author) client of ISE and CoA UDP **1700** is reachable ISE→EDGE1.

## 5. Test cases

Pass criteria include the **observed 2026-07-17 result** inline (`→ ✅ …`).

| ID | Objective | Steps | Expected result / pass criteria |
|---|---|---|---|
| `RTC-001` | Quarantine policy + enforcement objects exist | Create ANC `Quarantine` (`ise_create_anc_policy`, action QUARANTINE); rank-0 authz rule `ANC_Quarantine` (`Session:ANCPolicy EQUALS Quarantine` → Quarantined_Systems); egress cell `Quarantined_Systems→Shared_Services = Deny_IP_Log` | All three created and listable → ✅ ANC `Quarantine`, authz rule `14dd6556…` @rank 0, egress cell `f225c880…` |
| `RTC-002` | Baseline access (uncontained) | On EDGE1 `show access-session mac …`; from HOST1 `ping 172.16.20.10` and `198.18.128.51` | Session **Authorized, SGT 4**; both pings **0% loss** → ✅ SGT Value 4, both 0% loss |
| `RTC-003` | ANC apply issues a CoA sourced from ANC | `ise_apply_anc(Quarantine, 52:54:00:03:0B:0D)`; then `ise_session_by_username alice` | ANC endpoint listed; session record shows **`CoASourceComponent=ANC`**, **`CoAReason=Quarantine per ANC policy`**, CoA type Cisco CoA port 1700 → ✅ exactly that, `Acct-Terminate-Cause=Admin Reset` |
| `RTC-004` | Containment is effective | `ise_recent_authentications`; EDGE1 `show access-session mac …`; HOST1 pings to both dests | **0 active sessions**; no session on EDGE1; **100% loss** to both (was 0%) → ✅ 0 sessions, 100% loss to 172.16.20.10 **and** 198.18.128.51 |
| `RTC-005` | Release restores access | `ise_clear_anc(...)`; re-auth the endpoint (`sudo wpa_cli -i eth0 reassociate`); EDGE1 session; HOST1 pings | Re-auth **EAP SUCCESS / Authorized**, back to **SGT 4**; EID re-registered in LISP; both pings **0% loss** → ✅ SGT 4 authorized, LISP map-server ACK, both 0% loss |
| `RTC-006` | Reversibility / no residual | After release, `ise_list_anc_endpoints`; endpoint back to normal authz | No lingering ANC binding for the MAC; endpoint authorizes under its normal (Employees) rule → ✅ restored to Employees rule |
| `RTC-007` | *(soft re-admission — partial)* Quarantined re-auth is SGACL-restricted | While flagged, force a re-auth so authz hits `ANC_Quarantine` → SGT 255; test SHARED-SVC | Endpoint re-admits as Quarantined_Systems(255); `Quarantined_Systems→Shared_Services` **Deny** blocks SHARED-SVC while remediation stays reachable → ⚠️ **configured, not exercised** — the CoA terminated the session (RTC-004) instead of re-admitting; host supplicant stayed down until release |

## 6. Pass/fail & exit criteria

- **Plan pass =** `RTC-002` (baseline reach) → `RTC-003`+`RTC-004` (ANC-sourced CoA **and** full
  loss of reach + 0 sessions) → `RTC-005` (clean restore to Employees) all observed on the **same
  host**. That is the complete containment→release loop with ANC named as the trigger.
- The **contrast state** that would be a FAIL: applying ANC leaves the endpoint reachable, or the
  CoA is not attributable to ANC, or the endpoint cannot be restored after clear.
- `RTC-007` is a **known partial**: the soft SGT/SGACL re-admission path is built but the observed
  CoA behaviour was full session termination, so it is recorded as ⚠️ not-a-blocker.
- **Stage B (FMC auto-trigger) — attempted 2026-07-17, BLOCKED at pxGrid EPS.** Wiring an **FMC
  correlation rule + ISE remediation** so an FMC event auto-invokes this ANC is **GUI-only** (FMC
  correlation/remediation are **not in the FMC REST API**). The FMC plumbing builds fine —
  remediation module → instance `ISE-ANC-Quarantine` (pxGrid ANC Policy Assignment) → remediation
  type *ANC Policy for Source* — but the remediation's **ANC-policy dropdown is empty of ISE
  policies** (only "Clears ANC Policy"). pxGrid *transport is healthy* (FMC→ISE Test = "Primary
  host: Success"; Session Directory drives C3), so the gap is the **EPS/ANC (EndpointProtectionService)
  capability**: FMC's ISE identity source only offers Session Directory + SXP subscriptions (no
  ANC/EPS), and the pxGrid client isn't authorized to read ISE's ANC policies. Finishing Stage B
  needs ISE-side pxGrid EPS authorization (Administration → pxGrid Services → Client Management).
  This plan validates the ISE-driven containment primitive that Stage B would automate.

## 7. Traceability matrix

| Capability | Case IDs | Backlog |
|---|---|---|
| ANC quarantine + CoA containment (the C2 core) | RTC-001…006 | C2 |
| Soft SGT/SGACL re-admission | RTC-007 | C2 (partial) |
| FMC correlation → remediation auto-trigger | — (Stage B, out of scope) | C2 Stage B |

All cases are manual-live acceptance (no CI gate — require the live ISE + SDA fabric). Underlying
tool health is covered by the [ise-mcp](../MCP%20Servers/ise-mcp.md) server plan.

## 8. Execution record

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| 2026-07-17 | main session (live) | **6 PASS, 1 partial** (RTC-001…006 P; RTC-007 ⚠ configured-not-exercised) | ISE session record `CoASourceComponent=ANC` / `CoAReason=Quarantine per ANC policy`; HOST1 reach flip 0%→100%→0% to 172.16.20.10 & 198.18.128.51; EDGE1 `SGT Value 4`→no-session→`SGT 4`; ISE `noOfActiveSession=0` while contained | none — CoA-terminates-session (vs reauth-in-place) + host supplicant needing a reassociate nudge both noted as platform behaviours, not defects |

### Notes / gotchas observed

- **The quarantine CoA *terminated* alice's session** (`Admin Reset`) rather than a reauth-in-place;
  the endpoint kept its IP but had **zero** forwarding. This is a *stronger* quarantine than the
  SGACL path and is the reason RTC-007 was not exercised.
- **The host supplicant did not auto-re-authenticate** after termination (a switch `clear
  access-session` and a brief port flap were not enough); a **`sudo wpa_cli -i eth0 reassociate`**
  on HOST1 (console user is `cisco`, not root — use `sudo -n`) brought it back cleanly after the
  clear. On production supplicants this is the endpoint's normal retry behaviour.
- **Post-restore reconvergence:** after re-auth, allow **~15–20 s** for EDGE1 to re-register the
  EID with the LISP map-server before the data path returns — an immediate ping can still show loss.
- **ISE egress-matrix-cell POST** via the MCP returned `400 Resource Initialization Failed`; a
  direct `curl` to `/ers/config/egressmatrixcell` (creds from the shared `.env`) succeeded — the
  known ise-mcp body double-encoding gotcha.
