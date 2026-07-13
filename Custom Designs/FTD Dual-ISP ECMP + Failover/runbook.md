# Component — FTD Dual-ISP ECMP + Failover

Add a **second WAN transport** to the SD-WAN overlay: a parallel AUTO_VPN topology
over ISP2 so every spoke has two active tunnels, **ECMP** across them, and automatic
failover. Builds on [SD-WAN Auto-VPN](../Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md).

## Build

1. On the hub: a **second loopback** (`Lo2 10.255.254.1/32`) + **second DVTI**
   (`dvti2`, source Eth0/1) + a **second `IPv4AddressPool`** on a different /24
   (`10.255.254.100-200`).
2. A **second `AUTO_VPN` topology** (ISP2): HUB endpoint = dvti2 + pool2; SPOKE
   endpoint `interface` = the spoke's **Ethernet0/1** (the ISP2 physical WAN).
3. In its `autoVpnSettings.routeSettings`, set **`enableMultiPath: true`** → FMC adds
   `maximum-paths 8` + `maximum-paths ibgp 8` to the **shared** `router bgp 65070`
   (global, so it applies to both overlays). You do **not** need
   `enableEcmpAtHub/Spoke` — just `enableMultiPath` + one topology per ISP.
4. Deploy hub + all spokes.

## Verify

```
show crypto ikev2 sa    → Tunnel1 (ISP1) AND Tunnel2 (ISP2) both up
show bgp summary        → two iBGP sessions (10.255.255.1 + 10.255.254.1)
show bgp 10.100.0.0     → "1 multipath network, 2 multipath paths" — B via BOTH next-hops
```
**Failover:** `set_link_state stop` on a spoke's ISP1 link → host-to-host ping stays
**0% loss** (rides ISP2).

## Gotchas

- **FTDv doesn't detect carrier-loss** from a CML unmanaged switch — the interface
  stays `up/up`, so failover is driven by **IPsec DPD** (peer-dead), not interface-down:
  it takes **~40-60 s** to converge (BGP neighbor → Idle, route falls to the other
  ISP). On link-restore the spoke re-initiates via IKEv2 backoff (~1-2 min) before
  ECMP re-forms.
- A spoke's own LAN prefix sometimes installs single-path on the hub (a MED/metric
  artifact of the auto-VPN OUT route-maps: permit10 metric 1 / permit20 metric 100) —
  cosmetic, failover still works.
