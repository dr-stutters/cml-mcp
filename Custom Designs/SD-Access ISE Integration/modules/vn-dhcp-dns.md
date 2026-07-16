# Module — Windows DHCP/DNS for the fabric VN (roadmap "B2")

Give the CAMPUS_VN (172.16.10.0/24) real DHCP + DNS off the **mitchcloud.lab DC**
(`DC01`, 198.18.130.11), so HOST1 goes from a static IP to a DHCP lease that also
registers in DNS. Depends on **B1** (the border L3 handoff — the VN must be able to
reach the external DC).

## The wrinkle: relaying to an external DHCP server across the NAT'd handoff

The DC lives on the real /18, outside the fabric; the VN reaches it only via the B1
border handoff, where FUSION **NATs** 172.16.10.0/24 → its Gi1 (198.18.128.71). A DHCP
relay's reply is sent to the **giaddr** (the anycast GW 172.16.10.1), so the server must
be able to route *back* to that. Two things make it work:

1. **DC return route** — `route -p add 172.16.10.0 mask 255.255.255.0 198.18.128.71`
   (the DC is /18, so FUSION's .71 is on-link). The DHCP OFFER to giaddr 172.16.10.1 then
   routes DC → FUSION → (BGP `172.16.10.0/24`) → border → LISP → edge.
2. **Plain `ip helper-address` on the anycast SVI works here.** Despite the giaddr being
   the *anycast* GW (owned by both edge and border), the reply came back correctly — the
   OFFER routes to the border via BGP and is delivered into the fabric. No fabric-aware
   option-82 relay or CatC network-settings push was needed for this single-VN lab. (The
   NAT on the *request* source is harmless — the server keys off giaddr, not source IP.)

## Steps

**DC01 (windows MCP):**
```powershell
Install-WindowsFeature DHCP -IncludeManagementTools           # role wasn't present
Add-DhcpServerInDC -DnsName DC01.mitchcloud.lab -IPAddress 198.18.130.11
netsh dhcp add securitygroups ; Restart-Service dhcpserver
Add-DhcpServerv4Scope -Name CAMPUS_VN -StartRange 172.16.10.50 -EndRange 172.16.10.200 -SubnetMask 255.255.255.0 -State Active
Add-DhcpServerv4ExclusionRange -ScopeId 172.16.10.0 -StartRange 172.16.10.1 -EndRange 172.16.10.49
Set-DhcpServerv4OptionValue -ScopeId 172.16.10.0 -Router 172.16.10.1 -DnsServer 198.18.130.11 -DnsDomain mitchcloud.lab
Set-DhcpServerv4DnsSetting -ScopeId 172.16.10.0 -DynamicUpdates Always -UpdateDnsRRForOlderClients $true
route -p add 172.16.10.0 mask 255.255.255.0 198.18.128.71
```

**EDGE1 (anycast SVI) — the relay:** `interface Vlan1021` → `ip helper-address 198.18.130.11` → `write mem`.

**HOST1 (alpine) — static → DHCP:** keep wpa_supplicant (802.1X must authorize the closed-auth
port *first*), then `udhcpc -i eth0 -b -t 20 -T 2 -x hostname:host1`. Persist in
`/etc/local.d/sda-endpoint.start` (see [endpoints-and-supplicant.md](endpoints-and-supplicant.md)):
`hostname host1` → wpa_supplicant → `sleep 4` → udhcpc.

## Verify
- HOST1: `udhcpc` → `lease of 172.16.10.50 obtained from 198.18.130.11`; `ip route` default via
  172.16.10.1; `nslookup dc01.mitchcloud.lab` → 198.18.130.11 (DNS works from the VN);
  `ping 198.18.134.35` (ISE) 100% with the DHCP address.
- DC: `Get-DhcpServerv4Lease -ScopeId 172.16.10.0` → 172.16.10.50 **Active**, HostName
  `host1.mitchcloud.lab`.

## Gotchas
- **DNS auto-registration for a Linux client needs the DHCP DnsCredential.** `DynamicUpdates
  Always` + `UpdateDnsRRForOlderClients` alone did **not** create the A record for the
  udhcpc client (the server won't do secure DDNS on its behalf without a configured service
  account: `Set-DhcpServerv4DnsSetting -Credential ...`). Workaround used: register the A
  record explicitly (`Add-DnsServerResourceRecordA host1 → 172.16.10.50`). Resolution from
  the fabric then works. For true dynamic DDNS, set the DHCP DnsCredential.
- **Renaming the alpine host breaks pyATS prompt-matching.** Setting `hostname host1` changes
  the shell prompt from the CML default; the existing pyATS session then times out waiting on
  the old prompt. Fix: `pyats_sessions disconnect <node>` then reconnect (it re-learns the
  new prompt). Do the rename in its own step.
- **Closed-auth ordering:** DHCP only flows *after* 802.1X authorizes the port, so
  wpa_supplicant must run before udhcpc (the boot script sequences them with a short sleep).
