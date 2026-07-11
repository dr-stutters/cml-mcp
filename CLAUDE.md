# cml-mcp

MCP server for Cisco Modeling Labs (Python 3.11+, uv, FastMCP, httpx, pyATS).
Source in `src/cml_mcp/`; live-server tests in `tests/` (both create and
delete their own scratch labs). Config comes from `.env` (never commit it).

## Orchestrating lab work with the specialist agents

This repo ships Claude Code agents in `.claude/agents/`:

- **cml-lab-architect** - designs and builds topologies (labs, nodes, links,
  day-0 configs) and returns delegation briefs per device group.
- **catalyst-engineer** - configures and verifies IOS/IOS-XE/Catalyst devices
  over their consoles from such a brief.
- **firewall-engineer** - provisions and validates FTDv (local/FDM mode and
  FMC-managed mode), FMCv, and ASAv; drives the FDM/FMC REST APIs via a
  toolbox node or Bash.

Protocol for lab requests involving these device families:

1. Send the requirements to **cml-lab-architect**. It builds the topology and
   returns a lab_id plus one brief per device group. For Firepower labs the
   architect must decide the FTD management mode up front (day-0
   `ManageLocally` / `FmcIp`) - ask the user if it isn't stated.
2. Fan each brief out to the matching specialist (**catalyst-engineer**,
   **firewall-engineer**), passing the brief verbatim. Parallel invocations
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
