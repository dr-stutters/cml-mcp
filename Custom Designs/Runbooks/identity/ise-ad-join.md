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
- [ ] `dns.core` (ISE's resolver points at the DC — see `identity/ise-deploy`)

## Steps
1. Create an AD join point for `ad.domain` (ERS `activedirectory`).
2. Join — `PUT …/activedirectory/<id>/joinAllNodes` with `ad.join_user` (a domain admin) + password from
   `../.env` (inject via `jq --arg` so it never appears on the command line or in output).
3. Retrieve AD groups and add the ones policy needs (e.g. `Employees`) to the join point's selected groups.

## Verify — prove `provides`
Join point **Connected/Operational** and AD groups retrievable. On ISE 3.5, prove live connectivity with a
`getUserGroups` for a known user (e.g. `iseuser1@<domain>`) → HTTP 200 returning that user's group DNs.

## Rollback
`leaveAllNodes`, then delete the join point.

## Gotchas
- **ISE 3.5 `getGroups` 502s** (build bug) — prove the join is live via `getUserGroups` for a real user
  instead, and **add groups by SID** if `getGroups` won't enumerate. (Proven 2026-07-18.)
- The join needs ISE's resolver pointed at the DC for SRV lookups — that's the human step in
  `identity/ise-deploy`; if join fails to find a DC, check ISE's `ip name-server` first.
