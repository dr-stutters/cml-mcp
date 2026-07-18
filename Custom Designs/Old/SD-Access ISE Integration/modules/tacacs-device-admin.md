# Module — TACACS+ device administration (roadmap "A3")

Named admins log into the fabric switches via **ISE TACACS+** (AD-backed), replacing the
Phase-6 local-first-vty workaround while keeping **CatC's automation safe**. netadmin
(AD group `ISE-Admins`) → priv 15; `cisco` (CatC's device credential) stays on local.

## ISE side
1. **Enable Device Admin** on the node (`ise_enable_device_admin` — on this 3.5 box it was a
   fast ~0.5 min toggle, *not* the 10-20 min app-server restart the docs warn about).
2. **TACACS shell profile** `NetAdmin Priv15` (priv-lvl 15) + **command set** `PermitAllCommands`
   (`permit_unmatched=true`).
3. **NAD TACACS secret** — add `tacacsSettings` to each fabric switch NAD (full-doc ERS PUT via
   **curl**, preserving `authenticationSettings` (RADIUS) + `trustsecsettings`, or you wipe the
   SGT push): `{"sharedSecret":"SdaIseTacacs2026","connectModeOptions":"ON_LEGACY"}`.
4. **Device-admin authZ rule** in the **Default** device-admin policy set (`.../policy/device-admin/
   policy-set/<id>/authorization`), rank 0 above the default Deny: result `commands:["PermitAllCommands"]`
   + `profile:"NetAdmin Priv15"`; condition (same AD dict as the RADIUS rules):
   `{conditionType:ConditionAttributes, dictionaryName:"mitchcloud", attributeName:"ExternalGroups",
   operator:"equals", attributeValue:"mitchcloud.lab/Users/ISE-Admins"}`.

## Switch side (BORDER-CP, EDGE1 — per switch)
```
tacacs server ISE_DA
 address ipv4 198.18.134.35
 key 0 SdaIseTacacs2026
aaa group server tacacs+ ISE_TACACS
 server name ISE_DA
ip tacacs source-interface Loopback0                 ! NAD IP = Lo0 (10.1.0.x), matches ISE
!
aaa authentication login VTY_authen local group ISE_TACACS
aaa authorization exec  VTY_author local group ISE_TACACS if-authenticated
aaa accounting commands 15 default start-stop group ISE_TACACS
```
Then `write memory`.

## Why local-FIRST (the CatC-safe design)
- **CatC logs in as `cisco` (local, priv 15).** ISE **won't create an internal user `cisco`** — the
  password fails ISE's complexity policy (`400 Incorrect username or password`). So a **TACACS-first**
  list would send `cisco` to ISE, ISE **rejects** it, and IOS does **not** fall back to local on a
  reject → CatC locked out.
- **Local-first + TACACS still lets named users in:** on the cat9000v (IOS-XE 17.x) the `local`
  method **falls through to TACACS when the username isn't in the local db** (verified — netadmin, not
  a local user, logged in via TACACS and got priv 15). So `local group ISE_TACACS` gives *both*:
  `cisco`→local (CatC safe, break-glass) and `netadmin`→TACACS→ISE→AD→priv 15. Best of both.
- To make it truly TACACS-first later, give CatC an **ISE-authenticatable service account** (point
  the CatC CLI credential at an AD/ISE user with a policy-compliant password) instead of local `cisco`.

## Verify
- `test aaa group ISE_TACACS netadmin Cisco12345! legacy` → **User successfully authenticated** (both switches).
- SSH `netadmin@<switch>` → `show privilege` = **15** (live login via TACACS; EDGE1 confirmed).
- SSH `cisco@<switch>` → 15 (local); **CatC `forceSync` of the switch → isError:false** (automation intact).

## Gotchas
- **FUSION (cat8000v router) rejected `tacacs server`** — it's the external fusion router, not a
  CatC-managed fabric switch; skipped (device-admin isn't its job here).
- **NAD PUT must be the full doc** (ERS has no PATCH) — include `trustsecsettings` verbatim or the
  TrustSec SGT-push config is lost. Body must be a **string** → use curl, not the MCP body param.
- A re-provision re-applies the CatC Network-AAA template (RADIUS-first `dnac-network-radius-group`)
  → re-apply this `ISE_TACACS` list afterward.
