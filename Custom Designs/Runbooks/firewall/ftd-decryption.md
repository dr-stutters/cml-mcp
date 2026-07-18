---
id: firewall/ftd-decryption
category: firewall
agent: firewall-engineer
human: none
requires: [ftd.acp, ca.online]
provides: [ftd.decrypt]
params: [resign.ca]
est: 15m
---

# firewall/ftd-decryption

> TLS decryption: resign CA + Decrypt-Resign rule (C8) and Do-Not-Decrypt bypass (C16).

## Preflight — assert `requires`
- [ ] `ftd.acp`
- [ ] `ca.online`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Cert issuer proves resign vs bypass on the right destinations.

## Rollback
_TODO_

## Gotchas
- Decryption logging uses logEnd (logBegin → 422); insertBefore=1 works despite a false 500.
