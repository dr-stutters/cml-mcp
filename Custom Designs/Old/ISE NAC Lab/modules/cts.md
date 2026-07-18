# Module — Full CTS (switch downloads the SGACL policy from ISE)

Layers onto the [base runbook](../runbook.md) and [TrustSec](trustsec.md). Instead
of configuring the SGACL locally, the switch **downloads** the environment data
(SGT name table + server list) *and* the SGACL policy from ISE via CTS — ISE owns
the entire policy.

## ISE — enable TrustSec device-auth on the NAD

Add `trustsecsettings` to the NAD (`GET` the `networkdevice`, add the block, `PUT`).
**The ERS schema misspells several fields** (`downlaod…`) — use the exact names:

```json
"trustsecsettings": {
  "deviceAuthenticationSettings": { "sgaDeviceId": "SW-ISE35", "sgaDevicePassword": "CTSsecret123" },
  "sgaNotificationAndUpdates": {
    "downlaodEnvironmentDataEveryXSeconds": 86400,
    "downlaodPeerAuthorizationPolicyEveryXSeconds": 86400,
    "reAuthenticationEveryXSeconds": 86400,
    "downloadSGACLListsEveryXSeconds": 86400,
    "otherSGADevicesToTrustThisDevice": false,
    "sendConfigurationToDevice": false,
    "sendConfigurationToDeviceUsing": "ENABLE_USING_COA",
    "coaSourceHost": "ise35"
  },
  "deviceConfigurationDeployment": { "includeWhenDeployingSGTUpdates": false },
  "pushIdSupport": false
}
```

## Switch — CTS provisioning

```
aaa authorization network CTS-LIST group radius
cts authorization list CTS-LIST
cts role-based enforcement
no cts role-based permissions from 4 to 11 TS_DENY_ICMP   ! drop the LOCAL one so ISE's is used
```
Then in **exec** (credentials must match ISE's device-auth):
```
cts credentials id SW-ISE35 password CTSsecret123
cts refresh environment-data
cts refresh policy
```

## Verify

```
show cts environment-data
   Current state = COMPLETE, Last status = Successful
   Server: 198.18.134.35 … Status = ALIVE, A-ID <hash>
   Security Group Name Table:  4-00:Employees … 11-01:Production_Servers …   ← names from ISE
show cts rbacl TS_Deny_ICMP
   name = TS_Deny_ICMP-00          ← the "-00" generation = downloaded (vs your local ALL-CAPS)
   RBACL ACEs:  deny icmp / permit ip
show cts role-based permissions from 4 to 11
   from group 4:Employees to group 11:Production_Servers: TS_Deny_ICMP-00
show cts role-based counters from 4 to 11   →  HW-Denied still increments
```

## Gotchas

- `cts credentials` is an **exec** command stored in the keystore (persists across
  reload), not in `running-config`; it **must exactly match** the ISE NAD's Device
  Authentication Settings.
- Env-data/policy download is **async** — right after `cts refresh` you may briefly
  see `state = START / Last status = Failed`; re-check, it goes `COMPLETE/Successful`.
- A **downloaded** SGACL carries a generation suffix (`-00`) and mixed-case name
  from ISE; a locally-configured one keeps the name you typed — an easy way to tell
  them apart.
- `debug cts` for env-data/policy download troubleshooting.
