---
id: access/endpoint-hosts
category: access
agent: ise-engineer
human: none
requires: [access.dot1x, ad.users]
provides: [endpoints.authenticated]
params: [endpoints]
est: 10m
---

# access/endpoint-hosts

> Alpine endpoints + wpa_supplicant supplicants (MAB / PEAP-AD; EAP-TLS is open item A1).

## Preflight — assert `requires`
- [ ] `access.dot1x`
- [ ] `ad.users`

## Steps
- **MAB (baseline, no supplicant)** — the endpoint just needs to put its MAC on the port. Register the MAC in
  an ISE endpoint group (e.g. `Lab_MAB_Devices`) with **`ise_bulk_update_endpoints`** (plain create/update do
  NOT set `staticGroupAssignment`). Bring the host interface up; the switch MABs the MAC → ISE authorizes.
- **802.1X (identity)** — install a supplicant (alpine/debian `wpa_supplicant`) on the host, wired to the
  edge port. **PEAP-MSCHAPv2** authenticates an AD user (e.g. `iseuser1@mitchcloud.lab`) via
  `All_User_ID_Stores`; **EAP-TLS** uses a Mitchcloud-CA-signed client cert (mutual TLS). Both proven pre-outage.

## Verify — prove `provides`
Endpoint authenticates → the switch session is **Authorized** and ISE MnT (`ise_session_by_mac` /
`ise_recent_authentications`) shows the pass with the expected identity + authZ (later: the correct
VLAN/dACL/SGT).

## Rollback
Delete the endpoint / stop wpa_supplicant.

## Gotchas
- **Alpine host console has a shell-prompt escape (`\x1b[6n`)** that trips the pyATS prompt matcher (reports
  a timeout) — but the command still runs and output is in the buffer; verify with a follow-up read/ping.
- **cat9000v console garbles long lines** — move supplicant/cert files in ~700-byte base64 chunks and
  `tr -d '[:space:]'` on reassembly.
- `ise_bulk_update_endpoints` is the reliable path for static endpoint-group assignment.
