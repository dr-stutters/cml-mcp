---
id: fabric/sda-underlay
category: fabric
agent: catalyst-engineer
human: none
requires: [lab.up]
provides: [fabric.underlay]
params: [underlay.igp, loopbacks]
est: 15m
---

# fabric/sda-underlay

> IGP underlay, loopbacks, p2p links across the fabric nodes.

## Preflight — assert `requires`
- [ ] `lab.up` — nodes BOOTED, links STARTED, consoles reachable (see the pyATS-proxy gotcha below).

## Steps
The `topology.yaml` day-0 already sets hostnames, mgmt IPs, **Loopback0 RLOCs**, SNMP, SSH, and the
**OSPF area-0 underlay** over the /30 p2p links — so this atom mostly **verifies** day-0, plus two runtime bits:
1. **Verify the underlay** — `show ip ospf neighbor` (border↔edge **FULL**) and `show ip interface brief`
   (Lo0 RLOC + the /30s up/up). RLOCs `10.1.0.2` border / `10.1.0.3` edge / `10.1.0.254` fusion; underlay
   `10.1.23.0/30` border↔edge, handoff `10.1.24.0/30` border↔fusion. If day-0 didn't apply, configure per `topology.yaml`.
2. **FUSION-R1 SSH key** — EXEC `crypto key generate rsa modulus 4096` (≥3072). cat8000v boots with
   `ip ssh version 2` but NO host key, so SSH stays off until this runs (cat9000v self-generate).

## Verify — prove `provides`
Border↔edge OSPF **FULL** both ends; loopback/RLOC reachability.

## Rollback
Day-0 config; to reset, CML `wipe` reverts to `topology.yaml`.

## Gotchas
- **pyATS console-proxy host-key** — if EVERY node (incl. the Linux host) fails `failed to connect via
  proxy` and no session opens, the CML server's SSH host key changed (common after a CML reboot/rebuild):
  run **`ssh-keygen -R <cml-ip>`** on the `cml` MCP host, then retry. This is host-level, not device
  debugging. See [[pyats-proxy-hostkey-gotcha]]. (Hit again in the 2026-07-18 rebuild.)
- **cat8000v needs the manual RSA key** (step 2) — `ip ssh version 2` alone leaves SSH off.
- **UADP front-panel `Gi1/0/x` ports lag BOOTED ~1–2 min** — don't diagnose a "down" port prematurely.
