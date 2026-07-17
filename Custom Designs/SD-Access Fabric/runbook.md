# SD-Access Fabric (no ISE) — end-to-end runbook

A repeatable build of a **Cisco SD-Access fabric in CML without ISE**: an OSPF
underlay, a LISP (pub/sub) overlay with a collapsed **Border + Control-Plane** node
and a **fabric Edge**, one L3 virtual network, and an endpoint **statically
onboarded** ("No Authentication"). Validated end-to-end **2026-07-15** on CML
`cat9000v-uadp` 17.18 — the LISP control-plane session establishes, the edge detects
the host and registers its EID to the map-server, and the host reaches its anycast
gateway.

> **Two provisioning methods, one fabric.** The fabric can be provisioned two ways:
> [**CLI**](modules/cli-provisioning.md) (validated working) or
> [**Catalyst Center**](modules/catc-provisioning.md) (blocked on this appliance —
> see that module). This runbook covers the shared build (topology, underlay,
> discovery); the two modules diverge at fabric provisioning.

> **Orchestration:** the main session builds the topology (cml-lab-architect),
> configures the underlay + fabric (catalyst-engineer / direct pyATS), and reads
> inventory/health via the **`catc`** MCP tools (catalyst-center-engineer).

## What it builds

```
                     Catalyst Center 198.18.128.5 (external; inventory/site only here)
                                    │
      ┌──────── underlay/OOB mgmt 198.18.128.0/18 (System Bridge) ────────┐
      │  Gi1 .71          Gi0/0(Mgmt-vrf) .72        Gi0/0(Mgmt-vrf) .73    │
  ┌───┴──────┐        ┌──────┴───────┐          ┌────┴─────┐
  │ FUSION-R1│        │  BORDER-CP    │          │  EDGE1   │
  │ cat8000v │◀──────▶│ cat9000v-uadp │◀────────▶│cat9000v  │
  └──────────┘ 10.1.24│ Border + CP   │ 10.1.23  │ Edge/xTR │
    (fusion,    /30    │ (LISP MS/MR)  │  /30     └────┬─────┘
     outside          └───────────────┘            Gi1/0/3 (access VLAN10)
     the fabric)     underlay OSPF area 0 (RLOCs = Lo0)  │
                     10.1.0.2 / 10.1.0.3 / .254       ┌──┴───┐
                                                      │ HOST1│ 172.16.10.10/24
   Overlay: VN CAMPUS_VN (VRF, LISP instance-id 4099) └──────┘ gw 172.16.10.1 (anycast)
```

- **FUSION-R1** (cat8000v) — fusion router **outside** the fabric; the per-VN VRF/eBGP
  handoff point + path to shared services. (Typically NOT managed by CatC.)
- **BORDER-CP** (cat9000v-uadp) — collapsed **Border + Control-Plane** (LISP
  Map-Server / Map-Resolver).
- **EDGE1** (cat9000v-uadp) — fabric **Edge** (LISP xTR); the endpoint attaches here.
- **HOST1** (alpine) — endpoint, **static ("No-Auth") onboarding** into `CAMPUS_VN`.

**Why no ISE:** the fabric (LISP control plane, VXLAN data plane, VN handoff) needs
no ISE. ISE only adds *dynamic* host onboarding (802.1X/closed auth) and SGT policy.
Without it we use **static port assignment** into the VN.

## Prerequisites

- **CML** (198.18.128.10) with `cat8000v`, `cat9000v-uadp`, `alpine` images + the
  **System Bridge** external connector on `198.18.128.0/18`. The `cml` MCP server.
- **Catalyst Center** on the underlay (for inventory/discovery/site; fabric
  *provisioning* is blocked here — see the CatC module). The `catc` MCP server;
  `CATC_*` in the shared `../.env`.
- Three free /18 mgmt IPs. Lab values (**adjust for your environment**): FUSION
  `.71`, BORDER-CP `.72`, EDGE1 `.73`; CatC `.5`; gw `.1`; device login
  `cisco/cisco`; SNMP RO `public`. Overlay: VN `CAMPUS_VN`, instance-id `4099`,
  anycast GW `172.16.10.1/24`, host `172.16.10.10`; LISP key `cisco123`.

---

## Stage 1 — Topology  → cml-lab-architect

Build from [`topology.yaml`](topology.yaml) with one `build_lab_from_spec` call
(validated `valid: true`). Start the lab; confirm **EXT is STARTED**; wait for the
two cat9000v (~6–8 min) + FUSION (~4–6 min) to reach **BOOTED**.

> **Gotcha — unique switch serials.** Every CML `cat9000v-uadp` defaults to System
> Serial `CMLUADP`, and Catalyst Center **dedups inventory by serial** — two switches
> with the same serial collapse into one record (discovery silently drops one). The
> spec gives each switch a **unique `<prod_serial_number>`** in its `conf/vswitch.xml`
> (`CMLBRDCP01`, `CMLEDGE001`). Do not remove that.
>
> **Gotcha — alpine interfaces are `eth0`-`eth3`**, not `port0`; the HOST1 link uses
> `eth0`.

## Stage 2 — Underlay + enablement  → catalyst-engineer

Day-0 (in the spec) sets hostnames, mgmt IPs, loopbacks (RLOCs), the OSPF area-0
underlay over the /30s, SNMP RO, and vty/SSH. At runtime:

1. **FUSION-R1 RSA key** (cat8000v SSH gotcha): EXEC `crypto key generate rsa modulus
   4096` (≥3072) — day-0 `ip ssh version 2` alone leaves SSH off. cat9000v self-generate.
2. **Wait for UADP front-panel ports.** After a cat9000v reports BOOTED, its
   `Gi1/0/x` front-panel ports lag **~1–2 min** before coming up (they show
   `notconnect` meanwhile even though the CML link is STARTED). Don't diagnose the
   config prematurely — re-check after a couple minutes.
3. Verify: `show ip ospf neighbor` (BORDER-CP↔EDGE1 **FULL**), loopback/RLOC
   reachability, and mgmt reachability to CatC (`ping vrf Mgmt-vrf 198.18.128.5`).

## Stage 3 — Discover into Catalyst Center  → catc tools

Range discovery over SSH + SNMPv2c (`catc_start_discovery` `198.18.128.71-73`,
`protocol_order ssh`, `snmp_ro_community public`, `cisco/cisco`) → poll to
**Complete** → 3 devices **Managed/Reachable** (confirm `numDevices == 3`; if it's
2, you hit the serial collision). Build the site hierarchy
`Global/SDA-Lab/Fabric-Bldg` (`catc_create_area` + `catc_create_building`) and assign
the devices (`catc_assign_devices_to_site`). CatC auto-pushes its telemetry config
(DNAC-CA trustpoint, syslog/SNMP-to-.5) on management.

## Stage 4 — Provision the fabric

Diverges by method — pick one:

- **[CLI (validated working)](modules/cli-provisioning.md)** — LISP pub/sub CP on
  BORDER-CP, xTR + anycast SVI on EDGE1, dynamic-EID host detection.
- **[Catalyst Center (validated)](modules/catc-provisioning.md)** — the full
  Intent-API flow (telemetry → fabric site → provision → CP/Edge roles → IP pool → VN
  → anycast GW → No-Auth port assignment). Requires the **SD Access app installed**
  first — see [enabling the SD-Access service](modules/enable-sda-service.md) (the
  original `NCSP11008` was a missing package, now resolved).

## Stage 5 — Static host onboarding + verify

Configure HOST1 (alpine — needs **`sudo`**): `ip addr add 172.16.10.10/24 dev eth0`,
`ip route add default via 172.16.10.1`; `ping 172.16.10.1`. Then verify the fabric:

| Check | Command | Expect |
|---|---|---|
| Control-plane session | BORDER-CP `show lisp session` | peer 10.1.0.3 **Up**, established 1 |
| Host detected | EDGE1 `show device-tracking database` | 172.16.10.10 on Gi1/0/3 REACHABLE |
| EID registered | BORDER-CP `show lisp instance-id 4099 ipv4 server summary` | **Registered 1** |
| Edge database | EDGE1 `show lisp instance-id 4099 ipv4 database` | 172.16.10.10/32 dynamic-eid |
| Host → gateway | HOST1 `ping 172.16.10.1` | success |
| Host → external | HOST1 `ping 198.18.134.35` | success — needs the border L3 handoff ([`catc-provisioning.md`](modules/catc-provisioning.md) steps 11–12) |

## Teardown

- **CatC:** delete the discovery + remove the 3 devices from inventory (async DELETE
  `/network-device/{id}`), then delete building + area (child-first).
- **CML:** `control_lab stop` → `wipe` → `delete`. A wipe reverts to `topology.yaml`
  day-0 — so the FUSION RSA key, the LISP fabric config, and HOST1's IP are gone;
  re-run Stages 2/4/5. (The fabric config is `write mem`'d to NVRAM, so a *reload*
  survives; only a *wipe* discards it.)

## Gotchas (consolidated)

1. **cat9000v serial collision** → unique `prod_serial_number` per switch (Stage 1).
2. **UADP front-panel ports lag BOOTED ~2 min** (Stage 2).
3. **cat8000v needs a manual ≥3072-bit RSA key** for SSH (Stage 2).
4. **LISP `locator default-set` is mandatory** — without it the map-server opens no
   socket and no session forms (CLI module).
5. **Pub/sub LISP syntax** — role enable is `service ipv4`→`map-server`/`map-resolver`,
   not legacy `ipv4 map-server` (CLI module).
6. **alpine host config needs `sudo`** (Stage 5).
7. **CatC SDA provisioning needs the SD Access app installed** — `NCSP11008` = missing
   package (not resources); install it, then the full flow works. See
   [enable-sda-service.md](modules/enable-sda-service.md) + CatC module. Two more:
   add **Control-Plane before Edge**; **`forceSync`** a device after manual config
   changes or CatC's stale cache throws `NCSO20148`.
8. **Provision the border role up front** — retro-fitting it needs a full fabric rebuild
   (CatC won't update roles in-place, and won't delete the only CP while an edge exists →
   `NCHS20529`). `borderPriority` must be **1–9** (`10` → `NCHS20300`).
9. **CatC config-push to a re-provisioned cat9000v fails** until you `no ip ssh bulk-mode`
   (fixes `ERROR-CONNECTION-CLOSED` / `NCIM12018`) **and** set both `aaa authentication login
   VTY_authen` and `aaa authorization exec VTY_author` **local-first** (a re-provision re-flips
   them RADIUS-first → `NCNP10200`). See the CatC module's push-gotcha block.

## Roadmap

- [`modules/switch-only.md`](modules/switch-only.md) — all-switch fabric (drop the
  fusion router).
- [`modules/fabric-in-a-box.md`](modules/fabric-in-a-box.md) — single cat9000v as
  collapsed CP+Border+Edge.
- **Border L3 handoff** (external reachability) — **✅ validated 2026-07-16** via the CatC
  path ([`catc-provisioning.md`](modules/catc-provisioning.md) steps 11–12): the border takes
  the **`BORDER_NODE` (Layer-3)** role + an IP-transit handoff (on cat9000v CatC renders it as
  an **SVI on a trunk**, not a dot1Q subinterface), matched by a fusion-router eBGP + NAT
  `default-originate`. Border redistributes the default → LISP so edges `use-petr`; fabric
  host → ISE/Splunk/CatC 100%.

## Related

- MCP: [`catc`](../../../catalyst-center-mcp) (122 tools) · agents
  catalyst-center-engineer, catalyst-engineer, cml-lab-architect.
- Memory: `sda-fabric-cli-cml`, `cml-cat9000v-serial-collision`,
  `catalyst-center-mcp-project`.
