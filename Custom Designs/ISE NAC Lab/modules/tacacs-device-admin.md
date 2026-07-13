# Module — TACACS+ device administration (device-admin)

Layers onto the [base runbook](../runbook.md). Adds **CLI login + command
authorization** for network devices via ISE's TACACS+ (Device Admin) persona — a
separate surface from RADIUS NAC. Built and config-validated live against ISE 3.5
(`ise35`, 198.18.134.35) with a dedicated scratch NAD. Driven by **ise-engineer**.

## Prerequisites / scope

- A router NAD reachable on the underlay. The overnight build used a throwaway
  1-node lab **`TACACS-DevAdmin-Scratch`** (lab_id `b6432804-6c06-494b-9f28-e896f0ccc972`,
  `TAC-RTR` iol-xe @ **198.18.128.68/18**) so nothing touched the ISE35-MAB lab.
- ERS enabled on ISE (as for the base runbook).
- **The Device Admin *service* must be enabled on the ISE node** — see Gotchas. Until
  it is, all the config below still applies cleanly but ISE won't answer TACACS+ on
  TCP 49, so `test aaa` fails.

## Stage 1 — ISE config plane (ise-engineer, all via `mcp__ise__*`)

Objects (overnight run used the `TAC-`/`tac-` prefix):

1. **Command sets** — `ise_create_tacacs_command_set`:
   - `TAC-CmdSet-NetAdmin` — `permit_unmatched=True` (admins run anything).
   - `TAC-CmdSet-ReadOnly` — `permit_unmatched=False`,
     `commands=[{"grant":"PERMIT","command":"show","arguments":"*"},
     {"grant":"PERMIT","command":"exit","arguments":""},
     {"grant":"PERMIT","command":"enable","arguments":""}]`.
2. **Shell profiles** — `ise_create_tacacs_profile`:
   - `TAC_Shell_Priv15` (`privilege=15`), `TAC_Shell_Priv1` (`privilege=1`).
   - **Profile names take only alphanumeric / underscore / space — no hyphens**
     (command-set names allow hyphens; this asymmetry is real).
3. **Internal users** — `ise_create_internal_user` `tac-admin`, `tac-oper`.
4. **NAD** — `ise_create_network_device("TAC-RTR", "198.18.128.68",
   radius_shared_secret=..., tacacs_shared_secret="TACkey123")` → adds
   `tacacsSettings: {sharedSecret, connectModeOptions: "ON_LEGACY"}`.
5. **Device-admin policy set** — `ise_create_policy_set(name="TAC-DeviceAdmin",
   kind="device-admin", condition=<JSON>)`. Default service is `Default Device Admin`.
   Condition on **`DEVICE:Device Type` = `All Device Types`** — `DEVICE:Device IP
   Address` is **illegal for the device-admin scope** (400).
6. **AuthZ rules** — `ise_create_authz_rule_raw(policy_id, body, kind="device-admin")`.
   The device-admin result shape differs from network-access:
   ```json
   {"rule": {"name": "TAC-Admins", "state": "enabled", "rank": 0,
             "condition": { ...REQUIRED... }},
    "commands": ["TAC-CmdSet-NetAdmin"],
    "profile": "TAC_Shell_Priv15"}
   ```
   `commands` = list of command-set names; `profile` = one shell-profile name; the
   rule condition is **mandatory** (no catch-all). Rules:
   `TAC-Admins` → NetAdmin + Priv15; `TAC-ReadOnly` → ReadOnly + Priv1.

   **Differentiate users by identity group — not `Device Type`.** If every rule
   conditions on `DEVICE:Device Type = All Device Types`, the rank-0 rule matches
   *every* user (both get whatever the first rule grants). Put each user in an
   identity group (`TAC_Admins`, `TAC_Operators`) and condition each rule on it:
   ```json
   {"conditionType": "ConditionAttributes", "dictionaryName": "IdentityGroup",
    "attributeName": "Name", "operator": "equals",
    "attributeValue": "User Identity Groups:TAC_Admins"}
   ```
   (Updating an internal user's group via ERS: GET the user, **drop the masked
   `password` field** — `*******` is rejected on PUT — set `identityGroups`, PUT.)

## Stage 2 — NAD config (catalyst/ise-engineer, pyATS)

```
crypto key generate rsa modulus 2048
aaa new-model
tacacs server ISE35
 address ipv4 198.18.134.35
 key TACkey123
aaa group server tacacs+ ISE-TAC
 server name ISE35
aaa authentication login VTY group ISE-TAC local
aaa authorization exec VTY group ISE-TAC local
aaa authorization commands 15 VTY group ISE-TAC local
aaa authorization commands 1 VTY group ISE-TAC local
aaa accounting exec default start-stop group ISE-TAC
aaa accounting commands 15 default start-stop group ISE-TAC
line vty 0 4
 login authentication VTY
 authorization exec VTY
 authorization commands 15 VTY
 authorization commands 1 VTY
 transport input ssh
```

Keep `local` in the method lists and leave the **console** line untouched — a
recoverable fallback if ISE is unreachable.

## Verification (proven live, ISE 3.5)

- On the NAD: `test aaa group ISE-TAC tac-admin <pw> new-code` → **User successfully
  authenticated** (both users); `show tacacs` → packets sent/received climbing,
  Server Alive.
- Real login (`ssh <user>@198.18.128.68`):
  - **tac-admin** → `show privilege` = **15**; `show running-config` runs (NetAdmin
    permit-all; debug shows `cmd=show` → `PASS_ADD`).
  - **tac-oper** → `show privilege` = **1**; `show clock` runs (ReadOnly permits
    show); `configure terminal` is blocked (priv-1 shell profile).
- The AAA debug (`debug aaa authorization` + `debug tacacs`) shows ISE returning
  `service=shell priv-lvl=N` on exec authorization and a per-command `AUTHOR/CMD`
  `PASS_ADD`/`FAIL` for each command — ISE drives both the privilege and per-command
  authorization.
- ISE side: no TACACS MnT tool exists; use the **GUI** Device-Admin livelog
  (Operations ▸ TACACS ▸ Live Logs).

## Gotchas (the expensive lessons)

- **Enable the Device Admin service or nothing works.** ISE listens on TCP 49 only
  when the node has the DeviceAdmin persona. `ise_enable_device_admin` builds the
  correct `NodeUpdateRequest` (`{roles, services+["DeviceAdmin"]}`), but a
  **standalone** ISE node rejects the persona change over the API with a generic
  `Exception occurred while making REST call` (the `da-only` variant proves the
  schema validates: it demands Profiler+Session too). **Enable it in the GUI:**
  Administration ▸ System ▸ Deployment ▸ *node* ▸ **Enable Device Admin Service**.
  `nc -zv <ise> 49` flips from *refused* to *open* once it's on. On the overnight
  run, TAC-RTR is fully staged — one GUI click then re-run `test aaa`.
- **Device-admin authZ ≠ network-access authZ.** Result fields are `commands` +
  `profile` (not `profile:[authZ profiles]` + `securityGroup`); the condition is
  mandatory.
- **Profile-name charset** (no hyphens) and the **`Device Type`** condition attribute
  (not `Device IP Address`) — both cause opaque 400s otherwise.
- **MCP tool inputs:** the dedicated tools take `commands`/`attributes` as native
  lists (a JSON-array string gets coerced by the MCP layer). The raw
  `condition`/`body` string params work from a real client but the same coercion can
  bite in-process test harnesses — pass them from the client for scripted validation.
