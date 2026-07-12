# FMC API Explorer — reference notes

The FMC REST API for complex config (VPN, VTI, routing, SD-WAN) is **not
discoverable by guessing JSON field names**. The authoritative source is the
FMC's own **API Explorer**, which serves the full OpenAPI/Swagger spec.

## Getting the spec

- **Interactive UI:** `https://<fmc>/api/api-explorer/` (log in with the FMC
  admin credentials).
- **Machine-readable spec (the useful one):**
  `GET https://<fmc>/api/api-explorer/fmc.json` — a large (~9 MB) OpenAPI 2.0
  doc. Authenticate with the `X-auth-access-token` header (same token as any
  API call).

A copy for the lab FMC is saved next to this file as
`fmc-api-explorer-spec.json` (gitignored — it's version-specific and
regenerable from the live FMC anytime).

## How to use it

```python
import json
d = json.load(open("fmc-api-explorer-spec.json"))
defs = d["definitions"]              # ~1600 models
# find a model:  [n for n in defs if "vti" in n.lower()]
# read its fields:  defs["FTDVTIInterface"]["properties"]
# find a path's POST body model:  d["paths"][<path>]["post"]["parameters"] -> in:body -> schema.$ref
```

## Key models discovered (Firewall SD-WAN build)

| Purpose | Model | Non-obvious fields |
|---|---|---|
| Physical interface | (physicalinterfaces) | `mode:"NONE"` = routed; `ifname`, `securityZone`, `ipv4.static` |
| Loopback | `LoopbackInterface` | `loopbackId`, `ipv4.static` /32 |
| VTI (DVTI/SVTI) | `FTDVTIInterface` | `tunnelId` (mandatory); borrow-IP = `ipAddressAssignmentType:"BORROW_IP_FROM_INTERFACE"` + `borrowIPfrom:{loopback}` |
| S2S VPN topology | `FTDS2SVpnModel` | `topologyType:"HUB_AND_SPOKE"`, `routeBased:true`, `ikeV2Enabled` |
| VPN endpoint | `VpnEndpoint` | needs top-level `name` + **named** device/interface refs; `peerType` HUB/SPOKE; `bgpAsNumber` |
| BGP process | `BGPIPvAddressFamilyModel` | `asNumber`, `addressFamilyIPv4` (`neighbors`, `networks`, `redistributeProtocols`) |
| BGP general | `BGPGeneralSettingModel` | `asNumber`, `routerId` |
| BGP neighbor | `INeighbors` | `ipv4Address`, `remoteAs`, `neighborGeneral` |

This technique applies to any complex FMC config, not just SD-WAN.
