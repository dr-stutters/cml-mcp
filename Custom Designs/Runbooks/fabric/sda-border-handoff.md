---
id: fabric/sda-border-handoff
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.overlay]
provides: [fabric.handoff]
params: [border.bgp]
est: 15m
---

# fabric/sda-border-handoff

> Border external handoff (VRF-lite/BGP) toward the fusion.

## Preflight — assert `requires`
- [ ] `fabric.overlay`

## Steps (validated live on cat9000v-uadp 2026-07-18 — [[sda-fabric-cli-cml]])
1. **Move the Border↔FUSION p2p link into the VN VRF** — put the border handoff port (e.g. `Gi1/0/2`,
   `10.1.24.1/30`) into `vrf CAMPUS_VN` as a routed port. (For a single VN a routed p2p link in-VRF is
   equivalent to the CatC-style VLAN-SVI-on-trunk and sidesteps the cat9000v "no L3 subinterface" limit.)
2. **eBGP in the VRF to FUSION** — border AS65001 ↔ fusion AS65000 over the /30; exchange the VN prefix.
3. **Default into LISP** — border acts `proxy-etr` / `proxy-itr`; the EDGE gets `use-petr` **and**
   `map-cache 0.0.0.0/0 map-request` so off-fabric traffic gets a CEF entry → negative map-reply →
   encapsulate to the proxy-ETR.
4. **Return-path** — do **NOT** use `route-export site-registrations` on a collapsed Border+CP (gotcha
   below); instead add a proxy-ITR `map-cache 172.16.10.0/24 map-request` on the border so replies from
   outside resolve to the edge RLOC and LISP-encapsulate.

## Verify — prove `provides`
Border eBGP to FUSION **Established**; fabric host → external shared services (e.g. ISE) reaches AND returns.

## Rollback
`no router bgp`; move the handoff port back to global; remove the border map-caches.

## Gotchas
- **`route-export site-registrations` on a collapsed Border+CP blackholes the RETURN path** — it installs
  the registered host `/32 → Null0` in the VRF RIB, so the forward path works (NAT proves the host reaches
  outside) but replies hitting the border are dropped. Fix: remove it + add the proxy-ITR
  `map-cache 172.16.10.0/24 map-request`. (Cost real time; banked 2026-07-18.)
- **`use-petr` alone is not enough** on the edge for off-fabric CEF — add `map-cache 0.0.0.0/0 map-request`
  (registering `0.0.0.0/0` as an EID is rejected by the site `eid-record` policy, so the map-cache path is correct).
