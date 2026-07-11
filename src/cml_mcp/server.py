"""CML MCP server entry point."""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from .client import CMLClient
from .config import load_settings
from .tools import register_all


def build_server() -> FastMCP:
    settings = load_settings()
    client = CMLClient(settings)
    mcp = FastMCP(
        "cml",
        instructions=(
            "Tools for Cisco Modeling Labs (CML) - create and manage network "
            "simulation labs, nodes, links, and the CML system itself via its "
            "REST API. Lab/node/link/interface ids are UUIDs; list tools return "
            "them. Typical flow: create_lab -> add_node (repeat) -> create_link "
            "(repeat) -> control_lab(start). Use cml_api_call for any endpoint "
            "not covered by a dedicated tool."
        ),
    )
    register_all(mcp, client)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="CML MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    args = parser.parse_args()
    build_server().run(transport=args.transport)


if __name__ == "__main__":
    main()
