# Fabric — SD-Access

Underlay, LISP pub/sub overlay, anycast gateways, border handoff, fusion VRF-leak, and host onboarding. Driven by **catalyst-engineer** (CLI path; CatC provisioning is the catc/ category).

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`sda-underlay`](sda-underlay.md) | none | fabric.underlay | IGP underlay, loopbacks, p2p links across the fabric nodes. |
| [`sda-lisp-overlay`](sda-lisp-overlay.md) | none | fabric.overlay | LISP + pub/sub; CP/border/edge roles; map-server/resolver. |
| [`sda-anycast-gw`](sda-anycast-gw.md) | none | fabric.gateways | Anycast gateway SVIs per VN/VLAN on the edges. |
| [`sda-border-handoff`](sda-border-handoff.md) | none | fabric.handoff | Border external handoff (VRF-lite/BGP) toward the fusion. |
| [`fusion-vrf-leak`](fusion-vrf-leak.md) | none | fusion.leak | Fusion router VRF route-leak (fabric VN ↔ shared services / mgmt). |
| [`sda-host-onboard`](sda-host-onboard.md) | none | fabric.hosts | Onboard hosts on edge ports (static or closed-auth) into their VN. |

## Example prompts
- "Build the SDA underlay then the LISP overlay and show me the map-server registrations"
- "Just do the border handoff + fusion leak so the fabric can reach shared services"

## Category gotchas
- LISP overlay keys: `locator default-set` + pub/sub `service ipv4` → map-server syntax.
- `sda-host-onboard` depends on `access.dot1x` under closed-auth — the manifest orders it after.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
