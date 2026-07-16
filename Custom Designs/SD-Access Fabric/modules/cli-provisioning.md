# SD-Access Fabric — CLI provisioning (validated working)

The **working** fabric-provisioning path: LISP **pub/sub** overlay built by hand on
the CML `cat9000v-uadp` (17.18), no ISE, no Catalyst Center provisioning. Validated
2026-07-15 — control-plane session established, host EID registered, host reaches
its anycast gateway.

Prereqs from the [runbook](../runbook.md): underlay OSPF up (BORDER-CP↔EDGE1 FULL,
loopback RLOCs reachable), devices BOOTED. RLOCs: BORDER-CP `10.1.0.2`, EDGE1
`10.1.0.3`. VN `CAMPUS_VN`, instance-id `4099`, anycast `172.16.10.1/24`, LISP key
`cisco123`.

> **Two non-obvious unlocks** (both cost real debugging time):
> 1. **`locator default-set <name>`** under `router lisp` is REQUIRED. Without it the
>    map-server accepts config but opens **no socket** (`show ip sockets` has nothing
>    on 4342; `show lisp session` = "Down (never)"). It is the line that makes the CP
>    listen. (CML cat9000v *can* be a LISP control-plane node — this was the missing
>    piece, not a platform limit.)
> 2. **Pub/sub syntax.** This image advertises `Capability: Publish-Subscribe`
>    (`show lisp`). The map-server/map-resolver **role** is enabled inside the
>    top-level **`service ipv4`** block as bare `map-server` / `map-resolver` — the
>    legacy `ipv4 map-server` returns `% Invalid input`.

## 1. Border + Control-Plane node (BORDER-CP) — LISP Map-Server / Map-Resolver

```
vrf definition CAMPUS_VN
 rd 1:4099
 address-family ipv4
  route-target export 1:4099
  route-target import 1:4099
 exit-address-family
!
router lisp
 locator-table default
 locator-set RLOC_BORDER
  IPv4-interface Loopback0 priority 10 weight 10
  exit-locator-set
 locator default-set RLOC_BORDER          ! <-- REQUIRED (see unlock #1)
 !
 service ipv4                             ! <-- role enable is here (unlock #2)
  map-server
  map-resolver
  exit-service-ipv4
 !
 instance-id 4099
  service ipv4
   eid-table vrf CAMPUS_VN
   exit-service-ipv4
  exit-instance-id
 !
 site FABRIC
  authentication-key cisco123
  eid-record instance-id 4099 172.16.10.0/24 accept-more-specifics
  exit-site
 exit-router-lisp
```

Confirm the CP is listening + the site is armed:
```
show ip sockets | include 4342                 ! a LISP listener now exists
show lisp instance-id 4099 ipv4 server summary ! Site FABRIC Configured 1, Registered 0 (until edge joins)
```

## 2. Fabric Edge (EDGE1) — LISP xTR + anycast gateway

```
vrf definition CAMPUS_VN
 rd 1:4099
 address-family ipv4
  route-target export 1:4099
  route-target import 1:4099
 exit-address-family
!
vlan 10
!
interface Vlan10
 description Anycast GW CAMPUS_VN
 vrf forwarding CAMPUS_VN
 ip address 172.16.10.1 255.255.255.0
 lisp mobility CAMPUS                      ! ties the SVI to the dynamic-EID
 no shutdown
!
interface GigabitEthernet1/0/3
 switchport mode access
 switchport access vlan 10
 no shutdown
!
router lisp
 locator-table default
 locator-set RLOC_EDGE
  IPv4-interface Loopback0 priority 10 weight 10
  exit-locator-set
 locator default-set RLOC_EDGE            ! <-- REQUIRED
 !
 service ipv4
  itr map-resolver 10.1.0.2
  etr map-server 10.1.0.2 key cisco123
  itr
  etr
  exit-service-ipv4
 !
 instance-id 4099
  dynamic-eid CAMPUS
   database-mapping 172.16.10.0/24 locator-set RLOC_EDGE
   exit-dynamic-eid
  service ipv4
   eid-table vrf CAMPUS_VN
   exit-service-ipv4
  exit-instance-id
 exit-router-lisp
```

Confirm the session establishes:
```
show lisp session          ! peer 10.1.0.2:4342 Up (may take a few seconds)
```

## 3. Static host onboarding (HOST1, alpine)

The console user is unprivileged — **`sudo`** is required:
```
sudo ip addr add 172.16.10.10/24 dev eth0
sudo ip link set eth0 up
sudo ip route add default via 172.16.10.1
ping -c 4 172.16.10.1                       ! reaches the anycast gateway
```
The gateway ping makes the edge see the host; `lisp mobility` detects it and the
edge registers `172.16.10.10/32` to the map-server.

## 4. Verify (the whole control-plane chain)

```
! EDGE1 — host detected + EID in local database
show device-tracking database               ! 172.16.10.10 on Gi1/0/3, REACHABLE
show lisp instance-id 4099 ipv4 database     ! 172.16.10.10/32 dynamic-eid CAMPUS

! BORDER-CP — EID registered to the map-server
show lisp session                            ! established 1 (peer 10.1.0.3 Up)
show lisp instance-id 4099 ipv4 server summary        ! Registered 1
show lisp instance-id 4099 ipv4 server 172.16.10.10/32 ! State complete, ETR 10.1.0.3
```

Persist: `write memory` on BORDER-CP + EDGE1 (survives reload; a CML *wipe* still
reverts to day-0). HOST1's IP is runtime-only — re-apply the `sudo ip ...` lines
after a HOST1 reboot.

## Next layer — border handoff (external reachability, not yet validated live)

The fabric above is self-contained (host ↔ anycast gateway ↔ registered EID). To let
the host reach **outside** the fabric (FUSION-R1 / shared services), add on BORDER-CP:
- a **LISP border**: `instance-id 4099 / service ipv4` → `route-import database bgp
  65001 locator-set RLOC_BORDER` + `route-export` and proxy behaviour, plus a
  default map-cache so unknown EIDs are proxied;
- **eBGP** in `vrf CAMPUS_VN` to FUSION-R1 over the `10.1.24.0/30` handoff (fabric AS
  65001 ↔ fusion AS 65100), redistributing the fabric EID space.

This exercises the VXLAN **data plane** edge→border, whose fidelity in the CML
cat9000v simulation is unverified — treat as a documented next step.
