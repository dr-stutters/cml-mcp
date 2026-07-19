---
id: catc/catc-network-settings
category: catc
agent: catalyst-center-engineer
human: none
requires: [catc.sites]
provides: [catc.settings]
params: [ip_pools, servers]
est: 10m
---

# catc/catc-network-settings

> Credentials, IP pools, per-site servers (DNS/DHCP/AAA).

## Preflight — assert `requires`
- [ ] `catc.sites`

## Steps
1. **Global credentials** (PROVEN — but note: these are actually a **discovery prerequisite**, so in
   practice create them before `catc-discovery`): CLI (`cisco`/`cisco`, enable) via
   `catc_create_cli_credential`, SNMP RO (`public`) via `catc_create_snmp_read_credential`.
2. **IP pools** *(provisioning-time — deferred until SDA fabric provisioning)* — `catc_create_global_pool`
   + `catc_reserve_subpool` per site for the fabric VN pools.
3. **Per-site servers** *(provisioning-time — deferred)* — DNS / DHCP / AAA (ISE) / NTP / syslog via
   `catc_set_site_settings`.

## Verify — prove `provides`
Credentials listed (`catc_list_global_credentials`); IP pools + per-site servers present once configured.

## Rollback
`catc_delete_global_credential` / `catc_delete_global_pool` / `catc_release_subpool`.

## Gotchas
- The **credentials portion is needed BEFORE discovery**, despite this atom's position after
  `catc-site-hierarchy` in the phase list — do credentials early.
- IP pools + per-site servers are **provisioning-time** (only needed when CatC actually provisions the SDA
  fabric — which is blocked/held on CML); onboarding (discovery + sites) doesn't need them.
