# Module — FMC Rapid Threat Containment (auto ANC over pxGrid)  [C2 Stage B]

Close the RTC loop so an **FMC event automatically quarantines the offender** on ISE — no human
running `ise_apply_anc`. An FTD connection event → FMC **correlation rule** → FMC **remediation** →
**pxGrid ANC** apply → ISE **CoA** → the endpoint's fabric session is bounced. Built on the C2
Stage A containment primitive ([`rapid-threat-containment.md`](../../../Test%20Plans/Lab%20Designs/rapid-threat-containment.md))
+ the C5 FMC↔ISE pxGrid ([`fmc-ise-pxgrid.md`](fmc-ise-pxgrid.md)).

**Status (2026-07-17): DONE — proven live end-to-end**, fully automatic.

> **All of Stage B is GUI-only** — FMC correlation policies + remediations are **not in the FMC
> REST API** (`fmc_search_spec "correlation|remediation"` → empty). Drive the `admin1` browser.

---

## THE fix — pxGrid EPS is an ISE client-group, not an FMC toggle

The blocker (Stage-B-v1) was that the FMC remediation's **ANC Policy dropdown was empty of ISE
policies** (only the built-in *"Clears ANC Policy"*, no `Quarantine`). It is **not** a transport
problem — FMC → ISE **Test = "Primary host: Success"** and Session Directory works (C3 proves it).
FMC's ISE identity source only exposes **Session Directory + SXP** subscriptions — **there is no
ANC/EPS toggle in FMC**. ANC access is granted **on ISE** by pxGrid **client-group** membership:

1. **ISE → Administration → pxGrid Services → Client Management → Groups** has an **`ANC`** group
   (alongside `Internal`). Session-directory access is open to all approved clients; **ANC needs
   the `ANC` group**.
2. **Client Management → Clients**: FMC registers **two** clients — the permanent
   **`fmc-<id>-fmcv`** and a temp **`t-fmc-<id>`** — both *Enabled* but with **no Client Group**.
3. Select the **`fmc-…-fmcv`** client → **Edit** → **Client Groups = `ANC`** → **Save**. (The
   Clients list then shows `ANC` in its Client Groups column.)
4. Back in FMC, re-open the remediation → the **ANC Policy dropdown immediately lists `Quarantine`**
   — **no pxGrid reconnect needed** (FMC queries ANC live, and the group authorizes the query).

That's the whole unlock. Everything else is standard FMC RTC wiring.

## The FMC build (Policies → Correlation)

1. **Remediation instance** (Modules present out of the box). Instances → *Add* module **"pxGrid
   Adaptive Network Control (ANC) Policy Assignment"** → name **`ISE-ANC-Quarantine`** → Create.
2. **Remediation** on that instance → type **"ANC Policy for Source"** (quarantine the connection's
   *source* = the offender) → name **`Quarantine-Source`**, **ANC Policy = `Quarantine`** → Create.
3. **Correlation rule** (Rule Management → Create Rule): **`Quarantine-on-CatC-Deny`**, event **"a
   connection event occurs"**, condition **`Access Control Rule Name` contains the string
   `Deny-CAMPUS-to-CatC`** → Save. (Any connection the FTD logs against that deny rule fires it.)
4. **Correlation policy** (Policy Management → Create Policy): **`RTC-Quarantine`** → **Add Rules**
   → the rule → on the rule row open **Responses** → move **`Quarantine-Source`** from *Unassigned*
   to *Assigned* → Update → **Save** → flip the policy **toggle ON** (active). No FTD deploy needed —
   correlation runs on the FMC.

## Proven live

From HOST1 (`alice`, `172.16.10.50`) generate blocked traffic to **host-catc `198.18.128.5`**
(`ping` + `nc` 443/80/22 + `wget https`) — all denied by `Deny-CAMPUS-to-CatC`. Within seconds,
**automatically**:
- ISE **ANC endpoint auto-created**: `GET /ers/config/ancendpoint/{id}` → `macAddress
  52:54:00:03:0B:0D`, `policyName Quarantine` (FMC applied it over pxGrid — no `ise_apply_anc`).
- alice's session bounced with the **identical CoA as Stage A**: `ise_session_by_username alice` →
  `CoASourceComponent=ANC`, `CoAReason=Quarantine per ANC policy`, `Acct-Terminate-Cause=Admin Reset`.
- Release: `ise_clear_anc` + `sudo -n wpa_cli -i eth0 reassociate` on HOST1 → alice re-auths to
  **Employees SGT 4**, ~15-20 s LISP reconverge, both dests **0% loss**, `ise_list_anc_endpoints=[]`.

The `RTC-Quarantine` policy is **left active** — it re-quarantines any HOST1→host-catc attempt
(that *is* the feature). Deactivate its toggle to pause.

## FMC classic-GUI gotchas (the `/ddd/` + `.cgi` pages are flaky)

- **Double Create.** Instance/remediation/rule create forms need **two** Create clicks — the first
  "arms"/validates, the second actually POSTs (watch for the green *Success* banner).
- **`select` change events.** Setting a native dropdown via tooling may not fire the page's
  onchange, so the POST sends the default — verify the field shows the intended value, and if a
  Create silently no-ops, re-select and Create again.
- **Condition value text can silently drop** — after typing the rule value (`Deny-CAMPUS-to-CatC`),
  confirm it's in the field before Save or you get *"You must supply a value…"*.
- **Left nav overlaps** the correlation tab bar / condition builder — collapse it (hamburger) to
  reach `Policy Management` / `Rule Management` tabs and the far-left dropdowns.

Related: [[cml-fmc-ise-pxgrid-recipe]], [[sda-ise-integration-lab]], [`fmc-ise-pxgrid.md`](fmc-ise-pxgrid.md).
