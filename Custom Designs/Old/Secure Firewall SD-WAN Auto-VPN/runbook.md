# Component — Secure Firewall SD-WAN Auto-VPN

Build the **route-based SD-WAN overlay** (the FMC "SD-WAN wizard", fully via API): a
DVTI hub, an auto-created spoke SVTI, and auto-generated **iBGP** — all from one
`ftds2svpns` topology. The core of the
[Firewall SD-WAN runbook](../../Cisco%20Validated%20Designs/Firewall%20SD-WAN/runbook.md).
Driven by **firewall-engineer**; schemas from `https://<fmc>/api/api-explorer/fmc.json`.

## Prereqs on the FTDs

- WAN + inside interfaces **assigned to security zones** (OUTSIDE1/INSIDE) — else the
  auto-VPN won't treat them as VPN interfaces.
- **Hub:** a loopback (`10.255.255.1/32`) + a **DVTI** borrowing it
  (`ipAddressAssignmentType:"BORROW_IP_FROM_INTERFACE"`, `borrowIPfrom:{name,id}`).
- **Spoke:** nothing — the wizard builds the SVTI.
- An **`IPv4AddressPool`** object (`/object/ipv4addresspools`, `ipAddressRange`+`mask`,
  e.g. `10.255.255.100-200/24`) — a plain `Range` object is rejected ("not of type
  IPv4").
- FMC **export-controlled license** (`exportControl:true`) — in eval the API silently
  drops `autoVpnSettings`.

## The topology (`POST /policy/ftds2svpns`)

```jsonc
{ "topologyType": "AUTO_VPN",           // ← the real trigger. NOT "HUB_AND_SPOKE"
  "routeBased": true, "ikeV2Enabled": true,
  "autoVpnSettings": { "routeSettings": {
      "enableBgp": true, "autonomousSystemNumber": 65070,
      "communityAttribute": 1000, "communityTagToAdvertiseLearntRoutes": 1000,
      "distributeConnectedNetwork": { "enableDistribution": true,
                                      "interfaceSelection": "INSIDE_INTERFACE" } },
      "spokeSvtiSecurityZone": { <TUNNEL zone> } } }
```
With `HUB_AND_SPOKE` the FMC returns **201 but GET shows `autoVpnSettings:null`** —
the whole SD-WAN behaviour is silently dropped. Use `AUTO_VPN`.

## Endpoints

- **HUB** (`…/{tid}/endpoints`): `interface` = the pre-created **DVTI**,
  `peerType:"HUB"`, `isPrimaryHub:true`, **`ipv4PoolsForSpokeVti":[{IPv4AddressPool}]`**,
  `insideInterface:[Eth0/2]`.
- **SPOKE:** `interface` = the **physical WAN interface itself** (Ethernet0/0, in an
  OUTSIDE zone), `peerType:"SPOKE"`. FMC **auto-builds the spoke SVTI** (Tunnel1) and
  assigns its IP from the hub pool via IKEv2 mode-config. Do **not** pre-create a
  static VTI ("Static VTI cannot be selected in spoke endpoint") and do **not** pass
  only `tunnelSourceInterface` ("Missing configuration for endpoint interface"). The
  physical-WAN-as-`interface` is only accepted under AUTO_VPN.

## Deploy → what FMC generates

Deploy **hub + spoke**. FMC auto-renders the CVD's iBGP overlay:
```
router bgp 65070
 neighbor <hubTunIP> remote-as 65070
 neighbor <hubTunIP> route-map FMC_VPN_RMAP_COMMUNITY_IN/OUT
 redistribute connected route-map FMC_VPN_CONNECTED_DIST_RMAP_1000
```

## Verify

```
show crypto ikev2 sa           → Tunnel1 up, peer = hub WAN IP
show bgp summary               → neighbor <hub tunnel IP> up
NYC-HOST → spoke inside host    → 0% loss across the VTI overlay
```
