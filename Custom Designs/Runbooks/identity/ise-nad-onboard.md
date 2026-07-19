---
id: identity/ise-nad-onboard
category: identity
agent: ise-engineer
human: none
requires: [ise.reachable]
provides: [ise.nads]
params: [nads, radius.secret]
est: 5m
---

# identity/ise-nad-onboard

> Add the switches/WLC as RADIUS clients (NADs) + device groups.

## Preflight — assert `requires`
- [ ] `ise.reachable`

## Steps
1. For each switch (edge / access), `ise_create_network_device` (ERS) — **IP = the switch's RADIUS *source*
   interface IP**, the shared secret (`RADIUS_SECRET` from `../.env`, or a consistent lab secret), and a
   device group. Reuse ONE secret across NADs.
2. **cat9000v: the NAD IP is the front-panel global-table (or in-band MGMT-VRF) uplink**, NOT `Gi0/0`
   (Mgmt-vrf) — RADIUS sources from the front-panel interface (see [[cat9000v-mab-radius-needs-global-table-uplink]]).

## Verify — prove `provides`
`ise_list_network_devices` lists each NAD; a MAB/dot1x session's `nas_ip_address` (via `ise_session_by_mac`)
equals the registered NAD IP.

## Rollback
`ise_delete_network_device` per NAD.

## Gotchas
- **The NAD IP MUST equal the RADIUS *source* IP** or ISE drops the request as an unknown NAD (silently).
  On the 2026-07-19 3-lab MAB build the NADs were the front-panel uplinks: L3-ACCESS-SW `.78`,
  L1-EDGE1 `.79`, L2-EDGE2 `.80` — each session's NAS-IP matched.
