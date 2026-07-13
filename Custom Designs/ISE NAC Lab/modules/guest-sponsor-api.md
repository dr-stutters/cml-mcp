# Module — Guest provisioning via a sponsor (over the API)

Layers onto the [base runbook](../runbook.md). Provisions ISE **guest users** through
a **sponsor account over ERS** — proven end-to-end live against ISE 3.5, beating the
common assumption that guest users are GUI/sponsor-portal-only. Driven by
**ise-engineer**.

## Why it's not obvious

Guest *types*, *sponsor portals*, and *sponsor groups* read fine with an ISE admin,
but the admin account **cannot** create guest users — `/ers/config/guestuser` returns
`401 Unauthorized access`. Guests are owned by **sponsors**. Two things unlock the API
path:

1. A sponsor **account** — an internal user in an identity group that a sponsor group
   maps to.
2. That sponsor group's **`canAccessViaRest`** permission, which is **off by default**.
   Without it the sponsor authenticates but gets `401 Sponsor does not have permission
   to access REST Apis`.

## Validated flow

```
# 1. sponsor account (as admin, via the ise MCP)
ise_create_internal_user("GST-sponsor1", "<pw>", identity_groups="ALL_ACCOUNTS (default)")

# 2. grant the sponsor group REST access (as admin, via the ise MCP)
ise_enable_sponsor_rest_access("ALL_ACCOUNTS (default)")   # sets otherPermissions.canAccessViaRest = True

# 3. create the guest AS THE SPONSOR — the admin-authed MCP server always 401s here,
#    so use Bash with a sponsor-cred ISEClient:
POST /ers/config/guestuser
{"GuestUser": {
  "guestType": "Contractor (default)",
  "portalId": "<sponsor portal id from ise_list_sponsor_portals>",
  "guestInfo": {"userName": "GST-guest1", "firstName": "...", "lastName": "...",
                "emailAddress": "...", "company": "...", "notificationLanguage": "English"},
  "guestAccessInfo": {"fromDate": "MM/DD/YYYY HH:MM", "toDate": "MM/DD/YYYY HH:MM",
                      "validDays": 3, "location": "San Jose"}}}
# GET /ers/config/guestuser/{id}  and  DELETE  also work as the sponsor.
```

Result (live): guest `GST-guest1` created, `status = AWAITING_INITIAL_LOGIN`, password
auto-generated, then read back and deleted — all authenticated as the sponsor.

## Gotchas (from live validation)

- **`canAccessViaRest` is the gate.** Off by default on the built-in sponsor groups;
  `ise_enable_sponsor_rest_access` flips it (it's a benign permission — revert with
  `enable=False` if you're restoring a shared ISE to its default).
- **Guest create needs sponsor credentials.** The `ise` MCP server authenticates as
  admin, so the dedicated `ise_create_guest_user_raw`/`ise_delete_guest_user` tools
  401 through it — drive them with a second `ISEClient` built from the sponsor's
  username/password (Bash + `uv run python`).
- **`fromDate`/`toDate` are mandatory** (`MM/DD/YYYY HH:MM`); `validDays` alone isn't
  enough.
- **Omit the guest `password`** and let ISE auto-generate it per the portal's password
  policy — a caller-set password is validated hard against that policy and usually
  rejected (`Your password does not meet the password policy requirements`), even for
  long random strings.
- **BYOD / CWA** (device registration, web-auth redirect) need a real supplicant + a
  browser redirect flow — not feasible with Linux-only CML endpoints; a Windows client
  VM would be required.
