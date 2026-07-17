# MCP Suite — Test Report

**Run date:** 2026-07-17 · **Tester:** testing-agent (live) · **Verdict:** PASS

Roadmap item **C6 — IPS / Snort 3 → Rapid Threat Containment** (Stage C of the
rapid-threat-containment plan) on the **SD-Access ISE Integration** lab. This is a
sibling report to the C2 Stage A+B report ([report-ANC.pdf](report-ANC.pdf)) — same
lab, same containment primitive, a **new detection-based trigger**.

## 1. Executive summary

Live, independent re-verification of **C6**: a custom **Snort 3 intrusion rule**
(SID 1000001) on the FTD, matched by live host traffic, auto-quarantines the offending
endpoint through the existing Rapid-Threat-Containment loop — an **IPS *detection*** (not
just an ACL deny) driving the containment. The subject is a single live, already-
authenticated 802.1X endpoint — **alice / HOST1** (`172.16.10.50`, MAC
`52:54:00:03:0B:0D`) on fabric edge **EDGE1**.

Firing `printf 'C6TRIGGER probe\n' | nc -w 3 198.18.128.51 8000` from HOST1 caused the
FTD's Snort 3 engine to **drop** the packet (Blocked-Packets counter **7 → 9**) and raise
an **intrusion event**. With **no human in the loop**, the FMC correlation rule
`Quarantine-on-IPS-C6` matched **Rule SID 1000001** and its remediation `Quarantine-Source`
**auto-applied an ISE ANC Quarantine over pxGrid** against alice's MAC. ISE then fired a
**RADIUS Change-of-Authorization (CoA, RFC 5176)** — MnT event **5205**, `Error-Cause=200`
— that **terminated her fabric session** (active sessions **1 → 0**, EDGE1 port with no
session, HOST1 → host-splunk **0% → 100% loss**). Clearing the ANC and reassociating the
supplicant **fully restored** her to Employees / SGT 4 (session back, 0% loss, no ANC
residual).

**Result: 6 PASS · 0 partial · 0 FAIL.** The complete detection→containment→release loop
was observed on a single live host; **alice is verified restored**; no built configuration
was modified (read-only plus reversible ANC round-trips, all undone).

## 2. Scope & systems under test

**Test plan:** Lab Designs / rapid-threat-containment — **new Stage C** (`RTC-020…025`),
extending the v2.0 plan (Stage A `RTC-001…007`, Stage B `RTC-010…014`). **Design:** C6 on
the SD-Access ISE Integration lab; context module
`Custom Designs/SD-Access ISE Integration/modules/fmc-ips-rtc.md`.

**What the lab is (plain English).** A virtual **Cisco SD-Access campus fabric** (a
LISP/VXLAN overlay with a control-plane/border node **BORDER-CP** and a fabric edge
**EDGE1**, fused to the outside by **FUSION-R1**) with a full identity + security stack:
**Cisco ISE 3.5** as the RADIUS policy server, TrustSec and pxGrid controller; **Microsoft
AD** (`mitchcloud.lab`) as the external identity store; a **Cisco Secure Firewall (FMC +
FTD)** at the fabric's external edge running **Snort 3** intrusion prevention; and
**Splunk** as the telemetry sink. Employee endpoint `alice` authenticates with **802.1X
(PEAP)**, is placed in the **Employees** security group (SGT 4) under **Closed
Authentication**, and gets normal fabric access.

**What C6 adds.** C2 (Rapid Threat Containment) proved the ANC→CoA containment primitive,
triggered by an operator (Stage A) or by an FMC correlation on a **connection/ACL** event
(Stage B). **C6** adds a **detection-based** trigger into the *same* `RTC-Quarantine`
correlation policy: a custom Snort 3 rule that fires on a payload signature, so an **IPS
drop** now auto-quarantines the source. The chain under test:

```
HOST1 (alice 172.16.10.50) sends "C6TRIGGER"
  → FTD Snort custom rule SID 1000001 → DROP + intrusion event
  → FMC correlation rule "Quarantine-on-IPS-C6" (condition: Rule SID is 1000001)
  → response "Quarantine-Source" (ANC Policy for Source, pxGrid EPS)
  → ISE ANC Quarantine on alice's MAC → CoA → 802.1X session terminated → 100% loss
```

### Component versions verified live this run

| Component | Version |
|---|---|
| Cisco ISE (PSN / pxGrid) | **3.5.0.527** |
| Cisco Secure Firewall Management Center (FMC) | **10.0.1 (build 1)** (vdb 433, sru 2026-07-15) |
| Cisco Secure Firewall Threat Defense (FTD) | **10.0.0** — Snort 3, PREVENTION, base *Connectivity Over Security* |
| Fabric edge / NAD (EDGE1) | **cat9000v IOS-XE 17.18** |
| SD-Access fabric | **LISP/VXLAN, Closed Authentication** |

## 3. Test environment

**Lab:** CML "SDA-Fabric" (`77dd2fde-1fda-4cc9-9b29-48ff98bd1395`) — STARTED / converged,
all nodes BOOTED. IPs are **lab-specific**.

| Hostname | Role / node-type | Mgmt IP | Data IP(s) | VRF / VLAN |
|---|---|---|---|---|
| **HOST1 (`alice`)** | 802.1X test subject · alpine | — | **172.16.10.50** · MAC 52:54:00:03:0B:0D | CAMPUS_VN (VLAN 1021) |
| **EDGE1** | fabric edge / **NAD + CoA client** · cat9000v | 198.18.128.73 | RADIUS/CoA id **10.1.0.3** · port Gi1/0/3 | CAMPUS_VN |
| **BORDER-CP** | fabric control-plane + border · cat9000v | 198.18.128.72 | LISP map-server / L3 handoff | CAMPUS_VN / IOT_VN |
| **FUSION-R1** | fusion router (PBR to FTD) · cat8000v | 198.18.128.71 | inside 10.1.245.1/30 | global |
| **FTDv** | Secure Firewall TD — **Snort 3 IPS (SDA-IPS)** · ftdv | 198.18.128.81 | inside→FUSION, outside→/18 | routed |
| **FMCv** | Mgmt Center — correlation + remediation · fmcv | 198.18.128.80 | — | — |
| **ISE 3.5 PSN (`ise35`)** | policy + CoA origin (UDP 1700) + pxGrid | **198.18.134.35** | — | external VM |
| **host-splunk** | trigger dest (allow → Snort-inspected) · splunk | 198.18.128.51 | — | — |

The labeled C6 chain diagram (Figure 1) is the primary figure; the CML canvas capture is in
the Appendix (§8).

Reproduce (live, requires the SDA fabric + ISE + FMC/FTD): fire the trigger from HOST1 and
observe the ISE ANC + CoA outcome per §5.

## 4. Results — automated gate (MCP servers)

**Not applicable to this run.** C6 acceptance is **manual-live** end-to-end against the live
ISE 3.5 + FMC/FTD + SDA fabric; there is no offline CI gate for a lab-design case. The
underlying MCP tool health (ise-mcp, firepower-mcp, cml-mcp) is covered by those servers'
own plans and the 2026-07-15 automated-gate report. All live surfaces answered this run:
`ise_check_surfaces` → openapi/mnt/ers all reachable; FMC token auth + config API OK; FTDv
console + EDGE1/HOST1 pyATS consoles OK.

## 5. Results — lab-design acceptance

Manual-live, case-by-case. Trigger: `printf 'C6TRIGGER probe\n' | nc -w 3 198.18.128.51 8000`
(raw payload stays in `pkt_data`; x2 this run).

| ID | Objective | Result | Evidence |
|---|---|---|---|
| **RTC-020** | Custom Snort 3 rule exists in FMC (Local Rules, gid 2000 / sid 1000001) | **PASS** | `GET object/intrusionrules/5254002E-…972036` → name `2000:1000001`, **gid 2000, sid 1000001, rev 5**, group **Local Rules**, `content:"C6TRIGGER",nocase`, msg "LOCAL C6 RTC test trigger". Per-policy override in SDA-IPS = **DROP**. |
| **RTC-021** | IPS policy SDA-IPS attached to the allow rule (Snort inspects the flow) | **PASS** | FMC: `Permit-CAMPUS-Services` **action=ALLOW, ipsPolicy=SDA-IPS**, enabled. SDA-IPS = **PREVENTION**, base **Connectivity Over Security** (active base → compiles Local Rules). On-box `show access-control-config`: `Rule: Permit-CAMPUS-Services · Action: Allow · Intrusion Policy: SDA-IPS` (Source net-campus10 → Dest host-splunk 198.18.128.51 among others). |
| **RTC-022** | Baseline (uncontained): 1 active session, no ANC, HOST1→host-splunk 0% loss | **PASS** | `active_session_count=1`; `list_anc_endpoints=[]`; HOST1 eth0 `172.16.10.50/24`; ping 198.18.128.51 **0% loss (4/4)**; ISE: alice active, **Employees / SGT 4**, PermitAccess, rule `Employees_SGT`, PEAP(EAP-MSCHAPv2), store mitchcloud, audit-session `0217010A000000146FFB1A92`. |
| **RTC-023** | Fire C6TRIGGER → FTD Snort drops it (Blocked Packets increments) | **PASS** | `show snort statistics` **Blocked Packets 7 → 9** (+2, one drop per trigger connection). Intrusion event raised (drives the RTC loop). |
| **RTC-024** | IPS drop auto-quarantines alice via the RTC loop (ANC + CoA + containment) — **no human** | **PASS** | **No `ise_apply_anc` called.** `list_anc_endpoints` [] → **2 records, both macAddress 52:54:00:03:0B:0D / policyName Quarantine** (auto-created). CoA: MnT AuthStatus **msg 5205 "Dynamic Authorization succeeded"**, `Error-Cause=200`, 12:37:25.647Z, audit-session `0217010A000000146FFB1A92`. `active_session_count=0`; EDGE1 Gi1/0/3 → *No sessions match*; HOST1→198.18.128.51 **100% loss**. |
| **RTC-025** | Reversibility: clear ANC + reassociate → session restored, no residual, 0% loss | **PASS** | `ise_clear_anc(…, Quarantine)` ×2 → `list_anc_endpoints=[]`. HOST1 `sudo -n wpa_cli -i eth0 reassociate` → EAP **SUCCESS**, Authorized. EDGE1 Gi1/0/3 **Authorized, alice, SGT 4, 172.16.10.50**, new session `0217010A000000157016CAEF`; `active_session_count=1`; HOST1→198.18.128.51 **0% loss (5/5)** after ~90 s LISP EID re-registration. No ANC residual. |

## 6. Summary statistics

| Metric | Value |
|---|---|
| Stage C cases executed | 6 |
| PASS | **6** |
| Partial / FAIL / Skip / Unreachable | 0 / 0 / 0 / 0 |
| Snort Blocked-Packets delta on trigger | +2 (7 → 9) |
| CoA outcome | MnT 5205 `Error-Cause=200`, session terminated (1 → 0) |
| Reachability flip (HOST1 → host-splunk) | 0% → **100%** → 0% loss |
| alice restored | SGT 4, 1 session, 0% loss, no ANC residual |
| Built config modified | **None** (read-only + reversible ANC round-trips, all undone) |

## 7. Observations & defects

**Defects raised: none.** All six Stage-C cases passed and the endpoint was fully restored.
Observations (operational notes, none downgrade a case):

1. **Two ANC records auto-created for one MAC.** Firing the trigger twice produced two
   correlation fires and **two duplicate `ancendpoint` records** for `52:54:00:03:0B:0D`
   (ISE ERS permits duplicates per MAC). Full release therefore needed **two
   `ise_clear_anc` calls**. A single trigger creates one record. Containment is identical;
   this is a cleanup nuance, not a defect. *(Recommendation: fire once for the cleanest
   demo, or de-dup ancendpoints on release.)*
2. **HTTP-buffer nuance on port 8000.** The trigger's first data segment drew an HTTP 400
   from Splunkd, yet the Snort Blocked-Packets counter still incremented and the intrusion
   event fired the RTC loop — consistent with gotcha #2 (`pkt_data` vs HTTP buffers). The
   definitive outcome (auto-quarantine + 100% loss) is unambiguous; the raw `nc` payload is
   the reliable trigger.
3. **LISP reconvergence ~90 s this run.** After release, the control plane restored within
   seconds (EDGE1 Authorized / SGT 4, ISE live session) but the **data path** returned only
   after a further LISP EID re-registration cycle (~90 s, vs the prior ~15–30 s). Timing
   caveat, not a defect.
4. **FTDv health "yellow" (cosmetic).** The FTD reported `health=yellow` but was
   MANAGED/DEPLOYED and fully functional — it dropped the trigger and raised the event.

### C6 gotchas (carried from the module, re-confirmed this run)

- **"No Rules Active" base does NOT compile custom Local Rules.** SDA-IPS uses an **active**
  base (*Connectivity Over Security*) so the rule group compiles and the per-rule **DROP**
  override takes effect. With a "No Rules Active" base, Blocked Packets stays 0.
- **HTTP-inspected flows hide the payload from a bare `content`** — use a raw non-HTTP `nc`
  payload (bytes stay in `pkt_data`) or the `http_uri` sticky buffer.
- **Correlate on Rule SID, not Generator ID** — FMC files user rules under **GID 2000**,
  which is absent from the correlation Generator-ID picker; key on **Rule SID is 1000001**.

**Remediation briefs:** none required — no FAIL/gap to hand back.

## 8. Appendix

- **Figure 1** — labeled C6 IPS-RTC chain diagram (`topology-C6.svg`, embedded in §3).
- **CML canvas capture** (`c6-cml-canvas.png`) — ground-truth: SDA-Fabric ON, converged.
- **`results-C6.json`** — machine-collected raw results for all six cases.
- Raw evidence transcripts (FMC REST GETs, FTDv `show snort statistics` before/after and
  `show access-control-config`, ISE `list_anc_endpoints` / `auth_status_by_mac` / session
  lookups, EDGE1 `show access-session`, HOST1 pings + `wpa_cli`) captured inline in §5.

### Key raw evidence

```
FTDv# show snort statistics   (before / after trigger)
  Blocked Packets     7   ->   9

ISE MnT AuthStatus (52:54:00:03:0B:0D):
  msg 5205 "Dynamic Authorization succeeded"  {Error-Cause=200}  12:37:25.647Z
  audit-session 0217010A000000146FFB1A92   (alice's live session)

ISE ancendpoint (auto-created, no ise_apply_anc):
  de1dea5c-… -> 52:54:00:03:0B:0D / Quarantine
  8434eee2-… -> 52:54:00:03:0B:0D / Quarantine

HOST1 -> 198.18.128.51 :  0% loss  ->  100% loss  ->  0% loss (restored)
EDGE1 Gi1/0/3         :  Authorized(SGT 4) -> No sessions -> Authorized(SGT 4)
active_session_count  :  1 -> 0 -> 1
```
