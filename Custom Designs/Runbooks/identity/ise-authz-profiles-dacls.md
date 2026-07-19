---
id: identity/ise-authz-profiles-dacls
category: identity
agent: ise-engineer
human: none
requires: [ise.policy_sets]
provides: [ise.authz]
params: []
est: 5m
---

# identity/ise-authz-profiles-dacls

> Authorization profiles + downloadable ACLs referenced by the authZ rules.

## Preflight — assert `requires`
- [ ] `ise.policy_sets`

## Steps
- **MAB baseline:** reused the built-in **PermitAccess** profile (no custom authZ needed for the allowlist).
- **Differentiated authZ (proven pre-outage, re-apply for depth):** create authZ profiles that return
  **dynamic VLAN** + a **downloadable ACL** (dACL) and/or a **TrustSec SGT**:
  - `ise_create_dacl` (the permit/deny ACL), then `ise_create_authz_profile` referencing it + the VLAN
    (+ `security_group` for the SGT — SGT is a rule *result*, not on the profile).
  - Bind each profile to the matching authZ rule (per AD group / endpoint group) in `ise-policy-sets`.

## Verify — prove `provides`
Profiles + dACLs present (`ise_list_authorization_profiles` / `ise_list_dacls`); a test auth returns the
profile and the switch enforces it (dACL permit/deny proven by ping; SGT visible in `show access-session`).

## Rollback
`ise_delete_authz_profile` / `ise_delete_dacl` for custom objects (built-in PermitAccess stays).

## Gotchas
- **SGT via authZ needs `device-tracking` on the port** for the IP→SGT binding to form.
- dynamic-authZ (dACL + dynamic VLAN) and SGT-via-authZ are validated in the ise-engineer agent — see
  [[cat9000v-mab-radius-needs-global-table-uplink]].
