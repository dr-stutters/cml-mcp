# Module — Multiple VNs + inter-VN fusion routing (roadmap "B4")

Add a second L3 VN (`IOT_VN`, 172.16.20.0/24) alongside `CAMPUS_VN` (172.16.10.0/24) and
route **between** them through the **fusion router** — the macro-segmentation pattern where
inter-VN traffic *must* leave the fabric and hairpin through the fusion (the natural
insertion point for a firewall — see Wave 6 "FTD as SDA fusion firewall"). Depends on **B1**
(the border L3 handoff).

## Build the second VN (CatC Intent API — all async `taskId`)
1. **Reserve a sub-pool** off the global pool: `POST /reserve-ip-subpool/{siteId}`
   `{name:"IOT-Pool", type:"LAN", ipv4GlobalPool:"172.16.0.0/16", ipv4Prefix:true,
   ipv4PrefixLength:24, ipv4Subnet:"172.16.20.0", ipv4GateWay:"172.16.20.1"}` (returns an
   **executionId**, not a taskId → poll `/dnacaap/management/execution-status/{id}`).
2. **L3 VN** anchored: `POST /sda/layer3VirtualNetworks` `[{virtualNetworkName:"IOT_VN",
   fabricIds:[<fabricId>]}]`.
3. **Anycast gateway**: `POST /sda/anycastGateways` `[{fabricId, virtualNetworkName:"IOT_VN",
   ipPoolName:"IOT-Pool", vlanId:1022, trafficType:"DATA", isGroupBasedPolicyEnforcementEnabled:true,
   autoGenerateVlanName:true, ...false flags}]` — **omit `tcpMssAdjustment` or set 500–1440**
   (0 → `NCHS20311`). Note the auto `vlanName` (`172_16_20_0-IOT_VN`) for the port assignment.
4. **Border L3 handoff** for the new VN (same transit, new VLAN/IPs): `POST /sda/fabricDevices/
   layer3Handoffs/ipTransits` `[{networkDeviceId:<border>, fabricId, transitNetworkId:<IP transit>,
   interfaceName:"GigabitEthernet1/0/3", virtualNetworkName:"IOT_VN", vlanId:3002,
   localIpAddress:"10.1.244.5/30", remoteIpAddress:"10.1.244.6/30"}]` → border renders `Vlan3002`
   (SVI-on-trunk) + `address-family ipv4 vrf IOT_VN` eBGP to the fusion.
5. **Onboard a host**: `POST /sda/portAssignments` `[{fabricId, networkDeviceId:<edge>,
   interfaceName:"GigabitEthernet1/0/2", connectedDeviceType:"USER_DEVICE",
   dataVlanName:"172_16_20_0-IOT_VN", authenticateTemplateName:"No Authentication"}]` (SHARED-SVC).

## Fusion side (CLI) — the inter-VN routing point
```
interface GigabitEthernet3.3002
 encapsulation dot1Q 3002
 ip address 10.1.244.6 255.255.255.252
 ip nat inside
ip access-list standard NAT-FABRIC
 permit 172.16.20.0 0.0.0.255          ! external NAT for the new VN
router bgp 65000
 address-family ipv4
  neighbor 10.1.244.5 remote-as 65001  ! the border's IOT_VN handoff
  neighbor 10.1.244.5 activate
  neighbor 10.1.244.5 default-originate
```
Now the fusion's **global** table holds **both** `172.16.10.0/24` (via .1) and `172.16.20.0/24`
(via .5), so it routes between them. Inter-VN is inside→inside at the fusion, so **NAT doesn't
fire** (only inside→outside, to the /18, does).

## The inter-VN path (double hairpin)
`SHARED-SVC(IOT) → edge → border(IOT VRF, default) → fusion → border(CAMPUS VRF via Vlan3001)
→ edge → HOST1(CAMPUS)` and back. The border is transited twice (once per VN VRF) + the fusion
once — hence ~170 ms RTT. Macro-segmentation holds: the two VNs are separate VRFs in the fabric
and can only reach each other *through* the fusion (drop an FTD there to inspect/enforce).

## Verify
- eBGP: fusion `show ip bgp summary` → neighbors 10.1.244.1 (CAMPUS) **and** 10.1.244.5 (IOT), both
  PfxRcd≥1; `show ip route 172.16.20.0` + `172.16.10.0` both present.
- **Inter-VN host-to-host** (the proof): SHARED-SVC 172.16.20.10 ↔ HOST1 172.16.10.50 → **100%**
  (allow ~1 min convergence after the handoff). External from both VNs → 100%.

## Gotchas
- **Convergence lag** — right after the IOT handoff, inter-VN pings drop for ~30–60 s (BGP + host
  EID registration). Re-test before concluding.
- **Don't ping a host EID from the border sourced from the anycast GW** — the host replies to the
  *edge's* local anycast SVI, not the border, so it reads as 0% even when host-to-host works. Test
  real host-to-host.
- `tcpMssAdjustment` on the anycast gateway must be **500–1440** (or omitted).
