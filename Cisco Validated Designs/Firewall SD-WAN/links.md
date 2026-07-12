# Firewall SD-WAN — links

- **Cisco Validated Design (deployment guide):**
  https://www.cisco.com/c/en/us/td/docs/security/secure-firewall/cvd/secure-firewall-sdwan-deployment-guide.html

> Scope note: this is **Secure Firewall Threat Defense's native SD-WAN**
> (FMC-managed WAN interfaces, ECMP zones, path monitoring, application-aware
> policy-based routing, direct internet access) — **not** Cisco Catalyst
> SD-WAN (vManage/vSmart/vBond/cEdge).

- **Deployment/config guide (detailed FMC procedures):**
  `firewall-sd_wan-deployment.pdf` (in this folder) — Route-based VPN hub &
  spoke (DVTI/SVTI), OSPF/BGP over the tunnel, backup VTI + ECMP, DIA with
  PBR + path monitoring, and the SD-WAN wizard. Written for the FMC GUI.

<!-- Add related links below (config guides, feature docs, release notes). -->
