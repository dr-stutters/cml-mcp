# Component — FTD Overlay LAN Redistribution

Get a branch **LAN** (behind a spoke FTD) advertised across the SD-WAN overlay. The
per-site pattern from the [Firewall SD-WAN runbook](../../Cisco%20Validated%20Designs/Firewall%20SD-WAN/runbook.md);
validated with one protocol each: **connected, OSPF, EIGRP, eBGP**.

## The two crux facts

1. **The auto-VPN's `router bgp 65070` is not an editable object** (bgpgeneralsettings
   / bgp read empty), **but a companion config MERGES into it.** `POST
   /routing/bgpgeneralsettings {asNumber:"65070"}` then `POST /routing/bgp` with
   `addressFamilyIPv4.redistributeProtocols` → deploy renders **one** `router bgp
   65070` carrying the auto-VPN neighbors *and* your `redistribute`. (PUT gotcha:
   strip the deprecated `maximumPaths` field or you get 500 "use ebgp/ibgp".)
2. **Community-1000 gate.** The auto-VPN neighbor OUT route-map
   (`FMC_VPN_RMAP_COMMUNITY_OUT_*`) is *permit if community 1000, deny everything
   else*. Redistributed routes carry **no** community 1000, so they're **silently
   filtered** (the spoke advertises connected-inside but not the LAN loopbacks). Fix:
   create a `RouteMap {entries:[{action:PERMIT, communityListSetting:1000}]}` and
   attach it to the `redistributeProtocols` entry's `routeMap`.

## Per-protocol recipe

- **Connected** (simplest): `distributeConnectedNetwork` in the auto-VPN already does
  it — no extra config.
- **OSPF:** `POST /routing/ospfv2routes` (process 1, area 0, area-network = the LAN
  /24; full `processConfiguration` with `administrativeDistance` + timers). Companion
  BGP redistribute type = **`RedistributeOSPF`** (`processId:"1"`, subnets:true) + the
  set-community routeMap. **Return path:** OSPF `defaultInformationOriginate`
  (`alwaysAdvertise:true`, metricType TYPE_2) so the LAN router learns a default.
  Adjacency forms fine on the **physical inside** iface (unlike OSPF-over-DVTI).
- **EIGRP:** `POST /routing/eigrproutes` (`asNumber:"100"`, `autoSummary:false`,
  network = LAN /24). Companion BGP redistribute type = **`RedistributeEIGRP`**
  (`asNumber:"100"`) + set-community routeMap. Return path = a **static default in the
  LAN router's day-0** (`ip route 0.0.0.0 0.0.0.0 <fw-inside>`).
- **eBGP:** the LAN router runs its own AS (e.g. 65100), eBGP-peers the FW, and **sets
  community 1000 itself** (route-map set community + send-community) — so no FW-side
  inbound route-map needed. FW side = a companion `/routing/bgp` **neighbor**
  (`remoteAs:65100`) that MERGES with the auto-VPN neighbors. Gotchas: the neighbor
  needs `neighborAdvanced.neighborHops.maxHopCount:1` (0 → "Invalid MaxHopCount")
  **and** the full sub-object set (neighborTimers/Routes/TransportConnectionMode/
  TransportPathMTUDiscovery) or you get a vague 400 "internal error". Return path is
  automatic (overlay iBGP routes are advertised to the eBGP LAN peer).

## Verify

`NYC-HOST → 10.<site>.100.1` (a LAN loopback) = **0% loss**; `show bgp <lan>` on the
hub shows the prefix learned with the overlay community, via both ISPs.
