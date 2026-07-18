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
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Settings applied per site.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
