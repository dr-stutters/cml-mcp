# Example prompts — CML MCP

Copy any prompt below to an AI agent (Claude Code, Claude Desktop, …) with the
**`cml`** MCP server connected. The server is built to be driven in plain
language — you don't call tools by name, you describe the outcome and the agent
picks the tools. Names in `code` below just show which tools each prompt exercises.

## One end-to-end scenario

> **"Build a lab called `ospf-triangle` with three IOSv routers (R1, R2, R3) in a
> full triangle. Give each link a /30, configure OSPF area 0 on every interface,
> boot the lab, wait for it to converge, then confirm all three OSPF adjacencies
> reach FULL and every router can ping the others' loopbacks. Finally, export the
> whole thing as a topology spec I can commit to git."**

Exercises: `create_lab` → `add_node` ×3 → `create_link` ×3 → `control_lab(start)`
→ `get_lab_state` (until converged) → `pyats_configure` / `pyats_parse` (verify
`show ip ospf neighbor`) → `pyats_execute` (pings) → `export_lab_spec`.

## Focused tasks (one area each)

**Topology-as-code** — build a whole lab in one call
> "Here's a YAML lab spec — validate it, then build it and give me the delegation
> briefs for each device group."  *(`validate_lab_spec` → `build_lab_from_spec`)*

**Talk to a running device**
> "On R1, show me the BGP summary as structured data, then learn its full OSPF
> state."  *(`pyats_parse` `show bgp summary` → `pyats_learn ospf`)*

**WAN emulation / chaos**
> "Add 80 ms latency and 2% loss to the R1–R2 link, then show me how OSPF reacts
> over the next minute."  *(`configure_link_condition` → `pyats_execute`)*

**Packet capture**
> "Start a packet capture on the link between R2 and R3, run a ping across it,
> then download the pcap."  *(`manage_packet_capture`)*

**System / capacity**
> "What's eating the most memory and CPU on the CML server right now, and how many
> nodes are running across all labs?"  *(`get_system_status` / `get_lab_simulation_stats`
> / `list_all_running_nodes`)*

**Licensing**
> "Register this CML server with Smart Licensing token `<token>` and confirm it's
> In Compliance."  *(`manage_licensing` → `get_licensing_status`)*

**See the UI (needs the `browser` extra)**
> "Screenshot the CML web UI dashboard so I can see the current topology."
> *(`screenshot_cml_ui`)*

## Tips

- **Start broad, let it plan.** The architect-style prompt above works because the
  agent sequences the tools itself. For multi-device labs the `cml-lab-architect`
  agent (Claude Code) designs + builds, then fans briefs to the device specialists.
- **IDs are UUIDs**; node labels like `R1` work for the pyATS tools.
- **Lifecycle:** a lab must be stopped before wipe, and wiped before delete.
- **Anything not covered** by a dedicated tool is reachable via `cml_api_call`
  (see `list_api_endpoints`).
