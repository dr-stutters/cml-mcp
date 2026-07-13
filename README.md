# CML MCP Server

An [MCP](https://modelcontextprotocol.io) (Model Context Protocol) server for
**Cisco Modeling Labs (CML)**. It lets AI assistants like Claude build, run,
and interact with network simulation labs: create topologies, boot nodes, send
CLI commands to running devices, parse show output into structured data,
manage the CML system itself, and everything in between.

Built directly against the CML REST API (`/api/v0`); developed and tested
against **CML 2.10** (build 13).

> 🆕 **Companion servers — [Firepower MCP](https://github.com/dr-stutters/firepower-mcp),
> [ISE MCP](https://github.com/dr-stutters/ise-mcp),
> [Windows MCP](https://github.com/dr-stutters/windows-mcp),
> [Splunk MCP](https://github.com/dr-stutters/splunk-mcp) and
> [WLC MCP](https://github.com/dr-stutters/wlc-mcp).**
> Standalone sibling MCP servers for the Cisco Secure Firewall Management Center
> (FMC), Cisco Identity Services Engine (ISE), Windows Server (AD/DNS/DHCP/AD
> CS over WinRM), Splunk Enterprise (SIEM/observability), and the Catalyst 9800
> Wireless LAN Controller (RESTCONF). They're registered here as the `fmc`, `ise`,
> `windows`, `splunk` and `wlc` servers in [.mcp.json](.mcp.json) and used by the
> firewall-engineer, ise-engineer, windows-engineer, splunk-engineer and
> wireless-engineer agents — that work runs through `mcp__fmc__*` / `mcp__ise__*` /
> `mcp__windows__*` / `mcp__splunk__*` / `mcp__wlc__*` tools, no raw HTTP/WinRM. See
> [Firepower](#companion-server-firepower-fmc-mcp),
> [ISE](#companion-server-cisco-ise-mcp), [Windows](#companion-server-windows-server-mcp),
> [Splunk](#companion-server-splunk-mcp) and [WLC](#companion-server-wlc-mcp) below.

## What it can do

- **Full API coverage** — 73 tools spanning labs, nodes, links, interfaces,
  annotations, node/image definitions, users, groups, licensing, and system
  administration. Every one of the ~203 REST API operations is reachable:
  anything without a dedicated tool is available through the `cml_api_call`
  passthrough.
- **Talk to running devices (pyATS)** — send commands to node consoles through
  the CML console server (no management network needed), get show output as
  structured JSON via Genie parsers, apply configuration, and learn
  whole-feature state (OSPF, BGP, interfaces, ...). Console sessions persist
  between calls, so repeated commands are fast.
- **See the UIs (headless browser)** — capture screenshots of the CML web UI
  or any device management GUI (FMC/FDM) via bundled headless Chromium, returned
  inline as images. Optional extra; see Installation.
- **Agent-friendly ergonomics** — `create_link` accepts node ids and picks
  free interfaces automatically; annotations get sensible style defaults;
  large responses are truncated safely; node definition listings are compact
  by default.

## Companion server: Firepower (FMC) MCP

CML gives you the fabric; **[Firepower MCP](https://github.com/dr-stutters/firepower-mcp)**
gives you the firewalls. It's a separate, independently usable MCP server for the
**Cisco Secure Firewall Management Center (FMC)** REST API, built to the same
pattern as this one (FastMCP, async httpx). Once the two are combined, an agent
can build a topology in CML *and* fully configure the FTDs on it.

- **51 tools** across devices, deploy (deploy-and-wait), interfaces/VTIs/loopbacks,
  objects, site-to-site & SD-WAN (`AUTO_VPN`) VPN, routing (BGP/OSPF/EIGRP), FTD
  HA pairs, access policies, and licensing.
- **Spec-driven discovery** — `fmc_search_spec` + `fmc_get_definition` search the
  FMC API Explorer OpenAPI doc for any endpoint and its exact schema/enums, and
  `fmc_api_call` is the generic escape hatch for everything else.
- **Wired in here** — registered as the `fmc` server in
  [.mcp.json](.mcp.json) (it runs the sibling repo at `../Firepower_MCP`), and the
  **firewall-engineer** agent uses its `mcp__fmc__*` tools directly. Set the
  `FMC_*` credentials as env vars or in `../Firepower_MCP/.env` (see
  [.env.example](.env.example)).

Clone it alongside this repo (`../Firepower_MCP`) to enable the `fmc` server, or
use it entirely on its own — see its
[README](https://github.com/dr-stutters/firepower-mcp).

## Companion server: Cisco ISE MCP

CML gives you the fabric; Firepower gives you the firewalls;
**[ISE MCP](https://github.com/dr-stutters/ise-mcp)** gives you identity and NAC.
It's a separate, independently usable MCP server for **Cisco Identity Services
Engine (ISE)**, built to the same pattern (FastMCP, async httpx). ISE is usually
an external VM rather than a CML node.

- **128 tools** across three REST surfaces (all HTTP Basic auth): **OpenAPI**
  (443, `/api/…`) for endpoints, TrustSec (SGT/SGACL/egress), policy sets and
  policy authoring, day-2 ops (repositories, backups, patches, licensing,
  certificates + management, system summary), guest/sponsor, profiler, RBAC/admin;
  **ERS** (443, `/ers/config/…`) for network devices (NADs), internal users and
  identity/endpoint groups; and **MnT** (443, `/admin/API/mnt/…`) for read-only
  live session monitoring.
- **Spec-driven discovery** — `ise_search_spec` + `ise_get_definition` search the
  ISE OpenAPI docs (23 groups on 3.4, 30 on 3.5) for any endpoint and its exact
  schema, and `ise_openapi_call` / `ise_ers_call` / `ise_mnt_call` are the generic
  escape hatches. Verified against ISE 3.4 and 3.5.
- **Wired in here** — registered as the `ise` server in [.mcp.json](.mcp.json)
  (it runs the sibling repo at `../ISE_MCP`), and the **ise-engineer** agent uses
  its `mcp__ise__*` tools directly. Set the `ISE_*` credentials as env vars or in
  `../ISE_MCP/.env` (see [.env.example](.env.example)). ERS is disabled by
  default — enable it in the ISE GUI (API Settings); `ise_check_surfaces` reports
  which surfaces answer.

Clone it alongside this repo (`../ISE_MCP`) to enable the `ise` server, or use it
entirely on its own — see its
[README](https://github.com/dr-stutters/ise-mcp).

## Companion server: Windows Server MCP

CML gives you the fabric; ISE gives you identity; **[Windows MCP](https://github.com/dr-stutters/windows-mcp)**
gives you the **directory, DNS and PKI** behind it. It's a separate,
independently usable MCP server that drives a **Windows Server** over WinRM /
PowerShell remoting ([pypsrp](https://github.com/jborean93/pypsrp)).

- **37 tools** across **Active Directory (AD DS)** (promote a DC, users/groups/
  OUs/computers), **DNS** (zones/records), **DHCP** (scopes/reservations/leases),
  and **AD Certificate Services** (install a CA, export its cert, sign CSRs), plus
  `win_run_powershell` / `win_run_powershell_json` / `win_run_command` escape hatches.
- **Backs the ISE MCP** — AD as an external identity source; `win_get_ca_certificate`
  → `ise_import_trusted_cert` and `ise_generate_csr` → `win_sign_csr` for EAP-TLS;
  DNS A-records make ISE's CSR names resolvable.
- **Wired in here** — registered as the `windows` server in [.mcp.json](.mcp.json)
  (it runs the sibling repo at `../Windows_MCP`), and the **windows-engineer**
  agent uses its `mcp__windows__*` tools. Set the `WINRM_*` credentials as env
  vars or in `../Windows_MCP/.env`. **Enable WinRM on the server first**
  (`Enable-PSRemoting -Force`).

Clone it alongside this repo (`../Windows_MCP`) to enable the `windows` server, or
use it entirely on its own — see its
[README](https://github.com/dr-stutters/windows-mcp).

## Companion server: Splunk MCP

CML gives you the fabric; the other companions give you firewalls, identity and
the directory; **[Splunk MCP](https://github.com/dr-stutters/splunk-mcp)** gives
you the **SIEM / observability sink** they all forward telemetry to. It's a
separate, independently usable MCP server for **Splunk Enterprise**.

- **45 tools** across **system** (info/health/licensing), **search** (one-shot +
  async SPL, saved searches), **indexes**, **ingest** — data inputs
  (syslog UDP/TCP, file monitor) and the **HTTP Event Collector** (enable, tokens,
  send) — **apps/add-ons**, **dashboards**, **KV store** and **users/roles**, plus
  a `splunk_rest_call` escape hatch. REST management API on `8089` (Basic auth),
  HEC on `8088` (token).
- **The sink for the rest of the stack** — point CML devices' syslog, FTD/FMC, ISE
  and Windows at it; the device agents configure forwarding, splunk-engineer owns
  the receiving side + dashboards. Prefer existing Splunkbase add-ons (Cisco
  Security Cloud, Cisco ISE, Microsoft Windows) and their prebuilt dashboards.
- **Runs as a CML node** — the stock `splunk` Docker node is quick but CML caps
  Docker nodes to **1 CPU** (RAM overrides fine); for real multi-core, install
  Splunk on an `ubuntu` KVM node (4 vCPU works).
- **Wired in here** — registered as the `splunk` server in [.mcp.json](.mcp.json)
  (it runs the sibling repo at `../Splunk_MCP`), and the **splunk-engineer** agent
  uses its `mcp__splunk__*` tools. Set the `SPLUNK_*` credentials as env vars or in
  `../Splunk_MCP/.env`.

Clone it alongside this repo (`../Splunk_MCP`) to enable the `splunk` server, or
use it entirely on its own — see its
[README](https://github.com/dr-stutters/splunk-mcp).

## Companion server: WLC MCP

CML gives you the fabric; **[WLC MCP](https://github.com/dr-stutters/wlc-mcp)** gives
you the **wireless controller**. It's a separate, independently usable MCP server for
the **Cisco Catalyst 9800** WLC over **RESTCONF** (IOS-XE YANG).

- **26 tools** — WLANs, **AAA/RADIUS to ISE** (server/group/dot1x method list),
  policy profiles + tags, site/RF/AP-join tags, client/AP operational data, plus a
  `wlc_restconf_call` escape hatch + `wlc_list_models` discovery. RESTCONF on `443`
  (HTTPS Basic); `wlc_check` probes it (nginx yang-management lags the boot).
- **Wireless NAC** — pairs with the ISE MCP: onboard the WLC as a NAD, point its
  802.1X WLAN at ISE. **CML caveat:** CML's hostapd `wireless-ap` can't CAPWAP-join
  a C9800, so a CML C9800 has no live APs/clients — the `wlc` server still manages
  its full config, and live wireless 802.1X is proven separately via the hostapd AP
  + wpa_supplicant client (real EAP → hostapd → RADIUS → ISE).
- **Wired in here** — registered as the `wlc` server in [.mcp.json](.mcp.json) (it
  runs the sibling repo at `../WLC_MCP`), and the **wireless-engineer** agent uses
  its `mcp__wlc__*` tools. Set the `WLC_*` credentials as env vars or in
  `../WLC_MCP/.env`.

Clone it alongside this repo (`../WLC_MCP`) to enable the `wlc` server, or use it
entirely on its own — see its [README](https://github.com/dr-stutters/wlc-mcp).

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- A reachable CML 2.x server and credentials (an admin account unlocks the
  system-administration tools; a regular account works for lab operations)
- The first `uv sync` pulls in pyATS/Genie (a few hundred MB) for the console
  tools — this is expected.
- The pyATS console tools connect through the CML host's console server, so the
  machine running the server needs SSH reachability to the CML host (TCP 22).
- The screenshot tools are optional and pulled in only with the `browser`
  extra (see Installation).

## Installation

```bash
git clone https://github.com/dr-stutters/cml-mcp.git
cd cml-mcp
uv sync
cp .env.example .env   # then edit .env with your CML details

# Optional: headless-browser screenshot tools (screenshot_cml_ui, screenshot_web_ui)
uv sync --extra browser
uv run playwright install chromium
```

`.env` settings:

| Variable | Default | Description |
|---|---|---|
| `CML_URL` | (required) | CML server URL, e.g. `https://192.0.2.10` |
| `CML_USERNAME` | (required) | CML username |
| `CML_PASSWORD` | (required) | CML password |
| `CML_VERIFY_SSL` | `false` | Verify the TLS certificate (CML ships self-signed) |
| `CML_TIMEOUT` | `60` | API request timeout in seconds |

Authentication is automatic: the server obtains a JWT on first use and
re-authenticates transparently when the token expires. Credentials never
leave the machine the server runs on.

## Connecting an MCP client

**Claude Code** (one-time, global):

```bash
claude mcp add --scope user cml -- uv run --directory /path/to/cml-mcp cml-mcp
```

Or start Claude Code inside the repo — the included [.mcp.json](.mcp.json)
registers the server for this project automatically.

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cml": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/cml-mcp", "cml-mcp"]
    }
  }
}
```

**Any other MCP client** — launch `uv run --directory /path/to/cml-mcp cml-mcp`
over stdio. An HTTP transport is available with
`cml-mcp --transport streamable-http` for clients that prefer it.

## Using it

Once connected, just describe what you want in natural language. Examples:

> "Build a lab with three IOSv routers in a triangle, configure OSPF area 0 on
> all links, boot it, and confirm all adjacencies reach FULL."

> "What's eating the most memory on the CML server right now?"

> "Add 50ms of latency and 1% loss to the link between R1 and R2, then show me
> how OSPF reacts."

> "Export my 'Datacenter' lab as YAML so I can commit it to git."

> "Register the server with this Smart Licensing token: ..."

> "Build an FMC-managed FTD lab with two FTDs, register them, pair them into
> HA, then fail over to the standby and show me it took over."

A typical agent workflow maps to tools like this:

```
create_lab -> add_node (xN) -> create_link (xN) -> control_lab(start)
  -> get_lab_state (until converged)
  -> pyats_configure / pyats_parse / pyats_execute   (interact with devices)
  -> extract_node_configuration                       (persist configs)
  -> export_lab                                       (save as YAML)
```

Things worth knowing:

- **ids**: labs, nodes, interfaces, and links are identified by UUIDs; list
  tools return them. Node labels (e.g. `R1`) work for the pyATS tools.
- **Lifecycle**: a lab must be stopped before wiping, and wiped before
  deleting. `control_lab` / `control_node` handle start/stop/wipe.
- **pyATS sessions**: the first command to a node opens a persistent console
  session (~10–30 s); subsequent commands reuse it. Device credentials default
  to the CML-generated testbed values (typically `cisco`/`cisco`) and can be
  overridden per call.
- **Running vs stored config**: `pyats_configure` changes the running config
  only; `extract_node_configuration` persists it into the topology so it
  survives a wipe.
- **Escape hatch**: `list_api_endpoints` shows every REST operation on your
  server, and `cml_api_call` can invoke any of them — including binary
  downloads to a local file.

## Specialist agents (Claude Code)

The repo ships five Claude Code agent definitions in
[.claude/agents/](.claude/agents/) — other MCP clients can ignore this
directory:

- **cml-lab-architect** — designs and builds topologies (node-definition
  selection with boot-time/RAM trade-offs, layout, day-0 configs) and returns
  a delegation brief per device group.
- **catalyst-engineer** — configures and verifies IOS/IOS-XE/Catalyst devices
  (iosv, iosvl2, IOL, csr1000v, cat8000v, cat9000v) over their consoles:
  routing protocols, VLANs/trunking/STP/EtherChannel, with a per-platform
  cheat-sheet and a verification playbook.
- **firewall-engineer** — provisions and validates Cisco firewalls: FTDv in
  **local mode** (on-box FDM REST API) and **FMC-managed mode** (registration
  + FMC REST API, incl. the eval-license prerequisite and HA/failover pairing),
  **Secure Firewall SD-WAN** (route-based VTI overlay and the FMC SD-WAN
  auto-VPN wizard driven via the REST API), plus classic ASAv. Knows the day-0
  JSON provisioning flow and drives the FDM/FMC APIs directly or via an in-lab
  toolbox node when the management network isn't externally reachable.
- **ise-engineer** — identity/NAC specialist for **Cisco ISE** (usually an
  external VM): onboards network devices (NADs/RADIUS clients), manages
  endpoints, TrustSec/SGTs, policy sets and identity/endpoint groups, and
  monitors live RADIUS sessions via the companion ISE MCP's `mcp__ise__*` tools;
  also configures and tests the NAD side (802.1X/MAB/RADIUS) on CML switches via
  pyATS, proving auth from both ends — MAB, PEAP-MSCHAPv2 against AD, and EAP-TLS
  all validated end-to-end against ISE 3.4/3.5.
- **windows-engineer** — Windows Server / **Active Directory** specialist
  (external VM over WinRM): AD DS (domain, users, groups, OUs), DNS, DHCP, and
  **AD CS** (a certificate authority) via the companion Windows MCP's
  `mcp__windows__*` tools. The identity/PKI/DNS backing for ISE — external
  identity, EAP-TLS via the CA cert, and resolvable names for ISE CSRs.

The flow: the main session asks the architect to design and build, then fans
the returned briefs out to the matching specialist (catalyst-engineer,
firewall-engineer, ise-engineer, windows-engineer) — in parallel when device
groups are disjoint, since two agents must never share a node's console. See
[CLAUDE.md](CLAUDE.md) for the full protocol. Further specialists (SP/DC,
wireless) follow the same
pattern.

### Cisco Validated Designs library

[`Cisco Validated Designs/`](Cisco%20Validated%20Designs/) is a growing library
of reference designs — one subfolder each, holding the source materials and a
distilled `design-brief.md` that expands the relevant agent's knowledge. Drop a
design's PDF in its folder (PDFs are gitignored; briefs and links are
committed); the matching specialist consults the brief when a task maps to that
design. See the library's [README](Cisco%20Validated%20Designs/README.md) for
the "add a design" workflow. First entry: **Firewall SD-WAN** (Secure Firewall
Threat Defense's native SD-WAN → firewall-engineer) — its hub-and-spoke VTI
overlay has been **built and validated end-to-end in CML** (FMC SD-WAN auto-VPN
provisioned over the REST API, iBGP AS 65070 overlay, LAN-to-LAN reachability).

## Tool reference

### Topology-as-code

| Tool | Description |
|---|---|
| `validate_lab_spec` | Validate a declarative YAML lab spec (offline schema + live definition names) |
| `build_lab_from_spec` | Compile a spec into a complete lab in one call (nodes, links, annotations, briefs) |
| `export_lab_spec` | Reverse-compile a live lab into the concise spec YAML (for version control) |

A **lab spec** is a concise YAML document describing a whole topology — the
declarative alternative to calling `create_lab`/`add_node`/`create_link`
individually (keep those for incremental edits). Specs live next to their
design docs, e.g.
[`Custom Designs/Wireless NAC/topology.yaml`](Custom%20Designs/Wireless%20NAC/topology.yaml):

```yaml
version: 1
lab: {title: My Lab}
defaults: {definition: iol-xe}          # merged under every node
nodes:                                  # label -> node ({} ok with defaults)
  R1: {config: "hostname R1"}           # day-0: config (text) | config_json
  R2: {x: 180, y: 0}                    #   (ftdv/fmcv JSON) | config_files
  EXT: {definition: external_connector, config: System Bridge}
links:
  - R1:Ethernet0/1 -- R2:e0/1           # pinned (IOS abbreviations resolve)
  - R1 -- EXT                           # auto: next free interface
groups:                                 # optional -> per-specialist briefs
  core: {agent: catalyst-engineer, nodes: [R1, R2], tasks: "..."}
```

Link grammar: `A[:iface] -- B[:iface]` (whitespace around `--`); interface
labels accept IOS-style abbreviations (`Gi0/1`), matched never guessed —
ambiguity is an error. Nothing is created unless the whole spec validates
(`dry_run=true` previews; `rollback_on_error=true` deletes a failed partial
build). The build report includes one delegation brief per `groups:` entry,
ready to fan out to the specialist agents. Not covered in v1: diff/apply
reconciliation against an existing lab, and link conditioning.

### Labs

| Tool | Description |
|---|---|
| `list_labs` | List labs on the server (all users' labs with admin rights) |
| `get_lab` | Lab details: title, state, owner, node/link counts |
| `create_lab` | Create a new empty lab |
| `update_lab` | Change title, description, notes, or owner |
| `delete_lab` | Delete a lab permanently (stop + wipe first) |
| `control_lab` | Start, stop, or wipe an entire lab |
| `get_lab_state` | Runtime state plus convergence flag |
| `get_lab_element_state` | State of every node, interface, and link in one call |
| `get_lab_events` | Lab event log (state transitions, errors) |
| `get_lab_simulation_stats` | Per-node CPU/memory/disk usage |
| `get_lab_topology` | Full topology JSON (nodes, links, annotations) |
| `export_lab` | Download the lab as CML topology YAML |
| `import_lab` | Import a topology from YAML or JSON text |
| `get_lab_layer3_addresses` | Discovered IP addresses of running nodes |
| `get_pyats_testbed` | Generate the lab's pyATS testbed YAML |
| `search_lab_nodes` | Find nodes by label or tag |
| `manage_lab_groups` | Get/set which user groups a lab is shared with |
| `sample_labs` | List/inspect/load the built-in sample labs |

### Nodes

| Tool | Description |
|---|---|
| `list_nodes` | All nodes in a lab with properties and state |
| `get_node` | Full details for one node (incl. runtime data) |
| `add_node` | Add a node (type, position, config, RAM/CPU, tags) |
| `update_node` | Change label, position, config, image, resources |
| `delete_node` | Remove a node and its interfaces/links |
| `control_node` | Start, stop, or wipe a single node |
| `get_node_state` | Node state (DEFINED_ON_CORE/STOPPED/STARTED/BOOTED) + convergence |
| `extract_node_configuration` | Save a booted node's running config into the topology |
| `get_node_console_log` | Console/boot log (tail by line count) |
| `get_node_console_key` | Console or VNC key for terminal access |
| `list_all_running_nodes` | Admin view of nodes across all labs |

### Interfaces & links

| Tool | Description |
|---|---|
| `list_interfaces` | Interfaces in a lab or on one node |
| `get_interface` | One interface with its current state |
| `create_interface` | Add a physical interface to a node |
| `update_interface` | Change an interface's MAC address |
| `delete_interface` | Remove an interface (and any link using it) |
| `set_interface_state` | Up/down an interface (like pulling the cable) |
| `list_links` | All links with endpoints and state |
| `get_link` | One link's details |
| `create_link` | Link two endpoints — accepts node ids and auto-picks free interfaces |
| `delete_link` | Remove a link |
| `set_link_state` | Bring a link up or down |
| `configure_link_condition` | WAN emulation: bandwidth, latency, jitter, loss |
| `manage_packet_capture` | Start/stop/status/download pcap on a link |

### pyATS — interact with running devices

| Tool | Description |
|---|---|
| `pyats_execute` | Run exec-mode CLI (show commands, ping) on a node's console; raw output |
| `pyats_parse` | Run a show command and return **structured JSON** (Genie parsers) |
| `pyats_configure` | Apply configuration lines (enters/exits config mode) |
| `pyats_learn` | Learn whole-feature state: ospf, bgp, interface, routing, ... |
| `pyats_sessions` | Session status, disconnect, or testbed refresh per lab |

### Annotations

| Tool | Description |
|---|---|
| `manage_annotations` | List/create/update/delete canvas annotations (text, shapes, lines) |
| `manage_smart_annotations` | View/update tag-driven smart annotations |

### Node & image definitions

| Tool | Description |
|---|---|
| `list_node_definitions` | Available device types (compact summary or full) |
| `get_node_definition` | Full definition document for one device type |
| `manage_node_definition` | Create/update/delete/protect definitions; reload from disk |
| `list_image_definitions` | Disk images, optionally per node definition |
| `get_image_definition` | One image definition's details |
| `manage_image_definition` | Create/update/delete images, upload disk images, manage the drop folder, clone a node's disk into a new image |
| `get_definition_schema` | JSON schema for node/image definition documents |

### Users, groups & system administration

| Tool | Description |
|---|---|
| `manage_users` | List/create/update/delete users, look up ids |
| `manage_groups` | List/create/update/delete groups, membership, lab sharing |
| `get_system_status` | Server information, component health, CPU/memory/disk stats |
| `manage_compute_hosts` | Cluster compute hosts and admission configuration |
| `manage_external_connectors` | NAT/bridged connectors to the outside network |
| `manage_resource_pools` | CPU/RAM/node quotas and their usage |
| `manage_lab_repos` | Git repositories of shared topologies |
| `manage_system_notices` | User-facing banners/messages |
| `manage_maintenance_mode` | Block non-admin logins during maintenance |
| `get_diagnostics` | Low-level controller diagnostics by category |

### Licensing

| Tool | Description |
|---|---|
| `get_licensing_status` | Registration, authorization, features, transport, reservation mode |
| `manage_licensing` | Register/deregister/renew, transport, feature counts, product license, tech support |
| `manage_license_reservation` | Full offline SLR flow for air-gapped servers |

### Screenshots (headless browser — optional `browser` extra)

| Tool | Description |
|---|---|
| `screenshot_cml_ui` | Screenshot the CML web UI dashboard (logs in with the configured credentials) |
| `screenshot_web_ui` | Screenshot any URL — a device GUI (FMC/FDM) or lab canvas — with optional login; returned inline as an image |

Requires `uv sync --extra browser` then `uv run playwright install chromium`.
The tools return a clear message if the browser isn't installed, so the rest
of the server works without it.

### Escape hatch

| Tool | Description |
|---|---|
| `cml_api_call` | Call any CML REST endpoint (any method, query params, body, binary download) |
| `list_api_endpoints` | Discover every REST operation from the server's live OpenAPI spec |

## Testing

An offline unit suite (no CML needed — mocked HTTP) runs with plain pytest and
in CI:

```bash
uv run pytest
```

Four live suites run against a real CML server (all create scratch labs and
clean up after themselves):

```bash
# API tool coverage over the real MCP stdio layer (fast, ~30 s)
uv run python tests/smoke_test.py

# Topology-as-code: spec -> build -> export -> rebuild round trip (~30 s)
uv run python tests/labspec_e2e_test.py

# Boots a real IOSv node and drives its console via pyATS (~5 min)
uv run python tests/pyats_e2e_test.py

# Validates FTDv in BOTH management modes: local (FDM API) and FMC-managed
# (registration + FMC API). Heavy: ~48 GB free RAM on the host, 45-75 min
uv run python tests/firepower_e2e_test.py
```

## Project layout

```
src/cml_mcp/
  config.py         # settings from environment / .env
  client.py         # async httpx client: JWT auth, 401 retry, helpers
  server.py         # FastMCP entry point (stdio / streamable-http)
  pyats_manager.py  # persistent pyATS/unicon console sessions per lab
  screenshots.py    # headless-browser capture (optional 'browser' extra)
  tools/            # tool modules, one per functional area
tests/
  test_client_unit.py   # offline unit tests (mocked HTTP; runs in CI)
  test_labspec_unit.py  # offline topology-as-code tests (parser, matcher, build)
  smoke_test.py         # end-to-end API tool checks
  labspec_e2e_test.py   # spec -> build -> export -> rebuild round trip
  pyats_e2e_test.py     # console interaction against a booted node
  firepower_e2e_test.py # FTD local + FMC-managed mode validation (heavy)
.claude/agents/     # specialist agents (architect, catalyst, firewall)
CLAUDE.md           # agent orchestration protocol
```

## Troubleshooting & tips

Hard-won lessons, encoded in the specialist agents and worth knowing:

- **Connectivity down between nodes? Check the CML fabric first.** An interface
  added to an already-running node comes up `STOPPED` even though the link shows
  `STARTED`, so no traffic passes and the device sees it down/down. Verify both
  link and interface state (`list_links`, `list_interfaces`) and
  `set_interface_state` start them before diagnosing anything inside a device.
- **cat9000v MAB/802.1X RADIUS won't cross the Mgmt-vrf.** On a Catalyst 9000v the
  auth-manager (SMD) RADIUS for MAB/dot1x silently times out over the OOB management
  port (Gi0/0, Mgmt-vrf) even though IOSd RADIUS (`test aaa`) succeeds there — source
  RADIUS from a **front-panel data port in the global routing table** instead. And
  the lightweight L2 sims (**iosvl2**, **ioll2-xe**) accept the `mab` config but never
  hand the endpoint frame to the auth-manager, so MAB never fires: use a real
  dataplane switch (**cat9000v**) for NAC testing. Validated end-to-end (MAB →
  PermitAccess) against ISE 3.4 and 3.5.
- **"Booted" is not "ready" for Firepower.** FTDv reaches BOOTED in ~5 min but
  its FDM/registration services take 10-20 min more; FMCv takes ~15-30 min and
  its REST API answers before it is fully ready. Poll patiently.
- **A fresh FMC won't register devices until it's licensed.** Day-0 alone leaves
  it `UNREGISTERED` with no eval; enable Evaluation Mode first
  (`POST /api/fmc_platform/v1/license/smartlicenses {"registrationType":"EVALUATION"}`)
  or registration fails fast and the device record is discarded.
- **FTD HA needs two separate failover links** (LAN + stateful on different
  interfaces), both peers clean/deployed first, and — trust the device's
  `show failover` over the FMC's health poll, which lags.
- **FMC allows the admin user only one session.** The screenshot tools handle
  the "End Existing Session" dialog; for concurrent human + automation access,
  use a second admin account.

## Security notes

- Credentials live only in `.env` (gitignored) and are sent only to your CML
  server.
- TLS verification is off by default because CML ships a self-signed
  certificate; set `CML_VERIFY_SSL=true` if you've installed a trusted one.
- Admin credentials expose destructive tools (delete labs, manage users,
  maintenance mode) to the connected AI client — review your MCP client's
  permission prompts before approving state-changing calls.

## Roadmap

- Composite workflow helpers (`wait_for_converged`, `lab_health_summary`) to
  cut agent round-trips on large topologies.
- Topology-as-code v2: diff/apply reconciliation of a live lab against its spec.
- MCP resources/prompts (topology templates, guided lab designs).
- Hardening: authenticated HTTP transport for shared deployments.
