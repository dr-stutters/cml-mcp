# Module — Switch the fabric to Closed Authentication

Flip host onboarding from No-Auth to Closed Auth via CatC, register the fabric NADs in ISE, and
avoid the device-admin lockout. All `/dna/intent/api/v1/...` via a CatC token.

## 1. ISE as the site AAA server
```bash
PUT /sites/{siteId}/aaaSettings
{"aaaNetwork":{"serverType":"ISE","protocol":"RADIUS","pan":"198.18.134.35","primaryServerIp":"198.18.134.35"},
 "aaaClient":  {"serverType":"ISE","protocol":"RADIUS","pan":"198.18.134.35","primaryServerIp":"198.18.134.35"}}
```
Both blocks are required (empty/`null` → `NCND00027 cannot be empty`). It's the **Client** AAA
that drives host 802.1X, but the **Network** (device-admin) AAA is what bites you:

> ### ⚠ Device-admin lockout — the big gotcha
> Network AAA=ISE makes the switch vty login RADIUS-first
> (`aaa authentication login VTY_authen group dnac-network-radius-group local`). Once ISE
> RADIUS is reachable it **rejects** CatC's `cisco/cisco` (ISE has no device-admin policy) and
> IOS **won't fall back to local on a reject** → CatC loses SSH (`NCNP10200`) and every
> re-provision fails. Early steps only worked because ISE RADIUS wasn't reachable yet (fell
> back to local).
>
> **Fix — keep device admin local on the switches** (via console, EDGE1 + BORDER-CP):
> ```
> aaa authentication login VTY_authen local group dnac-network-radius-group
> aaa authorization exec  VTY_author  local group dnac-network-radius-group if-authenticated
> ```
> The CatC `aaaSettings` PUT is **merge-only** (omitting/`null`-ing `aaaNetwork` does NOT clear
> it), so you can't remove Network AAA via API — enforce local on-box and **don't re-provision**
> (a re-provision re-pushes the RADIUS-first vty). Confirm CatC can log in again with
> `catc_run_command` before continuing.

## 2. Fabric site + host port → Closed Authentication
```bash
PUT /sda/fabricSites      [{"id":"<fabricId>","siteId":"<site>","authenticationProfileName":"Closed Authentication","isPubSubEnabled":true}]
PUT /sda/portAssignments  [{"id":"<pa>","fabricId":"<f>","networkDeviceId":"<edge>","interfaceName":"GigabitEthernet1/0/3",
                            "connectedDeviceType":"USER_DEVICE","dataVlanName":"172_16_10_0-CAMPUS_VN",
                            "authenticateTemplateName":"Closed Authentication"}]
```
The port change 400s **`NCSO20804` "device missing Client Authentication settings"** until you
**re-provision** the device:
```bash
GET /sda/provisionDevices?fabricId=<f>          # → provision id per device
PUT /sda/provisionDevices  [{"id":"<prov>","networkDeviceId":"<edge>","siteId":"<site>"}]
```
Re-provision **pushes the RADIUS/dot1x config** (`radius server dnac-radius_198.18.134.35`,
`aaa … group dnac-client-radius-group`, `dot1x system-auth-control`, the `PMAP_*` policy-maps
and the `DefaultWiredDot1xClosedAuth` template) **and registers the fabric switches as NADs in
ISE** (`ise_list_network_devices` → all 3). Verify RADIUS reachability: EDGE1 `show aaa servers`
→ **UP** (sourced from Lo0 in the global table — Stage 1).

## 3. Bind the closed-auth template on the host port (CLI)
CatC records `authenticateTemplateName: Closed Authentication` but doesn't render the per-port
binding on the cat9000v (the template/policy-maps/AAA *are* pushed). Apply via console:
```
interface GigabitEthernet1/0/3
 source template DefaultWiredDot1xClosedAuth
```
`show access-session interface Gi1/0/3` then shows the closed-auth state machine engaging
(`PMAP_DefaultWiredDot1xClosedAuth_1X_MAB`). Bounce the port (`shut`/`no shut`) to start a
session if the port was already up when you bound the template.
