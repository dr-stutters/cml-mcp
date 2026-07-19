---
id: firewall/fmc-base
category: firewall
agent: firewall-engineer
human: none
requires: [mcp.connected]
provides: [fmc.api]
params: [fmc.mgmt_ip, fmc.cred]
est: 20m
---

# firewall/fmc-base

> FMCv up, **licensed**, API answering. One FMC can be **shared** by FTDs living in
> several different CML labs — put it on the mgmt /18 and every lab's FTD can reach it.
> Proven 2026-07-19: `SGT-Firewall-Core` lab, FMCv **10.0.1 (build 1)** at 198.18.128.90.

## Preflight — assert `requires`
- [ ] `mcp.connected`
- [ ] Host capacity: the `fmcv` node def is **32 GB RAM / 4 vCPU**. Check free RAM first
      (`cml_api_call GET /system_stats`) — FMCv is by far the heaviest node in these labs.

## Steps
1. **Add the FMCv node** (node_definition `fmcv`) with a complete **day-0** document. The
   day-0 that worked verbatim:
   ```
   EULA=accept
   Hostname=fmc01
   AdminPassword=<FMC_PASSWORD from ../.env>
   IPv4Mode=manual
   IPv4Addr=198.18.128.90
   IPv4Mask=255.255.192.0        # /18
   IPv4Gw=198.18.128.1
   DNS1=198.18.130.11            # the AD DC, so the FMC FQDN resolves
   DNS2=198.18.128.1
   ```
   **GOTCHA:** CML's `add_node` **`configuration` parameter coerces a JSON-shaped day-0
   string into an object and rejects it.** Post the node via
   **`cml_api_call POST /labs/{lab_id}/nodes`** instead, with the day-0 as a `day0-config`
   configuration entry. Verify it landed with `get_node` (`configuration`).
2. **Wire mgmt to the /18** — FMC mgmt/eth0 → an **unmanaged switch** → an
   **External Connector (System Bridge)**. Prefer the switch over cabling FMC straight to
   the EXT: later phases add more FTDs/transit without re-cabling.
3. **Boot and poll.** BOOTED in **~15-30 min**; the **REST API answers ~10-20 min after
   that** (observed answering at ~39 min uptime). **Poll `get_node_state` — never a
   blocking sleep.**
4. **Point the `fmc` MCP at it** — set `FMC_URL=https://<mgmt_ip>` (+ `FMC_USERNAME`,
   `FMC_PASSWORD`) in the shared `../.env`. **The MCP caches config → reload (`/mcp`)
   after editing**, or the tools keep using the old target.
5. **Enable a licence mode — THIS IS MANDATORY BEFORE ANY DEVICE REGISTRATION.** A fresh
   day-0 FMCv is `regStatus: UNREGISTERED, evalExpiresInDays: 0` and does **not**
   auto-start evaluation. Either register a Smart Account, or enable the 90-day eval —
   **fully API-drivable, no GUI needed**:
   ```
   fmc_register_eval_license            # == POST /api/fmc_platform/v1/license/smartlicenses
                                        #    {"registrationType":"EVALUATION"}
   ```

## Verify — prove `provides`
- `fmc_server_version` → returns a version (i.e. an API token was issued). Observed:
  `10.0.1 (build 1)`, hostname `fmc01`, model "Cisco Secure Firewall Management Center for KVM".
- `fmc_license_status` → **`regStatus: EVALUATION`**, `virtualAccount: "Evaluation Mode"`,
  `evalExpiresInDays: ~89`.

## Rollback
Stop → wipe → delete the FMCv node/lab (`control_node` / `delete_node` / `delete_lab`).
Revert `FMC_URL` in `../.env` and reload the MCP. Nothing on the managed FTDs needs undoing
first, but de-register devices (`fmc_delete_device`) if you want them re-registerable elsewhere.

## Gotchas
- **No first-boot wizard on 10.0.1 when day-0 is complete.** With EULA + AdminPassword +
  IPv4 set in day-0, FMC came up fully configured and issued API tokens immediately — no
  console interaction, no forced password change. (Don't *assume* it; confirm with
  `fmc_server_version`. Older/partial-day-0 builds can still present the wizard, and until
  it completes the API returns 401 rather than a token.)
- **Licensing is the real gate for device registration — and it IS an API call.** See step 5.
  Skipping it makes `fmc_register_device` fail ~30 s later with `REGISTRATION_FAILED` and the
  device record is silently discarded (looks like "nothing happened"). See [[ftd-register]].
- **`add_node`'s `configuration` param rejects a JSON-shaped day-0** → use `cml_api_call POST
  /labs/{id}/nodes`.
- **The `fmc` MCP caches config** — edit `../.env` then reload, or you'll silently talk to the
  previous FMC.
- **In EVALUATION mode `exportControl: false`** — export-controlled features (e.g. the SD-WAN
  auto-VPN wizard) stay locked until a real Smart Account with export control is registered.
- **Add a DNS A record for the FMC FQDN early** (e.g. `fmc01.mitchcloud.lab → <mgmt_ip>` on the
  DC). pxGrid/cert work later requires the cert CN to match a resolvable FQDN — cheaper to do
  now than to re-issue certs. See [[cml-fmc-ise-pxgrid-recipe]].
