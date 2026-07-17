# Module — FMC passive-identity user-based ACP  [C3]

Make the FTD enforce an **AD-user / AD-group** access-control rule using identity it learns
**passively** from ISE (no 802.1X on the firewall, no captive portal). ISE authenticates the
endpoint (802.1X → user `alice`), publishes the **session → user** mapping over **pxGrid Session
Directory**, FMC's ISE identity source consumes it, and the FTD resolves `source-IP → user →
AD group` at policy time. Built on C5 ([`fmc-ise-pxgrid.md`](fmc-ise-pxgrid.md)) + the C1 inline
FTD ([`firewall-in-fabric.md`](firewall-in-fabric.md)) + the MitchcloudCA/AD backing.

**Status (2026-07-17): DONE — proven live end-to-end** with the username captured in the FMC
connection event.

---

## The chain (what has to be true)
1. **ISE has a live session with BOTH a username and a framed-IP.** Here `alice` (802.1X, EAP)
   → `framed_ip 172.16.10.50` (HOST1). Verify: `ise_active_sessions` →
   `user_name: alice, framed_ip_address: 172.16.10.50`.
2. **pxGrid Session Directory is subscribed by FMC** — done in C5 (same ISE identity source that
   syncs SGTs also carries the user sessions). This is what turns IP→user at the FTD.
3. **An AD realm in FMC** so the FTD can expand `alice → Employees` (group membership) and match
   a group rule. Realm downloads users+groups from the DC over LDAP.
4. **An Identity Policy** (with a **passive** rule pointing at the realm) **attached to the ACP**.
5. **A user/group access rule** on the ACP + **deploy**.

## Realm (API) — but mind the DC IP
`POST object/realms` (realmType `AD`, `directoryConfigurations:[{hostname,port:389,encryptionProtocol}]`,
`dirUsername` = `CN=Administrator,CN=Users,DC=mitchcloud,DC=lab`, `dirPassword`, `baseDn`,
`adPrimaryDomain: mitchcloud.lab`).

> **⚠️ The one blocker that cost hours: the DC IP.** `DC01.mitchcloud.lab` resolves to
> **`198.18.130.11`**, NOT `198.18.134.11`. Pointing the realm's LDAP host at the wrong IP fails
> the sync with FMC task error **"could not initialize LDAP connection"** (looks like a
> firewall/389 problem; it's just the wrong host). Correct host → sync succeeds:
> **8 users / 54 groups**. AD-realm user/group **download is GUI-only** (`POST
> realms/operational/download` is SAML-only) — trigger it from the realm page (Download
> users/groups).

## Identity policy + passive rule (API)
- `POST policy/identitypolicies` → `{type:IdentityPolicy, name:SDA-Identity}`.
- `POST policy/identitypolicies/{id}/identityrules?intoCategory=<category-ID>` →
  `{type:IdentityPolicyRule, name:..., authenticationType:PASSIVE,
    realm:{id:<realmId>, type:"IdentityRealm"}}`.
  - **Gotchas:** the realm reference **type must be `IdentityRealm`** (not `Realm` → *"Invalid
    realm type"*); rule placement **must** use `intoCategory=<the category UUID>` (a category
    *name* is rejected: *"one of intoCategory/aboveRule/belowRule must be specified"*).

## The two things the FMC REST API will NOT let you do → **GUI**
Both were driven through the logged-in **`admin1`** browser session (see hygiene note):

1. **Attach the identity policy to the ACP — read-only over REST.** `identityPolicySetting` is a
   documented writable field on the `AccessPolicy` model, but a PUT returns `200 OK` and
   **silently drops it** — confirmed across three shapes (minimal-merge, corrected
   `identityPolicySetting.identityPolicy` nesting, and a full-object replace). Do it in the ACP
   editor: open the policy → the **packet-flow bar** at the top (Packets → Prefilter →
   Decryption → Security Intelligence → **Identity** → Access Control) → click the **Identity**
   step → pick **SDA-Identity** → Apply → **Save**. The Identity step's empty circle turns to a
   green check.
2. **Build the user/group rule — realm groups aren't in REST.**
   `GET object/realms/{id}/realmusergroups` returns **count 0** even after the realm downloaded
   54 groups, so you can't reference the group by id from the API. But the **Add Rule → Users
   tab** lists all **62** realm users/groups fine (search "Employee" → the **Employees** user
   group). Rule used: **`Employees-to-DC-Block`** — Action **Block**, **Users = Employees**,
   **Destination = host-dc**, **Logging ON** (log at beginning → FMC, so the block event
   records the user), inserted **into Mandatory** (evaluated before the C1 `Permit-CAMPUS-
   Services`). Then **Save** → `fmc_deploy`.

## Live test (the proof)
Same source host, same permit rule, two destinations that `Permit-CAMPUS-Services` both allow
(`net-ise, host-dc, host-splunk`) — so any difference is the identity rule:

| From HOST1 (alice, 172.16.10.50) | Permitted by C1 rule? | Result |
|---|---|---|
| → host-splunk `198.18.128.51` | yes | ✅ **0% loss** (control: routing through FTD works) |
| → host-dc `198.18.130.11` | yes | 🚫 **100% loss** (blocked by `Employees-to-DC-Block`) |

FMC **Events & Logs → Unified Events**, the Block row → **Event Details**:

```
Action              Block
Source IP           172.16.10.50
Destination IP      198.18.130.11
Access Control Policy   SDA-ACP
Access Control Rule     Employees-to-DC-Block
Device              FTDv
Source User         mitchcloud-AD\alice (LDAP)   ← passive identity resolved
Source SGT          Employees
```

The FTD blocked **by alice's AD user identity** — which it only knows because ISE's
`alice@172.16.10.50` session propagated ISE → pxGrid → FMC identity source → FTD. That is
passive-identity user-based enforcement, proven with the username on the wire.

## Session hygiene (bit us repeatedly)
FMC caps concurrent sessions **per user**, so a `curl .../generatetoken` as `admin` **evicts
`admin`'s GUI session** (and vice-versa). Keep **API work on `admin`** and the **GUI on a second
account (`admin1`)**. Also: the FMC `generatetoken` occasionally hangs — use `--max-time` and
retry; and mint fresh tokens per burst rather than reusing near the concurrent cap.

## Teardown
Delete rule `Employees-to-DC-Block` (or set disabled) → optionally unset the ACP Identity policy
(GUI) → `fmc_deploy`. The realm, identity policy, and the ISE pxGrid source are harmless to leave
(reused by C2). Related: [[cml-fmc-ise-pxgrid-recipe]], [[sda-ise-integration-lab]].
