# cml-mcp

MCP server for Cisco Modeling Labs (Python 3.11+, uv, FastMCP, httpx, pyATS).
Source in `src/cml_mcp/`; live-server tests in `tests/` (both create and
delete their own scratch labs). Config comes from `.env` (never commit it).

**Shared secrets across the suite:** every companion MCP below reads a shared
`../.env` (one level above the repos, i.e. the parent of all six checkouts) as a
base, so lab credentials can live in ONE file instead of six. Precedence, highest
first: process env > that repo's own `.env` > the shared `../.env`. The full
template (all six servers' variables) is [`.env.example`](.env.example) - copy it to
`../.env` for suite-wide config, or a block into a single repo's `.env`. All six
repos gitignore `.env`; never commit one.

**Companion Firepower MCP:** the `fmc` server (registered in `.mcp.json`, source
in the sibling repo `../Firepower_MCP`) wraps the FMC REST API - the
firewall-engineer agent uses its `mcp__fmc__*` tools (spec search, devices,
deploy, interfaces/VTIs, VPN/SD-WAN, routing, HA) instead of raw httpx. Set its
`FMC_*` creds as env vars or in `../Firepower_MCP/.env`.

**Companion ISE MCP:** the `ise` server (registered in `.mcp.json`, source in the
sibling repo `../ISE_MCP`) wraps Cisco Identity Services Engine's three REST
surfaces - OpenAPI (443, `/api/…`), ERS (443, `/ers/config/…`), and MnT (443,
`/admin/API/mnt/…`), all HTTP Basic auth. The ise-engineer agent uses its
`mcp__ise__*` tools (spec search, network devices/NADs, endpoints, TrustSec/SGT,
policy sets, identity/endpoint groups, live session monitoring) instead of raw
httpx. ISE is usually an external VM, not a CML node. Set its `ISE_*` creds as
env vars or in `../ISE_MCP/.env`. Note: ERS is disabled by default - enable it in
the ISE GUI (Admin > System > Settings > API Settings); it's served on 443 (the
legacy 9060 port is deprecated/often off). `ise_check_surfaces` reports what's
reachable.

**Companion Windows MCP:** the `windows` server (registered in `.mcp.json`, source
in the sibling repo `../Windows_MCP`) drives a Windows Server over WinRM/PowerShell
remoting (pypsrp) - the windows-engineer agent uses its `mcp__windows__*` tools for
Active Directory (AD DS), DNS, DHCP, and AD CS (a CA). It's the identity/PKI/DNS
backing for ISE: build a domain + users (external identity for ISE), a CA whose
cert feeds `ise_import_trusted_cert` (EAP-TLS), and resolvable DNS names for ISE
CSRs. WinRM must be enabled on the server first (`Enable-PSRemoting -Force`); set
`WINRM_*` creds as env vars or in `../Windows_MCP/.env`. Promote-to-DC and role
installs reboot the box (WinRM drops - reconnect and re-check).

**Companion Splunk MCP:** the `splunk` server (registered in `.mcp.json`, source
in the sibling repo `../Splunk_MCP`) wraps Splunk Enterprise's REST management API
(port 8089, HTTP Basic) and the HTTP Event Collector (port 8088, token auth) - the
splunk-engineer agent uses its `mcp__splunk__*` tools (indexes, data inputs for
syslog, HEC tokens, SPL search, apps/add-ons, dashboards, users/roles) instead of
raw httpx. It's the observability/SIEM sink the other stacks forward telemetry to.
Splunk runs as a CML node - either the stock `splunk` **Docker** node (fast, but
CML caps Docker nodes to **1 CPU**; RAM overrides fine) or, for real multi-core, an
`ubuntu` **KVM** node with Splunk installed on-box (4 vCPU works). Set its
`SPLUNK_*` creds as env vars or in `../Splunk_MCP/.env`; `splunk_check` reports
reachability. Prefer installing existing Splunkbase add-ons (Cisco Security Cloud,
Cisco ISE, Microsoft Windows) and their prebuilt dashboards over hand-built panels.
For demos/test data without live devices, `splunk_generate_telemetry` fabricates
realistic events (5 profiles: ios/ise_auth/ise_acct/asa/windows, host prefix `sim-`)
into the matching sourcetype/index so the add-on dashboards populate.

**Companion WLC MCP:** the `wlc` server (registered in `.mcp.json`, source in the
sibling repo `../WLC_MCP`) drives a **Cisco Catalyst 9800 Wireless LAN Controller**
over **RESTCONF** (IOS-XE YANG, HTTPS Basic) - the wireless-engineer agent uses its
`mcp__wlc__*` tools (WLANs, AAA/RADIUS to ISE, policy/site/RF tags, client/AP oper,
+ a `wlc_restconf_call` escape hatch) instead of raw httpx. Enable on the C9800:
`aaa new-model` + a priv-15 local user + `ip http secure-server` + `restconf`
(RESTCONF/nginx lags the boot by minutes - `wlc_check` probes it). Set `WLC_*` creds
as env vars or in `../WLC_MCP/.env`. **CML caveat:** CML's simulated `wireless-ap`
runs hostapd and can't CAPWAP-join a C9800, so a CML C9800 has no live APs/clients -
the `wlc` server still manages its full config; live wireless 802.1X in CML is done
separately via the hostapd AP + wpa_supplicant client (real EAP over the shared
`airduct`/hwsim RF medium, hostapd as the RADIUS authenticator to ISE).

**Companion Catalyst Center MCP:** the `catc` server (registered in `.mcp.json`, source
in the sibling repo `../catalyst-center-mcp`) wraps **Cisco Catalyst Center** (formerly
DNA Center) - the on-prem campus / SD-Access controller - via its **Intent API** (token
auth, `/dna/intent/api/v1/…`). The catalyst-center-engineer agent uses its `mcp__catc__*`
tools (reachability/version, device inventory, site hierarchy, Assurance health/issues,
read-only command-runner `show` commands, task polling, + a `catc_api_call` escape hatch)
instead of raw httpx. Catalyst Center is usually an external appliance, not a CML node;
most writes + the command runner are **async** (return a `taskId` to poll). Set its
`CATC_*` creds as env vars or in `../catalyst-center-mcp/.env` (or the shared `../.env`).

## Orchestrating lab work with the specialist agents

This repo ships Claude Code agents in `.claude/agents/`:

- **cml-lab-architect** - designs and builds topologies (labs, nodes, links,
  day-0 configs) and returns delegation briefs per device group.
- **catalyst-engineer** - configures and verifies IOS/IOS-XE/Catalyst devices
  over their consoles from such a brief.
- **firewall-engineer** - provisions and validates FTDv (local/FDM mode and
  FMC-managed mode), FMCv, and ASAv; drives the FDM/FMC REST APIs via a
  toolbox node or Bash.
- **ise-engineer** - identity/NAC specialist for Cisco ISE (usually an external
  VM): onboards NADs, manages endpoints, TrustSec/SGTs, policy sets, identity
  groups, and live session monitoring via the `mcp__ise__*` tools; also
  configures/tests the NAD side (802.1X/MAB/RADIUS) on CML switches.
- **windows-engineer** - Windows Server / Active Directory specialist (external
  VM over WinRM): AD DS (domain, users, groups, OUs), DNS, DHCP, and AD CS (a CA)
  via the `mcp__windows__*` tools - the identity/PKI/DNS backing for ISE (external
  identity, EAP-TLS via the CA cert, resolvable CSR names).
- **splunk-engineer** - observability/SIEM specialist for Splunk Enterprise:
  indexes, data inputs (syslog UDP/TCP) and HEC tokens for ingest, SPL search,
  saved searches, users/roles, and installing Splunkbase apps/add-ons and their
  prebuilt dashboards - via the `mcp__splunk__*` tools. Owns the Splunk receiving
  side + verification; device-side log forwarding is done by the device agents.
- **wireless-engineer** - wireless/NAC specialist for Cisco Catalyst 9800 WLCs and
  802.1X wireless: configures the C9800 (WLANs, AAA/RADIUS to ISE, policy/site/RF
  tags) over RESTCONF via the `mcp__wlc__*` tools, and drives live wireless 802.1X
  to ISE using CML's hostapd AP + wpa_supplicant client (hostapd ≠ CAPWAP, so the
  controller and the live client are two separate paths in CML).
- **catalyst-center-engineer** - campus / SD-Access controller specialist for Cisco
  Catalyst Center (formerly DNA Center): reads device inventory, the site hierarchy, and
  Assurance health/issues; runs read-only `show` commands on managed devices via the
  command runner; and reaches any Intent-API endpoint through the escape hatch - via the
  `mcp__catc__*` tools. Catalyst Center is usually an external appliance, not a CML node.
- **secure-by-design** - security-architecture specialist that runs a **READ-ONLY**
  secure-by-design review across the built lab + stack (device running-configs, ISE
  policy/certs, FMC access-control policies, C9800 WLAN security, and whether
  telemetry actually lands in Splunk): audits management-plane hardening, identity/
  NAC coverage, segmentation (ACL/TrustSec/zones), secure transport, logging, and
  resilience, then returns a prioritised findings report + per-device-group
  remediation briefs. Advisory only - never changes config; the main session fans
  its briefs to the other specialists.

Protocol for lab requests involving these device families:

1. Send the requirements to **cml-lab-architect**. It builds the topology and
   returns a lab_id plus one brief per device group. For Firepower labs the
   architect must decide the FTD management mode up front (day-0
   `ManageLocally` / `FmcIp`) - ask the user if it isn't stated. For
   multi-node builds it prefers **topology-as-code**: a declarative YAML lab
   spec + one `build_lab_from_spec` call (specs are committed at
   `Custom Designs/<Design>/topology.yaml`; `export_lab_spec` captures an
   existing lab the same way).
2. Fan each brief out to the matching specialist (**catalyst-engineer**,
   **firewall-engineer**, **ise-engineer**, **windows-engineer**,
   **splunk-engineer**, **wireless-engineer**), passing the brief verbatim. Parallel
   invocations
   are fine ONLY if their node sets are disjoint - two agents must never
   drive the same node's console (each agent runs its own MCP server process;
   the per-device locks don't protect across agents).
3. Subagents cannot spawn subagents: the main session does the fan-out, not
   the architect.
4. After specialists report, run lab-level acceptance from the main session
   (e.g. end-to-end pings via `pyats_execute`, `get_lab_layer3_addresses`).
5. To security-review or harden a lab, send it to **secure-by-design** (read-only).
   It returns a findings report + per-device-group remediation briefs; the main
   session then fans those briefs back to the matching specialists (step 2) to apply
   the fixes - secure-by-design never changes config itself.

Check the CML fabric before troubleshooting devices: whenever connectivity
between nodes is down (no adjacency, failover "Comm Failure", dead link),
FIRST confirm both the link state AND the interface state on each end are
`STARTED` (`list_links` + `list_interfaces`). Interfaces added to an
already-running node come up `STOPPED` even though the link shows `STARTED`,
so no traffic passes and the device sees the interface down/down - start them
with `set_interface_state` and re-check before diagnosing device config or
rebooting anything.

Boot times: IOL nodes boot in seconds; IOSv ~2-3 min; CSR/Cat8kv ~4-6 min;
ASAv ~2-4 min; FTDv BOOTED ~5 min but FDM API 10-20 min more; FMCv ~15-30 min.
Wait for BOOTED (`get_node_state`) before delegating device configuration,
and check host capacity before building FMC labs (FMCv alone wants 32 GB).

## Cisco Validated Designs library

`Cisco Validated Designs/` holds reference designs, one subfolder each, with a
distilled `design-brief.md` per design. When a lab request maps to a design,
the matching specialist should consult that brief (e.g. firewall-engineer reads
`Cisco Validated Designs/Firewall SD-WAN/design-brief.md`). See the library
[README](Cisco%20Validated%20Designs/README.md) for the "add a design" workflow.
Source PDFs are gitignored (kept local); the briefs and links are committed.

## Custom Designs library

`Custom Designs/` is the counterpart to the CVD library for **our own** lab builds
— one subfolder per design, each with a repeatable `runbook.md` (prerequisites →
topology → stage-by-stage config → verification → teardown → gotchas) and optional
per-capability `modules/`. Unlike CVDs there are no source PDFs, so everything is
committed. When a request maps to a design, the matching specialists rebuild
straight from its runbook (e.g. "rebuild the ISE NAC lab" → `Custom Designs/ISE NAC
Lab/runbook.md`, fanned out to ise-engineer / catalyst-engineer / windows-engineer).
See the library [README](Custom%20Designs/README.md) for the "add a design" workflow.
