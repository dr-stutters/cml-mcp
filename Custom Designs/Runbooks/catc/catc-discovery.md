---
id: catc/catc-discovery
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.reachable, fabric.underlay]
provides: [catc.inventory]
params: [discovery.range]
est: 15m
---

# catc/catc-discovery

> SSH/SNMP discovery of the fabric nodes into inventory.

## Preflight — assert `requires`
- [ ] `catc.reachable`
- [ ] `fabric.underlay` (devices reachable on mgmt, SSH up — cat8000v needs its RSA key; see
      `fabric/sda-underlay`)

## Steps
1. **Global credentials FIRST** (discovery prerequisite — the credentials half of `catc-network-settings`):
   `catc_create_cli_credential` (`cisco`/`cisco`, enable `cisco`) + `catc_create_snmp_read_credential`
   (`public`).
2. **`catc_start_discovery`** over the mgmt range (e.g. `198.18.128.71-73`), `protocol_order ssh`, using
   those credentials → poll **`catc_get_discovery`** until `discoveryCondition: Complete`.
3. Confirm **`numDevices == 3`** and each device's ping/SNMP/CLI probes SUCCESS → Reachable.

## Verify — prove `provides`
`catc_list_devices` → all fabric nodes **Managed + Reachable** with the correct hostnames/serials.

## Rollback
`catc_delete_discovery` + remove the devices from inventory (async DELETE `/network-device/{id}`).

## Gotchas
- **cat9000v serial collision** — CatC dedups inventory by serial; every CML cat9000v defaults to `CMLUADP`,
  so 2+ collapse into ONE record. Give each a unique `<prod_serial_number>` in `vswitch.xml` (baked into
  `topology.yaml` as `CMLBRDCP01`/`CMLEDGE001`). **`numDevices == 2` when you expect 3 is the tell.** See
  [[cml-cat9000v-serial-collision]].
- Discovery needs the **credentials created first** (step 1), despite `catc-network-settings` sitting after
  this atom in the phase list.
- cat8000v's first collection lags the switches by ~1 min (reaches Managed on its own).
