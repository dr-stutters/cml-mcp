# SD-Access Fabric — Catalyst Center provisioning (blocked on this appliance)

The intended **Catalyst Center-driven** fabric-provisioning flow via the `catc` MCP
tools + Intent API. On the appliance used here (Catalyst Center **3.2.2**, virtual)
it **fails at fabric-site creation** with `NCSP11008` — the SD-Access *provisioning*
microservice isn't functional (read APIs work; writes can't process a fabric). This
module documents the full intended flow, exactly where it blocks, and the working
pieces. See [enabling the SD-Access microservice](#enabling-sd-access) for the
follow-up investigation.

## Flow (Intent API + `catc` tools) — VALIDATED WORKING 2026-07-16

Once the SD Access app is installed ([enable-sda-service.md](enable-sda-service.md)),
this full sequence provisions a fabric end-to-end (No-Auth static host onboarding, no
ISE). All steps are async (`taskId` → poll `catc_get_task`; `isError:false` +
`processcfs_complete=true` = done). Validated: LISP edge↔CP session up, host EID
registered to the CP, host reaches its anycast gateway.

| # | Step | Endpoint | Notes |
|---|---|---|---|
| 1 | Discover + site + assign | `catc_start_discovery`, `catc_create_area/_building`, `catc_assign_devices_to_site` | see [runbook](../runbook.md) Stage 3 (unique serials!) |
| 2 | **Enable telemetry** (per site) | `PUT /sites/{siteId}/telemetrySettings` `{wiredDataCollection:{enableWiredDataCollection:true}, +4 null}` | else fabric-site create → `NCSO20572` |
| 3 | **Create fabric site** | `POST /sda/fabricSites` `[{siteId, authenticationProfileName:"No Authentication", isPubSubEnabled:true}]` | → `catc_fabric_sites` returns the `fabricId` |
| 4 | **Provision devices** | `POST /sda/provisionDevices` `[{networkDeviceId, siteId}...]` | required before a device can take a fabric role |
| 5 | **Add Control-Plane** | `POST /sda/fabricDevices` `[{networkDeviceId, fabricId, deviceRoles:["CONTROL_PLANE_NODE"]}]` | **CP before Edge** (edge 400s with no CP) |
| 6 | **Add Edge** | `POST /sda/fabricDevices` `[{... deviceRoles:["EDGE_NODE"]}]` | |
| 7 | Global pool → reserve sub-pool | `catc_create_global_pool`; then **`POST /reserve-ip-subpool/{siteId}`** `{name,type:"LAN",ipv4GlobalPool:"<cidr>",ipv4Prefix:true,ipv4PrefixLength,ipv4Subnet,ipv4GateWay}` | the reserve **tool** omits `ipv4GlobalPool` → use the raw call |
| 8 | Create L3 VN + anchor | `catc_create_layer3_virtual_network`; then `PUT /sda/layer3VirtualNetworks` `[{id, virtualNetworkName, fabricIds:[fabricId]}]` | VN must be anchored to the fabric |
| 9 | Anycast gateway | `POST /sda/anycastGateways` `[{fabricId, virtualNetworkName, ipPoolName, trafficType:"DATA", isCriticalPool:false, isLayer2FloodingEnabled:false, isWirelessPool:false, isIpDirectedBroadcast:false, isIntraSubnetRoutingEnabled:false, isMultipleIpToMacAddresses:false, autoGenerateVlanName:true}]` | note the auto `vlanName` (e.g. `172_16_10_0-CAMPUS_VN`) |
| 10 | **Static host onboarding** | `POST /sda/portAssignments` `[{fabricId, networkDeviceId:<edge>, interfaceName, connectedDeviceType:"USER_DEVICE", dataVlanName:<from #9>, authenticateTemplateName:"No Authentication"}]` | assigns the edge access port to the VN |

> **GOTCHA — `NCSO20148 "LISP configuration is already present on device … Remove the
> LISP configuration and retry"`** when adding a fabric role. Cause: CatC's *cached*
> config for the device is stale (collected while the device still had manual LISP).
> Remove the manual LISP on the device, then **`PUT /network-device/sync?forceSync=true`
> `[deviceIds]`** and wait for `collectionStatus:Managed` before retrying — CatC then
> sees the clean config.

**Verify** (same as the [CLI module](cli-provisioning.md)): edge `show lisp session`
(established to the CP); CP `show lisp site` (host `/32` registered); edge
`show device-tracking database` (host REACHABLE on the access port); host → anycast
gateway ping. Border L3 handoff (`/sda/fabricDevices/layer3Handoffs/ipTransits`) for
external reachability is the documented next layer.

### Original blocked flow (pre-install, for reference)

Before the SD Access app was installed, step 3 failed immediately:

### Step 4 request body (the exact shape — validated against the schema)

`POST /dna/intent/api/v1/sda/fabricSites` (body is a 1-element array):
```json
[{
  "siteId": "<Fabric-Bldg site id>",
  "authenticationProfileName": "No Authentication",
  "isPubSubEnabled": true
}]
```
- `authenticationProfileName` enum: `No Authentication` | `Low Impact` |
  `Open Authentication` | `Closed Authentication`. **"No Authentication" is the
  ISE-less profile.**
- `isPubSubEnabled` is **required** (omitting it 400s with "request body is invalid").

### The failure

Both the modern endpoint above **and** the legacy
`POST /dna/intent/api/v1/business/sda/fabric-site` return, on task poll:
```
errorCode:     NCSP11008
failureReason: NCSP11008: Package required to process the request was not found.
               Additional info for support: No application found for type
               'ConnectivityDomain' and qualifier 'null'.
```
`catc_fabric_sites` stays empty (nothing partial is created). The SDA package shows
*installed* in `catc_version` (`sda:2.739.65146`) and SDA **read** APIs respond — but
the fabric-write/provisioning application ("ConnectivityDomain") isn't running.

### Step 5 (for when provisioning works) — roles

`POST /dna/intent/api/v1/sda/fabricDevices`, one element per device:
```json
[
  {"networkDeviceId": "<BORDER-CP id>", "fabricId": "<fabricId>",
   "deviceRoles": ["CONTROL_PLANE_NODE", "BORDER_NODE"],
   "borderDeviceSettings": { "borderTypes": ["LAYER_3"], "layer3Settings": { ... } }},
  {"networkDeviceId": "<EDGE1 id>", "fabricId": "<fabricId>",
   "deviceRoles": ["EDGE_NODE"]}
]
```
`deviceRoles` enum: `CONTROL_PLANE_NODE` | `EDGE_NODE` | `BORDER_NODE` |
`WIRELESS_CONTROLLER_NODE`.

## Enabling SD-Access

> **✅ RESOLVED 2026-07-16 — full walkthrough in
> [`enable-sda-service.md`](enable-sda-service.md).** Root cause: the **SD Access
> application was simply not installed**. Installing it (System → Software
> Management, ~44 min) makes `NCSP11008` disappear and fabric provisioning work. The
> *"Resource reservation check failed"* console banner on this dCloud box was a **red
> herring** — the install completed fine despite it. The text below is the original
> diagnosis; treat the "resources / form factor" angle as **not** the cause here.

`NCSP11008 / "No application found for type 'ConnectivityDomain'"` is a
**service-availability** error, not a payload problem. SD-Access provisioning in
Catalyst Center is handled by a set of maglev microservices (spf-service-manager /
`spf-serv`, spf-device-manager, network-orchestration / `orch-eng`, network-design,
network-programmer) that exchange work over RabbitMQ. NCSP11008 means the
provisioning engine (`ncp`) **can't find a running application registered to handle
the `ConnectivityDomain` (fabric) object** — the SDA service stack isn't
deployed/running/registered on this box.

**What we confirmed here (Catalyst Center 3.2.2, virtual):**
- The `sda` package **is installed** (`catc_version` / `dnac-packages` →
  `sda:2.739.65146`, plus `ise-bridge`, `group-based-policy-analytics`).
- SDA **read** APIs work (`catc_fabric_sites` returns `[]`); SDA **writes** fail with
  NCSP11008. → *installed ≠ running.*
- Service/pod status is **not exposed over REST** (`/api/system/v1/maglev/...` →
  404); it has to be checked from the appliance CLI.

**What's needed to enable it (appliance-side — the API/lab is not the problem):**

1. **Install AND run the SD-Access application.** GUI **System → Software
   Management**: confirm SD-Access (and its dependencies — Network Controller
   Platform, Automation-Base) are installed/activated. Installed-but-not-running is
   the failure mode here.
2. **Adequate resources / supported form factor.** SD-Access only runs on a
   properly-sized Catalyst Center node; a minimal ESXi Virtual Appliance or an
   undersized/lab node can carry the package but never bring the SDA service stack
   up. This is the most likely root cause on a lab/virtual box.
3. **Verify + restart the services from the appliance CLI** (definitive step — needs
   `maglev` SSH, not the REST user):
   - `magctl appstack status` — find SDA/spf/network-orchestration/network-design/
     network-programmer pods that are **not Running** (Pending / CrashLoopBackOff /
     absent).
   - `magctl service logs -rf spf-service-manager` (and the other SDA services) for
     the reason (usually insufficient resources).
   - `magctl service restart -d <service>` to bounce a stuck service; fix resources
     if that's the cause. Re-check the `sda` package via GUI Software Management or
     `maglev catalog`.
4. **ISE is NOT required** to create a fabric or do static/No-Auth onboarding — ISE
   only adds dynamic auth / SGT. So ISE integration is not the blocker for
   fabric-site creation.

**Bottom line:** the fix lives on the Catalyst Center appliance (run/resource the SDA
services), not in the request. On a virtual/lab Catalyst Center where the SDA stack
can't run, provision the fabric via the [CLI module](cli-provisioning.md) (validated
working) and keep this CatC path documented for a properly-resourced appliance.

Refs: [Cisco SD-Access Provisioning Workflow & Troubleshooting Guide](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/dna-center/tech_notes/b_sda-provisioning-workflow-and-troubleshooting-guide.html)
· [Catalyst Center SD-Access LISP Fabric provisioning (User Guide 2.3.7)](https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/2-3-7/user_guide/b_cisco_catalyst_center_user_guide_237/b_cisco_dna_center_ug_2_3_7_chapter_01110.html).
