# C6 — IPS / Snort 3 → Rapid Threat Containment

**Goal:** a custom **Snort 3 intrusion rule** on the FTD, triggered by live host
traffic, chained into the existing [`fmc-rtc-anc.md`](fmc-rtc-anc.md) auto-quarantine
loop — so an **IPS *detection*** (not just an ACL deny) auto-quarantines the offender
on ISE. Extends C2 (RTC) with a second, detection-based trigger into the **same**
`RTC-Quarantine` correlation policy + `Quarantine-Source` ISE-ANC remediation.

Prereqs: C1 (FTD inline at the fusion), C2 Stage B done (RTC-Quarantine policy +
Quarantine-Source remediation + FMC pxGrid client in ISE's `ANC` client-group), IPS
license on the FTD (`license_caps` includes `IPS`). Live-proven 2026-07-17 on the
SDA-Fabric lab (FTDv 198.18.128.81, FMCv 198.18.128.80, ISE 3.5 198.18.134.35).

## The chain

```
HOST1 (alice 172.16.10.50) sends "C6TRIGGER"
  → FTD Snort matches custom rule SID 1000001 → DROP + intrusion event
  → FMC correlation rule "Quarantine-on-IPS-C6" (Rule SID is 1000001)
  → response "Quarantine-Source" (ANC Policy for Source, over pxGrid EPS)
  → ISE ANC Quarantine on alice's MAC → CoA (UDP 1700) → session terminated
  → 100% loss.  Fully automatic, no human in the loop.
```

## Stage 1 — custom rule + intrusion policy (FMC REST API)

The IPS object side is **all API** (unlike correlation, which is GUI-only). Drive it
with `curl` (the `fmc` MCP `fmc_api_call` rejects a JSON-object `body` — it wants a
string and double-parses; use curl). Token: `POST /api/fmc_platform/v1/auth/generatetoken`
(Basic), scope config calls under `/api/fmc_config/v1/domain/{uuid}/…`.

1. **Custom Snort 3 rule** — `POST object/intrusionrules`:
   ```json
   { "ruleData": "alert tcp any any -> any any ( msg:\"LOCAL C6 RTC test trigger\"; flow:to_server,established; content:\"C6TRIGGER\",nocase; sid:1000001; gid:2000; rev:5; )",
     "ruleGroups": [ { "id": "<Local Rules group id>", "type": "IntrusionRuleGroup", "name": "Local Rules" } ] }
   ```
   FMC parses gid/sid/msg from `ruleData`, forces **`gid:2000`** for user rules, names
   it `2000:1000001`, and files it in the **Local Rules** group.
2. **Intrusion policy** — `POST policy/intrusionpolicies` with `snortEngine:SNORT3`,
   `inspectionMode:PREVENTION`, and an **active** base policy (see gotcha #1).
3. **Enable the rule at DROP in the policy** —
   `PUT policy/intrusionpolicies/{ipsId}/intrusionrules/{ruleId}` with the **full**
   rule object + `"overrideState":"DROP"` (a bare `{id,overrideState}` 400s —
   "ruleData is Mandatory"). Editing the rule later (`PUT object/intrusionrules/{id}`)
   preserves this per-policy override.
4. **Attach to the ACP allow rule** — `GET` the allow rule (`Permit-CAMPUS-Services`),
   drop `metadata`/`links`, add `"ipsPolicy": {id,name,type:"IntrusionPolicy"}`, `PUT`
   it back. Action must be **ALLOW** (TRUST bypasses Snort). `fmc_deploy` the FTD.

Verify on the box: `show snort statistics` → **Blocked Packets** increments; or FMC
**Events & Logs → Unified Events** shows Event Type **Intrusion**, Action **Drop**,
your Source/Dest, and Enrichments → **Local Rules**.

## Stage 2 — correlation → remediation (FMC GUI only)

Correlation + remediation are **not** in the FMC REST API (same as C2 Stage B). Drive
the classic `.cgi` GUI (browser as `admin1`):

1. **Policies → Correlation → Rule Management → Create Rule**: name
   `Quarantine-on-IPS-C6`; event type **"an intrusion event occurs"**; **Add condition**
   → **Rule SID** `is` **1000001**. (See gotcha #3 — use **Rule SID**, not Generator ID.)
2. **Policy Management → edit `RTC-Quarantine` → Add Rules** → check `Quarantine-on-IPS-C6`
   → **Add**; then its **responses** icon → move **Quarantine-Source** from Unassigned to
   Assigned → **Update** → **Save** (twice — see gotcha #4). Leave the policy toggle **on**.

Now `RTC-Quarantine` fires on **either** a CatC-deny connection event (Stage B) **or**
this IPS drop (C6).

## Live proof + reversibility

Trigger from HOST1: `printf 'C6TRIGGER live\n' | nc -w 3 198.18.128.51 8000`
(raw payload — see gotcha #2). Result: intrusion drop SID 1000001 → **ANC endpoint
auto-created** (MAC `52:54:00:03:0B:0D`, policy `Quarantine`) → **active session count 0**
→ HOST1→Splunk **100% loss**. Restore: `ise_clear_anc(mac, "Quarantine")` +
`sudo -n wpa_cli -i eth0 reassociate` → session back, **0% loss** (~40 s incl. LISP
EID re-registration).

## Gotchas (all cost real time here)

1. **"No Rules Active" base does NOT compile custom Local Rules.** With that base the
   rule never loads — `show snort statistics` **Blocked Packets stays 0** even though the
   per-rule state is DROP and the policy is attached + deployed. Fix: use an **active**
   base policy (**Connectivity Over Security** is the lightest) so the rule group compiles;
   the per-rule DROP override then takes effect. This was the single biggest blocker.
2. **HTTP-inspected flows hide the payload from bare `content`.** On an HTTP flow (e.g.
   Splunk web :8000) Snort's http_inspect moves the bytes into HTTP buffers, so a bare
   `content` (which matches `pkt_data`) never fires — a `wget` gets a clean 404 back,
   undropped. Use the **`http_uri`** sticky buffer for an HTTP trigger, **or** a **raw
   non-HTTP payload** (`nc`) so the bytes stay in `pkt_data`. The raw `nc` trigger is the
   reliable demo path.
3. **Correlate on `Rule SID`, not `Generator ID`.** FMC assigns custom rules **GID 2000**,
   which is *not* in the correlation "Generator ID" value picker (that lists only classic
   preprocessor GIDs — 1 Standard Text Rule, 3 Shared Object Rule, 116 Snort Decoder, …).
   The intrusion-event condition fields include **Rule SID** and **Rule Message** — key on
   **Rule SID is 1000001** (unique, numeric, no substring ambiguity).
4. **Classic `.cgi` GUI quirks** (same family as [`fmc-rtc-anc.md`](fmc-rtc-anc.md)):
   native `<select>`s **revert on click-select** — they only commit via keyboard or by
   setting `select.value` + dispatching a `change` event (used the browser JS tool to set
   the condition field to `sid` reliably); **Save/Create needs two clicks** (first arms,
   second submits); typed condition **values can silently drop** — verify the input value
   stuck before saving.

## Teardown (to remove C6, leaving C1/C2 intact)

Detach the IPS policy from `Permit-CAMPUS-Services` (PUT the rule without `ipsPolicy`) +
`fmc_deploy`; delete correlation rule `Quarantine-on-IPS-C6` from `RTC-Quarantine`;
optionally delete intrusion policy `SDA-IPS` and custom rule SID 1000001. The custom rule
and IPS policy are harmless if left (only `C6TRIGGER` over HTTP-less TCP is dropped).
