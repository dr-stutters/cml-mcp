# Wireless NAC Lab — end-to-end runbook

A repeatable build of **wireless 802.1X Network Access Control** against Cisco ISE
in CML. Because of a hard CML constraint (below), wireless NAC splits into **two
real-but-separate paths**, both validated:

1. **Program a Catalyst 9800-CL WLC** (WLANs, AAA→ISE, policy/tags) over **RESTCONF**
   via the `wlc` MCP, and onboard it as an ISE NAD. Proven with `test aaa … new-code`
   → Access-Accept (the C9800↔ISE RADIUS path), with no AP joined.
2. **Live wireless 802.1X → ISE** via CML's **hostapd AP ↔ wpa_supplicant client**
   (real EAP over simulated RF; **hostapd is the authenticator/NAD**, not the C9800).
   Proven end-to-end: client EAP-SUCCESS (PEAP-MSCHAPv2) → ISE Access-Accept.

> **The hard CML reality (read first):** CML's `wireless-ap` node runs **hostapd**
> and `wireless-client` runs **wpa_supplicant** over simulated radios
> (`mac80211_hwsim`). **hostapd does NOT speak CAPWAP, so it never joins the
> Catalyst 9800.** In pure CML you therefore **cannot** have a client authenticate
> *through* the C9800 to ISE — hence the two paths. This was confirmed empirically
> (the C9800's AP-oper is empty; only a *physical* AP bridged into the C9800-CL via
> external connectivity does a real CAPWAP join). Both paths are real and reusable;
> the WLC MCP is valuable for any real C9800 even though CML can't give it a client.

> **Orchestration:** the main session runs the stages and fans work to
> **wireless-engineer** (C9800 via `mcp__wlc__*`, hostapd/supplicant via SSH/pyATS)
> and **ise-engineer** (NAD onboarding, live sessions). ISE is an external VM on the
> underlay; the C9800, AP, and client are CML nodes.

## What it builds

```
                                   Cisco ISE 3.5 (PAN/PSN/MnT)
                                   198.18.134.35  (ise35)
                                          │
        ┌──────────────  underlay 198.18.128.0/18 (System Bridge) ──────────────┐
        │                                                                       │
   ┌────┴───────────────────┐                          ┌────────────────────────┴───┐
   │  Path 1: config only    │                          │  Path 2: live 802.1X        │
   │                         │                          │                             │
   │   WLC-1  Cat9800-CL     │  RADIUS (test aaa)       │   AP-1  hostapd  ens2 ──┐    │
   │   Vlan1 = 198.18.128.70 │ ───────────────────────▶ │   198.18.128.71  (NAD)  │    │
   │   (RESTCONF :443)       │     ISE NAD:             │            │ wlan0 (RF)  │    │
   │   ISE NAD: WLC-1-c9800  │     WLC-1-c9800          │      ~~~ mac80211_hwsim ~~~   │
   └─────────────────────────┘                          │            │ wlan0        │  │
                                                        │   CLIENT-1 wpa_supplicant   │
                                                        │   (PEAP-MSCHAPv2, wifiuser) │
                                                        └─────────────────────────────┘
```

## Prerequisites

- **CML 2.10+** with a `cat9800` (Catalyst 9800-CL) image, and the wireless beta
  node types `wireless-ap` (hostapd) + `wireless-client` (wpa_supplicant). The
  **System Bridge** external connector must be bridged to the underlay
  `198.18.128.0/18`.
- **Cisco ISE** reachable on the underlay (3.5 used here, `198.18.134.35`). ERS
  enabled (Admin ▸ System ▸ Settings ▸ API Settings). MCP: the `ise35` server.
- The `cml`, `ise`, and `wlc` MCP servers wired into `.mcp.json`. The `wlc` server
  points at the C9800 (`WLC_URL=https://198.18.128.70`, `admin`/`Cisc0123#`).

Lab values used below (**adjust for your environment**): C9800 `198.18.128.70`
(mgmt on the **Vlan1 SVI**), hostapd AP `198.18.128.71`, ISE `198.18.134.35`,
RADIUS shared key `WLCsecret123`, internal test user `wifiuser` / `WifiP@ss123`,
WLAN/SSID `nac-corp`.

---

## Stage 0 — Wireless NAC lab (topology)  → cml-lab-architect

**Topology-as-code:** [`topology.yaml`](topology.yaml) in this folder is the
validated spec — one `build_lab_from_spec` call rebuilds the whole lab (with the
corrected C9800 day-0 already baked in, so Stage 1 becomes a verification). The
prose below describes the same build:

Build a lab "Wireless NAC" on the `198.18.128.0/18` underlay:

- **WLC-1** (`cat9800`, 6 GB / 2 vCPU) — day-0 `iosxe_config.txt`: hostname,
  `aaa new-model`, a priv-15 local user (`admin`/`Cisc0123#`), `ip http
  secure-server`, `restconf`, `netconf-yang`. **Do NOT put the mgmt IP on Gi1** — see
  Gotchas; it goes on **Vlan1**. Gi1 → System-Bridge connector.
- **AP-1** (`wireless-ap`, hostapd) — `ens2` (wired) → System-Bridge connector,
  static `198.18.128.71/18`; `wlan0` is the simulated radio (no drawn link — RF is a
  shared medium via the host relay).
- **CLIENT-1** (`wireless-client`, wpa_supplicant) — `wlan0` simulated radio.
- **Start every external connector** (they come up `DEFINED_ON_CORE`) or nothing
  reaches the underlay — see Gotchas.

Boot times: C9800 BOOTED ~5 min; **RESTCONF (nginx) lags boot by minutes** — poll
`wlc_check`.

---

## Stage 1 — Fix the C9800 mgmt plane (the make-or-break)  → wireless-engineer

The Catalyst 9800-**CL** is switch-based: its `GigabitEthernet` ports are **L2
switchports in VLAN 1** and cannot take `ip address` directly. Put mgmt on the SVI
and add a default route so it can reply off-subnet:

```
interface Vlan1
 ip address 198.18.128.70 255.255.192.0
 no shutdown
ip route 0.0.0.0 0.0.0.0 198.18.128.1
```

Confirm RESTCONF is up (`wlc_check` → 200, reports IOS-XE 17.18). `write memory`.

## Stage 2 — Onboard the C9800 as an ISE NAD  → ise-engineer

```
ise_create_network_device(name="WLC-1-c9800", ip="198.18.128.70",
                          radiusSharedSecret="WLCsecret123")
```

## Stage 3 — Program the C9800 (Path 1, RESTCONF)  → wireless-engineer

Via the `wlc` MCP (RESTCONF over `https://198.18.128.70/restconf/data`,
`application/yang-data+json`). The dedicated create-tools' YANG bodies are accepted
as-is on IOS-XE **17.18** (validated):

1. **RADIUS server → ISE** — `wlc_create_radius_server(name="ISE35",
   ip="198.18.134.35", key="WLCsecret123")` → native
   `Cisco-IOS-XE-native:native/radius`.
2. **AAA group** — `wlc_create_aaa_radius_group(name="ISE-GROUP", servers=["ISE35"])`.
3. **dot1x method list** — `wlc_create_dot1x_method_list(name="default",
   group="ISE-GROUP")` (`aaa authentication dot1x default group ISE-GROUP`). Also set
   `aaa authentication login default local` so you don't lock out the vty.
4. **WPA2-Enterprise WLAN** — `wlc_create_wlan_dot1x(profile="nac-corp",
   wlan_id=1, ssid="nac-corp")` → `Cisco-IOS-XE-wireless-wlan-cfg` (auth-key-mgmt
   dot1x, wpa2-enabled). Confirm with `wlc_list_wlans`.

> Equivalent CLI (what RESTCONF writes), if you drop to pyATS: `radius server ISE35
> / address ipv4 198.18.134.35 auth-port 1812 acct-port 1813 / key WLCsecret123`;
> `aaa group server radius ISE-GROUP / server name ISE35`; `aaa authentication dot1x
> default group ISE-GROUP`. (The C9800 logs a harmless "RADIUS without TLS" warning.)

## Stage 4 — Prove the C9800↔ISE RADIUS path (no AP needed)  → wireless-engineer

```
test aaa group ISE-GROUP wifiuser WifiP@ss123 new-code
```

Expect **"User successfully authenticated"** (username `wifiuser`) — that IS the ISE
Access-Accept. `new-code` is required (the modern `test aaa` syntax). `wifiuser` is
an ISE internal user (`ise_create_internal_user`); All_User_ID_Stores accepts it.

## Stage 5 — Live wireless 802.1X → ISE (Path 2, hostapd)  → wireless-engineer

Onboard the **hostapd AP's IP** (`198.18.128.71`) as a *second* ISE NAD (its own
shared secret). SSH to AP-1 (`cisco`/`cisco`) and rewrite `/home/cisco/hostapd.conf`
to WPA2-Enterprise:

```
 interface=wlan0
driver=nl80211
ssid=nac-corp
ieee8021x=1
wpa=2
wpa_key_mgmt=WPA-EAP
auth_server_addr=198.18.134.35
auth_server_port=1812
auth_server_shared_secret=<AP-NAD-secret>
own_ip_addr=198.18.128.71
```

SSH to CLIENT-1 and set `/home/cisco/wpa_supplicant.conf` to EAP (PEAP-MSCHAPv2,
identity `wifiuser` / password `WifiP@ss123`, `key_mgmt=WPA-EAP`). Restart hostapd,
run `wpa_supplicant -i wlan0 -c …` and associate.

**Verify (three-sided):** `wpa_cli status` = `COMPLETED`; the hostapd log shows
`RADIUS Access-Accept` / `EAP-SUCCESS`; ISE shows the auth
(`ise_session_by_username wifiuser` / `ise_active_sessions`) from the hostapd NAS IP.

---

## Verification (both paths)

| Path | Evidence |
|---|---|
| **1 — C9800 config** | `wlc_check` → 200 (IOS-XE 17.18); `wlc_list_wlans` shows `nac-corp`; C9800 is ISE NAD `WLC-1-c9800`; `test aaa group ISE-GROUP wifiuser … new-code` → "User successfully authenticated". |
| **2 — Live wireless** | client `wpa_cli status`=COMPLETED; hostapd log Access-Accept/EAP-SUCCESS; ISE MnT session for `wifiuser` from the hostapd NAS. |

## Teardown

Delete the two ISE NADs (`ise_delete_network_device` for `WLC-1-c9800` + the AP
NAD) and the internal test user; stop/wipe/delete the CML lab. (Specialists never
delete labs — the main session does.)

## Gotchas (hard-won)

- **hostapd ≠ CAPWAP.** The single biggest one: the CML AP never joins the C9800.
  Don't expect a client through the controller in pure CML. Flag this in every
  wireless summary.
- **C9800-CL mgmt IP goes on `Vlan1`, not `Gi1`.** Gi ports are L2 switchports
  (`show interfaces Gi1 switchport` → "Switchport: Enabled, static access, VLAN 1").
  `ip address` on Gi1 is rejected ("% Invalid input"). Put it on the `Vlan1` SVI.
- **Add a default route** (`ip route 0.0.0.0 0.0.0.0 198.18.128.1`). Without it the
  C9800 can't reply to off-subnet hosts (e.g. the MCP host), so RESTCONF times out
  even though the SVI is up.
- **RESTCONF (nginx) lags the boot** by minutes — a first `WLCConnectionError` /
  `000` usually means yang-management isn't up yet. Poll `wlc_check`; don't reboot.
- **Start the external connectors.** They come up `DEFINED_ON_CORE`; if left
  stopped, the C9800/AP can't reach ISE or the host at all.
- **`test aaa` needs `new-code`.** The legacy syntax is gone on IOS-XE 17.18.
- **Two ISE NADs**, both → ISE 3.5: the C9800 (`198.18.128.70`) for Path 1 and the
  hostapd AP (`198.18.128.71`) for Path 2 — different source IPs, so ISE needs both.
- **CML wireless is 2.10 beta.** The RF link + hostapd/supplicant path is the
  higher-risk part; the WLC-MCP/config path is low-risk and deterministic.
