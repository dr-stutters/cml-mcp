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

Protocol for lab requests involving Catalyst-family devices:

1. Send the requirements to **cml-lab-architect**. It builds the topology and
   returns a lab_id plus one brief per device group.
2. Fan each brief out to a **catalyst-engineer** invocation, passing the brief
   verbatim. Parallel invocations are fine ONLY if their node sets are
   disjoint - two agents must never drive the same node's console (each agent
   runs its own MCP server process; the per-device locks don't protect across
   agents).
3. Subagents cannot spawn subagents: the main session does the fan-out, not
   the architect.
4. After specialists report, run lab-level acceptance from the main session
   (e.g. end-to-end pings via `pyats_execute`, `get_lab_layer3_addresses`).

Boot times: IOL nodes boot in seconds; IOSv ~2-3 min; CSR/Cat8kv ~4-6 min.
Wait for BOOTED (`get_node_state`) before delegating device configuration.
