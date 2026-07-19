---
id: fabric/sda-anycast-gw
category: fabric
agent: catalyst-engineer
human: none
requires: [fabric.overlay]
provides: [fabric.gateways]
params: [vns, anycast_gw]
est: 10m
---

# fabric/sda-anycast-gw

> Anycast gateway SVIs per VN/VLAN on the edges.

## Preflight — assert `requires`
- [ ] `fabric.overlay`

## Steps
1. **EDGE1 anycast SVI** — `interface Vlan10` in `vrf CAMPUS_VN`, `ip address 172.16.10.1 255.255.255.0`,
   **`lisp mobility CAMPUS`** (binds the SVI to the dynamic-EID so the edge registers attached hosts).
2. **Host access port** — the endpoint port (e.g. `Gi1/0/3`) `switchport access vlan 10`.

## Verify — prove `provides`
SVI up; EDGE1 `show device-tracking database` → host `172.16.10.10` on the access port **REACHABLE**;
host `ping 172.16.10.1` succeeds (first packet may drop during ARP / EID detect).

## Rollback
`no interface Vlan10`; return the access port to default.

## Gotchas
- **`lisp mobility CAMPUS` on the SVI** is what ties the gateway to the dynamic-EID — without it the edge
  won't register attached hosts.
