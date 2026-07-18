---
id: foundation/windows-adcs-ca
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up, dns.core]
provides: [ca.online]
params: [ca.name]
est: 10m
---

# foundation/windows-adcs-ca

> Install the enterprise AD CS CA and export its root cert (feeds ISE + FTD decryption trust).

## Preflight — assert `requires`
- [ ] `ad.domain_up`
- [ ] `dns.core`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
CA responds; root cert exported.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
