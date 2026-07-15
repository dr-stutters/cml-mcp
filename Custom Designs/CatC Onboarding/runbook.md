# CatC Onboarding — end-to-end runbook

A repeatable build of a small **Cisco Catalyst Center** (formerly DNA Center)
campus-onboarding lab in CML: two `cat8000v` routers and one `cat9000v-uadp`
switch, discovered into Catalyst Center over **SSH + SNMPv2c**, placed in a site
hierarchy, and running an **OSPF area-0 fabric** over routed /30s so Catalyst
Center's **topology, path-trace, and Assurance** views have real adjacencies to
show. Validated end-to-end 2026-07-15 against a live Catalyst Center **3.2.2** at
`198.18.128.5`.

> **Orchestration:** the main session runs the stages and fans device work out to
> **cml-lab-architect** (topology) and **catalyst-engineer** (IOS-XE config), then
> drives Catalyst Center itself through the **`catc`** MCP tools (or the
> **catalyst-center-engineer** agent). Catalyst Center is an **external appliance**
> on the underlay, not a CML node.

## What it builds

```
                          Cisco Catalyst Center 3.2.2
                          198.18.128.5  (external appliance)
                                    │
      ┌──────────────── underlay 198.18.128.0/18 (System Bridge) ───────────────┐
      │                                                                          │
   ┌──┴───┐                                                                      │
   │ EXT  │  external_connector (System Bridge)                                  │
   └──┬───┘                                                                      │
   ┌──┴──────┐  unmanaged_switch (pure L2 mgmt bridge)                           │
   │ MGMT-SW │                                                                   │
   └─┬───┬──┬┘                                                                   │
     │   │  └──────────────┐                                                     │
 Gi1 │   │ Gi0/0(Mgmt-vrf)  │ Gi1                                                 │
 .61 │   │ .62              │ .63                                                 │
 ┌───┴──────┐   ┌───────────┴───┐   ┌──────────┐                                 │
 │ CAT8K-R1 │   │   CAT9K-SW1    │   │ CAT8K-R2 │   mgmt IPs on the /18           │
 │ cat8000v │   │ cat9000v-uadp  │   │ cat8000v │                                 │
 └────┬─────┘   └───┬────────┬───┘   └────┬─────┘                                 │
   Gi2│          Gi1/0/1  Gi1/0/2         │Gi2                                    │
      │  10.10.12.0/30 │      │ 10.10.13.0/30                                     │
      └────────────────┘      └───────────────┘   ← OSPF area 0 routed fabric     │
                                                     (Lo0: R1 .1 / R2 .2 / SW .3) │
```

- **Management plane:** each device's management NIC → `MGMT-SW` (unmanaged L2) →
  `EXT` (System Bridge) → underlay `198.18.128.0/18`. Catalyst Center reaches the
  devices here; default route to `198.18.128.1`.
- **Data/fabric plane:** two routed /30 point-to-points (R1↔SW1, R2↔SW1) in **OSPF
  1 area 0**, plus a /32 Loopback0 per device advertised into OSPF. This is what
  makes CatC's L2/L3 topology and path-trace show adjacencies rather than three
  isolated nodes.

**Key caveat — the switch's management port is in `Mgmt-vrf`.** On the
`cat9000v-uadp`, `GigabitEthernet0/0` is the dedicated OOB port and lives in the
`Mgmt-vrf`; its default route and CatC's syslog/SNMP source must be VRF-aware. The
two `cat8000v` routers use `GigabitEthernet1` in the **global** table for mgmt (no
VRF). Don't try to move the cat9000v mgmt onto a front-panel port — keep it on
Gi0/0/Mgmt-vrf.

## Prerequisites

- **CML** (198.18.128.10) with `cat8000v` and `cat9000v-uadp` images, plus the
  **System Bridge** external connector bridged to the underlay `198.18.128.0/18`.
  The `cml` MCP server wired into `.mcp.json`.
- **Cisco Catalyst Center** reachable on the underlay (validated on **3.2.2**;
  `catc_check` confirms token auth + reachability). The `catc` MCP server wired in;
  `CATC_*` creds in the shared master `../.env`.
- Three free host IPs on the /18 for device management. Lab values used below
  (**adjust for your environment**): R1 `198.18.128.61`, SW1 `198.18.128.62`, R2
  `198.18.128.63`; CatC `198.18.128.5`; gateway `198.18.128.1`; device login
  `cisco/cisco` (priv-15), enable `cisco`; SNMP RO community `public`.

---

## Stage 1 — Topology  → cml-lab-architect

Build straight from [`topology.yaml`](topology.yaml) with a single
`build_lab_from_spec` call (it is a validated spec — `validate_lab_spec` returns
`valid: true`). It creates all five nodes, the day-0 configs, and the six links
(3 mgmt + 1 bridge uplink + 2 routed /30s), then start the lab.

After start, **confirm `EXT` is STARTED** (external connectors come up
`DEFINED_ON_CORE`; nothing reaches the underlay until started) and wait for the
two `cat8000v` (~4–6 min) and the `cat9000v` (~6–8 min, wants ~18 GB RAM) to reach
**BOOTED** before configuring.

## Stage 2 — Device enablement + fabric  → catalyst-engineer

The day-0 in the spec sets hostnames, mgmt IPs, loopbacks, the OSPF /30s, SNMP RO,
and vty/SSH. Two things day-0 **cannot** do — apply them at runtime:

1. **Generate SSH host keys on the two cat8000v routers (the big gotcha).** A
   `cat8000v` boots with `ip ssh version 2` but **no usable host key**, so
   `show ip ssh` reads *"SSH Disabled"* and CatC discovery / any SSH probe fails.
   In EXEC mode on **R1 and R2**:
   ```
   crypto key generate rsa modulus 4096
   ```
   (≥3072 bits required by modern IOS-XE; 4096 used here. The `cat9000v`
   self-generates a key from its self-signed PKI trustpoint and needs no step.)
2. **Verify the fabric is up** before onboarding, so topology has something to
   show:
   ```
   show ip ospf neighbor        ! expect SW1<->R1 and SW1<->R2 FULL
   show ip route ospf           ! expect the two remote loopbacks + /30s
   ```
   From SW1, `ping 198.18.128.5` (the CatC box, sourced from Mgmt-vrf) and from
   each router `ping 198.18.128.5` to confirm the management path.

Persist everything so it survives a wipe: `write memory` on each device, then
`extract_node_configuration` on all three IOS-XE nodes.

> If pyATS console access fails with *"failed to connect via proxy"* on **every**
> node, that's the CML server SSH host-key changing, not the lab —
> `ssh-keygen -R 198.18.128.10` and retry (see [Gotchas](#gotchas)).

## Stage 3 — Discovery into Catalyst Center  → catc tools

Kick off a **Range** discovery over SSH + SNMPv2c across the three mgmt IPs
(`catc_start_discovery`, or the raw call below). Inline the CLI + SNMP credentials;
CatC returns a `taskId` whose `progress` field is the **discoveryId**.

```
POST /dna/intent/api/v1/discovery
{
  "name": "CML-CatC-Onboarding",
  "discoveryType": "Range",
  "ipAddressList": "198.18.128.61-198.18.128.63",
  "protocolOrder": "ssh",
  "snmpVersion": "v2",
  "snmpROCommunity": "public",
  "userNameList": ["cisco"],
  "passwordList": ["cisco"],
  "enablePasswordList": ["cisco"],
  "retry": 3, "timeout": 5
}
```

Poll `GET /dna/intent/api/v1/discovery/{discoveryId}` until
`discoveryCondition == "Complete"`. Then confirm inventory
(`catc_list_devices` / `catc_device_count`): both routers and the switch should be
**Managed / Reachable**; the initial collection sync flips `collectionStatus`
`In Progress → Managed` and populates hostname/serial/platform (~1–3 min).

**On management, CatC auto-pushes telemetry config** to each device — a `DNAC-CA`
crypto trustpoint (+ cert chain), `logging host 198.18.128.5`, `snmp-server host
198.18.128.5`, and a large `snmp-server enable traps` block. This is expected and
is deliberately **not** in `topology.yaml`; it reappears on every re-onboard.

## Stage 4 — Site hierarchy + assignment  → catc tools

Build `Global / CML-Lab / CML-Bldg-1` and assign the devices:

1. **Area:** `POST /dna/intent/api/v1/site` `type:area` name `CML-Lab` parent
   `Global` (async **executionId** — poll `/dnacaap/management/execution-status/{id}`
   to `SUCCESS`). *(`catc_create_area`.)*
2. **Building:** same endpoint `type:building` name `CML-Bldg-1` parent
   `Global/CML-Lab` with lat/long + address. *(`catc_create_building`.)*
3. **Assign:** `POST /dna/intent/api/v1/networkDevices/assignToSite/apply` with the
   device UUIDs + the building `siteId` (async **taskId**). *(`catc_assign_devices_to_site`.)*

Verify with `GET /dna/intent/api/v1/membership/{siteId}` — both devices list the
building's `siteHierarchyId`. (The legacy `catc_list_devices.locationName` lags;
use membership as the source of truth.)

## Verification

- **Inventory:** `catc_device_count` = 3; each device `Managed` + `Reachable`,
  serial/platform/software populated (`C8000V` 17.x, `C9KV-UADP-8P` 17.x).
- **Fabric:** `catc_physical_topology` / `catc_l3_topology` show the R1–SW1 and
  R2–SW1 links; `catc_start_path_trace` `198.18.128.61 → 198.18.128.63` returns a
  path across SW1.
- **Command runner:** `catc_run_command` `show ip ospf neighbor` on any device
  returns two `FULL` adjacencies on SW1.
- **Assurance:** `catc_device_health` / `catc_network_health` populate a health
  window **~15 min after** site assignment (empty, and `network-health` may 500,
  before the first window closes — not a failure).

## Teardown

- **CatC side:** delete the discovery (`catc_delete_discovery`), remove devices
  from inventory, then delete building + area (child-first). Devices keep the
  CatC-pushed `DNAC-CA`/telemetry config until wiped.
- **CML side:** `control_lab stop` → `wipe` (→ `delete` if discarding). A wipe
  reverts to the `topology.yaml` day-0 — which means **the cat8000v RSA keys are
  gone**; re-run Stage 2 step 1 on next boot.

## Gotchas

- **cat8000v SSH needs a manual RSA key.** Day-0 `ip ssh version 2` does **not**
  create a host key; SSH stays disabled until EXEC `crypto key generate rsa modulus
  4096` (≥3072). This is invisible in `show run` (keys aren't in config) and is
  lost on wipe. The cat9000v self-generates and is fine. *This is the single most
  common reason discovery fails on a fresh build.*
- **cat9000v mgmt is in `Mgmt-vrf`.** Gi0/0 is the OOB port; its default route,
  syslog source, and SNMP trap source are all VRF-scoped. Keep mgmt there — don't
  move it to a front-panel SVI.
- **pyATS "failed to connect via proxy" on every node** = the CML server's SSH host
  key changed (VM rebuild/redeploy), not the lab. Fix: `ssh-keygen -R
  198.18.128.10` then one `ssh -o StrictHostKeyChecking=accept-new` to re-seed.
  `refresh_testbed` does **not** fix it. See memory `pyats-proxy-hostkey-gotcha`.
- **Assurance lags.** Device/network health is empty for ~15 min after onboarding
  and `network-health` returns HTTP 500 on a device-less box — both are CatC
  behavior, not errors. Give it a window before asserting health.
- **Async shapes differ.** Discovery + `assignToSite` return a **taskId** (poll
  `catc_get_task`); `/site` create returns an **executionId** (poll the
  `execution-status` endpoint). The `catc` tools handle both, but know which you're
  polling if you drop to `catc_api_call`.
- **Two free IPs for growth.** The build uses .61–.63; leave headroom on the /18 if
  you plan to add discovery targets.

## Related

- MCP: [`catc`](../../../catalyst-center-mcp) (122 tools) · agent
  [catalyst-center-engineer](../../.claude/agents/catalyst-center-engineer.md).
- Spec: [`topology.yaml`](topology.yaml) (validated, `build_lab_from_spec`-ready).
- Memory: `catalyst-center-mcp-project`, `pyats-proxy-hostkey-gotcha`.
