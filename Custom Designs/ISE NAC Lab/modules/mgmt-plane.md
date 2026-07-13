# Module — NAC management plane on the cat9000v (RADIUS + CoA sourcing)

Layers onto the [base runbook](../runbook.md). Covers **how the access switch sources
RADIUS (auth) and CoA to ISE**, and the cat9000v gotcha that shapes it. Resolves the
long-standing "Mgmt-vrf" question (#18) with three approaches, validated live against
ISE 3.5 on `SW-ISE35`.

## The cat9000v gotcha (proven, with evidence)

On the Catalyst 9000, the **auth-manager / SMD** (Session Manager Daemon — the process
that runs MAB/dot1x sessions) sends its RADIUS from the **data plane (FED)**. The
dedicated **OOB management port `GigabitEthernet0/0` (the built-in `Mgmt-vrf`) is
control-plane only** — IOSd features traverse it, the SMD cannot.

Empirical proof (moving RADIUS source to Gi0/0/Mgmt-vrf):
- `ping vrf Mgmt-vrf <ISE>` → **100%, 1 ms** (IOSd reachability is perfect)
- IOSd `show aaa servers` → `State: UP`
- but `Platform State from **SMD**: down`, `%RADIUS_AUDIT_MESSAGE...sessmgrd: RADIUS
  server not responding`, **20 auth timeouts**, MAB stuck `Running / Unauthorized`.

**Conclusion:** it was never routing or aaa config — the OOB `Mgmt-vrf` **cannot**
carry MAB/dot1x session RADIUS on the cat9000v. RADIUS for NAC must egress a
**front-panel** L3 interface (global table or a *user-defined* VRF — both are
data-plane).

## Approach A — front-panel SVI in the global table (simple)

The original validated pattern. A front-panel access port to the underlay + a global
SVI as the NAD source IP:

```
interface GigabitEthernet1/0/1
 switchport access vlan 100
interface Vlan100
 ip address 198.18.128.66 255.255.192.0
aaa group server radius ISE-GROUP
 ip radius source-interface Vlan100
aaa server radius dynamic-author
 client 198.18.134.35 server-key ISEsecret123
```

Works, minimal config. NAC RADIUS shares the global/user table (no VRF separation).

## Approach B — in-band management VRF (real-world, recommended)

What production access-switch NAC actually looks like: a **dedicated management VRF on
a front-panel SVI**, so RADIUS/CoA/mgmt are VRF-separated from the user/global table —
*and* it works with the SMD (front-panel = data-plane). This is the canonical config on
`SW-ISE35` now, MAB + CoA both validated:

```
vrf definition MGMT
 address-family ipv4
 exit-address-family
interface Vlan100
 vrf forwarding MGMT
 ip address 198.18.128.66 255.255.192.0
ip route vrf MGMT 0.0.0.0 0.0.0.0 198.18.128.1
aaa group server radius ISE-GROUP
 ip vrf forwarding MGMT
 ip radius source-interface Vlan100
aaa server radius dynamic-author
 client 198.18.134.35 vrf MGMT server-key ISEsecret123
 auth-type any
```

Key points:
- The **NAD source IP is unchanged** (198.18.128.66), so the ISE network-device entry
  still matches — no ISE-side change needed.
- **CoA client carries the vrf on its own line** (`client <ip> vrf MGMT server-key …`)
  so the inbound CoA is processed in the MGMT VRF. Validated: an ISE MnT
  `CoA/Reauth` returned `results: true` (the NAD ACKed the CoA over the VRF).
- Moving an SVI into a VRF **flushes its ARP** — the first ping after the change may
  show 0% while ARP re-resolves; it recovers immediately.
- The OOB `Gi0/0`/built-in `Mgmt-vrf` can stay for pure box management (SSH/SNMP) — it
  just can't carry the session RADIUS.

## What NOT to do — the built-in OOB Mgmt-vrf

Don't source NAC RADIUS from `GigabitEthernet0/0` / the built-in `Mgmt-vrf` — the SMD
can't egress it and MAB will hang in `Running` (see the gotcha above). This is a real
Catalyst 9000 trait, not a CML artifact.

## Verification

`show access-session interface <port> details` → `Status: Authorized`, `mab Authc
Success`; `show aaa servers` → `Platform State from SMD: UP`, no new timeouts; an ISE
`CoA/Reauth` for the endpoint → `results: true` and the session reauthorizes in place.
