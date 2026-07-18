# Module — Dynamic authorization (dACL + dynamic VLAN)

Layers onto the [base runbook](../runbook.md). Moves beyond `PermitAccess`: ISE
pushes a **downloadable ACL** and a **dynamic VLAN** to the authenticated session,
and the switch applies + enforces both.

## ISE

```python
# downloadable ACL (IOS ACE lines)
ise_create_dacl(name='ISE_DACL_TEST',
                dacl='permit icmp any host 198.18.128.1\npermit udp any any eq 53\ndeny ip any any')
# authZ profile carrying the dACL and/or a VLAN
ise_create_authz_profile(name='Dot1X_dACL',  dacl_name='ISE_DACL_TEST')          # dACL only
ise_create_authz_profile(name='Dot1X_VLAN200', vlan='200', dacl_name='ISE_DACL_TEST')  # dACL + VLAN
# point a high-rank authZ rule at it (matches the 802.1X session)
ise_create_authz_rule(policy_id=<default>, name='Dot1X_Restricted',
                      profiles=['Dot1X_dACL'], condition_name='Wired_802.1X', rank=0)
```
To swap the profile on an existing rule, `GET`/`PUT`
`/api/v1/policy/network-access/policy-set/{id}/authorization/{ruleId}` and set
`rule['profile']=['Dot1X_VLAN200']`.

## Switch

For dynamic VLAN, the target VLAN must exist: `vlan 200 / name ISE_ASSIGNED`. No
other switch config is needed — the dACL is downloaded and the VLAN is pushed via
RADIUS on the next (re)auth. Re-auth by bouncing the port (or via [CoA](coa.md)).

## Verify

```
show access-session interface Gi1/0/3 details
   →  ACS ACL: xACSACLx-IP-ISE_DACL_TEST-<hash>     ← dACL applied
      Vlan Group:  Vlan: 200                        ← VLAN assigned
show ip access-lists   → the downloaded dACL, with the exact ACEs
```
**Enforcement (keep the endpoint in a *bridged* VLAN for this):** from the endpoint,
a ping to the **permitted** dest succeeds and a ping to a **denied** dest is 100%
blocked.

## Gotchas

- Assigning a **non-bridged** VLAN isolates the endpoint (no path) — fine for
  proving the assignment via `show`, but you can't ping-test the dACL at the same
  time. Test the dACL in VLAN 100 (bridged), test the VLAN move separately.
- Rapid re-auths + VLAN changes on a **single-host** port can trip
  `%PM-4-ERR_DISABLE: security-violation` from a transient MAC move — self-recovers;
  a stable endpoint in production won't flap.
- `show access-session … details` can read **empty for a few seconds** while the
  policy is applying (`Fg: A` flag) — re-check once it settles.
