"""Tool registry.

Each tool module exposes register(mcp, ctx) — one module per CML API area.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from cml_mcp.safety import AppContext
from cml_mcp.tools import console, convergence, labs, links, nodes, system

ALL_MODULES = [
    labs,
    nodes,
    links,
    system,
    convergence,
    console,
]


def register_all_tools(mcp: MCPServer, ctx: AppContext) -> None:
    for module in ALL_MODULES:
        module.register(mcp, ctx)
