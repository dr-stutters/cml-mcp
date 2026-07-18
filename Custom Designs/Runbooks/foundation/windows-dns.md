---
id: foundation/windows-dns
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up]
provides: [dns.core]
params: [ad.domain, dns.records]
est: 5m
---

# foundation/windows-dns

> Forward/reverse zones + A/PTR records for ISE, the CA, and devices that need resolvable names.

## Preflight — assert `requires`
- [ ] `ad.domain_up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
ISE and device FQDNs resolve both ways.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
