---
id: identity/ise-ad-join
category: identity
agent: ise-engineer
human: none
requires: [ise.certs, ad.domain_up, dns.core]
provides: [ise.ad_joined]
params: [ad.domain, ad.join_user]
est: 5m
---

# identity/ise-ad-join

> Join ISE to AD as an external identity source.

## Preflight — assert `requires`
- [ ] `ise.certs`
- [ ] `ad.domain_up`
- [ ] `dns.core`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Join point Connected; AD groups retrievable.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
