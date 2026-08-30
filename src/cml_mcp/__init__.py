"""cml_mcp — MCP server for Cisco Modeling Labs (CML 2.x).

Exposes CML's REST API (labs, nodes, interfaces, links, captures, system
inventory) plus pyATS-backed console access as MCP tools. Read-only unless
CML_MCP_ENABLE_WRITES=true. See README.md for the tool list.
"""

__version__ = "0.1.0"
