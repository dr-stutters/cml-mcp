---
id: foundation/windows-dc-promote
category: foundation
agent: windows-engineer
human: none
requires: [mcp.connected]
provides: [ad.domain_up]
params: [ad.domain, dc.mgmt_ip]
est: 20m
---

# foundation/windows-dc-promote

> Build the Windows Server and promote it to an AD DS domain controller.

## Preflight — assert `requires`
- [ ] `mcp.connected`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Domain answers AD queries; DC reachable after the promote reboot.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
