#!/usr/bin/env python3
"""Scaffold + validate the atomic-runbook catalog.

Single source of truth for the atom graph. Running this:
  * writes an atom stub `.md` for every atom that doesn't exist yet (never clobbers
    a hand-edited atom — the stub is a starting point, the atom becomes the truth);
  * (re)writes each category README (derived index — safe to regenerate);
  * (re)writes catalog.json (machine index for composition manifests);
  * validates the requires/provides DAG (every `requires` must be `provides`d by
    some atom; no cycles) and prints a topological build order.

Usage:  python3 Runbooks/_scaffold.py [--force-atoms]
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent            # .../Custom Designs/Runbooks

# ---------------------------------------------------------------- categories
CATEGORIES = {
    "foundation": dict(
        title="Foundation — the substrate",
        owns="Stands up the lab itself and the AD/DNS/PKI backing every other stack leans on. "
             "Driven by **cml-lab-architect** and **windows-engineer**.",
        prompts=[
            "Build the lab base from the sda-ise-integration topology spec",
            "I already promoted the DC by hand — just run `foundation/windows-dns` and verify it",
            "Rebuild the whole foundation category against the current addressing.yaml",
        ],
        gotchas=[
            "`build_lab_from_spec` from the deployment's topology.yaml; boot times vary wildly "
            "(IOL secs · IOSv 2-3m · cat9000v/CSR 4-6m · FTDv 5m + FDM 10-20m · FMCv 15-30m).",
            "Interfaces added to an already-running node come up STOPPED — start them before diagnosing.",
            "promote-to-DC + role installs reboot the box (WinRM drops → reconnect + re-check).",
            "AD CS: `certreq` hangs over WinRM → use the COM `ICertRequest`; EAP-TLS needs a custom "
            "clientAuth template (defaults give serverAuth OR clientAuth, not both).",
        ],
    ),
    "identity": dict(
        title="Identity — Cisco ISE",
        owns="Everything ISE: deploy, certs, AD join, NAD onboarding, policy sets, TrustSec, and the "
             "ANC quarantine that anchors Rapid Threat Containment. Driven by **ise-engineer**.",
        prompts=[
            "Run the identity stack end to end against ise.mgmt_ip from addressing.yaml",
            "ISE is already AD-joined — pick up from `identity/ise-policy-sets`",
            "Just build TrustSec: sgt → sgacl → anc",
        ],
        gotchas=[
            "ERS is off by default (GUI: Admin > System > Settings > API Settings; served on 443, not 9060).",
            "Certs: no pkcs12-terminal import; one server per IP; restart browser sessions after a cert swap; "
            "root must be `trustForClientAuth:true` for later EAP-TLS.",
            "Durable authN store = `All_User_ID_Stores`.",
        ],
    ),
    "access": dict(
        title="Access — NAD + endpoints",
        owns="The switch (RADIUS/802.1X/MAB closed-auth) and the endpoint side (wpa_supplicant). "
             "Driven by **ise-engineer** across the CML consoles.",
        prompts=[
            "Configure closed-auth 802.1X on the fabric edges and prove a session authorizes",
            "Bring up the alpine endpoints and confirm alice lands in the Employees SGT",
        ],
        gotchas=[
            "cat9000v SMD RADIUS needs a front-panel GLOBAL SVI (not Mgmt-vrf); iosvl2/ioll2-xe can't MAB.",
            "A wedged edge-auth SMD is cleared only by a RELOAD (the 'mystery outage' NAC fault).",
            "Under closed-auth the anycast SVI is autostate-tied to an authorized session on the port.",
        ],
    ),
    "fabric": dict(
        title="Fabric — SD-Access",
        owns="Underlay, LISP pub/sub overlay, anycast gateways, border handoff, fusion VRF-leak, and "
             "host onboarding. Driven by **catalyst-engineer** (CLI path; CatC provisioning is the catc/ category).",
        prompts=[
            "Build the SDA underlay then the LISP overlay and show me the map-server registrations",
            "Just do the border handoff + fusion leak so the fabric can reach shared services",
        ],
        gotchas=[
            "LISP overlay keys: `locator default-set` + pub/sub `service ipv4` → map-server syntax.",
            "`sda-host-onboard` depends on `access.dot1x` under closed-auth — the manifest orders it after.",
        ],
    ),
    "catc": dict(
        title="Catalyst Center",
        owns="Discovery into inventory, site hierarchy, network settings, ISE integration (pxGrid), and "
             "fabric provisioning (with a CLI fallback). Driven by **catalyst-center-engineer**.",
        prompts=[
            "Discover the fabric nodes into CatC inventory and get them to Managed",
            "Wire CatC to ISE and confirm ISE shows Active",
        ],
        gotchas=[
            "Every CML cat9000v defaults to serial CMLUADP → CatC dedups by serial → set a unique "
            "prod_serial_number per vswitch.xml BEFORE boot; cat8000v needs a manual >=3072-bit RSA key for SSH.",
            "pxGrid: clientAuth EKU + FQDN/DNS-resolvable CN + manual approve; watch the old-CN gotcha.",
            "CatC provisioning can block (NCSP11008) → the CLI fabric path is the verified fallback.",
        ],
    ),
    "firewall": dict(
        title="Firewall — FMC + FTD",
        owns="FMCv base, FTDv registration, interfaces/zones, the access-control policy and every depth "
             "feature (identity, IPS, malware, decryption, URL/geo/app, EVE) + the eStreamer client. "
             "Driven by **firewall-engineer**.",
        prompts=[
            "Register the FTDv to FMC and build the base ACP",
            "Add the depth features: ips, malware, decryption, url-geo-app, eve",
            "Create the eStreamer client for the Splunk box",
        ],
        gotchas=[
            "Fix FTD day-0 mode up front (ManageLocally/FmcIp); gate registration on TCP 8305, not the API.",
            "`fmc_api_call` double-parses object bodies → curl for writes; tokens expire ~30 min.",
            "Decryption logging uses `logEnd` (not logBegin → 422); `insertBefore=1` works despite a false 500.",
            "Applications endpoint ignores name filters → page the catalog (HTTP=676, HTTPS=1122); "
            "Country objects go straight into destinationNetworks (China=156).",
        ],
    ),
    "observability": dict(
        title="Observability — Splunk",
        owns="Splunk base + indexes, syslog/HEC inputs, the telemetry sources, CIM, the Cisco add-ons, "
             "and the four dashboards. Driven by **splunk-engineer** (device agents point their syslog).",
        prompts=[
            "Stand up Splunk with the ise/network/catc/health indexes and the syslog inputs",
            "Install CIM then the ISE add-on and confirm index=ise is CIM-parsed",
            "Deploy the four dashboards from the committed XML",
        ],
        gotchas=[
            "CML docker Splunk is capped at 1 CPU → use an ubuntu-KVM node; SSH is closed → app installs via "
            "Splunk Web :8000 upload; env var is SPLUNK_PASSWORD.",
            "FTD gets its OWN 5514 input (cisco:ftd:syslog) + the message_id search-time EXTRACT + DM acceleration.",
            "Security Cloud 4.0 eStreamer REST handler rejects the `password` arg → use the Add-Input UI; "
            "index default cisco_secure_fw doesn't exist → use `network`.",
            "ISE remote-logging-target name must have NO hyphens (GUI-only step, lives in syslog-sources).",
        ],
    ),
    "wireless": dict(
        title="Wireless — C9800 + hostapd",
        owns="C9800 RESTCONF config (WLAN/AAA/tags) and the live 802.1X path via CML's hostapd AP + "
             "wpa_supplicant. Driven by **wireless-engineer**. Optional stack.",
        prompts=[
            "Configure the C9800 WLAN with RADIUS to ISE",
            "Run the live hostapd 802.1X path and confirm the ISE session",
        ],
        gotchas=[
            "RESTCONF/nginx lags boot by minutes; needs aaa new-model + priv-15 user + ip http secure-server + restconf.",
            "hostapd != CAPWAP: the C9800 config path and the live RF client are two SEPARATE proofs in CML.",
        ],
    ),
    "validate": dict(
        title="Validate — acceptance",
        owns="Closes a deployment: the testing-agent authors/updates the Test Plan, runs the automated gate "
             "+ live acceptance against the deployment's declared provides, and produces a PDF Test Report.",
        prompts=[
            "Run the testing-agent against the sda-ise-integration deployment and give me the report",
        ],
        gotchas=[
            "Read-only + reversible round-trips only; failures come back as briefs, never auto-remediated.",
        ],
    ),
}

# ---------------------------------------------------------------- atoms
# (id, agent, human, requires, provides, params, est, purpose, verify, [gotchas])
A = lambda **k: k
ATOMS = [
    # ---- foundation
    A(id="foundation/cml-lab-base", agent="cml-lab-architect", human="none",
      requires=[], provides=["lab.up", "mgmt.net"], params=["topology_spec"], est="15-40m",
      purpose="Create the lab + mgmt network + external connector from the deployment topology.yaml (one build_lab_from_spec).",
      verify="Every node BOOTED, every link/interface STARTED, mgmt reachable."),
    A(id="foundation/apply-addressing", agent="cml-lab-architect", human="none",
      requires=["lab.up"], provides=["mcp.connected"], params=["addressing.yaml"], est="5m",
      purpose="Sync the deployment's mgmt IPs/hostnames from addressing.yaml into the master ../.env so every companion MCP can reach its box; reload configs.",
      verify="Each MCP server (ise/fmc/splunk/catc/wlc/windows) answers its check tool.",
      gotchas=["THE single choke point where 'new IPs everywhere' is applied — one file (addressing.yaml) drives ../.env.",
               "Secrets are set once by hand in ../.env (gitignored); this atom only writes mgmt IPs/hostnames."]),
    A(id="foundation/windows-dc-promote", agent="windows-engineer", human="none",
      requires=["mcp.connected"], provides=["ad.domain_up"], params=["ad.domain", "dc.mgmt_ip"], est="20m",
      purpose="Build the Windows Server and promote it to an AD DS domain controller.",
      verify="Domain answers AD queries; DC reachable after the promote reboot."),
    A(id="foundation/windows-dns", agent="windows-engineer", human="none",
      requires=["ad.domain_up"], provides=["dns.core"], params=["ad.domain", "dns.records"], est="5m",
      purpose="Forward/reverse zones + A/PTR records for ISE, the CA, and devices that need resolvable names.",
      verify="ISE and device FQDNs resolve both ways."),
    A(id="foundation/windows-dhcp", agent="windows-engineer", human="none",
      requires=["ad.domain_up"], provides=["dhcp.scopes"], params=["dhcp.scopes"], est="5m",
      purpose="DHCP scopes for endpoints (optional — static host onboarding doesn't need it).",
      verify="Scope active; a test lease is handed out."),
    A(id="foundation/windows-adcs-ca", agent="windows-engineer", human="none",
      requires=["ad.domain_up", "dns.core"], provides=["ca.online"], params=["ca.name"], est="10m",
      purpose="Install the enterprise AD CS CA and export its root cert (feeds ISE + FTD decryption trust).",
      verify="CA responds; root cert exported."),
    A(id="foundation/ad-users-groups", agent="windows-engineer", human="none",
      requires=["ad.domain_up"], provides=["ad.users"], params=["ad.users", "ad.groups"], est="5m",
      purpose="OUs, test users (alice/bob/carol), and groups (Employees…) the identity + firewall stacks key off.",
      verify="Users + groups queryable in AD."),
    # ---- identity
    A(id="identity/ise-deploy", agent="ise-engineer", human="none",
      requires=["mcp.connected"], provides=["ise.reachable"], params=["ise.mgmt_ip", "ise.admin_cred"], est="10m",
      purpose="Bring ISE up, base network settings, enable the API surfaces (incl. ERS).",
      verify="ise_check_surfaces all green."),
    A(id="identity/ise-certs", agent="ise-engineer", human="none",
      requires=["ise.reachable", "ca.online", "dns.core"], provides=["ise.certs"], params=["ca.name", "ise.fqdn"], est="15m",
      purpose="CSR → CA-signed system cert; import the root as trusted (clientAuth) for EAP + admin.",
      verify="CA-signed system cert active; root trusted."),
    A(id="identity/ise-ad-join", agent="ise-engineer", human="none",
      requires=["ise.certs", "ad.domain_up", "dns.core"], provides=["ise.ad_joined"], params=["ad.domain", "ad.join_user"], est="5m",
      purpose="Join ISE to AD as an external identity source.",
      verify="Join point Connected; AD groups retrievable."),
    A(id="identity/ise-nad-onboard", agent="ise-engineer", human="none",
      requires=["ise.reachable"], provides=["ise.nads"], params=["nads", "radius.secret"], est="5m",
      purpose="Add the switches/WLC as RADIUS clients (NADs) + device groups.",
      verify="NADs listed with the shared secret."),
    A(id="identity/ise-idstores-protocols", agent="ise-engineer", human="none",
      requires=["ise.ad_joined"], provides=["ise.idstores"], params=[], est="5m",
      purpose="Allowed protocols + the All_User_ID_Stores identity source sequence.",
      verify="Sequence present and selectable in policy."),
    A(id="identity/ise-policy-sets", agent="ise-engineer", human="none",
      requires=["ise.idstores", "ise.nads"], provides=["ise.policy_sets"], params=[], est="10m",
      purpose="Wired/wireless policy set(s) with authN + authZ rules (incl. the ANC_Quarantine authz rule).",
      verify="Policy set active; matches on a test auth."),
    A(id="identity/ise-authz-profiles-dacls", agent="ise-engineer", human="none",
      requires=["ise.policy_sets"], provides=["ise.authz"], params=[], est="5m",
      purpose="Authorization profiles + downloadable ACLs referenced by the authZ rules.",
      verify="Profiles + dACLs present."),
    A(id="identity/ise-trustsec-sgt", agent="ise-engineer", human="none",
      requires=["ise.reachable"], provides=["trustsec.sgts"], params=["sgts"], est="5m",
      purpose="Security Group Tags (Employees, Quarantined_Systems, Shared-Services…).",
      verify="SGTs listed."),
    A(id="identity/ise-trustsec-sgacl", agent="ise-engineer", human="none",
      requires=["trustsec.sgts"], provides=["trustsec.sgacls"], params=[], est="10m",
      purpose="SGACLs + the egress matrix that enforces segmentation between SGTs.",
      verify="Egress matrix populated."),
    A(id="identity/ise-anc", agent="ise-engineer", human="none",
      requires=["ise.reachable"], provides=["ise.anc"], params=[], est="5m",
      purpose="ANC Quarantine policy — the Rapid Threat Containment backbone (ANC apply → CoA).",
      verify="Quarantine ANC policy present; apply/clear round-trips."),
    # ---- access
    A(id="access/switch-radius-dot1x", agent="ise-engineer", human="none",
      requires=["ise.nads", "ise.policy_sets", "fabric.underlay"], provides=["access.dot1x"], params=["edge.ports"], est="15m",
      purpose="cat9000v edge: 802.1X/MAB, closed-auth policy-map, RADIUS to ISE over the global SVI.",
      verify="A dot1x/MAB session authorizes against ISE."),
    A(id="access/endpoint-hosts", agent="ise-engineer", human="none",
      requires=["access.dot1x", "ad.users"], provides=["endpoints.authenticated"], params=["endpoints"], est="10m",
      purpose="Alpine endpoints + wpa_supplicant supplicants (MAB / PEAP-AD; EAP-TLS is open item A1).",
      verify="Endpoint authenticates → lands in the correct SGT."),
    # ---- fabric
    A(id="fabric/sda-underlay", agent="catalyst-engineer", human="none",
      requires=["lab.up"], provides=["fabric.underlay"], params=["underlay.igp", "loopbacks"], est="15m",
      purpose="IGP underlay, loopbacks, p2p links across the fabric nodes.",
      verify="Underlay adjacencies up; loopbacks reachable."),
    A(id="fabric/sda-lisp-overlay", agent="catalyst-engineer", human="none",
      requires=["fabric.underlay"], provides=["fabric.overlay"], params=["fabric.roles"], est="20m",
      purpose="LISP + pub/sub; CP/border/edge roles; map-server/resolver.",
      verify="LISP sessions up; map-server registrations present."),
    A(id="fabric/sda-anycast-gw", agent="catalyst-engineer", human="none",
      requires=["fabric.overlay"], provides=["fabric.gateways"], params=["vns", "anycast_gw"], est="10m",
      purpose="Anycast gateway SVIs per VN/VLAN on the edges.",
      verify="Anycast SVI up; gateway pings."),
    A(id="fabric/sda-border-handoff", agent="catalyst-engineer", human="none",
      requires=["fabric.overlay"], provides=["fabric.handoff"], params=["border.bgp"], est="15m",
      purpose="Border external handoff (VRF-lite/BGP) toward the fusion.",
      verify="Border BGP up; fabric→outside route present."),
    A(id="fabric/fusion-vrf-leak", agent="catalyst-engineer", human="none",
      requires=["fabric.handoff"], provides=["fusion.leak"], params=["vrf_leak"], est="10m",
      purpose="Fusion router VRF route-leak (fabric VN ↔ shared services / mgmt).",
      verify="Cross-VRF reachability fabric↔shared-services."),
    A(id="fabric/sda-host-onboard", agent="catalyst-engineer", human="none",
      requires=["fabric.gateways", "access.dot1x"], provides=["fabric.hosts"], params=[], est="10m",
      purpose="Onboard hosts on edge ports (static or closed-auth) into their VN.",
      verify="Host reaches services through the fabric."),
    # ---- catc
    A(id="catc/catc-reachability", agent="catalyst-center-engineer", human="none",
      requires=["mcp.connected"], provides=["catc.reachable"], params=["catc.url", "catc.cred"], est="2m",
      purpose="Token auth + reachability (catc_check).",
      verify="catc_check returns version."),
    A(id="catc/catc-discovery", agent="catalyst-center-engineer", human="none",
      requires=["catc.reachable", "fabric.underlay"], provides=["catc.inventory"], params=["discovery.range"], est="15m",
      purpose="SSH/SNMP discovery of the fabric nodes into inventory.",
      verify="Devices reach Managed state."),
    A(id="catc/catc-site-hierarchy", agent="catalyst-center-engineer", human="none",
      requires=["catc.inventory"], provides=["catc.sites"], params=["sites"], est="10m",
      purpose="Areas/buildings/floors + assign devices to sites.",
      verify="Sites created; devices assigned."),
    A(id="catc/catc-network-settings", agent="catalyst-center-engineer", human="none",
      requires=["catc.sites"], provides=["catc.settings"], params=["ip_pools", "servers"], est="10m",
      purpose="Credentials, IP pools, per-site servers (DNS/DHCP/AAA).",
      verify="Settings applied per site."),
    A(id="catc/catc-ise-integration", agent="catalyst-center-engineer", human="gui",
      requires=["catc.reachable", "ise.certs"], provides=["catc.ise_integrated"], params=[], est="15m",
      purpose="CatC ↔ ISE integration (pxGrid + ERS).",
      verify="ISE shows Active in CatC.",
      human_note=("**You approve the pxGrid client in the ISE GUI** (pxGrid Services → pending → Approve). "
                  "No clean API alternative — pxGrid approval is GUI-gated. Watch the old-CN cert gotcha.")),
    A(id="catc/catc-fabric-provision", agent="catalyst-center-engineer", human="none",
      requires=["catc.sites", "catc.ise_integrated"], provides=["catc.provisioned"], params=[], est="20m",
      purpose="Provision the fabric via CatC (fabric site, roles, VNs) — with the CLI path as fallback.",
      verify="Fabric provisioned (or CLI-fallback parity confirmed).",
      gotchas=["If CatC provisioning blocks (NCSP11008), fall back to the CLI fabric build and verify parity."]),
    # ---- firewall
    A(id="firewall/fmc-base", agent="firewall-engineer", human="none",
      requires=["mcp.connected"], provides=["fmc.api"], params=["fmc.mgmt_ip", "fmc.cred"], est="20m",
      purpose="FMCv up, licensing, domain confirmed.",
      verify="Token + fmc_server_version."),
    A(id="firewall/ftd-register", agent="firewall-engineer", human="none",
      requires=["fmc.api"], provides=["ftd.registered"], params=["ftd.mgmt_ip", "reg.key"], est="15m",
      purpose="Register the FTDv to FMC (day-0 mode fixed up front).",
      verify="Device healthy/Managed in FMC.",
      gotchas=["Gate on the FMC's ACTIVE LICENCE MODE (fmc_license_status -> EVALUATION/REGISTERED), "
               "not on TCP 8305 - an external 8305 probe reads closed even when registration "
               "succeeds, because sftunnel is the FTD dialling OUT. Unlicensed FMC = silent "
               "REGISTRATION_FAILED after ~30s with the device record discarded."]),
    A(id="firewall/ftd-interfaces-zones", agent="firewall-engineer", human="none",
      requires=["ftd.registered"], provides=["ftd.interfaces"], params=["interfaces", "zones"], est="10m",
      purpose="Physical interfaces, security zones, routing.",
      verify="Interfaces up; zones bound."),
    A(id="firewall/ftd-acp-base", agent="firewall-engineer", human="none",
      requires=["ftd.interfaces"], provides=["ftd.acp"], params=["objects", "rules"], est="15m",
      purpose="Access-control policy + base permit/deny rules + network/host objects.",
      verify="ACP deployed; test traffic matches expected rules."),
    A(id="firewall/ftd-identity-realm", agent="firewall-engineer", human="none",
      requires=["ftd.acp", "ad.domain_up"], provides=["ftd.identity"], params=["realm"], est="15m",
      purpose="FMC↔AD realm + identity policy for user-based rules.",
      verify="Realm downloads users; a user-based rule matches."),
    A(id="firewall/ftd-ips", agent="firewall-engineer", human="none",
      requires=["ftd.acp"], provides=["ftd.ips"], params=["ips.policy"], est="10m",
      purpose="Intrusion policy (SDA-IPS) attached to the ACP.",
      verify="Intrusion event fires on a test trigger."),
    A(id="firewall/ftd-malware-file", agent="firewall-engineer", human="none",
      requires=["ftd.acp"], provides=["ftd.files"], params=["file.policy"], est="10m",
      purpose="File/malware policy (C9-Malware).",
      verify="EICAR → FileEvent SHA_Disposition=Malware."),
    A(id="firewall/ftd-decryption", agent="firewall-engineer", human="none",
      requires=["ftd.acp", "ca.online"], provides=["ftd.decrypt"], params=["resign.ca"], est="15m",
      purpose="TLS decryption: resign CA + Decrypt-Resign rule (C8) and Do-Not-Decrypt bypass (C16).",
      verify="Cert issuer proves resign vs bypass on the right destinations.",
      gotchas=["Decryption logging uses logEnd (logBegin → 422); insertBefore=1 works despite a false 500."]),
    A(id="firewall/ftd-url-geo-app", agent="firewall-engineer", human="none",
      requires=["ftd.acp"], provides=["ftd.depth"], params=[], est="15m",
      purpose="URL filtering (C12), application/AVC (C13), geolocation (C15) rules.",
      verify="App-ID block proven; URL + geo rules deployed.",
      gotchas=["Applications endpoint ignores name filters → page it (HTTP=676, HTTPS=1122); Country China=156."]),
    A(id="firewall/ftd-eve", agent="firewall-engineer", human="none",
      requires=["ftd.acp"], provides=["ftd.eve"], params=[], est="5m",
      purpose="Encrypted Visibility Engine (C14) — classify encrypted apps/threats without decryption.",
      verify="evesettings enabled:true, mode MONITOR_TRAFFIC."),
    A(id="firewall/ftd-estreamer-client", agent="firewall-engineer", human="gui",
      requires=["fmc.api"], provides=["ftd.estreamer_client"], params=["splunk.mgmt_ip", "pkcs12.pass"], est="10m",
      purpose="eStreamer client cert for the Splunk box (feeds splunk-security-cloud).",
      verify="Client created; FMC:8302 open; pkcs12 exported.",
      human_note=("**FMC GUI (your account):** Integrations → eStreamer → tick event types → Save → Create Client "
                  "for the Splunk IP + a pkcs12 password → download the .pkcs12. Then hand the file into the session. "
                  "GUI-only in FMC — no REST equivalent for client-cert export.")),
    # ---- observability
    A(id="observability/splunk-base", agent="splunk-engineer", human="none",
      requires=["mcp.connected"], provides=["splunk.up", "splunk.indexes"], params=["splunk.mgmt_ip", "splunk.cred"], est="15m",
      purpose="Splunk node up; indexes ise/network/catc/health created.",
      verify="splunk_check green; indexes exist.",
      gotchas=["Prefer an ubuntu-KVM node (docker Splunk is capped at 1 CPU in CML)."]),
    A(id="observability/splunk-syslog-inputs", agent="splunk-engineer", human="none",
      requires=["splunk.up"], provides=["splunk.inputs"], params=[], est="10m",
      purpose="UDP inputs: 514 (cisco:ios), 5514 (cisco:ftd:syslog), 20514 (cisco:ise:syslog).",
      verify="Inputs listening with the right sourcetype/index.",
      gotchas=["FTD gets its OWN 5514 input + the message_id EXTRACT + data-model acceleration."]),
    A(id="observability/syslog-sources", agent="splunk-engineer", human="gui",
      requires=["splunk.inputs", "fabric.overlay", "ise.reachable", "ftd.acp"], provides=["telemetry.syslog"], params=[], est="15m",
      purpose="Point each device's syslog at Splunk (switches → 514, FTD → 5514, ISE remote-logging-target → 20514).",
      verify="Events landing per source in the right index.",
      human_note=("**ISE remote-logging-target is a GUI-only step** (Administration → System → Logging) and its name "
                  "must have NO hyphens/special chars. Switch + FTD syslog are agent-automatable.")),
    A(id="observability/splunk-hec", agent="splunk-engineer", human="none",
      requires=["splunk.up"], provides=["splunk.hec"], params=[], est="5m",
      purpose="Enable HEC + tokens (CatC webhooks, cross-platform health).",
      verify="HEC accepts a test event."),
    A(id="observability/healthcheck-cron", agent="splunk-engineer", human="none",
      requires=["splunk.hec"], provides=["telemetry.health"], params=[], est="5m",
      purpose="Scheduled cross-platform health check → HEC → index=health.",
      verify="Health events arrive ~every 30 min."),
    A(id="observability/splunk-cim", agent="splunk-engineer", human="external-download",
      requires=["splunk.up"], provides=["splunk.cim"], params=[], est="5m",
      purpose="Install the Splunk CIM add-on (Splunk_SA_CIM 8.5.0) — normalization prerequisite.",
      verify="Splunk_SA_CIM present + enabled.",
      human_note=("Download CIM 8.5.0 from Splunkbase (app 1621 — login-gated) and hand it in; install via "
                  "Splunk Web :8000 upload (SSH is closed on the box).")),
    A(id="observability/splunk-ise-addon", agent="splunk-engineer", human="external-download",
      requires=["splunk.cim", "telemetry.syslog"], provides=["splunk.ise_addon"], params=[], est="10m",
      purpose="Install the Splunk Add-on for Cisco ISE 5.0.0; index=ise CIM-parsed + its dashboards.",
      verify="Add-on parses cisco:ise:syslog; dashboards populate.",
      human_note="Download ISE add-on 5.0.0 (Splunkbase app 1915 — login-gated); install via Splunk Web :8000 upload."),
    A(id="observability/splunk-security-cloud", agent="splunk-engineer", human="gui",
      requires=["splunk.up", "ftd.estreamer_client"], provides=["splunk.securitycloud"], params=[], est="20m",
      purpose="Install Cisco Security Cloud 4.0 + wire the eStreamer input (V6/V8) → real Conn/Intrusion/File/Malware.",
      verify="eStreamer events flowing; Secure_Firewall_Dataset populated.",
      human_note=("Download the app (login-gated) + upload via Splunk Web :8000; add the eStreamer input via the app's "
                  "Add-Input UI (the 4.0 REST handler rejects the `password` arg); hand in the pkcs12 from ftd-estreamer-client; index=network.")),
    A(id="observability/splunk-dashboards", agent="splunk-engineer", human="none",
      requires=["splunk.securitycloud", "telemetry.syslog"], provides=["splunk.dashboards"], params=[], est="10m",
      purpose="Deploy the four committed dashboards (firewall-noc, soc-noc-overview, threat-rtc, tls-decryption).",
      verify="All four render with data.",
      gotchas=["XML sources are the committed dashboards/*.xml — deploy with splunk_create_dashboard."]),
    # ---- wireless
    A(id="wireless/wlc-base", agent="wireless-engineer", human="none",
      requires=["mcp.connected"], provides=["wlc.restconf"], params=["wlc.mgmt_ip", "wlc.cred"], est="10m",
      purpose="C9800 RESTCONF up (aaa new-model, priv-15 user, http secure-server, restconf).",
      verify="wlc_check green."),
    A(id="wireless/wlc-radius-ise", agent="wireless-engineer", human="none",
      requires=["wlc.restconf", "ise.nads"], provides=["wlc.aaa"], params=[], est="10m",
      purpose="RADIUS server + AAA group + dot1x method list to ISE; onboard the WLC as an ISE NAD.",
      verify="RADIUS group + method list present."),
    A(id="wireless/wlc-wlan-dot1x", agent="wireless-engineer", human="none",
      requires=["wlc.aaa"], provides=["wlc.wlan"], params=["ssid"], est="10m",
      purpose="802.1X WLAN + policy/site/RF tags.",
      verify="WLAN + tags configured."),
    A(id="wireless/hostapd-dot1x", agent="wireless-engineer", human="none",
      requires=["ise.policy_sets", "ad.users"], provides=["wireless.authenticated"], params=[], est="15m",
      purpose="Live 802.1X via CML's hostapd AP + wpa_supplicant (hostapd != CAPWAP).",
      verify="wpa_supplicant EAP auth → ISE session."),
    # ---- validate
    A(id="validate/deployment-acceptance", agent="testing-agent", human="none",
      requires=[], provides=["validated"], params=["deployment"], est="30m",
      purpose="Author/update the Test Plan, run the automated gate + live acceptance against the deployment's provides, produce the PDF Test Report.",
      verify="Report PASS verdict; any FAIL returned as a brief.",
      gotchas=["Consumes the whole deployment graph (requires handled specially); read-only + reversible only."]),
]

# ---------------------------------------------------------------- generate
def cat_of(atom_id): return atom_id.split("/", 1)[0]

def atom_md(a):
    reqs = a["requires"]
    pre = "\n".join(f"- [ ] `{r}`" for r in reqs) or "- none — this is a root atom"
    human = ""
    if a.get("human", "none") != "none":
        human = (f"\n## Human steps (⚠ requires operator — `human: {a['human']}`)\n"
                 f"{a.get('human_note','_TODO_')}\n")
    gotchas = "\n".join(f"- {g}" for g in a.get("gotchas", [])) or "- _none banked yet_"
    fm = (f"---\nid: {a['id']}\ncategory: {cat_of(a['id'])}\nagent: {a['agent']}\n"
          f"human: {a.get('human','none')}\nrequires: [{', '.join(reqs)}]\n"
          f"provides: [{', '.join(a['provides'])}]\nparams: [{', '.join(a.get('params',[]))}]\n"
          f"est: {a.get('est','?')}\n---\n")
    return (f"{fm}\n# {a['id']}\n\n> {a['purpose']}\n\n"
            f"## Preflight — assert `requires`\n{pre}\n\n"
            f"## Steps\n_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._\n\n"
            f"## Verify — prove `provides`\n{a['verify']}\n\n"
            f"## Rollback\n_TODO_\n{human}\n"
            f"## Gotchas\n{gotchas}\n")

def cat_readme(cat, meta, atoms):
    rows = "\n".join(
        f"| [`{a['id'].split('/')[1]}`]({a['id'].split('/')[1]}.md) | {a.get('human','none')} "
        f"| {', '.join(a['provides'])} | {a['purpose']} |"
        for a in atoms)
    prompts = "\n".join(f'- "{p}"' for p in meta["prompts"])
    gotchas = "\n".join(f"- {g}" for g in meta["gotchas"])
    return (f"# {meta['title']}\n\n{meta['owns']}\n\n"
            f"## Atoms\n\n| atom | human | provides | purpose |\n|---|---|---|---|\n{rows}\n\n"
            f"## Example prompts\n{prompts}\n\n"
            f"## Category gotchas\n{gotchas}\n\n"
            f"---\nSee [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, "
            f"and how Deployments compose atoms.\n")

def validate():
    provides, requires = {}, {}
    for a in ATOMS:
        for p in a["provides"]:
            provides.setdefault(p, []).append(a["id"])
        requires[a["id"]] = a["requires"]
    problems = []
    for aid, reqs in requires.items():
        for r in reqs:
            if r not in provides:
                problems.append(f"  MISSING: {aid} requires `{r}` — nothing provides it")
    # Kahn topo sort over provides/requires (special-case validate/* = consumes-all)
    state, order, atoms = set(), [], {a["id"]: a for a in ATOMS}
    pending = [a for a in ATOMS if not a["id"].startswith("validate/")]
    progressed = True
    while pending and progressed:
        progressed = False
        for a in list(pending):
            if all(r in state for r in a["requires"]):
                order.append(a["id"]); state.update(a["provides"]); pending.remove(a); progressed = True
    if pending:
        problems.append("  CYCLE/UNREACHABLE: " + ", ".join(a["id"] for a in pending))
    return problems, order

def main():
    force = "--force-atoms" in sys.argv
    made = 0
    by_cat = {c: [] for c in CATEGORIES}
    for a in ATOMS:
        by_cat[cat_of(a["id"])].append(a)
    for a in ATOMS:
        p = ROOT / f"{a['id']}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        if force or not p.exists():
            p.write_text(atom_md(a)); made += 1
    for c, meta in CATEGORIES.items():
        (ROOT / c / "README.md").write_text(cat_readme(c, meta, by_cat[c]))
    (ROOT / "catalog.json").write_text(json.dumps(
        {"atoms": [{k: a.get(k) for k in ("id", "agent", "human", "requires", "provides", "params", "est", "purpose")} for a in ATOMS]},
        indent=2) + "\n")
    problems, order = validate()
    print(f"atoms: {len(ATOMS)}   stubs written: {made}   categories: {len(CATEGORIES)}")
    if problems:
        print("DAG PROBLEMS:"); [print(p) for p in problems]; sys.exit(1)
    print("DAG OK — every `requires` is provided; no cycles.")
    print("topo build order:")
    for i, aid in enumerate(order, 1):
        print(f"  {i:2}. {aid}")

if __name__ == "__main__":
    main()
