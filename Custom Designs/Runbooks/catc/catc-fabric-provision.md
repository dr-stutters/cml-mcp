---
id: catc/catc-fabric-provision
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.sites, catc.ise_integrated]
provides: [catc.provisioned]
params: []
est: 20m
---

# catc/catc-fabric-provision

> Provision the fabric via CatC (fabric site, roles, VNs) — with the CLI path as fallback.

## Preflight — assert `requires`
- [ ] `catc.sites`
- [ ] `catc.ise_integrated`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Fabric provisioned (or CLI-fallback parity confirmed).

## Rollback
_TODO_

## Gotchas
- If CatC provisioning blocks (NCSP11008), fall back to the CLI fabric build and verify parity.
