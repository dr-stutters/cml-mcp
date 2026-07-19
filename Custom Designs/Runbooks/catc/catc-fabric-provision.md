---
id: catc/catc-fabric-provision
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.sites]
provides: [catc.provisioned]
params: []
est: 30m
---

# catc/catc-fabric-provision

> Provision the SDA fabric via Catalyst Center (fabric site, roles, VN, anycast GW, No-Auth port). The
> CLI build ([[sda-fabric-cli-cml]]) is the fallback / A-B parity reference.

## Preflight — assert `requires`
- [ ] `catc.sites` (devices discovered + assigned to a building; underlay up on the boxes)
- [ ] **SD Access application installed on CatC** — otherwise every SDA write fails `NCSP11008`. On a fresh
      CatC, install it via **System → Software Management** (~44 min, GUI-only; see
      `Old/SD-Access Fabric/modules/enable-sda-service.md`). ISE is **not** required for No-Auth onboarding;
      authenticated/dot1x onboarding needs the pxGrid/ISE integration (`catc/catc-ise-integration`).

## Steps (proven 2026-07-16, re-validated 2026-07-19; mine `Old/SD-Access Fabric/modules/catc-provisioning.md`)
1. **Fabric site** — `POST /dna/intent/api/v1/sda/fabricSites` `[{siteId, authenticationProfileName:"No
   Authentication", isPubSubEnabled:true}]`. First returns **`NCSO20572`** (per-site telemetry prereq) →
   enable Wired Client Data Collection: `PUT /sites/{siteId}/telemetrySettings`
   `{wiredDataCollection:{enableWiredDataCollection:true}, applicationVisibility/wirelessTelemetry/snmpTraps/syslogs:null}`
   → poll task → re-POST fabricSites → success. Confirm `catc_fabric_sites`.
2. **Device roles** — `POST /sda/provisionDevices` then `POST /sda/fabricDevices`, **CONTROL_PLANE (border)
   BEFORE EDGE** (ordering matters). Border = BORDER_NODE + CONTROL_PLANE_NODE (LAYER_3, its AS,
   isDefaultExit/importExternalRoutes); edge = EDGE_NODE. Fusion stays off-fabric (external peer).
3. **IP pool + L3 VN + anycast GW** — global pool → `POST /reserve-ip-subpool/{siteId}` (**body needs
   `ipv4GlobalPool`** — the `catc_reserve_subpool` tool omits it, use `catc_api_call`) → create L3 VN +
   `PUT /sda/layer3VirtualNetworks` to anchor `fabricIds` → `POST /sda/anycastGateways` (auto vlanName).
4. **Host onboarding** — `POST /sda/portAssignments` (edge access port, USER_DEVICE, dataVlan = the VN's
   auto VLAN, `authenticateTemplateName "No Authentication"`).
5. **Host IP** — a No-Auth pool has no DHCP → give the endpoint a static IP (alpine:
   `sudo ip addr add <ip>/24 dev eth0; sudo ip route add default via <gw>`).

## Verify — prove `provides`
`catc_fabric_sites` lists the site; `catc_fabric_devices` shows the roles. On-box (command runner / pyATS):
edge↔CP LISP session **established**; host `/32` registers dynamic-EID on the CP (`show lisp instance-id
<iid> ipv4 server summary` → **Registered 1**); host → anycast gateway ping OK. Same outcome as the CLI
fabric ([[sda-fabric-cli-cml]]).

## Rollback
Delete port assignment → anycast GW → L3 VN → release subpool → remove fabric devices → delete fabric site
(child-first); or CML `wipe` → day-0.

## Gotchas
- **`NCSP11008` = SD Access app not installed** (preflight). **`NCSO20572` = installed, but per-site Wired
  Data Collection telemetry not yet enabled** (step 1). The progression `NCSP11008 → NCSO20572 → success`
  is the proof the install took effect.
- **CP role before Edge**; the fusion stays off-fabric (external eBGP peer).
- **`reserve-ip-subpool` needs `ipv4GlobalPool` in the body** — the dedicated tool omits it; use `catc_api_call`.
- **`NCSO20148` "LISP already present"** — if a device already has manual/CLI LISP, remove it, then
  `PUT /network-device/sync?forceSync=true` and wait for Managed before adding roles (CatC's cached config
  is stale). A fresh day-0-underlay-only box (like the CatC lab) avoids this — don't CLI-provision LISP first.
