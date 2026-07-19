---
id: identity/ise-trustsec-sgt
category: identity
agent: ise-engineer
human: none
requires: [ise.reachable]
provides: [trustsec.sgts, trustsec.sgt-assignment]
params: [sgts]
est: 15m
---

# identity/ise-trustsec-sgt

> Security Group Tags + **per-group SGT assignment**: create SGTs, then make an AD
> group drive a *differentiated* authZ result (its own SGT) via a group-keyed
> authorization rule. Proven end-to-end on 3 labs (SDA-CLI edge, SDA-CatC edge,
> traditional switch) against ISE 3.5.0.527 + the `mitchcloud` AD join point.
> Phase A = assignment only (no SGACL/egress-matrix/SXP enforcement — that is a
> separate atom).

## Preflight — assert `requires`
- [ ] `ise.reachable` (`ise_check_surfaces` → openapi + mnt + ers reachable).
- [ ] AD join point present with the target groups **selected** on it
      (`ise_get_active_directory` → `adgroups.groups[]` lists e.g.
      `mitchcloud.lab/MitchcloudLab/Lab1-Employees`). The join-point `name`
      (here `mitchcloud`) is also the **policy dictionary name** used in the
      condition; the group-membership attribute is `ExternalGroups`
      (`GET /api/v1/policy/network-access/dictionaries/<name>/attribute`).
- [ ] 802.1X/MAB already working on each edge (a live `Authorized` session per
      host — this atom only *changes the authZ result*, it does not build auth).
- [ ] Each host port already has a **device-tracking** policy attached
      (prerequisite for the IP→SGT binding to form).

## Steps

### 1. Create the SGTs (OpenAPI/ERS)
```
ise_create_sgt(name="Lab1_Employees", value=100)
ise_create_sgt(name="Lab2_Employees", value=110)
ise_create_sgt(name="Lab3_Employees", value=120)
```
Names are alphanumeric/underscore only (no spaces/hyphens). Pick free numeric
values (built-ins are all low-numbered; `ise_list_sgts` shows names/ids only, not
values — 100/110/120 were free here). Record name↔value↔id.

### 2. AuthZ result = PermitAccess + SGT on the *rule result*
Do **not** clone PermitAccess three times. ISE natively carries the SGT as a
**rule result** (`securityGroup`), exactly like the built-in rules
(`Wi-Fi_Guest_Access` = PermitAccess + Guests). So the profile stays
`PermitAccess` and each rule sets `securityGroup: LabN_Employees`. ISE then adds
the `cts:security-group-tag=<hex>-00` AV pair to the Access-Accept automatically —
no TrustSec device-auth on the NAD is required just to *send* the tag.

### 3. Group-keyed authZ rules — **the compound-rule workaround (key deliverable)**
A condition-bearing authZ rule cannot be pushed via `ise_create_authz_rule` /
`ise_openapi_call`: the MCP layer coerces the `body`/`condition` param into a dict
and pydantic string-validation then fails. **Workaround: POST the rule with httpx
using a correctly-typed JSON body** straight to the OpenAPI authorization
collection. This works cleanly (HTTP 201).

- Endpoint: `POST /api/v1/policy/network-access/policy-set/<policySetId>/authorization`
- Condition is an inline `ConditionAttributes` referencing the AD dictionary:
  ```json
  {
    "rule": {
      "name": "Lab1_Employees_SGT",
      "rank": 10,
      "state": "enabled",
      "condition": {
        "conditionType": "ConditionAttributes",
        "isNegate": false,
        "dictionaryName": "mitchcloud",
        "attributeName": "ExternalGroups",
        "operator": "equals",
        "attributeValue": "mitchcloud.lab/MitchcloudLab/Lab1-Employees"
      }
    },
    "profile": ["PermitAccess"],
    "securityGroup": "Lab1_Employees"
  }
  ```
  `operator: "equals"` on the multi-valued `ExternalGroups` attribute is a
  *membership* test; use the **full DN-style group name** as the value (unambiguous
  even though the labs share the `-Employees` suffix). `securityGroup` takes the
  SGT **name**, not id.
- **Rank ABOVE the catch-all** (`Basic_Authenticated_Access` → PermitAccess). POST
  the three rules at ranks 10/11/12; ISE re-ranks the existing rules down (Basic
  moved 10→13, Default 11→14). Leave Basic as the no-SGT catch-all.
- Reusable script pattern:
  `scratchpad/push_authz_rules.py` (loads `/home/reptar/MCP/.env` →
  `ISE_URL/ISE_USERNAME/ISE_PASSWORD`; `httpx.Client(verify=False)`; Basic auth;
  defensively fetches `X-CSRF-TOKEN` first — harmless when CSRF is off, which it was
  here so a plain POST also works). Run it with a python that has httpx, e.g.
  `/home/reptar/MCP/ISE_MCP/.venv/bin/python` (the base system python lacks httpx).
- **Alternative** (also valid): first create a reusable **library condition** per
  group (`POST /api/v1/policy/network-access/condition`, same typed-body httpx
  trick) and reference it by id via a `ConditionReference` child in the rule — keeps
  the rule bodies small and the conditions reusable.

### 4. Minimal switch CTS (per edge, additive)
Just enough for the switch to accept/display the RADIUS-assigned SGT and form the
IP→SGT binding:
```
conf t
 cts role-based enforcement
end
```
That single global command is sufficient — **no** `cts credentials`, PAC, or
environment-data download is needed to *receive & display* the session SGT and
build the local binding. (Env-data is only needed to resolve the SGT *name* on-box
and to download SGACLs — that is Phase B.) `cts role-based enforcement` global does
not drop host traffic: with no egress matrix the default is permit, and switched
intra-VLAN traffic is only enforced if you add `... vlan-list <vlan>` (don't, for
Phase A). Keep MAB/802.1X and the RADIUS source-interface untouched.

### 5. Re-auth so the new SGT-bearing Access-Accept lands
```
clear access-session interface <host-port>
```
The supplicant re-authenticates within a few seconds. On a fabric edge the
re-auth bounces the port and **flushes device-tracking**, so the IP shows
`Unknown` briefly — generate one packet so DT re-learns it (see Verify).

## Verify — prove `provides`
**Switch (per edge):**
- `show access-session interface <port> details` → `Status: Authorized`,
  `dot1x  Authc Success`, and under **`Server Policies:`** a **`SGT Value: <n>`**
  line with the lab's value (Lab1=100 / Lab2=110 / Lab3=120). This alone proves
  per-session SGT assignment.
- Traditional switch: `show cts role-based sgt-map all` → `<host-ip>  <sgt>  LOCAL`
  (e.g. `172.16.30.10  120  LOCAL`).
- Fabric edge: the local sgt-map stays **empty by design** (SGT is inline in the
  fabric, not a LOCAL binding). After re-auth, force DT to re-learn the host first:
  `ping vrf CAMPUS_VN <host-ip>` from the edge → `show device-tracking database
  interface <port>` shows the IP `REACHABLE`. The `SGT Value` in the access-session
  is the proof here.

**ISE (MnT) — authoritative:**
- `ise_session_by_mac(<mac>)` / `ise_auth_status_by_mac(<mac>, filter="All")` →
  `cts_security_group: LabN_Employees`, and in `other_attr_string`
  `AuthorizationPolicyMatchedRule=LabN_Employees_SGT`, plus the raw
  `cisco-av-pair=cts:security-group-tag=<hex>-00` in `response`
  (0064-00=100, 006e-00=110, 0078-00=120). `selected_azn_profiles: PermitAccess`,
  `ISEPolicySetName=Default`.
- Note MnT filter tokens are case/spelling-sensitive: use `filter="All"` (not
  `"Success"` → 400 "Invalid parameter"). MnT can also briefly return only the
  Accounting-On record for a just-re-authed session — re-query or use
  `ise_auth_status_by_mac` to get the full dot1x record with the SGT.

Proven mapping: l1user1→Lab1_Employees(100), l2user1→Lab2_Employees(110),
l3user1→Lab3_Employees(120).

## Rollback
- Delete the 3 authZ rules (httpx `DELETE
  /api/v1/policy/network-access/policy-set/<id>/authorization/<ruleId>`, or
  `ise_delete_authz_rule`). Basic_Authenticated_Access/PermitAccess and the default
  set are untouched.
- `ise_delete_sgt(<id>)` for each SGT (only after no rule references it).
- Switch: `conf t ; no cts role-based enforcement ; end` per edge (additive-only
  change; MAB/802.1X unaffected).

## Gotchas
- **Compound/condition-bearing authZ rules can't go through the MCP** (`body`/
  `condition` coerced to dict → pydantic string-validation fails). Push them with
  **httpx + a typed JSON body** (Step 3). This graduates the banked blocker.
- **httpx isn't in the base system python** — run the push script with a venv that
  has it (`/home/reptar/MCP/ISE_MCP/.venv/bin/python`).
- **CSRF**: disabled on this box, so a plain authenticated POST returns 201. If
  "Enable CSRF for Admin/ERS" is on, first `GET` the collection with header
  `X-CSRF-TOKEN: fetch`, then send the returned `X-CSRF-Token` on the POST (the
  script does this pre-emptively).
- **Dictionary name = the AD join point `name`** (here `mitchcloud`), attribute
  `ExternalGroups`; value is the **full** `domain/OU/Group` string. `equals` on this
  multi-valued attr = membership.
- **Rank above the catch-all**: insert the group rules above
  `Basic_Authenticated_Access`, or everyone keeps hitting generic PermitAccess.
- **device-tracking must be on the host port** for the IP→SGT binding, and re-auth
  flushes it — the host must send a frame (a `ping` from the edge in the host VRF
  re-populates DT) before the binding/DT database repopulate.
- **SGT propagation differs by lab type (Phase B planning):**
  - **Fabric edges (SDA):** SGT is assigned to the session and carried **inline**
    in the VXLAN/fabric encapsulation — **no** local `cts role-based sgt-map`
    binding forms (verified: DT `REACHABLE` yet sgt-map empty). Intra-fabric
    enforcement therefore needs **no SXP**; SGACLs are downloaded from ISE to the
    fabric.
  - **Traditional switch:** SGT lands as a **LOCAL** `cts role-based sgt-map`
    binding. To carry that SGT off-box to a remote enforcement point (firewall /
    another switch) it needs **SXP** (ISE speaker → device listener) or inline SGT
    tagging on an uplink.
