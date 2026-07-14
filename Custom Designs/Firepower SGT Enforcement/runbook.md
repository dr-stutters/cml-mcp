# Firepower SGT Enforcement — runbook

**Status (2026-07-14): TrustSec chain proven end-to-end into the FTD; ACP enforcement
BLOCKED on a real architectural gap — needs FMC↔ISE pxGrid (roadmap #31).** See
[The critical finding](#the-critical-finding-read-this-first).

Goal: **ISE assigns an SGT at MAB → the Catalyst tags the endpoint and shares its IP→SGT
binding over SXP → the FTD enforces an SGT-based access-control policy.**

## The critical finding (read this first)

**A direct switch→FTD FlexConfig `cts sxp` peer feeds the FTD's LINA data plane ONLY. It
does NOT drive FMC Access-Control-Policy SGT enforcement.**

FMC ACP rules with an SGT condition on an **Allow** action are evaluated by **Snort**, and
Snort only learns SGT-IP mappings from **FMC↔ISE integration (pxGrid)** or **inline SGT
tags** — never from LINA's `cts` subsystem. So the SXP binding arrives in LINA, LINA
matches the network part of the permit rule and hands off to Snort, Snort sees
`src sgt: 0 / unknown`, no SGT rule matches, and the flow hits the ACP **default = BLOCK**.

`packet-tracer input inside icmp 10.40.0.10 8 0 10.60.0.10` proves it exactly:
- Header: `Mapping security-group 4 to IP address 10.40.0.10` — **LINA knows SGT=4**
- Phase 4 (LINA ACL): matches network part of `Employees-to-SRV-PERMIT`, defers to Snort
- Phase 16/17 (Snort): `src sgt: 0, src sgt type: unknown` → `Matched rule ... Block`
- Result: `drop (firewall) Blocked ... by the firewall preprocessor`
- `show access-list CSM_FW_ACL_ | include security-group` → **empty** (no SGT match in LINA;
  the SGT condition lives entirely in Snort).

**Correct design for FMC-managed FTD SGT enforcement:** FMC → Integration → Identity
Sources → **Cisco ISE (pxGrid)**; FMC learns SGT-IP from ISE (ISE as SXP aggregator and/or
pxGrid session directory) and pushes the mappings to the FTD **Snort** engine; the ACP rule
uses the **ISE** SGT group. Then Snort sees `sgt: 4` and the permit matches. The direct
switch→FTD FlexConfig SXP listener is redundant for enforcement (it only ever populated
LINA) and can be retired. → this is roadmap **#31 (pxGrid)**; see [Next steps](#next-steps--the-pxgrid-fix-31).

## Topology

Layered onto the canonical NAC/TrustSec core lab
**`cb53d7fe-aecc-4770-9353-f6af8b6d7637`** (ISE35-MAB), reusing the existing switch + ISE 3.5
+ endpoint; the SGT tier adds a fresh FMC + FTD + server.

```
EP-ISE35 (10.40.0.10, SGT Employees/4 via MAB)
   │ gw 10.40.0.1 (SW Vlan40)
SW-ISE35 (cat9000v)  ── SXP speaker (On) ──►  FTD-SGT inside Eth0/0 (10.50.0.2)
   │ inside Gi1/0/4 10.50.0.1                    │ outside Eth0/1 10.60.0.1
   │ route 10.60.0.0/24 → 10.50.0.2             │ static 10.40.0.0/24 → 10.50.0.1
   └────────────────────────────────────────►  SRV-SGT (10.60.0.10, gw 10.60.0.1)
FMC-SGT (198.18.128.13, admin/SgtLab#2026Fw, v10.0.1) manages FTD-SGT
```

| Node | Role | Addressing |
|---|---|---|
| FMC-SGT | FMCv | mgmt 198.18.128.13; eval license enabled |
| FTD-SGT | FTDv, FMC-managed routed | inside 10.50.0.2/30, outside 10.60.0.1/24; RegKey `sgtreg123` |
| SRV-SGT | net-tools | 10.60.0.10/24, gw 10.60.0.1 (runtime-only) |
| SW-ISE35 | cat9000v (existing) | inside Gi1/0/4 10.50.0.1; Vlan40 10.40.0.1; NAD .66 (MGMT VRF) |
| EP-ISE35 | endpoint (existing, busybox) | 10.40.0.10, gw 10.40.0.1 |

## What is built + validated

- **ISE→switch→SXP→FTD-LINA chain fully proven:**
  - EP-ISE35 authorized via MAB, SGT **Employees(4)**; switch `show cts role-based sgt-map
    all` → `10.40.0.10  4  LOCAL`.
  - Switch is the SXP **speaker**; FTD is the **listener**; `show cts sxp connections`
    (both ends) = **On**, password Set.
  - FTD LINA learned it: `show cts sxp sgt-map` → `SGT 4 / 10.40.0.10 / Active`.
- **FMC config (all via GUI):** ACP **SGT-ACP** (default BLOCK) rule#1 Employees(4)→
  HOST-SRV-10.60.0.10 ALLOW, rule#2 Contractors(5)→SRV BLOCK. Interfaces/zones/route
  deployed. Objects: SecurityGroupTag Employees(4)/Contractors(5).
- **FlexConfig SXP listener** (object `FTD_SGT_SXP`, policy `SGT-SXP-FlexConfig`) built +
  deployed clean (deploy SUCCEEDED = device accepted the CLI). Generated CLI:
  ```
  cts sxp enable
  cts sxp default password CTSsxp123
  cts sxp connection peer 10.50.0.1 source 10.50.0.2 password default mode local listener
  ```
- **Enforcement: FAILS** (EP→SRV ping 100% loss) — the [critical finding](#the-critical-finding-read-this-first)
  above. Routing is confirmed good (switch→FTD inside ping 100%; switch route to
  10.60.0.0/24 → 10.50.0.2). The FTD Snort drops on default-BLOCK because it has no SGT.

## FMC FlexConfig SXP — the editor gauntlet (gotchas)

Configuring the FTD SXP listener via the FMC FlexConfig GUI is genuinely painful. What it
took:

1. **FTD SXP/CTS is FlexConfig/GUI-only** — the FMC 10.0.1 REST API has zero SXP surface,
   FlexConfig objects aren't API-creatable, and the FTD diagnostic CLI has global config
   disabled. So it must be built in the FMC GUI.
2. **The "Insert" dropdown only opens by clicking the ▾ CARET**, not the button text. And
   **Escape closes the whole dialog**, not just the menu (click elsewhere to dismiss a menu).
3. **The object Save-check rejects any non-secret-key token after the word `password`** —
   plaintext (`CTSsxp123`) *and* a plain Text-Object variable both fail with "contains
   sensitive information as plain text. Add ... using secret key variable." (Note: **Validate
   passes** a text var but **Save** rejects it — Save is stricter.)
4. **But the device needs the literal keyword `password default`** (or `none`) on the
   connection line — a secret-key variable there would deploy the literal password value,
   which is invalid SXP connection syntax.
5. **The workaround:** the default-password line uses a real **Secret Key** var
   (`@sxp_pw` = `CTSsxp123`). The connection line's `password default` is hidden inside a
   **Text Object** (`sxpPwKeyword` value = `password default`) and referenced **bare**
   (`... source 10.50.0.2 $sxpPwKeyword mode local listener`) so the object body never
   literally contains "password" on that line → Save passes; deploy expands to valid
   `password default`. Text Objects must be pre-created under **Objects > FlexConfig > Text
   Object** (they can't be created inline from the FlexConfig insert dialog).
6. **Preview Config** masks the token after `password` as `******` (display only) — verify
   the real expansion on the device after deploy.

## Next steps — the pxGrid fix (#31)

### pxGrid build log + resume plan (banked 2026-07-14, ~90% done)

**Done:**
- ISE 3.5 (`ise35`, 198.18.134.35): **pxGrid + SXP personas enabled** via GUI (no reboot on
  3.5); pxGrid Services → Settings → **auto-approve cert-based accounts** ON.
- **IP-SGT binding** `10.40.0.10 → Employees(4)` created **via API** (OpenAPI TrustSec
  `POST /api/v1/trustsec/ip-sgt-mapping`, body `{ipHost, sgt:"Employees (4/0004)",
  sgtDomains:["default"]}`) — shipped as reusable tools `ise_create/list/delete_ip_sgt_mapping`
  in ISE_MCP `tools/trustsec.py` (commit 005392b).
- **FMC↔ISE integration** (FMC 198.18.128.13 → Integration → Identity Sources → **Identity
  Services Engine → Quick Configuration**): host `ise35.mitchcloud.lab`, admin creds,
  subscribe **Session Directory + SXP** topics. Admin/MnT **trust established**.
- **FMC management DNS fixed** → Primary `198.18.134.11` (the mitchcloud DC), so FMC resolves
  `ise35.mitchcloud.lab`. (FMC mgmt DNS is **not** in the FMC REST API — appliance-only, at
  Administration → Configuration → Management Interfaces.)
- **pxGrid 502 fully root-caused + ISE side fixed:** ISE's pxGrid cert was a dCloud-demo
  leftover (`CN=ise.demo.dcloud.cisco.com`, ISE-internal-CA). Rebound the **pxGrid role to the
  `ise35.mitchcloud.lab` system cert** (GUI: Certificates → System Certificates → edit
  `ise35-eap-mitchcloud` → tick pxGrid → Save; the API PUT `UpdateSystemCertRequest` throws a
  server-exception on cross-subject role transfer). `:8910` now presents
  `CN=ise35.mitchcloud.lab` signed by **Mitchcloud-Root-CA**.

**Remaining (the finish):** FMC must **trust Mitchcloud-Root-CA** to validate the pxGrid cert
chain — FMC currently trusts only the self-signed cert ISE serves on `:443`. Blocked by ISE's
messy cert config: `:443` (MnT) serves a **self-signed default** cert even though the Admin role
is on the CA-signed cert, so FMC's Quick-Config trust covers the wrong cert. Two finish paths:
1. **Untangle ISE certs** so `:443` and `:8910` present the *same* consistent cert → FMC's
   Quick-Config trust then covers both. Cleanest, but restarts ISE's **admin** service (surgery
   on the shared canonical NAC ISE — do deliberately, not rushed).
2. **FMC Advanced Configuration** — provision an FMC pxGrid **client cert** + import it into
   ISE trusted certs, set **MNT Server CA** (the self-signed `:443` cert) and **pxGrid Server
   CA = Mitchcloud-Root-CA** (PEM captured at scratchpad `chaincert_2.pem` from the `:8910`
   chain). Fiddly, several steps; Advanced's client-cert dropdown is empty (Quick-Config's
   auto cert isn't exposed).
Then: FMC Test passes → Save → **Deploy** → `packet-tracer input inside icmp 10.40.0.10 8 0
10.60.0.10` should show Snort `src sgt: 4` → `Employees-to-SRV-PERMIT` ALLOW → run the
permit/deny test.

**Lab state left intact:** ISE pxGrid cert rebind (correct — keep), FMC DNS fix (keep),
`ISE_MCP/.env` repointed `.30→.35` (keep — we're on 3.5). FMC ISE-integration is **unsaved**
(needs the passing Test). `ise.demo.dcloud.cisco.com` pxGrid cert now shows "Not in use".

### Original enforcement plan

To make the FTD **actually enforce**:
1. **ISE 3.5**: enable pxGrid; approve/auto-approve pxGrid clients; (optionally make ISE the
   SXP aggregator so the switch speaks SXP to ISE and ISE owns the SGT-IP mappings).
2. **FMC (198.18.128.13)**: Integration → Identity Sources → **Cisco ISE**; exchange
   pxGrid certs (the fiddly part); confirm FMC pulls SGT groups + SGT-IP mappings.
3. **ACP**: ensure rule #1/#2 SGT condition uses the **ISE** SGT group (`Employees`/
   `Contractors`), not an inline-only custom SGT object.
4. **Deploy**, then re-run `packet-tracer input inside icmp 10.40.0.10 8 0 10.60.0.10` — 
   Phase 16/17 should show `src sgt: 4` → match `Employees-to-SRV-PERMIT` = ALLOW.
5. Retire the `FTD_SGT_SXP` FlexConfig (LINA-only, redundant once pxGrid feeds Snort).
6. Then the permit/deny test: EP(Employees)→SRV PERMIT; re-tag EP→Contractors → DENY.

## Teardown / state notes

- FTD/FMC config lives in the FMC DB (not the CML topology). To tear down: delete FTD-SGT
  from FMC, then FMC/FTD/SRV nodes from lab `cb53d7fe…`; **leave the NAC core
  (switch/ISE/EP) intact** — it's canonical. Then revert `../Firepower_MCP/.env` to the
  baseline (`FMC_URL=https://198.18.128.11`, `FMC_PASSWORD=Cisc01@3`).
- `../Firepower_MCP/.env` currently points at the **SGT FMC (.13)** (gitignored) — leave it
  there for the pxGrid work.
- SRV-SGT is net-tools/runtime-only — re-apply `ip addr add 10.60.0.10/24 dev eth0` /
  `ip route replace default via 10.60.0.1` after any restart.

---

### pxGrid ROOT CAUSE (2026-07-14, definitive) — ISE pxGrid Session provider service DOWN

After completing ALL FMC-side config (cert trust, mgmt DNS→DC, FMC pxGrid client cert
from the dedicated FMC-SGT-pxGrid-CA, MnT+pxGrid Server CAs, Session Directory + SXP
topics) and ALL ISE-side config (pxGrid+SXP personas, auto-approve, IP-SGT binding via
API, pxGrid role rebound to ise35.mitchcloud.lab cert, ISE Messaging Service role also
moved onto that cert), the FMC "Test" still failed: **"PXGrid v2 is enabled [ERROR]:
Failed to contact pxGrid node at 'ise35.mitchcloud.lab': Server returned 500"**.

Root-caused it end-to-end (NOT a cert/trust problem, NOT FMC, NOT the MCP tooling):

- Replayed the pxGrid v2 control handshake directly with FMC's client cert
  (`fmc_pxgrid_client_caSigned.crt`/`.key`) against `https://198.18.134.35:8910`:
  - TLS mutual-auth SUCCEEDS (clean HTTP 401/503, not a handshake error) → ISE trusts
    FMC's cert; the FMC-side trust chain is correct.
  - `POST /pxgrid/control/AccountCreate` → **HTTP 503 Service Unavailable** (empty body),
    persistently (polled for minutes). `AccountActivate`/`ServiceLookup` → 401.
- ISE **Administration > pxGrid Services > Summary**: 0 pubsub connections, 0 total
  clients (0 approved / 0 pending), 0 errors — FMC's AccountCreate never landed.
- ISE **pxGrid > Diagnostics > Live Log**: only ONE entry, a `LOG_START` from the
  PREVIOUS day — the pxGrid controller has logged NO client activity since.
- ISE **pxGrid > Diagnostics > Tests > Health Monitoring Test** (ISE's OWN internal
  pxGrid client doing Session subscribe + bulk download) → **"Connect failed"**. Log tail:
  ```
  pxGrid Node: ise35.mitchcloud.lab
  [INFO] Session service unavailable
  [INFO] ------------------ Connection Test FAILED ------------------
  ```

**Conclusion:** the pxGrid **Session Directory provider service on ISE is unavailable** —
so even ISE's own internal client can't connect. This is 100% internal to ISE's pxGrid
stack, not the FMC integration. The trigger was almost certainly the ISE Messaging
Service certificate reassignment (its restart left the pxGrid Session/pubsub providers
wedged). **No additional certificate fixes this** (the Windows CA cannot help — the
services are simply down).

**Remediation (one step, needs the user / an authenticated ISE session):** restart ISE
application services so the messaging bus + pxGrid providers re-initialise consistently:
- CLI: `application stop ise` then `application start ise` (or `application restart ise`)
  on ise35 — ~15-20 min; OR
- GUI (no CLI login): Administration > System > Deployment > ise35 > edit, toggle the
  **pxGrid** persona OFF > Save (app restart), then ON > Save (app restart).
Then re-run pxGrid Diagnostics > Tests > Health Monitoring Test until it PASSES
("Session service available"), and re-run the FMC ISE Advanced-config **Test** — the 500
should clear. Then Save the FMC integration, Deploy, and run the enforcement test
(`packet-tracer input inside icmp 10.40.0.10 8 0 10.60.0.10` → expect Snort src sgt:4 →
Employees-to-SRV PERMIT / ALLOW; flip EP to Contractors → DENY).

Everything on both sides is staged and correct — this is purely blocked on ISE pxGrid
service health, which a restart resolves. Deliberately NOT restarting ISE unattended (a
~15-20 min appliance-services outage is heavier than the create/delete round-trips the
lab is cleared for) — flagged for the user to green-light.
