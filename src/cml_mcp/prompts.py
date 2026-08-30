"""MCP prompt templates: reusable workflow playbooks for common CML tasks.

Prompts are user-invoked recipes (unlike tools, the agent doesn't call them on
its own). Each returns plain instruction text that names the real tools in this
server, so an agent following it never has to guess tool names or ordering.
Registered from build_server() via register_prompts().
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def register_prompts(mcp: MCPServer) -> None:
    """Register all prompt templates on the server."""

    @mcp.prompt(
        name="cml_troubleshoot_lab",
        title="Troubleshoot a CML Lab",
        description="Stepwise diagnosis plan for a lab that is broken or misbehaving.",
    )
    def cml_troubleshoot_lab(lab_id: str) -> str:
        return f"""Troubleshoot CML lab {lab_id} step by step:

1. Orient: cml_get_lab for status, then cml_get_lab_topology (summary first)
   to see nodes, links, and their states in one call.
2. Health sweep: cml_get_lab_element_state — list every node/link/interface
   not in BOOTED/STARTED. Those are your suspects.
3. For each suspect node: cml_get_node for state/CPU/RAM, then
   cml_get_node_console_log to check boot progress or config errors.
4. Recent history: cml_get_lab_events for errors around the failure time.
5. Network layer: cml_get_lab_layer3_addresses to confirm expected IPs came
   up; run live checks (show commands, ping) with cml_run_commands — it
   returns parsed output per node and command.
6. Link issues: cml_get_link and cml_get_link_condition (impairments like
   loss/latency may be set — clear with cml_set_link_condition action='clear').
7. Remediate (needs writes enabled): restart a stuck node with
   cml_set_node_state action='stop' then 'start' (use wait=true), then
   confirm with cml_wait_for_node_converged.
8. Summarize findings, root cause, and what you changed."""

    @mcp.prompt(
        name="cml_build_topology",
        title="Build a CML Topology",
        description="Plan and build a lab topology from a natural-language description.",
    )
    def cml_build_topology(description: str) -> str:
        return f"""Build this CML topology: {description}

Writes must be enabled (CML_MCP_ENABLE_WRITES=true) — if the create tools are
missing, tell the user to enable writes and restart, then stop.

1. Plan: map the description to concrete devices. Check what images exist
   with cml_list_node_definitions; pick definitions accordingly.
2. Create the lab: cml_create_lab with a descriptive title.
3. Add nodes: cml_add_node per device (spread x/y coordinates for a readable
   diagram). Note node IDs from each response.
4. Wire it: cml_create_link between node interfaces. Loopbacks cannot be
   linked. Verify the result with cml_get_lab_topology.
5. Configure: provide day-0 configs via cml_add_node's configuration
   parameter, or later with cml_extract_node_configuration / cml_send_config.
6. Boot: cml_start_lab, then cml_wait_for_lab_converged (IOS nodes can take
   minutes — raise timeout_seconds for big labs).
7. Verify: cml_get_lab_layer3_addresses for addressing, cml_run_commands for
   show commands or pings across nodes.
8. Report the lab ID, node IDs, and any deviations from the request."""

    @mcp.prompt(
        name="cml_capture_traffic",
        title="Capture Traffic on a CML Link",
        description="Packet-capture workflow: pick a link, capture, and analyze packets.",
    )
    def cml_capture_traffic(lab_id: str, link_hint: str) -> str:
        return f"""Capture and analyze traffic in CML lab {lab_id}.
Link to capture (user hint): {link_hint}

1. Find the link: cml_list_links (or cml_get_lab_topology) and match the
   hint against the endpoint nodes/interfaces. Confirm with cml_get_link
   that its state is STARTED — captures need a running link.
2. Start the capture: cml_set_link_capture action='start' (writes must be
   enabled). Bound it with maxpackets/maxtime, and use bpfilter (BPF syntax,
   e.g. 'icmp' or 'tcp port 179') to capture only relevant traffic.
3. Generate traffic if needed: cml_run_commands on an endpoint node
   (e.g. ping the far side) so the capture has something to see.
4. Monitor: cml_get_link_capture_status until enough packets are captured,
   then cml_set_link_capture action='stop'.
5. Analyze: cml_get_link_capture_packets for decoded summaries; offer
   cml_download_link_pcap to save a .pcap for Wireshark.
6. Report what the traffic shows relative to the user's question."""
