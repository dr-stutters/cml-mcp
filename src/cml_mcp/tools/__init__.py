"""Tool registration for the CML MCP server."""

import importlib
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient

MAX_OUTPUT_CHARS = 60_000


def dumps(data: Any) -> str:
    """Serialize a tool result, truncating pathologically large payloads."""
    if data is None:
        return "OK (no content returned)"
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, indent=2, default=str)
    if len(text) > MAX_OUTPUT_CHARS:
        text = (
            text[:MAX_OUTPUT_CHARS]
            + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars - "
            "request a narrower query for full data]"
        )
    return text


_TOOL_MODULES = (
    "labs",
    "nodes",
    "interfaces",
    "links",
    "annotations",
    "definitions",
    "users_groups",
    "system",
    "licensing",
    "pyats_tools",
    "screenshots",
    "raw",
)


def register_all(mcp: FastMCP, client: CMLClient) -> None:
    for name in _TOOL_MODULES:
        module = importlib.import_module(f".{name}", __package__)
        module.register(mcp, client)
