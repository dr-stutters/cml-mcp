---
id: catc/catc-site-hierarchy
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.inventory]
provides: [catc.sites]
params: [sites]
est: 10m
---

# catc/catc-site-hierarchy

> Areas/buildings/floors + assign devices to sites.

## Preflight — assert `requires`
- [ ] `catc.inventory`

## Steps
1. **Area** — `catc_create_area` `Global/SDA-Lab`.
2. **Building** — `catc_create_building` `Global/SDA-Lab/Fabric-Bldg` (needs a lat/long — a geocodable
   address).
3. **Assign devices** — `catc_assign_devices_to_site` for the fabric device UUIDs (from `catc_list_devices`)
   → the building.

## Verify — prove `provides`
`catc_site_membership` shows each device under `/Global/SDA-Lab/Fabric-Bldg/`.

## Rollback
`catc_delete_site_element` child-first (building → area).

## Gotchas
- A building **requires lat/long** (geocoded address), not just a name.
- Device assignment is **async** (`taskId`).
