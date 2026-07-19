---
id: firewall/ftd-register
category: firewall
agent: firewall-engineer
human: none
requires: [fmc.api]
provides: [ftd.registered]
params: [ftd.mgmt_ip, reg.key]
est: 15m
---

# firewall/ftd-register

> Register an FTDv to FMC (management mode fixed in day-0, up front). The FTD and the FMC
> do **not** need to be in the same CML lab — one shared FMC can manage FTDs across several
> labs, as long as both sit on the mgmt /18. Proven 2026-07-19: `L3-FTD` (ftdv 10.0.0,
> 198.18.128.91, in the Traditional-NAC lab) registered to the shared FMC at 198.18.128.90.

## Preflight — assert `requires`
- [ ] `fmc.api` — `fmc_server_version` returns a version.
- [ ] **THE REAL GATE: the FMC has an active licence mode.** `fmc_license_status` must show
      `regStatus: EVALUATION` (or `REGISTERED`). A fresh FMCv is `UNREGISTERED` with
      `evalExpiresInDays: 0` and does **not** auto-start eval. Enable it via API —
      `fmc_register_eval_license` (`POST …/license/smartlicenses {"registrationType":"EVALUATION"}`).
      See [[fmc-base]] step 5.
- [ ] FTD mgmt IP reachable from the FMC subnet (both on the mgmt /18 here).

## Steps
1. **Decide management mode in day-0 — before boot.** For FMC-managed, the day-0 that worked:
   ```
   EULA=accept
   Hostname=L3-FTD
   AdminPassword=<same as FMC admin, keeps ../.env consistent>
   FirewallMode=routed
   IPv4Mode=manual
   IPv4Addr=198.18.128.91
   IPv4Mask=255.255.192.0        # /18
   IPv4Gw=198.18.128.1
   DNS1=198.18.130.11
   IPv6Mode=disabled
   ManageLocally=No              # <-- FMC-managed, NOT FDM/local
   FmcIp=198.18.128.90
   FmcRegKey=Cisco123Reg
   FmcNatId=                     # omit/empty when BOTH ends have routable addresses
   ```
   Day-0 effectively performs `configure manager add <FmcIp> <FmcRegKey>`, so the FTD starts
   dialling the FMC (sftunnel) as soon as it boots. (Same `add_node` JSON-coercion gotcha as
   [[fmc-base]] — post the node via `cml_api_call POST /labs/{id}/nodes`.)
   **NAT-ID** is only required when the FTD and FMC can't reach each other directly by IP
   (NAT in between) — not the case on a flat mgmt /18.
2. **Boot the FTD** and poll `get_node_state` to BOOTED (~5 min). Never a blocking sleep.
3. **Confirm the FMC licence mode** (preflight above). Do this *first* — it is the step that
   actually determines success.
4. **Register**: `fmc_register_device` — host = FTD mgmt IP, registration key = the day-0
   `FmcRegKey`, no NAT-ID, a device name, and an access-control policy. Registration completes
   in roughly a minute once the FMC is licensed (task RUNNING / REGISTRATION_IN_PROGRESS →
   SUCCESS / DISCOVERY_SUCCESS). **Poll** `fmc_list_devices` — don't sleep.

## Verify — prove `provides`
- `fmc_list_devices` → the device present with a real UUID, `health: green`.
  Observed: `L3-FTD`, id `5cd7f8ce-836f-11f1-8c6e-ca52f898e99d`, model
  "Cisco Secure Firewall Threat Defense for KVM", version 10.0.0, health **green**.
- `fmc_device_health` → `{"<device>": "green"}`.
- On the FTD console, `show managers` → `Registration: Completed`.

## Rollback
`fmc_delete_device(<device_id>)` to de-register from FMC. On the FTD, `configure manager delete`
then re-add if you need to re-point it. A CML `wipe` → day-0 gives the cleanest reset (the day-0
re-applies the manager config on next boot).

## Gotchas
- **Gating on TCP 8305 is a RED HERRING — do not do it.** An earlier theory said "gate
  registration on TCP 8305, not the API surface". That is **wrong** and wasted a session: an
  external probe of 8305 reads **closed even when registration is succeeding**, because
  **sftunnel is the FTD dialling OUT to the FMC** — there is no inbound listener to probe from a
  third host. Gate on the **FMC licence mode** instead (preflight).
- **Unlicensed FMC = silent failure.** With no licence mode, every device add fails after ~30 s
  with `REGISTRATION_FAILED` and **the device record is discarded**, so FMC looks untouched and
  the API gives no useful error. This is the single most common cause of "registration hangs".
- **Management mode is a day-0 decision.** `ManageLocally=No` (FMC-managed) vs `ManageLocally=Yes`
  (local/FDM) can't be flipped later without a wipe → day-0. Decide before building.
- FTD reaches BOOTED in ~5 min, but if you chose **local/FDM** mode instead, the FDM API lags
  BOOTED by ~15 min (and needs `POST /devices/default/action/provision {acceptEULA:true}` first).
- Keep the FTD admin password identical to the FMC's so the shared `../.env` stays valid for both.
