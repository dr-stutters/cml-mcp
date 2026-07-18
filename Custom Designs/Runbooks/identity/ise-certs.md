---
id: identity/ise-certs
category: identity
agent: ise-engineer
human: none
requires: [ise.reachable, ca.online, dns.core]
provides: [ise.certs]
params: [ca.name, ise.fqdn]
est: 15m
---

# identity/ise-certs

> CSR → CA-signed system cert; import the root as trusted (clientAuth) for EAP + admin.

## Preflight — assert `requires`
- [ ] `ise.reachable`
- [ ] `ca.online`
- [ ] `dns.core`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
CA-signed system cert active; root trusted.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
