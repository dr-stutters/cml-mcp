# SD-Access Fabric — Fabric-in-a-Box variant (roadmap)

**Status:** roadmap — designed, not yet validated. The smallest possible SD-Access
footprint: a **single `cat9000v`** acting as collapsed **Control-Plane + Border +
Edge** (FiaB), with the endpoint attached directly to it.

## Why

Fabric-in-a-Box is Cisco's small-site SD-Access design (one switch is CP + border +
edge). In CML it's the cheapest way to demonstrate a fabric — one cat9000v + one
host — and it removes the underlay/LISP-session-between-nodes variable (the xTR and
MS/MR are the same box).

## Topology

```
   ── mgmt /18 (System Bridge) ──   [+ optional FUSION for external handoff]
            │ Gi0/0 (Mgmt-vrf)
      ┌─────┴───────┐
      │    FIAB      │  cat9000v-uadp = CP + Border + Edge (collapsed)
      │ CP+Border+Edge│
      └──────┬───────┘
          Gi1/0/3 (access VLAN10)
          ┌───┴──┐
          │ HOST1│ 172.16.10.10/24, gw 172.16.10.1 (anycast, local)
          └──────┘
```

- **FIAB** (`cat9000v-uadp`, unique serial) — one node with the full base config
  from the [CLI module](cli-provisioning.md) **merged onto itself**: locator-set +
  `locator default-set`, `service ipv4` {`map-server`,`map-resolver`,`itr`,`etr`,
  `itr map-resolver <self-loopback>`, `etr map-server <self-loopback> key ...`},
  `instance-id 4099` with the `dynamic-eid` + `eid-table vrf CAMPUS_VN`, the `site`
  record, and the anycast `Vlan10` with `lisp mobility`.
- The map-server and xTR are the **same box**, so the `map-resolver`/`map-server`
  targets are its **own** Loopback0.
- Optional FUSION for external reachability (border handoff); omit for a pure
  intra-fabric proof.

## Build

A compression of the base runbook: Stage 1 (single switch + host), Stage 2 (loopback
RLOC + mgmt; no inter-node underlay needed), Stage 4 (the merged CLI config), Stage 5
(host onboarding + verify). Discovery/site (Stage 3) optional — CatC provisioning is
blocked here anyway.

## Open questions to validate

- LISP self-registration (xTR registering to a co-located MS on the same box) — the
  `locator default-set` unlock still applies; confirm the session/registration form
  loopback-to-loopback.
- Whether the single-box collapse needs any role-specific extra config vs. the split
  CP/edge in the base build.

## Provisioning

[CLI](cli-provisioning.md) (expected to work — it's the base config collapsed) or
[Catalyst Center](catc-provisioning.md) (blocked by NCSP11008).
