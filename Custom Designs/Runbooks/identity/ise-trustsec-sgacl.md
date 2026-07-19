---
id: identity/ise-trustsec-sgacl
category: identity
agent: ise-engineer
human: none
requires: [trustsec.sgts, trustsec.sgt-assignment]
provides: [trustsec.sgacls, trustsec.enforcement]
params: [src_sgts, dst_sgt, sgacl]
est: 25m
---

# identity/ise-trustsec-sgacl

> **Phase B** of TrustSec: destination classification + **SGACL egress enforcement**
> on top of Phase A (per-group Employees SGTs, see `ise-trustsec-sgt.md`). Builds
> the shared ISE objects once (dest SGT, SGACL, egress-matrix cells) then makes each
> edge enforce. Proven live on 3 labs against ISE 3.5.0.527: **traditional switch**
> (global table), **SDA-CLI fabric edge**, **SDA-CatC fabric edge** — a clean
> permit->deny ping flip with **HW-Denied** counters on every architecture, plus the
> **propagation divergence** finding (fabric enforces at the edge with no SXP;
> traditional needs SXP to share the tag off-box).

## Preflight — assert `requires`
- [ ] `trustsec.sgts` + `trustsec.sgt-assignment` (Phase A): the source SGTs exist and
      an authenticated session already classifies each Employees host (a LOCAL
      `cts role-based sgt-map` binding on its edge — verify per lab). Phase B does
      **not** touch the Phase A authZ rules or the live 802.1X sessions.
- [ ] `cts role-based enforcement` present on each edge. **Not guaranteed** — a
      CatC-managed edge may be missing it (it was, on lab 2); add it (drift, note it).
- [ ] The Servers hosts have **no supplicant** → they are classified by **static
      IP-SGT**, not a RADIUS session.

## Build — shared ISE objects (once)

### 1. Destination SGT
```
ise_create_sgt(name="Servers", value=200)      # names: alphanum/underscore only
```

### 2. SGACL (selective: deny the probe, permit the rest)
```
ise_create_sgacl(body='{"Sgacl":{"name":"Emp_to_Srv_Restrict",
  "description":"Phase B Employees to Servers deny icmp then permit ip",
  "aclcontent":"deny icmp\npermit ip","ipVersion":"IPV4"}}')
```
`deny icmp` **then** `permit ip` — proves enforcement by a clean ICMP flip while
leaving the segment otherwise open (TCP/UDP still pass -> HW-Permitt).
**GOTCHA:** ISE's ERS content filter rejects `()`, `-`, `<`, `>`, `%` in the
`description` with `400 Validation Error - Harmful content found`. Keep SGACL/object
descriptions to plain words. (The `aclcontent` with `\n` is fine.)

### 3. Egress-matrix cells (source Employees SGT -> dest Servers)
One cell per lab: `100->200`, `110->200`, `120->200`, all referencing the SGACL.
**GOTCHA:** the ERS egress-matrix POST **cannot** go through `ise_ers_call` — the MCP
layer coerces a JSON-object `body` into a dict and pydantic rejects it (same blocker as
condition-bearing authZ rules). Push it with **httpx + a typed JSON body** (helper:
`scratchpad/ise_call.py`, run with `/home/reptar/MCP/ISE_MCP/.venv/bin/python`):
```
POST /ers/config/egressmatrixcell
{"EgressMatrixCell":{"sourceSgtId":"<EmpSgtId>","destinationSgtId":"<ServersSgtId>",
 "matrixCellStatus":"ENABLED","defaultRule":"NONE","sgacls":["<sgaclId>"]}}
```
ISE auto-names each cell `<SrcSgt>-<DstSgt>` (e.g. `Lab3_Employees-Servers`). Verify
with `ise_list_egress_matrix` (ANY-ANY default + your 3 cells).

## Enforce — get the policy onto each edge

Two methods. **Prefer ISE-download (full CTS)**; fall back to **local** if PAC
enrollment is flaky (it was, in the rebuilt env — see below). Enforcement is identical
either way once the policy + both bindings are on the box.

### Classify the Servers host (static IP-SGT, local sgt-map)
```
# traditional (global table):
cts role-based sgt-map <server-ip> sgt 200
# fabric edge (endpoint VRF):
cts role-based sgt-map vrf CAMPUS_VN <server-ip> sgt 200
```
Shows as `<server-ip>  200  CLI` in `show cts role-based sgt-map [vrf ...] all`.
(Lab 2 is CatC-managed; CatC does **not** own SGT static maps, so a local sgt-map is a
small acceptable classification add — but it **is** out-of-band drift, note it.)

### Method A — ISE download (full CTS)  *[preferred; failed PAC in rebuilt env]*
1. On the NAD in ISE, set `trustsecsettings.deviceAuthenticationSettings`
   (`sgaDeviceId` + `sgaDevicePassword`) via an ERS `PUT /ers/config/networkdevice/<id>`
   (the notification fields are **misspelled** in the schema:
   `downlaodEnvironmentDataEveryXSeconds`, `downlaodPeerAuthorizationPolicyEveryXSeconds`).
2. On the switch:
   ```
   aaa authorization network CTS-AUTH group <radius-group>
   cts authorization list CTS-AUTH
   cts credentials id <sgaDeviceId> password <sgaDevicePassword>   # exec, not config
   cts refresh environment-data
   ```
3. Verify: `show cts environment-data` = `Last status = Succeeded` + SGT name table;
   `show cts pacs` shows a PAC; `show cts role-based permissions` shows the downloaded
   cell. Then it enforces.
- **Result here:** the switch retrieved the CTS server A-ID (`show cts server-list` ->
  `198.18.134.35 ... Status = ALIVE`) but **EAP-FAST PAC provisioning + env-data
  download `Failed`** on all three virtual cat9000v edges (no PAC installed). CTS/PAC
  enrollment is unreliable in this rebuilt env -> used Method B.

### Method B — local static CTS  *[used; reliable, no PAC/env-data]*
Local RBACL + local permissions are fully static — they do **not** need env-data or a
PAC:
```
ip access-list role-based Emp_to_Srv_Restrict
 deny icmp
 permit ip
!
cts role-based enforcement                         # add if missing (lab 2 needed it)
cts role-based permissions from <EmpSGT> to 200 ipv4 Emp_to_Srv_Restrict
```
The `cts role-based permissions` matrix + `ip access-list role-based` are **global**
(not per-VRF); the sgt-map bindings + `enforcement` cover routed traffic in every VRF.
Clean up the failed download loop (`no cts authorization list ...`, `clear cts
credentials`) so `show cts environment-data` isn't stuck `Failed`.

## Verify — prove `provides` (per lab, the money shot)
1. `show cts role-based sgt-map [vrf CAMPUS_VN] all` -> Employees host `<n> LOCAL`
   **and** Servers host `200 CLI`.
2. `show cts role-based permissions from <EmpSGT> to 200 ipv4` -> `Emp_to_Srv_Restrict`.
3. `clear cts role-based counters`, then from the **Servers host** `ping -c4
   <Employees-host>` (or Employees->Servers) — baseline **N/N** now flips to **0/N,
   100% loss**.
4. `show cts role-based counters from <EmpSGT> to 200` -> **HW-Denied increments**
   (ICMP), while a non-ICMP flow (e.g. `wget http://<server>:80` -> `Connection
   refused`) is permitted and bumps **HW-Permitt** — proving the SGACL is *selective*.

**Proven:** L3 trad `120->200` HW-Denied=6 / HW-Permitt=1; L1 SDA-CLI `100->200`
HW-Denied=8; L2 SDA-CatC `110->200` HW-Denied=8. Ping 4/4 -> 0/4 on all three.

**Fabric first-packet slow-path (GOTCHA):** on a fabric edge the **very first** packets
of a new flow are punted to software while LISP resolves the map-cache (tell-tale
2-3 s / 400-900 ms latency) and that slow path **bypasses the HW SGACL**, so the first
ping of a just-configured flow can *pass* even though enforcement is active. Steady
state is fully denied and **HW-Denied is authoritative** — re-run the ping once the flow
is warm, or trust the counter.

## Propagation divergence — fabric vs traditional (the payoff)
- **Fabric (SDA-CLI, SDA-CatC):** the Employees SGT is known at the enforcing edge
  (LOCAL binding from the on-edge session; carried inline in the fabric, no off-box
  protocol). `show cts sxp connections` on both edges = **SXP Disabled, no
  connections** — enforcement needs **no SXP**.
- **Traditional:** the SGT lives as a LOCAL binding on the one switch. To share it
  off-box you need **SXP**. Configure the switch as **speaker** to ISE (**listener**):
  ```
  cts sxp enable
  cts sxp default source-ip <switch-src-ip>
  cts sxp default password <pw>
  cts sxp connection peer <ise-ip> password default mode local speaker
  ```
  then `ise_create_sxp_connection(sxp_peer=<switch-src-ip>, ise_node=<node>,
  ise_node_ip=<ise-ip>, sxp_mode="LISTENER")`. Verify `show cts sxp connections`
  (Speaker, peer, status) + `ise_list_sxp_connections`.
  **Enabling the ISE SXP service IS API-drivable:** `PUT /api/v1/deployment/node/<h>`
  with `{"roles":["Standalone"],"services":["Profiler","Session","SXP"]}` turns the SXP
  persona on (the MCP coerces an object body -> push via the httpx helper). Until then
  `ise_create_sxp_connection` 400s `SXP service is turned off on node with hostname:<n>`.
  It **restarts ISE app services** (a standalone all-in-one -> RADIUS/Session bounce,
  ~5-15 min); in practice the switches' *already-authorized* 802.1X sessions **survived**
  the restart (LOCAL Employees bindings persisted, no re-auth needed) — but plan for a
  brief drop and **poll `ise_check_surfaces`/deployment GET, never a blocking sleep**.
  Confirm the listener is up: `GET /api/v1/trustsec/sxp/node` (node bound, e.g.
  `eth0@<ise-ip>`) + `GET /api/v1/node/<h>/sxp-interface`.
  **GOTCHA — the global SXP password is GUI-only:** there is **no** OpenAPI/ERS endpoint
  for the TrustSec *Default/Global SXP Password* (`/api/v1/trustsec/sxp/settings`,
  `/ers/config/sxpsettings`, ... all 404) and the ERS `sxpconnection` carries **no
  per-connection password**. If ISE's global SXP password doesn't match the switch's
  `cts sxp default password`, the peer sticks at **Pending_On** (TCP-MD5 fails) or flips
  to **Off** (TCP up, SXP OPEN rejected) and you **cannot fix it via API** — set it in
  the GUI (Work Centers ▸ TrustSec ▸ Settings ▸ SXP Settings ▸ Default SXP
  Password) to match, then the peer reaches **On** within one retry cycle (≤120 s) and
  the switch's LOCAL/CLI bindings export to ISE (ISE, as LISTENER, learns them). A
  standalone ISE may already carry a global SXP password from a prior lab, so neither
  `none` nor a fresh value matches until you set it explicitly.
  **GOTCHA — a trailing space in the global SXP password silently breaks TCP-MD5.** A
  hidden/trailing space when typing the password makes the TCP-MD5 key differ, so the SYN
  is never accepted and the peer cycles `Pending_On → Off` with no obvious error. Tell
  (from `debug cts sxp conn/message/error`): `socket_connect ... in progress` then ~30 s
  later `socket_recv failed ... errno = 257` → `TRP_TCP_CLOSE` — a SYN that *times out* =
  MD5 mismatch (vs `Off` with `TCP conn fd: 1` = TCP up / OPEN rejected). Re-type cleanly,
  or set both ends to `password none` to remove the variable while isolating other issues.
  **HARD BLOCKER (2026-07-19, rebuilt CML) — SXP v5 ↔ v4 version wall, not fixable in CML.**
  With the password fully removed (both ends `none`, TCP up `fd:1`) the peer **still** never
  reaches `On` — it cycles `Pending_On/Off` at `Conn version: 5`. Root cause: the virtual
  **cat9000v (IOS-XE 17.18) SXP speaker is hard-wired to v5 with no command to cap it**
  (`cts sxp version 4` → `% Invalid input`; nothing in `show run all | include cts sxp`),
  while **ISE 3.5's SXP listener maxes at V4** (device SXP-version dropdown offers ≤ V4, no
  V5, cannot be cleared for auto-negotiate), and the two do **not** negotiate down. So in
  CML the switch→ISE SXP session cannot complete and the LOCAL binding does not export to
  ISE. This is a virtual-platform interop limit (same family as the cat9000v virtual-crypto
  limits, e.g. TACACS-over-TLS PSK-only), **not** a config error — roles, TCP, password, and
  the ISE listener registration + persona are all correct. The **propagation divergence is
  still fully demonstrated**: the traditional lab is configured end-to-end for SXP and
  actively peering (vs the fabric's inline, no-SXP path); only the final ISE-learned binding
  is blocked by the version gap. On real hardware (overlapping SXP versions) the same config
  completes.

## Rollback (enforcement reversible; Phase A untouched)
- ISE: delete the 3 egress cells (`DELETE /ers/config/egressmatrixcell/<id>`),
  `ise_delete_sgacl(<id>)`, `ise_delete_sgt(<ServersId>)` (only after the cells are
  gone). Optionally strip the NAD `trustsecsettings` (inert without a PAC).
  `ise_delete_sxp_connection(<id>)` if created.
- Switch (each edge): `no cts role-based permissions from <EmpSGT> to 200 ipv4
  Emp_to_Srv_Restrict`, `no ip access-list role-based Emp_to_Srv_Restrict`, `no cts
  role-based sgt-map [vrf CAMPUS_VN] <server-ip> sgt 200`; on L3 `no cts sxp ...`. Leave
  `cts role-based enforcement` (Phase A) in place except where you added it.

## Gotchas (summary)
- ERS description content filter rejects `() - < > %` -> "Harmful content found".
- Egress-matrix ERS POST can't go via `ise_ers_call` (dict coercion) -> httpx typed body.
- Virtual cat9000v EAP-FAST **PAC provisioning is unreliable** (env-data `Failed` even
  though the CTS server shows ALIVE) -> local static CTS is the reliable fallback and
  needs no PAC/env-data.
- Fabric first-packet LISP slow-path bypasses the HW SGACL -> trust HW-Denied, not the
  first ping.
- CatC-managed edge may lack `cts role-based enforcement` and doesn't own static
  sgt-maps -> both are out-of-band drift (a Sync would revert them).
- ISE SXP needs the SXP persona **service** enabled on the node (service restart) before
  an SXP connection can be created — plan around live sessions.
