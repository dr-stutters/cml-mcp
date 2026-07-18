# C12–C16 — Firewall depth (URL / AVC / EVE / Geo / Decrypt-bypass)

Five FMC/ACP features on the FTDv (`SDA-ACP` id `5254002E-…-968720`, decryption policy
`SDA-Decrypt` id `b10b55fe-…`). All built via the **FMC REST API with curl** (`fmc_api_call`
double-parses object bodies → use curl + a token from `/api/fmc_platform/v1/auth/generatetoken`;
tokens expire ~30 min — refresh). Deploy once at the end (`fmc_deploy`). **DONE ✅ 2026-07-18.**

Shared object IDs: net-campus10 `…-969467` · net-ise `…-969485` · host-splunk `…-969557` ·
inside-zone `3afe1e90-…` · outside-zone `3b98f708-…`. HOST1 = CAMPUS `172.16.10.50` (no internet).

## C14 — Encrypted Visibility Engine (simplest — a setting)
`PUT /policy/accesspolicies/{acp}/evesettings/{id}` body `{...,"enabled":true}` → returns
`enabled:true, mode:MONITOR_TRAFFIC`. Classifies encrypted client apps/threats **without**
decryption (complements C8 decrypt-resign + C16 bypass).

## C13 — Application control / AVC (access rule)
`POST /policy/accesspolicies/{acp}/accessrules?insertBefore=2` (above `Permit-CAMPUS-Services`):
`{name:"C13-Block-HTTP-App", action:"BLOCK", sourceZones:[inside-zone], destinationZones:[outside-zone],
sourceNetworks:[net-campus10], destinationNetworks:[host-splunk], applications:{applications:[{id:"676",type:"Application"}]}, logBegin:true, sendEventsToFMC:true, enableSyslog:true}`.
**PROVEN:** HOST1 `wget http://198.18.128.51:8000/` **times out** (blocked by app-ID, not port) — was allowed.
> **Gotcha:** the FMC `/object/applications` endpoint **ignores `?filter=name:` / `nameStartsWith:`**
> (returns the unfiltered alphabetical list). Page it (`?offset=…&limit=1000`) and grep — **HTTP = 676,
> HTTPS = 1122**. Symbol/numeric app names sort first, so letters start deep in the catalog.

## C12 — URL filtering (access rule)
`POST …/accessrules` `{name:"C12-Block-Malware-URL", action:"BLOCK", …src net-campus10,
urls:{urlCategoriesWithReputation:[{category:{id:"abba9b63-…-01001",name:"Malware Sites",type:"URLCategory"}}]}}`.
Talos URL DB reachable over the `/18` mgmt path (like C9's AMP). *Proof deferred* — HOST1 has no
internet; rule is live (packet-tracer-verifiable).

## C15 — Geolocation / country blocking (access rule)
`POST …/accessrules` `{name:"C15-Block-Country-China", action:"BLOCK", …src net-campus10,
destinationNetworks:{objects:[{name:"China",id:"156",type:"Country"}]}}`. **Country objects go
straight into the network condition** (`/object/continents?expanded=true` lists all — China=156,
Russia=643). *Proof deferred* — no internet.

## C16 — Identity/category decryption bypass (decryption rule) → C8
`POST /policy/decryptionpolicies/{SDA-Decrypt}/decryptionpolicyrules?insertBefore=1`
`{name:"C16-DND-ISE", type:"DecryptionPolicyRule", ruleAction:"DO_NOT_DECRYPT", sourceNetworks:[net-campus10],
destinationNetworks:[net-ise], logging:{logEnd:true, sendEvents:true}}` — lands at **ruleIndex 1**,
above the `Decrypt-CAMPUS-443` resign rule. **PROVEN:** `openssl s_client -connect 198.18.134.35:443`
from HOST1 → issuer **`CN=Mitchcloud-Lab-Root-CA`** (ISE's *real* cert = bypassed) vs. the
`CN=SDA-Decrypt-Resign-CA` C8 produced → selective decryption (ISE bypassed, other 443 still resigns).
> **Gotchas:** decryption-rule logging uses **`logEnd`** (not `logBegin` → 422) inside a `logging`
> object; `insertBefore=1` **works** even though it returned a spurious **500 "JsonNull"** (the rule
> was created at index 1 — re-GET before retrying, or you'll hit "Name already exists").

## End-state / note
All five are attached to `SDA-ACP`/`SDA-Decrypt` and deployed. **C13 blocked CAMPUS→Splunk HTTP** — a
side effect on the HOST1→Splunk upload path used for C9/eStreamer connection generation (eStreamer
pulls from FMC, so the dashboard is unaffected). After the block was proven, **`C13-Block-HTTP-App` was
left `enabled:false` + deployed (2026-07-18)** to restore that path — HOST1 `wget http://198.18.128.51:8000/`
returns the Splunk login page again (`RC=0`). Re-enable the rule (PUT `enabled:true` + deploy) to re-demo
the app-ID block. EVE + URL + geo + AVC events all surface via the eStreamer feed ([[splunk-security-cloud]]).
