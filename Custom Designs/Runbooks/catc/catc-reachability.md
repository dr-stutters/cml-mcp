---
id: catc/catc-reachability
category: catc
agent: catalyst-center-engineer
human: none
requires: [mcp.connected]
provides: [catc.reachable]
params: [catc.url, catc.cred]
est: 2m
---

# catc/catc-reachability

> Token auth + reachability (catc_check).

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
1. **`catc_check`** — token auth + reachability against `CATC_URL` / `CATC_USERNAME` / `CATC_PASSWORD`
   (from `../.env`). Returns `reachable` + `managed_device_count`.
2. **`catc_version`** — the package manifest (core-platform, `sda`, `assurance`, `ise-bridge`,
   `api-catalog`); confirms the SDA read package is present.

## Verify — prove `provides`
`catc_check` → `reachable: true`; `catc_version` returns the manifest.

## Rollback
n/a (read-only).

## Gotchas
- Catalyst Center is an **external appliance**, not a CML node. Ping may be blocked; `catc_check` (Intent-API
  token auth) is the real reachability test.
- Most CatC **writes are async** (`taskId` → poll; older ones use `executionId`) — the tools handle it.
