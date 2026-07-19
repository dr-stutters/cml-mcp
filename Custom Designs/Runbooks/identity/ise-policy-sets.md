---
id: identity/ise-policy-sets
category: identity
agent: ise-engineer
human: none
requires: [ise.idstores, ise.nads]
provides: [ise.policy_sets]
params: []
est: 10m
---

# identity/ise-policy-sets

> Wired/wireless policy set(s) with authN + authZ rules (incl. the ANC_Quarantine authz rule).

## Preflight — assert `requires`
- [ ] `ise.idstores`
- [ ] `ise.nads`

## Steps
- **MAB baseline (2026-07-19):** reuse the built-in **Default** policy set — its rank-0 authN rule **MAB** →
  **Internal Endpoints** (`ifUserNotFound: CONTINUE`), authZ **Basic_Authenticated_Access** → **PermitAccess**.
  A registered endpoint authenticates + permits; an unregistered MAC is "not found" → falls through → Deny.
  This is a correct allowlist and needs no custom set.
- **Deeper NAC:** create a **Wired** policy set — authN `Dot1X`/`Wired_MAB` → **`All_User_ID_Stores`** (one
  sequence serves MAB + PEAP + EAP-TLS); authZ rules keyed on AD group / endpoint group → the profiles from
  `ise-authz-profiles-dacls` (dynamic VLAN / dACL / SGT), plus an **ANC_Quarantine** rule
  (`Session:ANCPolicy EQUALS <name>`) for `identity/ise-anc`.

## Verify — prove `provides`
The policy set is active and matches on a test auth (MnT shows `ISEPolicySetName` + the matched authN/authZ rules).

## Rollback
`ise_delete_policy_set` for any custom set (the built-in Default stays).

## Gotchas
- **MCP raw-JSON `body`/`condition` params are JSON-coerced to a dict → pydantic `string` validation fails**,
  so compound authZ rules (e.g. `Wired_MAB` AND group) can't be pushed via `ise_create_authz_rule` /
  `ise_openapi_call` as raw JSON. Reuse built-ins, or use a dedicated typed tool. (Worth an `ise` MCP fix.)
- A policy set REQUIRES a condition — resolve a library condition by name (`Wired_802.1X` / `Wired_MAB`).
