# Module — FTDv as the SDA fabric firewall + the live drop (roadmap "C1", Wave 6)

Register an **FMCv/FTDv** and insert the FTD **inline** for a VN's external traffic so you get
the **live permit/deny packet proof** the virtual cat9000v can't give (SGACL enforcement there
is control-plane only). Depends on **B1** (border handoff) + **B4** (the inter-VN fusion path).

## Deploy FMCv + FTDv (managed mode)
- CML nodes: `fmcv` (32 GB) + `ftdv` (8 GB), mgmt on the /18 via the MGMT-SW bridge.
  **FMCv day-0 `IPv4Mode` must be `"manual"`** (not `"static"` — static leaves the mgmt IP blank).
  FTDv day-0: `ManageLocally:"No"`, `FmcIp`, `FmcRegKey`.
- **The registration gate is the FMC 90-day eval license, not 8305.** Fresh FMC = `regStatus:
  UNREGISTERED, evalUsed:false` → device-registration/sftunnel services stay down. Start it in
  the GUI (System → Licenses → Smart Licenses → **Evaluation Mode**); then registration works
  immediately. (A `/dev/tcp :8305` probe from an ops host off the mgmt subnet is a false negative.)
- Register: `POST devices/devicerecords` `{hostName, regKey, license_caps:[MALWARE,URLFilter,
  THREAT], accessPolicy:{id:<ACP>}}` → device gets model/sw/serial, ACP assigned, no pending deploy.

## Insert the FTD inline (source-PBR on FUSION — minimal blast radius)
Route **only CAMPUS_VN external** through the FTD; leave inter-VN, underlay, and RADIUS alone.

**FTD (FMC API — all `fmc_config/v1/domain/<DOM>`; drive via curl if the MCP is on a stale IP):**
- Interfaces (`PUT physicalinterfaces/<id>`, **`mode:"NONE"`** is mandatory): `Ethernet0/1`→`inside`
  10.1.245.2/30 (to FUSION), `Ethernet0/0`→`outside` 198.18.128.82/18 (to the /18). *FMC names them
  `Ethernet0/x`, not the CML `GigabitEthernet0/x`.*
- Zones: `inside-zone`, `outside-zone` (`interfaceMode:ROUTED`).
- Static routes: `172.16.10.0/24 → 10.1.245.1` (inside), `0.0.0.0/0 → 198.18.128.1` (outside, use the
  built-in `any-ipv4` object).
- NAT (`ftdnatpolicies` + `manualnatrules`, assign to device): dynamic PAT, `originalSource:net-campus10`,
  `interfaceInTranslatedSource:true`, **`unidirectional:true`** (dynamic NAT can't be bidirectional).
- ACP rules (default action already BLOCK; **every logging rule needs `sendEventsToFMC:true`** or it
  400s): `Permit-CAMPUS-Services` (net-campus10 → ISE/DC/Splunk, ALLOW), `Deny-CAMPUS-to-CatC`
  (net-campus10 → CatC, BLOCK+log). Then `POST deployment/deploymentrequests`.

**FUSION (CLI):**
```
interface GigabitEthernet4
 ip address 10.1.245.1 255.255.255.252     ! to FTD inside
ip access-list extended CAMPUS-TO-FTD
 deny   ip 172.16.10.0 0.0.0.255 172.16.0.0 0.0.255.255   ! preserve inter-VN (don't PBR intra-fabric)
 permit ip 172.16.10.0 0.0.0.255 any                       ! divert external to the FTD
route-map PBR-CAMPUS permit 10
 match ip address CAMPUS-TO-FTD
 set ip next-hop 10.1.245.2
interface GigabitEthernet3.3001            ! the CAMPUS handoff (apply AFTER the FTD deploy)
 ip policy route-map PBR-CAMPUS
```
The PBR diverts CAMPUS→external out Gi4 to the FTD *before* FUSION's own NAT (so the FTD does NAT).
The ACL `deny` line keeps CAMPUS↔IOT on the normal fusion hairpin (B4 stays 100%).

## Verify — the live drop
- HOST1 → ISE / Splunk: **allowed** (100%); HOST1 → CatC: **dropped** (100% loss).
- FMC hit counts (`accesspolicies/<id>/operational/hitcounts?filter=deviceId:<dev>`):
  `Permit-CAMPUS-Services` +hits, **`Deny-CAMPUS-to-CatC` +hits** = the FTD is the enforcer.
- Regression: HOST1 ↔ SHARED-SVC (inter-VN) still 100% (excluded from PBR).

## Reversible
Remove `ip policy route-map PBR-CAMPUS` from Gi3.3001 → CAMPUS external instantly falls back to the
direct FUSION NAT path; the FTD/FMC config stays for the next test.
