---
id: access/endpoint-hosts
category: access
agent: ise-engineer
human: none
requires: [access.dot1x, ad.users]
provides: [endpoints.authenticated]
params: [endpoints]
est: 10m
---

# access/endpoint-hosts

> Alpine endpoints + wpa_supplicant supplicants (MAB / PEAP-AD; EAP-TLS is open item A1).

## Preflight — assert `requires`
- [ ] `access.dot1x`
- [ ] `ad.users`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Endpoint authenticates → lands in the correct SGT.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
