# Test Plan — Firewall SD-WAN (end-to-end acceptance)

**Plan ID prefix:** `SDWAN-` · **Version:** 1.0 · **Last updated:** 2026-07-15

## 1. Scope & purpose

End-to-end acceptance of the
[Firewall SD-WAN](../../Cisco%20Validated%20Designs/Firewall%20SD-WAN/) CVD as built in CML:
a multi-site **Cisco Secure Firewall Threat Defense SD-WAN** (not Catalyst SD-WAN) — an
FMC-provisioned AUTO_VPN VTI overlay with an iBGP overlay, dual-ISP ECMP, and FTD HA at the
hub — proving LAN-to-LAN reachability and failover resilience. **Out of scope:** the physical
underlay/ISP simulation internals, throughput/perf, and Catalyst SD-WAN (vManage).

## 2. System under test

| Item | Value |
|---|---|
| Design | Firewall SD-WAN (CVD) — 6 sites, VTI overlay |
| Verified against | FMC 10.x + FTDv (**lab-specific** IPs); iBGP **AS 65070** overlay |
| Environment | CML lab (spec `Cisco Validated Designs/Firewall SD-WAN/topology.yaml`) |
| Dependencies | FTDs registered + healthy; **export-controlled license** (mandatory for auto-VPN); ACP allowing overlay traffic |

## 3. Test approach / levels

**Solution acceptance — Manual/Live.** Provisioning via the `fmc` MCP tools; overlay/routing
state and end-to-end proof via pyATS on the FTD consoles and FMC monitoring dashboards. The
real proof is **0% packet loss** across the overlay, including under failover.

## 4. Preconditions & environment

- FMC reachable + licensed (`exportControl:true`); all FTDs registered and `fmc_device_health`
  green.
- Overlay provisioned with `topologyType: AUTO_VPN` (HUB_AND_SPOKE silently drops auto-VPN
  settings); spoke endpoint `interface` = the physical WAN interface.
- Redistributed LAN routes tagged **community 1000** (else the auto-VPN OUT route-map filters
  them).

## 5. Test cases

### Provisioning & overlay

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SDWAN-001` | Auto-VPN topology provisioned via REST | `fmc_create_auto_vpn_topology` → `fmc_list_s2s_topologies` | Hub-spoke AUTO_VPN present; GET shows non-null `autoVpnSettings` | `manual-live` (SD-WAN CVD build) |
| `SDWAN-002` | VTI overlay tunnels UP | FTD `show crypto ikev2 sa` (pyATS) | IKEv2 SAs established hub↔spoke on both ISPs | `manual-live` |
| `SDWAN-003` | iBGP overlay established | FTD `show bgp` (pyATS) | AS 65070 neighbors up over the tunnels; overlay prefixes learned | `manual-live` |
| `SDWAN-004` | Dual-ISP ECMP | FTD `show bgp` / `show route` | `maximum-paths`; LAN prefix installed via **both** next-hops (ECMP) | `manual-live` |

### Reachability & resilience

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `SDWAN-010` | LAN-to-LAN reachability | `NYC-HOST 10.100.0.100 → each branch LAN loopback 10.<site>.100.1` (pyATS ping) | **0% loss** across the dual-ISP overlay | `manual-live` (the real proof) |
| `SDWAN-020` | ISP failover (spoke) | `set_interface_state`/`set_link_state stop` a spoke ISP1 link | Traffic rides ISP2 (DPD-driven, ~40-60 s); pings recover to 0% loss | `manual-live` |
| `SDWAN-021` | Hub failover (dual-hub) | Isolate the NYC hub | Traffic rides the NNJ hub; 0% loss through the overlay | `manual-live` |
| `SDWAN-022` | FTD HA failover (hub) | Kill the HA active unit | Standby takes over the hub role; 0% loss through the overlay | `manual-live` |

## 6. Pass/fail & exit criteria

- **Plan pass =** SDWAN-001…004 establish the overlay, SDWAN-010 shows 0% loss LAN-to-LAN,
  and each failover case (SDWAN-020…022) recovers to **0% loss**. Any sustained loss after
  the convergence window = FAIL.
- Underlying tool health is covered by the [firepower-mcp](../MCP%20Servers/firepower-mcp.md)
  and [cml-mcp](../MCP%20Servers/cml-mcp.md) server plans; component build detail is in the
  6 FMC/FTD component runbooks under `Custom Designs/`.

## 7. Traceability matrix

| Capability | Case IDs | Source |
|---|---|---|
| Auto-VPN + overlay routing | SDWAN-001…004 | SD-WAN Auto-VPN + ECMP + Overlay component runbooks |
| Reachability + failover | SDWAN-010…022 | Dual-Hub + HA Pair component runbooks |

All cases are manual-live acceptance (no CI gate — require the live FMC/FTD lab; FMCv wants
32 GB, so this lab is built on demand, not kept running).

## 8. Execution record

Filled by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
