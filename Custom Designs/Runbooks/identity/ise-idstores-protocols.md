---
id: identity/ise-idstores-protocols
category: identity
agent: ise-engineer
human: none
requires: [ise.ad_joined]
provides: [ise.idstores]
params: []
est: 5m
---

# identity/ise-idstores-protocols

> Allowed protocols + the All_User_ID_Stores identity source sequence.

## Preflight — assert `requires`
- [ ] `ise.ad_joined`

## Steps
1. **Allowed protocols** — ensure Default Network Access permits **PEAP (MSCHAPv2)**, **EAP-TLS**, and
   **EAP-MSCHAPv2** (usually already enabled — verify rather than recreate).
2. **Identity source sequence `All_User_ID_Stores`** — order `[AD join point, then Internal Users]`.
   `All_User_ID_Stores` is a **built-in** (unique name), so **edit it in place** (PUT); don't duplicate.
   Keep `Preloaded_Certificate_Profile` as the cert-auth profile so EAP-TLS still resolves through it.

## Verify — prove `provides`
The sequence exists with `sequenceList = [<AD join point>, Internal Users]` and is selectable in a
network-access authorization rule.

## Rollback
Restore the built-in's default `sequenceList` (`Internal Users, All_AD_Join_Points, Guest Users`).

## Gotchas
- **`All_User_ID_Stores` already exists as a built-in** and names must be unique → shape the built-in,
  don't create a duplicate. It's referenced by default policies, so editing it changes those (deliberate,
  it's the intended identity backbone). (Proven 2026-07-18.)
