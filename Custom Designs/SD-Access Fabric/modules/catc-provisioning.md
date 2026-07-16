# SD-Access Fabric — Catalyst Center provisioning (blocked on this appliance)

The intended **Catalyst Center-driven** fabric-provisioning flow via the `catc` MCP
tools + Intent API. On the appliance used here (Catalyst Center **3.2.2**, virtual)
it **fails at fabric-site creation** with `NCSP11008` — the SD-Access *provisioning*
microservice isn't functional (read APIs work; writes can't process a fabric). This
module documents the full intended flow, exactly where it blocks, and the working
pieces. See [enabling the SD-Access microservice](#enabling-sd-access) for the
follow-up investigation.

## Flow (Intent API + `catc` tools)

Discovery + site are **shared** with the [runbook](../runbook.md) Stage 3 and
**work**; the SDA-specific writes are where it blocks.

| # | Step | Tool / endpoint | Result here |
|---|---|---|---|
| 1 | Discover devices | `catc_start_discovery` | ✅ 3 Managed (needs unique serials) |
| 2 | Site hierarchy | `catc_create_area` + `catc_create_building` | ✅ `Global/SDA-Lab/Fabric-Bldg` |
| 3 | Assign to site | `catc_assign_devices_to_site` | ✅ assigned |
| 4 | **Create fabric site** | `POST /dna/intent/api/v1/sda/fabricSites` | ❌ **NCSP11008** |
| 5 | Add fabric devices + roles | `POST /dna/intent/api/v1/sda/fabricDevices` | ⛔ blocked by #4 |
| 6 | Create L3 VN | `catc_create_layer3_virtual_network` | ⛔ (needs fabric) |
| 7 | Anycast gateway | `POST /dna/intent/api/v1/sda/anycastGateways` | ⛔ blocked |
| 8 | Border L3 handoff | `POST /dna/intent/api/v1/sda/fabricDevices/layer3Handoffs/ipTransits` | ⛔ blocked |
| 9 | Static host onboarding | `POST /dna/intent/api/v1/sda/portAssignments` | ⛔ blocked |

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
