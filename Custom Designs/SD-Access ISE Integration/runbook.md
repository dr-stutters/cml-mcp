# SD-Access + ISE + AD Integration — end-to-end runbook

Turns the CatC-provisioned **[SD-Access Fabric](../SD-Access%20Fabric/runbook.md)** (No-Auth
static onboarding) into a **full identity-driven fabric**: a fresh **Cisco ISE 3.5**
joined to **Active Directory** (`mitchcloud.lab`), integrated with **Catalyst Center**
(pxGrid + ERS, all certs re-issued from the AD **MitchcloudCA**), doing **802.1X + MAB
(Closed Authentication)** for fabric endpoints, with **TrustSec** SGTs + SGACLs. Validated
live **2026-07-16** on CML `cat9000v-uadp` 17.18 — both auth paths land the correct SGT and
the SGACL matrix is programmed onto the fabric edge.

> **Orchestration:** the main session fans out per phase to **ise-engineer** (ISE + AD-side
> + NAD 802.1X), **windows-engineer** (AD/DNS/CA on the DC), **catalyst-center-engineer**
> (CatC↔ISE, site AAA, fabric auth template), and **catalyst-engineer** (device verify).
> Much of the ISE REST work uses `curl` against ERS/OpenAPI because the MCP body-as-string
> params get JSON-coerced to dicts (a wrapper quirk) — the phases note where.

## What it builds (on top of the SD-Access Fabric)

```
  mitchcloud.lab AD/DNS/AD CS          Catalyst Center 198.18.128.5
  DC01 198.18.130.11                    (ISE = auth server, ACTIVE)
  (MitchcloudCA Enterprise Root)              │ ERS + pxGrid (MitchcloudCA trust)
        │ AD join (PEAP/AD)                    │
        ▼                                       ▼
   ISE 3.5  198.18.134.35  ◀── RADIUS (1812/1813, secret SdaIseRadius2026) ──┐
   (Admin/EAP/pxGrid certs = MitchcloudCA, CN=ise.mitchcloud.lab)            │ from global-table Lo0
        ▲ shared-services static route via FUSION                            │
        │                                                                    │
   FUSION-R1 .71 ── BORDER-CP(.72, CP) ══ EDGE1(.73, Edge) ── Gi1/0/3 ── HOST1 (alpine)
                    underlay OSPF, RADIUS source = Lo0 (global table)   Closed Auth:
                                                                        • MAB → SGT IoT(100)
   VN CAMPUS_VN (LISP inst 4099, anycast 172.16.10.1/24 VLAN 1021)     • 802.1X PEAP as alice
                                                                          (AD Employees)→SGT 4
```

## Prerequisites

- The **[SD-Access Fabric](../SD-Access%20Fabric/runbook.md)** built & CatC-provisioned
  (fabric site, CP/Edge roles, `CAMPUS_VN`, anycast GW, No-Auth port on EDGE1 Gi1/0/3).
- **ISE 3.5** on the /18 (`198.18.134.35`), reachable; `ise35` MCP creds current
  (`ISE_*` in the shared `../.env`). ERS + OpenAPI + pxGrid enabled (fresh ISE has ERS/pxGrid off).
- **`mitchcloud.lab`** DC (`DC01 = 198.18.130.11`): AD DS + DNS + **AD CS Enterprise Root
  `Mitchcloud-Lab-Root-CA`**; `windows` MCP (`WINRM_*`).
- **Catalyst Center** (`198.18.128.5`, SD Access app installed); `catc` MCP (`CATC_*`).
- Lab values: RADIUS shared secret `SdaIseRadius2026`; AD demo users `alice`/`bob` pw
  `Cisco12345!`.

---

## Stage 1 — Fabric→ISE RADIUS reachability  → catalyst-engineer

The crux: fabric edge/border **source RADIUS from the global table**, but the fabric nodes
reach the 198.18.x network (where ISE lives) only via **Mgmt-vrf**. Fix = give the *global*
table a path to the shared-services subnet:

- Static routes on the fabric nodes' global table to `198.18.134.0/24` via the border→fusion
  path (BORDER-CP `ip route 198.18.134.0 255.255.255.0 10.1.24.2`; EDGE1 via 10.1.23.1;
  FUSION-R1 back-route `10.1.0.0/16` toward the border).
- One static route on ISE for the fabric loopbacks: (ISE CLI) `ip route 10.1.0.0 255.255.0.0
  gateway 198.18.128.71` (FUSION, which is L2-adjacent to ISE on the /18). **Chosen over NAT**
  so CatC can register the fabric NADs in ISE with their real loopback IPs.
- **Verify:** EDGE1 `ping ip 198.18.134.35 source Loopback0` succeeds; later `show aaa
  servers` shows the ISE RADIUS server **UP**.

## Stage 2 — ISE base + MitchcloudCA system certs  → ise-engineer + windows-engineer

DNS/NTP on ISE → DC `.11`. Enable **pxGrid** persona (GUI: Administration → System →
Deployment → the node → enable pxGrid; the OpenAPI only exposes pxGrid *Direct/Cloud*, not
persona enable), **ERS** (both surfaces), Policy Service. Then re-issue ISE's system certs
from **MitchcloudCA** (per the "use the MitchcloudCA" directive) — see
[modules/mitchcloudca-certs.md](modules/mitchcloudca-certs.md):

- Import MitchcloudCA root into **CatC** trust (`POST /dna/intent/api/v1/trustedCertificates/import`,
  multipart) and confirm it's in ISE's trusted store.
- ISE CSR (`used_for MULTI-USE`, `CN=ise.mitchcloud.lab`, SAN, a unique OU to dodge the
  "subject matches existing cert" 409) → `win_sign_csr` (WebServer template) → bind to
  **Admin + EAP** (`POST /api/v1/certs/signed-certificate/bind`). **⚠ rebinding Admin
  restarts ISE (~5 min).**
- A **second** CSR bound to **pxGrid** — because this dCloud ISE was renamed
  `ise.demo.dcloud.cisco.com → ise.mitchcloud.lab` but its internal-CA pxGrid cert kept the
  **old CN**, which CatC rejects (`FQDN…doesn't match CN`). Re-issue pxGrid from MitchcloudCA
  with the right CN (serverAuth-only is accepted for the pxGrid controller cert).

## Stage 3 — ISE ↔ Active Directory  → ise-engineer + windows-engineer

- **DC side:** AD groups `Employees`/`Contractors`/`IoT` + users `alice`→Employees,
  `bob`→Contractors (`win_create_ad_group` / `win_create_ad_user` / `win_add_group_member`).
- **ISE side** (ERS via `curl`): create the AD join point (`POST /ers/config/activedirectory`),
  **join** via `PUT /ers/config/activedirectory/{id}/joinAllNodes` with a domain-admin
  credential in `OperationAdditionalData.additionalData` (username/password) — sourced from
  `.env`, not printed. **Confirm the join** independently with `win_list_ad_computers`
  (ISE's computer object appears). **Gotcha:** ISE 3.5 ERS `getGroups` runtime 502s on this
  build — instead add groups by SID via `PUT …/addGroups` (pull SIDs from AD:
  `Get-ADGroup … SID`).
- **Identity source sequence** `AD_Internal_Seq` (`POST /ers/config/idstoresequence`, wrapper
  `IdStoreSequence`, needs `certificateAuthenticationProfile: Preloaded_Certificate_Profile`):
  idstore `mitchcloud` then `Internal Users`.

## Stage 4 — Catalyst Center ↔ ISE  → catalyst-center-engineer + ise-engineer

Register ISE as the auth/policy server (`POST /dna/intent/api/v1/authentication-policy-servers`):
`isIseEnabled:true`, `pxgridEnabled:true`, `useDnacCertForPxgrid:false`, RADIUS secret,
`ciscoIseDtos` with ERS creds. **Include the top-level `port:49`** (TACACS+ port) or it 406s
`NCND00041 port=0`. Poll → the server object's `state` goes **INPROGRESS → ACTIVE** and both
roles (PRIMARY/ERS + PXGRID) reach `trustState: TRUSTED` **because CatC now trusts
MitchcloudCA and every ISE cert chains to it**. If a prior attempt is stuck/FAILED, DELETE it
and re-add. See [modules/catc-ise-integration.md](modules/catc-ise-integration.md).
(NADs are *not* pushed yet — that happens in Stage 6.)

## Stage 5 — TrustSec policy (SGTs + SGACLs + authZ)  → ise-engineer

Manage TrustSec **directly in ISE** (source of truth; CatC reads via pxGrid). ERS/OpenAPI via
`curl` — see [modules/trustsec-policy.md](modules/trustsec-policy.md):

- **SGTs:** Employees(4), Contractors(5) exist by default; create **IoT(100)** +
  **Shared_Services(200)** (`ise_create_sgt`).
- **SGACL:** custom `SDA_Web_Permit` (`permit icmp / tcp dst 443 / tcp dst 80 / deny ip`) +
  defaults (`Deny_IP_Log`).
- **Egress matrix** (`POST /ers/config/egressmatrixcell`): Employees→Shared = `SDA_Web_Permit`;
  Contractors→Shared = `Deny_IP_Log`; IoT→Shared = `Deny_IP_Log`.
- **Policy set `SDA_Wired`** (`POST /api/v1/policy/network-access/policy-set`, condition =
  `ConditionOrBlock` of `Wired_802.1X` + `Wired_MAB` references):
  - **authN** default rule → identity source `AD_Internal_Seq`, **`ifUserNotFound=CONTINUE`**
    (so dot1x hits AD and MAB falls through to authZ).
  - **authZ** rules (each `profile:["PermitAccess"]` + `securityGroup`): Employees AD-group →
    Employees; Contractors AD-group → Contractors (condition dict = the join-point name
    `mitchcloud`, attr `ExternalGroups`, value `mitchcloud.lab/Users/<Group>`); `Wired_MAB` →
    IoT; **Default → DenyAccess** (Closed Auth).

## Stage 6 — Switch fabric to Closed Authentication  → catalyst-center-engineer

See [modules/closed-auth.md](modules/closed-auth.md):

1. **Assign ISE as the site's Client AAA** (`PUT /dna/intent/api/v1/sites/{id}/aaaSettings`;
   both `aaaNetwork`+`aaaClient` are required, each `serverType:ISE, protocol:RADIUS, pan +
   primaryServerIp = ISE`). **⚠ DEVICE-ADMIN LOCKOUT:** the required **Network** AAA makes vty
   login RADIUS-first (`dnac-network-radius-group local`); once ISE RADIUS is reachable it
   **rejects** CatC's `cisco/cisco` (no device-admin policy) and IOS won't fall back to local
   on a *reject* → CatC loses SSH (`NCNP10200`). **Fix:** device admin stays **local** —
   on the switches `aaa authentication login VTY_authen local group dnac-network-radius-group`
   (+ the exec-authz list local-first). The `aaaSettings` PUT is **merge-only** (null/omit
   won't clear `aaaNetwork`), so enforce local on-box and don't re-provision.
2. **Fabric site + host port → Closed Authentication**
   (`PUT /sda/fabricSites` + `PUT /sda/portAssignments`). The port change 400s `NCSO20804`
   until you **re-provision** the device (`PUT /sda/provisionDevices`) so it picks up the
   client-auth settings — this is also when CatC **registers the fabric switches as NADs in
   ISE** (all 3 appear).
3. **Bind the closed-auth template** to the host port — CatC records the intent but doesn't
   render the per-port `source template DefaultWiredDot1xClosedAuth` on the cat9000v, so apply
   it via CLI (the whole closed-auth stack — policy-maps `PMAP_*`, template, `aaa … dnac-*`
   groups — *is* pushed; only the interface binding is missing).

## Stage 7 — Endpoints + validation  → ise-engineer / catalyst-engineer

See [modules/endpoints-and-supplicant.md](modules/endpoints-and-supplicant.md):

- **MAB (no supplicant):** bounce EDGE1 Gi1/0/3; HOST1 → dot1x timeout → **MAB** → ISE
  `IoT_MAB` → PermitAccess + **SGT IoT(100)**. Speed the dot1x fallthrough with
  `dot1x timeout tx-period 5` + `dot1x max-reauth-req 1` on the port.
- **802.1X PEAP as alice:** the alpine HOST1 has no `wpa_supplicant` and the fabric has no
  internet. **Install it via the external connector:** repoint HOST1 eth0 from EDGE1 to the
  **MGMT-SW/EXT** bridge, give it `198.18.128.201/18` + DNS `8.8.8.8`, `apk add
  wpa_supplicant`, then repoint eth0 back to EDGE1 and reset the fabric IP. Run
  `wpa_supplicant -D wired -i eth0 -c wired.conf -B` (key_mgmt=IEEE8021X, eap=PEAP,
  identity="alice", password, phase2=MSCHAPV2, ap_scan=0, eapol_flags=0) → **EAP SUCCESS**,
  ISE `SDA_Wired`/`Employees_SGT` → **SGT Employees(4)**.

### Verify

| Check | Where | Expect |
|---|---|---|
| RADIUS to ISE up | EDGE1 `show aaa servers` | State **UP** |
| Fabric NADs | `ise_list_network_devices` | BORDER-CP / EDGE1 / FUSION-R1 |
| MAB result | EDGE1 `show access-session int Gi1/0/3 det` / `ise_session_by_mac` | mab, Authorized, **SGT 100**, rule `IoT_MAB` |
| 802.1X result | same | dot1x, `alice`, **SGT 4**, PEAP(EAP-MSCHAPv2), store `mitchcloud`, rule `Employees_SGT` |
| Enforcement (control-plane) | EDGE1 `show cts role-based permissions` (after `cts role-based enforcement` + a dest SGT-200 binding) | `4→200 SDA_Web_Permit`, `5→200 Deny_IP_Log`, `100→200 Deny_IP_Log` |

## Enforcement — control-plane vs data-plane (CML limit)

The SGACL matrix **downloads and programs** onto the fabric edge (verify above). A **live
packet-drop between two hosts is not reproducible on virtual cat9000v**: (a) statically-placed
hosts in the fabric VLAN get no connectivity (SDA hosts must onboard via LISP/auth); (b)
fabric hosts' SGTs ride **inline in VXLAN**, not as local `sgt-map`/`device-tracking` IP-SGT
bindings, so IP-based SGACL counters don't light up; (c) a second added alpine's MAB frames
never reached the virtual switch. **Assert enforcement at the control plane** and treat the
data-plane drop as a documented CML fidelity limit.

## Teardown

- Endpoint: kill `wpa_supplicant` on HOST1; the fabric config `write mem`'d survives a reload
  (a CML *wipe* reverts to `topology.yaml`).
- ISE: delete policy set `SDA_Wired`, the egress cells + `SDA_Web_Permit`, SGTs IoT/Shared,
  `AD_Internal_Seq`, the AD join point (leave AD to reuse); CatC: DELETE the ISE
  authentication-policy-server; site AAA back to none (GUI — the API merge won't clear it).
- Base fabric teardown: see the [SD-Access Fabric runbook](../SD-Access%20Fabric/runbook.md).

## Gotchas (consolidated)

1. **Fabric global-table → ISE reachability** needs global static routes + one ISE route via
   FUSION (Stage 1). RADIUS sources from Lo0 in the *global* table, not Mgmt-vrf.
2. **dCloud ISE renamed** → its internal pxGrid cert has the **old CN** → CatC `FQDN mismatch`.
   Re-issue Admin/EAP **and** pxGrid from MitchcloudCA with `CN=ise.mitchcloud.lab` (Stage 2).
3. **`authentication-policy-servers` needs top-level `port:49`** (Stage 4).
4. **ISE 3.5 ERS `getGroups` 502s** → add AD groups by SID via `addGroups` (Stage 3).
5. **Site AAA device-admin lockout** — Network AAA=ISE makes vty RADIUS-first; ISE rejects
   `cisco/cisco` → CatC SSH dies. Keep device admin **local** on-box: set **both**
   `aaa authentication login VTY_authen` **and** `aaa authorization exec VTY_author` local-first
   (exec-authz RADIUS-first blocks config mode → "unable to push"). `aaaSettings` PUT is
   merge-only so it can't be cleared via API; **any re-provision re-applies the RADIUS-first
   template → re-fix after** (Stage 6).
6. **`NCSO20804`** on the port auth-template change → **re-provision** the device first (Stage 6).
7. **Closed-auth per-port template not rendered** by CatC on cat9000v → bind
   `source template DefaultWiredDot1xClosedAuth` via CLI (Stage 6).
8. **UADP front-panel ports lag ~1–2 min** after a link/bounce; **added nodes need
   `refresh_testbed`** before pyATS can reach them.
9. **Alpine has no wpa_supplicant + no fabric internet** → install via the external connector
   (Stage 7). Console user is `cisco` (sudo, not root); the runtime IP+supplicant are lost on a
   plain reboot → persist via `/etc/local.d/sda-endpoint.start` (OpenRC `local`); a **wipe** loses
   the apk binary too. See [`endpoints-and-supplicant.md`](modules/endpoints-and-supplicant.md).
10. **TrustSec data-plane** enforcement is control-plane-only on virtual cat9000v (above).
11. **Border L3 handoff (B1) for the VN's external reachability** — the fabric must have a
    **`BORDER_NODE` (Layer-3)** role + IP-transit handoff; a CP-only "border" black-holes the
    return path. Retro-fitting the role needs a full fabric rebuild; CatC renders the handoff on
    cat9000v as an **SVI on a trunk**, and the fusion router does eBGP + NAT `default-originate`.
    Verified: HOST1 (alice→SGT4) → ISE/Splunk 100%. See the [SD-Access Fabric CatC module](../SD-Access%20Fabric/modules/catc-provisioning.md) steps 11–12 + `no ip ssh bulk-mode` push gotcha.

## Related

- Base: [SD-Access Fabric](../SD-Access%20Fabric/runbook.md) · reuses
  [ISE NAC Lab](../ISE%20NAC%20Lab/runbook.md), [Windows DC Foundation](../Windows%20DC%20Foundation/runbook.md).
- MCP: `ise`/`ise35`, `catc`, `windows`, `cml` · agents ise-engineer,
  catalyst-center-engineer, windows-engineer, catalyst-engineer.
- Memory: `sda-ise-integration-lab`, `sda-fabric-cli-cml`, `cat9000v-mab-radius-needs-global-table-uplink`.
- Original plan: [PLAN.md](PLAN.md).
