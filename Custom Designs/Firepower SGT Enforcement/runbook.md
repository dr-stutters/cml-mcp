# Firepower SGT Enforcement — runbook

**Status (2026-07-15): PROVEN end-to-end.** ISE assigns an SGT → ISE shares the IP→SGT
binding → **FMC↔ISE pxGrid** hands it to the FTD → **Snort** enforces an SGT-based
access-control policy: **Employees permitted, Contractors denied** to a protected server.
See [Enforcement proof](#enforcement-proof).

Goal: **ISE assigns an SGT at MAB → the IP→SGT binding reaches the FTD → the FTD enforces an
SGT-based access-control policy** (permit Employees / deny Contractors to the server).

## The critical finding (read this first)

**A direct switch→FTD `cts sxp` peer (FMC FlexConfig) feeds the FTD's LINA data plane ONLY.
It does NOT drive FMC Access-Control-Policy SGT enforcement.**

FMC ACP rules with an SGT condition on an **Allow** action are evaluated by **Snort**, and
Snort only learns SGT-IP mappings from **FMC↔ISE integration (pxGrid)** or **inline SGT
tags** — never from LINA's `cts` subsystem. So a switch→FTD SXP binding lands in LINA, LINA
matches the *network* part of the rule and defers to Snort, Snort sees `src sgt: 0`, no SGT
rule matches, and the flow hits the ACP **default = BLOCK**.

`packet-tracer` proved it exactly, *before* pxGrid was wired up:
- Header: `Mapping security-group 4 to IP address 10.40.0.10` — LINA knows SGT=4.
- Snort phase: `src sgt: 0, src sgt type: unknown` → `Matched rule ... Block` → `drop`.
- `show access-list CSM_FW_ACL_ | include security-group` → **empty** (the SGT condition
  lives entirely in Snort, not the LINA ACL).

**The fix = FMC↔ISE pxGrid.** FMC learns the SGT-IP mappings from ISE (Session Directory +
SXP topics) and pushes them to the FTD **Snort** engine; the ACP rule uses the **ISE** SGT
group. Then Snort sees the real SGT and the rule matches. The direct switch→FTD FlexConfig
SXP listener is redundant for enforcement (LINA-only) and can be retired.

## Topology

Layered onto the canonical NAC/TrustSec core lab
**`cb53d7fe-aecc-4770-9353-f6af8b6d7637`** (ISE35-MAB), reusing the existing switch + ISE 3.5
+ endpoint; the SGT tier adds an FMC + FTD + server.

```
EP-ISE35 (10.40.0.10, SGT Employees/4 via MAB)
   │ gw 10.40.0.1 (SW Vlan40)
SW-ISE35 (cat9000v)  ──►  FTD-SGT inside Eth0/0 (10.50.0.2)
   │ inside Gi1/0/4 10.50.0.1                 │ outside Eth0/1 10.60.0.1
   │ route 10.60.0.0/24 → 10.50.0.2          │ static 10.40.0.0/24 → 10.50.0.1
   └─────────────────────────────────────►  SRV-SGT (10.60.0.10, gw 10.60.0.1)
FMC-SGT (198.18.128.13, admin/SgtLab#2026Fw, v10.0.1) manages FTD-SGT, integrates with ISE pxGrid
ISE35 (198.18.134.35, 3.5) — SGT assignment + pxGrid publisher
```

| Node | Role | Addressing |
|---|---|---|
| FMC-SGT | FMCv | mgmt 198.18.128.13; eval license (Advantage/Premier) |
| FTD-SGT | FTDv, FMC-managed routed | inside 10.50.0.2/30, outside 10.60.0.1/24; RegKey `sgtreg123` |
| SRV-SGT | net-tools | 10.60.0.10/24, gw 10.60.0.1 (runtime-only) |
| SW-ISE35 | cat9000v (existing) | inside Gi1/0/4 10.50.0.1; Vlan40 10.40.0.1; ISE NAD .66 (Mgmt VRF) |
| EP-ISE35 | endpoint (existing, busybox) | 10.40.0.10, gw 10.40.0.1 |

## Build

### 1. SGT assignment + the IP→SGT binding (ISE)

- EP-ISE35 authorized via **MAB → SGT Employees(4)**; switch `show cts role-based sgt-map all`
  → `10.40.0.10  4  LOCAL`.
- **pxGrid + SXP personas enabled** on ise35 (GUI; no reboot on 3.5); pxGrid Services →
  Settings → **auto-approve certificate-based accounts = ON**.
- **Static IP-SGT binding** `10.40.0.10 → Employees(4)` created via API (OpenAPI TrustSec
  `POST /api/v1/trustsec/ip-sgt-mapping`, body `{ipHost, sgt:"Employees (4/0004)",
  sgtDomains:["default"]}`) — shipped as reusable ISE_MCP tools
  `ise_create/list/delete_ip_sgt_mapping` (`tools/trustsec.py`). This is what ISE advertises
  over the pxGrid **SXP topic**.

### 2. FMC access-control policy (SGT-ACP)

ACP **SGT-ACP**, default action **BLOCK**, using the **ISE** SGT groups:
- rule `Employees-to-SRV-PERMIT` — src SGT Employees(4) → HOST-SRV-10.60.0.10 = **Allow**
- rule `Contractors-to-SRV-DENY` — src SGT Contractors(5) → SRV = **Block**

Interfaces/zones/route deployed; server object `HOST-SRV-10.60.0.10`.

### 3. FMC↔ISE pxGrid integration (the enabler)

FMC → **Integrations → Identity Sources → Identity Services Engine → Advanced Configuration
(Old)**:

| Field | Value |
|---|---|
| Primary Host Name/IP | `ise35.mitchcloud.lab` |
| pxGrid Client Certificate | `FMC-SGT-pxGrid-Client` |
| MNT Server CA | `ISE35-MnT-CA` |
| pxGrid Server CA | `Mitchcloud-Root-CA` |
| Subscribe To | **Session Directory** + **SXP** topics |

Prerequisites that make the above work:
- **FMC management DNS → `198.18.134.11`** (the mitchcloud DC) so FMC resolves
  `ise35.mitchcloud.lab`. FMC mgmt DNS is **not** in the FMC REST API — set it at
  Administration → Configuration → Management Interfaces.
- **Certificate chain:** the FMC pxGrid client cert (`FMC-SGT-pxGrid-Client`, cut from a
  dedicated `FMC-SGT-pxGrid-CA`) is imported into ISE's trusted certs; FMC trusts ISE's
  pxGrid server cert via **`Mitchcloud-Root-CA`** and the MnT `:443` cert via `ISE35-MnT-CA`.
  ISE's `:8910` presents `CN=ise35.mitchcloud.lab` signed by `Mitchcloud-Root-CA` (the
  pxGrid system-cert role was moved off the dCloud-demo leftover cert onto `ise35-eap`).

**Test → "Primary host: Success" → Save.** ISE **pxGrid → Client Management** then shows the
FMC clients (`fmc-…` + `t-fmc-…`) **Enabled/approved** (auto-approve). FMC now receives the
SGT-IP bindings and pushes them to the FTD Snort engine.

## Enforcement proof

`packet-tracer` on FTD-SGT (LINA/diagnostic CLI). All three source SGTs are **learned via
pxGrid** (`src sgt type: sxp`) and select **distinct** ACP rules:

| Source IP | SGT (via pxGrid) | Snort rule matched | Verdict |
|---|---|---|---|
| `10.40.0.10` | **Employees (4)** | `268434434` Employees-to-SRV-PERMIT | **ALLOW** |
| `10.40.0.11` | **Contractors (5)** | `268434435` Contractors-to-SRV-DENY | **DROP** |
| _(unmapped)_ | `0` / unknown | `268434432` default | Block |

Permit trace (`... icmp 10.40.0.10 8 0 10.60.0.10`):
```
Phase 15 SNORT identity:  src sgt: 4, src sgt type: sxp   → ALLOW
Phase 16 SNORT firewall:  src sgt: 4 ... Matched rule 268434434 - Allow   → allow
```
Deny trace (`... icmp 10.40.0.11 8 0 10.60.0.10`):
```
Phase 15 SNORT identity:  src sgt: 5, src sgt type: sxp
Phase 16 SNORT firewall:  src sgt: 5 ... Matched rule 268434435 - Block   → drop
```

That is the whole chain working: **ISE (SGT + IP-SGT binding) → pxGrid SXP topic → FMC → FTD
Snort → SGT-based ACP → permit Employees / deny Contractors.** Contrast the pre-pxGrid state
where Snort saw `src sgt: 0` and everything hit the default BLOCK.

## Field lessons (hard-won)

- **A flaky browser cost days.** The pxGrid integration *looked* broken for a long stretch:
  ISE's own admin GUI threw `Server Error: undefined`, `pxGrid Client Management`/`Settings`
  wouldn't load, and `systemCertificatesAction.do … status:0`. **`status:0` means the HTTP
  request never completed client-side — a browser/network failure, not a server error.**
  Restarting the operator's browser cleared every one of those with **zero changes to ISE**.
  → When an ISE admin GUI errors, **suspect the browser first; reproduce via API/CLI before
  concluding ISE is broken.** (The overnight full-ISE restart + Data Grid/IMS cert renews
  chased this ghost — harmless, and they left ISE's messaging/data-grid certs on the internal
  CA, which is fine.)
- **`AccountCreate` 503 is a red herring.** `POST /pxgrid/control/AccountCreate` is the
  *password-based* registration endpoint, **disabled by default**. FMC uses **certificate-
  based** pxGrid and never calls it. The other control endpoints (AccountActivate /
  ServiceLookup / pubsub) answering **401** = servlets up, awaiting an approved client = healthy.
- **A `red` FTD health in FMC lags — don't call it a dead tunnel.** The enforcing Employees
  mapping was on the FTD the whole time while FMC health showed red.
- **Propagation timing:** the SGT-IP set present *at pxGrid connect* reaches the FTD fast (FMC
  bulk-downloads it). A **new** ISE static IP-SGT binding takes **~5-6 min** to reach FTD Snort
  via the *incremental* pxGrid/SXP path — wait before concluding it failed.
- **Not** the cause: licensing (Essential/Advantage/Premier all enabled in eval), and **not**
  FMC bug CSCwq75449 (that's an FMC-7.7.x Quick-Config *502*; we're on FMC 10.0.1 via Advanced
  Configuration, and the transient error was a 500, per Cisco doc 225770).

## The FlexConfig SXP listener — the LINA-only path (historical, superseded)

Before pxGrid, a switch→FTD `cts sxp` listener was built via FMC FlexConfig. It populates
**LINA only** and does **not** drive Snort enforcement (see the critical finding), so it's
redundant now — but the editor gotchas are worth keeping:

1. FTD SXP/CTS is **FlexConfig/GUI-only** — no FMC 10.x REST surface, FlexConfig objects
   aren't API-creatable, and the FTD diagnostic CLI has global config disabled.
2. The **Insert dropdown opens only by clicking the ▾ CARET**, not the button text; **Escape
   closes the whole dialog** (click elsewhere to dismiss just a menu).
3. The object **Save-check rejects any non-secret-key token after the word `password`** —
   plaintext *and* a plain Text-Object var both fail ("add … using secret key variable");
   Validate passes a text var but Save is stricter and rejects it.
4. But the device needs the literal keyword **`password default`** on the connection line (a
   secret-key var there would deploy the literal password = invalid SXP syntax).
5. **Workaround:** default-password line uses a real Secret Key var (`@sxp_pw`=`CTSsxp123`);
   the connection's `password default` is hidden inside a **Text Object** (`sxpPwKeyword`
   value=`password default`) referenced **bare**, so the object body has no literal "password"
   on that line → Save passes, deploy expands to valid `password default`. Text Objects must
   be pre-created under Objects → FlexConfig → Text Object.

Generated CLI (LINA): `cts sxp enable` / `cts sxp default password CTSsxp123` / `cts sxp
connection peer 10.50.0.1 source 10.50.0.2 password default mode local listener`.

## Teardown / state notes

- FTD/FMC config lives in the FMC DB (not the CML topology). To tear down: remove the ISE
  pxGrid integration + delete FTD-SGT from FMC, then delete the FMC/FTD/SRV nodes from lab
  `cb53d7fe…`; **leave the NAC core (switch/ISE/EP) intact** — it's canonical. Then revert
  `../Firepower_MCP/.env` to baseline (`FMC_URL=https://198.18.128.11`,
  `FMC_PASSWORD=Cisc01@3`).
- `../Firepower_MCP/.env` currently points at the **SGT FMC (.13)** (gitignored) — correct
  while this lab stays up.
- SRV-SGT is net-tools/runtime-only — re-apply `ip addr add 10.60.0.10/24 dev eth0` /
  `ip route replace default via 10.60.0.1` after any restart.
- Left in place as the deny demonstrator: ISE static IP-SGT binding `10.40.0.11 →
  Contractors(5)` (delete via `ise_delete_ip_sgt_mapping` if you want the lab back to just the
  Employees binding).
