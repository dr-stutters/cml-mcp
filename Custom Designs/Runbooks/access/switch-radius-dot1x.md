---
id: access/switch-radius-dot1x
category: access
agent: ise-engineer
human: none
requires: [ise.nads, ise.policy_sets, fabric.underlay]
provides: [access.dot1x]
params: [edge.ports]
est: 15m
---

# access/switch-radius-dot1x

> cat9000v edge: 802.1X/MAB, closed-auth policy-map, RADIUS to ISE over a front-panel global source.

## Preflight — assert `requires`
- [ ] `ise.nads`
- [ ] `ise.policy_sets` (or reuse the built-in Default set for a MAB baseline)
- [ ] `fabric.underlay` (edge reachable; a **front-panel global-table (or MGMT-VRF) uplink to ISE** exists —
      for a fabric edge this is an ADDED interface, since its global table is the fabric underlay)

## Steps (proven 2026-07-19 across all 3 architectures; deeper 802.1X/CoA per [[cat9000v-mab-radius-needs-global-table-uplink]])
1. **RADIUS + AAA** — `aaa new-model`; `radius server <name>` → ISE `198.18.134.35` :1812/1813 + key;
   `aaa group server radius <grp>` with **`ip radius source-interface <front-panel global uplink>`**;
   `aaa authentication dot1x / authorization network / accounting dot1x default group <grp>`.
2. **CoA** — `aaa server radius dynamic-author` → `client 198.18.134.35 server-key …` in the **same
   VRF/table as the RADIUS source** (global here; `client <ip> vrf MGMT` if the source is in an in-band VRF).
3. **Enable + IBNS-2.0** — `dot1x system-auth-control`; device-tracking policy; `policy-map type control
   subscriber` (authenticate using mab, and/or dot1x). On the host port: `access-session host-mode
   single-host`, `access-session port-control auto`, `mab` (+ `dot1x pae authenticator` for 802.1X),
   `service-policy … <the policy-map>`.
4. `write memory`.

## Verify — prove `provides`
`show access-session interface <port> details` → the endpoint **Authorized**, method **mab** (or dot1x)
Authc Success; ISE `ise_session_by_mac` → passed, NAS-IP = this NAD, authZ profile returned.

## Rollback
Remove the `service-policy`/`access-session`/`mab` from the port + the `aaa`/`radius` blocks (note the IBNS
conversion below is not cleanly reversible — CML `wipe` → day-0 is the clean reset).

## Gotchas
- **cat9000v RADIUS MUST source from a front-panel (data-plane) interface**, NOT the OOB `Gi0/0` Mgmt-vrf —
  SMD/sessmgrd can't egress the Mgmt-vrf (IOSd `test aaa` works but MAB times out with zero responses). The
  tell: IOSd-works / SMD-times-out. [[cat9000v-mab-radius-needs-global-table-uplink]].
- **CoA `dynamic-author` client must be in the SAME VRF/table as the RADIUS source**, or CoA is silently dropped.
- **On a fabric edge:** add MAB **additively** — the host port already carries the fabric VLAN + dynamic-EID;
  don't strip it. MAB then front-ends fabric onboarding (host authorizes → placed in the anycast VN/VRF).
- **On a CatC-managed edge (lab 2):** CLI MAB is **out-of-band drift** — CatC marks it `RUNNING_CONFIG` +
  `NETWORK_SETTINGS` **NON_COMPLIANT** (remediation-supported → a Sync would REVERT it). Do NAC via CatC's
  intent (port auth template + pxGrid), or accept it's transient. (Confirmed 2026-07-19.)
- Applying the IBNS `policy-map type control subscriber` **irreversibly** converts the switch to new-style
  CPL auth (prompts once). **iosvl2 / ioll2-xe can't do MAB at all** — cat9000v only.
