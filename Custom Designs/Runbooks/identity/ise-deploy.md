---
id: identity/ise-deploy
category: identity
agent: ise-engineer
human: gui
requires: [mcp.connected]
provides: [ise.reachable]
params: [ise.mgmt_ip, ise.admin_cred]
est: 10m
---

# identity/ise-deploy

> Bring ISE up, base network settings, enable the API surfaces (incl. ERS).

## Prerequisite (human — GUI/CLI, no API)
ISE is deployed from OVA and given its mgmt IP / hostname / admin cred at first boot (out of band). Two
settings have **no API to self-set** and must be done by the operator, both **before the AD-join atom**:
- **Enable ERS** — GUI ▸ Administration ▸ System ▸ Settings ▸ API Settings ▸ API Service Settings → turn
  on **ERS (Read/Write)** (and OpenAPI). There is no API to enable ERS itself — it's a bootstrap toggle.
- **Point ISE's resolver at the DC** — ISE CLI `conf t` → `ip name-server <dc.mgmt_ip>` so ISE resolves
  the AD domain (DC SRV records). A name-server change can bounce ISE services, so do it up front.

## Preflight — assert `requires`
- [ ] `mcp.connected` — the `ise` MCP reaches the box (`ise_version` returns).

## Steps
1. Confirm the node — `ise_version` + `ise_deployment_nodes`: note version, FQDN, personas, Standalone/roles.
2. Ensure **ERS + OpenAPI** are enabled (operator GUI step above).
3. Ensure ISE's **DNS points at the DC** (operator CLI step above).
4. `ise_check_surfaces` → all three green.

## Verify — prove `provides`
`ise_check_surfaces` → `openapi`, `mnt`, `ers` all **reachable**.

## Rollback
n/a (enablement only); the ERS toggle reverts via the same GUI page.

## Gotchas
- **ERS is off by default and has no enable-API** — GUI-only bootstrap toggle. `ise_check_surfaces` reports
  `ers: unreachable (302 redirect)` until it's on. (Proven 2026-07-18.)
- ERS on ISE 3.x is served on **443** (`/ers/config/...`), not the legacy 9060 (deprecated/often off).
