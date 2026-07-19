---
id: foundation/ad-users-groups
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up]
provides: [ad.users]
params: [ad.users, ad.groups]
est: 5m
---

# foundation/ad-users-groups

> OUs, test users, and groups the identity + firewall stacks key off.

## Preflight — assert `requires`
- [ ] `ad.domain_up`

## Steps
1. **Create an OU** to hold the lab identities — `win_create_ad_ou` (e.g. `MitchcloudLab`).
2. **Create the group(s)** — `win_create_ad_group` (e.g. `Employees`; add others per `ad.groups`).
3. **Create the user(s)** — `win_create_ad_user` with names/password from `AD_TEST_USER` /
   `AD_TEST_USER_PASSWORD` (or the `ad.users` list). This is ISE's external identity downstream.
4. **Add users to groups** — `win_add_group_member` (e.g. `iseuser1` → `Employees`).

## Verify — prove `provides`
`win_get_ad_user <user>` returns the account (Enabled, correct OU/UPN) with the expected `MemberOf`. A
throwaway `create → get → delete` round-trip proves write access (clean it up).

## Rollback
`win_delete_ad_user` for each user; delete the group and OU (`win_run_powershell` Remove-ADGroup /
Remove-ADOrganizationalUnit) if they were created solely for this.

## Gotchas
- _none banked yet_
