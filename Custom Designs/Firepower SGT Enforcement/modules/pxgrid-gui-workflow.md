# pxGrid integration — manual (GUI) workflow

Click-by-click guide for the **browser/GUI** steps of the FMC↔ISE pxGrid integration — the
parts that can't be driven by API/CLI. Companion to the parent
[`runbook.md`](../runbook.md); follow that for the full lab, this for the manual sections.

**Environment:** ISE 3.5 `https://198.18.134.35`, FMC 10.0.1 `https://198.18.128.13`
(admin / `SgtLab#2026Fw`). **You perform every login yourself** — never hand credentials to
automation.

> **📷 Screenshots:** each step marks where a screenshot belongs and describes exactly what
> the screen should look like, so this is followable without images and doubles as a
> screenshot-capture checklist (see the [index](#screenshot-capture-checklist) at the end).

## What's manual vs automatable

| Piece | How |
|---|---|
| ISE SGTs, IP-SGT bindings, session/enforcement checks | **API/CLI** (ISE MCP tools, `packet-tracer`) |
| ISE pxGrid persona + settings + system-cert role | **GUI** (this doc, Part A) |
| Certificate exchange (FMC client cert → ISE trust; CAs → FMC trust) | **GUI + openssl** (Part B) |
| FMC ISE Advanced Configuration + Test + Save | **GUI** (Part C) |
| Verify pxGrid on ISE (Client Management, Health Test) | **GUI** (Part D) |

## Prerequisites (before the GUI steps)

- **FMC management DNS resolves `ise35.mitchcloud.lab`.** Point FMC mgmt DNS at the DC
  `198.18.134.11`. This is an **appliance setting, not in the FMC REST API** — set it at
  *Administration → Configuration → Management Interfaces → DNS*. Without it, the Test fails
  with a `502 Proxy Error` (FMC can't resolve the host).
- Certificates staged (Part B): an FMC pxGrid **client** cert exists and ISE trusts it; FMC
  trusts ISE's pxGrid **server** CA and the MnT `:443` cert.

---

## Part A — ISE: enable pxGrid (one-time)

1. **Enable the pxGrid + SXP personas.** *Administration → System → Deployment →* click the
   node (`ise35`) *→* on **General Settings** tick **pxGrid**; on **SXP Settings** tick
   **Enable SXP Service** *→ Save*. (On a standalone 3.5 node this does **not** reboot.)
   - 📷 *node edit page with pxGrid + SXP ticked.*
2. **Auto-approve pxGrid clients.** *Administration → pxGrid Services → Settings →* tick
   **Automatically approve new certificate-based accounts** *→ Save*. (Without this, FMC's
   client registers as **Pending** and you must Approve it manually in Part D.)
   - 📷 *pxGrid Settings with auto-approve on.*
3. **Confirm the pxGrid system-cert.** *Administration → System → Certificates → System
   Certificates.* The cert whose **Used By** includes **pxGrid** should be a real cert
   (here `ise35-eap-mitchcloud`, issued by `Mitchcloud-Root-CA`) — **not** a leftover
   `CN=ise.demo.dcloud.cisco.com` demo cert. If it's on the demo cert, edit the good cert and
   tick **pxGrid** (the API PUT throws a server-exception on this cross-subject move, so do it
   in the GUI). ISE `:8910` should then present `CN=ise35.mitchcloud.lab`.
   - 📷 *System Certificates list showing pxGrid on the ise35 cert.*

---

## Part B — Certificates (the fiddly prerequisite)

FMC uses **certificate-based** pxGrid: FMC presents a client cert ISE trusts, and FMC must
trust ISE's pxGrid server cert + MnT cert. What must exist:

1. **FMC pxGrid client cert** — `FMC-SGT-pxGrid-Client` (CN e.g. `fmc-sgt.mitchcloud.lab`),
   cut from a dedicated CA (`FMC-SGT-pxGrid-CA`) via openssl, imported into FMC
   (*Objects → PKI → Internal Certs*).
2. **ISE trusts that client cert's CA** — import `FMC-SGT-pxGrid-CA` into ISE:
   *Administration → System → Certificates → Trusted Certificates → Import*, tick **Trust for
   authentication within ISE**. (ISE rejects importing a self-signed **leaf** into trust —
   import the **CA**, not the leaf.)
   - 📷 *ISE Trusted Certificates import dialog.*
3. **FMC trusts ISE's server certs** — import into FMC (*Objects → PKI → Trusted CAs*, or on
   the fly with the **+** next to each dropdown in Part C):
   - **pxGrid Server CA** = `Mitchcloud-Root-CA` (the CA that signed ISE's pxGrid cert; grab
     the chain from `openssl s_client -connect 198.18.134.35:8910`).
   - **MNT Server CA** = `ISE35-MnT-CA` (ISE's `:443` MnT cert).

---

## Part C — FMC: the ISE Advanced Configuration (main flow)

> This is the flow that was proven end-to-end. The whole form is **config data** (host name,
> dropdown selections, checkboxes) — safe to fill; only the **login** is manual.

1. **Log in** to FMC `https://198.18.128.13` (you do this).
2. *Manage →* **Integrations → Identity Sources**. (Left nav → Integrations.)
   - 📷 *Configure Identity Sources page.*
3. **Service Type:** select **Identity Services Engine** (radio).
4. Click the **Advanced Configuration (Old)** tab (next to *Quick Configuration (New)*).
   - ⚠️ **Do not use Quick Configuration** — on some FMC/ISE combos it fails with a spurious
     `502 Proxy Error` (Cisco bug CSCwq75449). Advanced is the reliable path.
5. **Primary Host Name/IP Address:** `ise35.mitchcloud.lab`. (Leave Secondary blank.)
6. **pxGrid Client Certificate:** click the dropdown → select **`FMC-SGT-pxGrid-Client`**.
7. **MNT Server CA:** click the dropdown (it lists *all* trusted CAs — hundreds) → **type
   `ISE`** to filter → select **`ISE35-MnT-CA`**.
   - 💡 These dropdowns are **searchable** — type to filter; don't scroll the whole list.
8. **pxGrid Server CA:** click the dropdown → **type `Mitch`** → select
   **`Mitchcloud-Root-CA`**.
9. **Subscribe To:** tick **Session Directory Topic** *and* **SXP Topic**. (SXP is what carries
   the IP-SGT static bindings that drive FTD Snort enforcement — don't skip it.)
   - 📷 *filled form: host, all 3 certs set, both topics ticked.*
10. Click **Test**.
    - ✅ Expect the **Status** dialog: **"ISE connection status: Primary host: Success"**.
      Expand *Additional Logs* to confirm. Click **OK**.
    - 📷 *Status dialog showing "Primary host: Success".*
11. Click **Save** (top-right, turns blue once the form is valid). The **"You have unsaved
    changes"** banner disappears and the buttons grey out = saved.
    - ⚠️ **If you navigate away without Save, the whole form clears** — you'll have to
      re-enter all 6 fields. (This bit us: the config kept resetting because the failing Test
      blocked the Save.)

---

## Part D — Verify on ISE

1. *Administration → pxGrid Services →* **Client Management → Clients.** FMC now appears as
   **two** clients — `fmc-…` and `t-fmc-…` (its session sub-client) — both **Status = Enabled**
   (auto-approve did this; if **Pending**, select and **Approve**).
   - 📷 *Client Management list, both FMC clients Enabled.*
2. *pxGrid Services →* **Diagnostics → Tests →** **Health Monitoring Test → Start Test.** It
   shows *"Running. Please check back in a few minutes."*
3. *Diagnostics →* **Log** (Live Log). You should see the internal test client
   `~ise-internal_test` with events **WS_SERVER** (WebSocket connected) + **PUBSUB** (subscribe)
   against `wss://ise35.mitchcloud.lab:8910/pxgrid/ise/pubsub` = pxGrid healthy.
   - 📷 *Live Log with WS_SERVER + PUBSUB entries.*

Once verified, FMC receives the SGT-IP bindings and pushes them to the FTD Snort engine — go
run the enforcement `packet-tracer` in the parent runbook.

---

## Gotchas (the ones that cost us days)

- **`Server Error: undefined` / `status:0` in the ISE admin GUI = a flaky BROWSER, not ISE.**
  `status:0` means the HTTP request never completed client-side. **Restart the browser** and
  re-check before touching ISE. (We wasted a full ISE restart + cert renewals chasing this
  ghost — ISE was healthy the whole time.)
- **`AccountCreate` → 503 on `:8910` is a red herring.** That's the *password-based*
  registration endpoint, disabled by default; cert-based FMC never uses it. Healthy signs are
  AccountActivate/ServiceLookup/pubsub returning **401** (up, awaiting an approved client).
- **A `red` FTD health in FMC lags** — it does **not** mean the FMC↔FTD tunnel is down.
- **New IP-SGT bindings take ~5-6 min** to reach FTD Snort via the incremental pxGrid/SXP path
  (the set present at connect-time arrives fast via FMC's bulk download). Wait before assuming
  failure.
- Dropdowns are **searchable**; the FMC form **resets on navigate-away without Save**.

## Screenshot capture checklist

To produce the illustrated version, capture these (in order) while re-driving the flow:

| # | Screen | Page |
|---|---|---|
| A1 | Node edit — pxGrid + SXP ticked | ISE Deployment → node |
| A2 | pxGrid auto-approve setting | ISE pxGrid Services → Settings |
| A3 | System Certificates — pxGrid role | ISE System Certificates |
| B1 | Trusted-cert import (FMC client CA) | ISE Trusted Certificates |
| C1 | Configure Identity Sources (start) | FMC Integrations → Identity Sources |
| C2 | Filled Advanced form (host + 3 certs + 2 topics) | FMC Advanced Configuration |
| C3 | Test result — "Primary host: Success" | FMC (Test dialog) |
| D1 | Client Management — 2 FMC clients Enabled | ISE pxGrid → Client Management |
| D2 | Live Log — WS_SERVER + PUBSUB | ISE pxGrid → Diagnostics → Log |

_Say the word and I'll re-drive the live GUIs and capture C1–D2 (the FMC + verify screens are
easiest to reproduce now that the integration is up)._
