# cml-mcp

MCP server for Cisco Modeling Labs (Python 3.11+, uv, FastMCP, httpx, pyATS).
Source in `src/cml_mcp/`; live-server tests in `tests/` (both create and
delete their own scratch labs). Config comes from `.env` (never commit it).

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

Protocol for lab requests involving these device families:

1. Send the requirements to **cml-lab-architect**. It builds the topology and
   returns a lab_id plus one brief per device group. For Firepower labs the
   architect must decide the FTD management mode up front (day-0
   `ManageLocally` / `FmcIp`) - ask the user if it isn't stated.
2. Fan each brief out to the matching specialist (**catalyst-engineer**,
   **firewall-engineer**, **ise-engineer**, **windows-engineer**), passing the
   brief verbatim. Parallel invocations
   are fine ONLY if their node sets are disjoint - two agents must never
   drive the same node's console (each agent runs its own MCP server process;
   the per-device locks don't protect across agents).
3. Subagents cannot spawn subagents: the main session does the fan-out, not
   the architect.
4. After specialists report, run lab-level acceptance from the main session
   (e.g. end-to-end pings via `pyats_execute`, `get_lab_layer3_addresses`).

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
