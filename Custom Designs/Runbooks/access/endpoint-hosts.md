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
  Re-proven **2026-07-19 on all 3 rebuild architectures** (traditional L3-ACCESS-SW, SDA-CLI fabric L1-EDGE1,
  CatC-managed L2-EDGE2) with **per-lab AD users/groups** — `lNuser1@mitchcloud.lab` ∈ `LabN-Employees` (added
  to the `mitchcloud` join point) → dot1x/PEAP → `identity_store=mitchcloud` → PermitAccess. Alpine
  `wpa_supplicant.conf` that worked: `ap_scan=0`, `key_mgmt=IEEE8021X`, `eap=PEAP`,
  `identity="user@mitchcloud.lab"`, `anonymous_identity="anonymous@mitchcloud.lab"`, `phase2="auth=MSCHAPV2"`,
  `eapol_flags=0` (server-cert validation off for the baseline); run wired: `sudo wpa_supplicant -Dwired
  -ieth0 -c<conf> -B`, verify `wpa_cli -ieth0 status` → `EAP state=SUCCESS` / `wpa_state=COMPLETED`.

## Verify — prove `provides`
Endpoint authenticates → the switch session is **Authorized** and ISE MnT (`ise_session_by_mac` /
`ise_recent_authentications`) shows the pass with the expected identity + authZ (later: the correct
VLAN/dACL/SGT).

## Rollback
Delete the endpoint / stop wpa_supplicant.

## Gotchas
- **Air-gapped Alpine host needs a package? Temporarily swing it onto the mgmt/internet net, install, swing
  back (proven 2026-07-19, all 3 labs).** The lab access VLAN has no internet, so the host can't `apk add`.
  Fix without swapping the node to Debian: `delete_link` the host's eth0↔edge link, `create_link` eth0 →
  the lab's **MGMT-SW** (the unmanaged switch that bridges to the System Bridge on `198.18.128.0/18`),
  `set_interface_state start` eth0, then on the host `sudo ip addr add <free .128.x>/18 dev eth0` +
  `sudo ip route add default via 198.18.128.1` + `echo nameserver 8.8.8.8 > /etc/resolv.conf` (**`.1` has
  real internet egress** — 8.8.8.8 + dl-cdn.alpinelinux.org reachable), `sudo apk add wpa_supplicant`.
  Then reverse: delete the temp link, recreate eth0↔edge port, start both ends, and **restore the host's
  exact lab IP + default route** (capture them first with `ip -4 addr`/`ip route`). MAB/dot1x re-authorizes
  on link-up, so the baseline is undisturbed. Note: `create_link` can't hot-**add** an interface to a running
  node ("physical configuration locked"), so **repoint the existing eth0** rather than adding an eth1.
- **Alpine host console has a shell-prompt escape (`\x1b[6n`)** that trips the pyATS prompt matcher (reports
  a timeout) — but the command still runs and output is in the buffer; verify with a follow-up read/ping.
- Write `wpa_supplicant.conf` via **base64 → `sudo tee`** so the AD password never hits the console echo.
- The supplicant runs as a backgrounded `wpa_supplicant -B` process — **not boot-persistent**; make it an
  OpenRC service (`wpa_supplicant-openrc` is pulled in by the package) if it must survive a host reboot.
- **cat9000v console garbles long lines** — move supplicant/cert files in ~700-byte base64 chunks and
  `tr -d '[:space:]'` on reassembly.
- `ise_bulk_update_endpoints` is the reliable path for static endpoint-group assignment.
