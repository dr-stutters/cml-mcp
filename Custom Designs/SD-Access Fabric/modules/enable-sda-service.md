# Enabling the SD-Access service in Catalyst Center

How we turned CatC-driven SD-Access provisioning from **blocked** (`NCSP11008`) to
**working** (fabric site created) on a Catalyst Center **3.2.2** appliance. Validated
live 2026-07-16. Screenshots referenced below live in [`screenshots/`](screenshots/)
(add the captured images with the referenced names).

## TL;DR

`NCSP11008 "No application found for type 'ConnectivityDomain'"` on SDA writes means
the **SD-Access application is not installed** — not a resource or payload problem.
Install it from **System → Software Management**, satisfy the per-site telemetry
prerequisite, and fabric provisioning works.

> **Correction to an earlier hypothesis:** the maglev console banner *"Resource
> reservation check failed (0 vs 262144 MB / 64000 MHz)"* on this dCloud box is a
> **red herring** — the base services run anyway and the SD-Access install completed
> fine. The blocker was purely the **uninstalled package**.

## Symptom

Any SDA fabric write fails immediately:
```
POST /dna/intent/api/v1/sda/fabricSites  →  taskId
catc_get_task → isError:true, errorCode NCSP11008,
  "No application found for type 'ConnectivityDomain' and qualifier 'null'."
```
SDA **read** APIs (`catc_fabric_sites` → `[]`) work; only writes fail.
_Screenshot: `01-ncsp11008-task.png` (the failing task)._

## Diagnosis (three angles)

1. **GUI** — System → Software Management: **SD Access** sits under *"Available
   Applications for the release"* (i.e. **not installed**), not under installed apps.
   _Screenshot: `02-software-mgmt-sd-access-available.png`._
2. **Console** (maglev) — `magctl appstack status sda` → **"No resources found in
   sda namespace"** (no SDA pods). Note the SDA services actually deploy into the
   **`fusion`** appstack, so post-install don't re-check the `sda` namespace — the
   authoritative signal is the GUI Release Activities status + the API test below.
   _Screenshot: `03-magctl-no-sda.png`._
3. **API** — the fabric write returns NCSP11008 (above).

## Fix — install the SD Access application

1. **System → Software Management**. Under **Available Applications for the release
   \<x\>**, tick **SD Access** (dependencies are auto-selected). _Screenshot:
   `04-tick-sd-access.png`._
2. Click **Install**. A banner shows *"Installation of Optional Packages is in
   progress."* _Screenshot: `05-install-in-progress.png`._
3. Track it under **View Release Activities**: action `INSTALL_OPTIONAL_PACKAGE`,
   status **In Progress**. On this box it took **~44 min** (a constrained
   dCloud appliance; download/image-load dominates — the `sda`/`fusion` pods only
   appear near the end). _Screenshots: `06-release-activities-inprogress.png`,
   `07-release-activities-success.png` (Status **Success**, Duration 44m 31s)._

> The install runs **server-side** — a GUI session timeout / logout does not affect
> it. The maglev restricted shell blocks the `maglev` command, so you can't read
> install progress from the console; use Release Activities.

## Post-install prerequisite (per fabric site)

With the app installed, the first `POST /sda/fabricSites` returns a **different**
error — the SDA service is now processing the intent:
```
errorCode NCSO20572:
  "Before creating a new Fabric Site ... enable wired client IP Device Tracking in
   Network Settings > Telemetry > Wired Client Data Collection for site <name>."
```
Enable it (GUI: Design → Network Settings → Telemetry → **Wired Client Data
Collection** for the site; or API):
```
PUT /dna/intent/api/v1/sites/{siteId}/telemetrySettings
{ "applicationVisibility": null,
  "wiredDataCollection": { "enableWiredDataCollection": true },
  "wirelessTelemetry": null, "snmpTraps": null, "syslogs": null }
```
(All five fields are required; `null` = inherit.) Poll the task → *"Desired Common
Settings operation successful."* _Screenshot: `08-wired-data-collection.png`._

## Verify — fabric provisioning now works

```
POST /dna/intent/api/v1/sda/fabricSites
[{ "siteId": "<building>", "authenticationProfileName": "No Authentication",
   "isPubSubEnabled": true }]
→ taskId → catc_get_task: isError:false, processcfs_complete:true

GET (catc_fabric_sites) →
  [{ "id": "...", "siteId": "<building>",
     "authenticationProfileName": "No Authentication",
     "isPubSubEnabled": true, "underlayTransport": "IPV4" }]
```
`NCSP11008` is gone; the fabric site exists. SD-Access provisioning is **enabled**.
_Screenshot: `09-fabric-site-created.png`._

## Notes

- **What each error meant:** `NCSP11008` = SDA app not installed (service missing);
  `NCSO20572` = SDA app installed and working, but a per-site telemetry prerequisite
  is unmet. The progression NCSP11008 → NCSO20572 → success is the signal that the
  install took effect.
- **ISE is still not required** — this whole enablement uses `No Authentication`
  (static host onboarding).
- After enabling, continue the fabric build (device roles → L3 VN → anycast gateway
  → port assignment) — see the [CatC provisioning module](catc-provisioning.md).
