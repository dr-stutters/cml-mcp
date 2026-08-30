"""Server assembly and entry point.

This is a stdio MCP server: stdout belongs to the protocol, so ALL logging goes
to stderr. Never print() from tool code.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from pydantic import ValidationError

from cml_mcp.auth import AuthStrategy, LoginTokenAuth, StaticTokenAuth
from cml_mcp.client import ApiClient
from cml_mcp.config import Settings
from cml_mcp.errors import PlatformError
from cml_mcp.prompts import register_prompts
from cml_mcp.safety import AppContext
from cml_mcp.tools import register_all_tools

SERVER_NAME = "cml_mcp"

logger = logging.getLogger(__name__)


def create_auth(settings: Settings) -> AuthStrategy:
    """CML auth (verified against CML 2.10 OpenAPI spec).

    POST {base_url}/authenticate with JSON {"username", "password"}; the 200
    response body IS the JWT (a JSON-encoded string). Sent on every request as
    Authorization: Bearer <token>; a 401 triggers one transparent re-login.

    A pre-acquired JWT can be supplied via CML_MCP_API_TOKEN instead (takes
    precedence; used by the test suite and short-lived automation). Note that
    base_url must include the API prefix, e.g. https://cml.example.com/api/v0.
    """
    if settings.api_token:
        return StaticTokenAuth(settings.api_token)
    return LoginTokenAuth(
        "/authenticate",
        settings.username,
        settings.password,
        login_style="json",
        token_location="body",
    )


def build_instructions(settings: Settings) -> str:
    """Server-level instructions shown to connecting agents."""
    prefix = Settings.model_config.get("env_prefix", "")
    lines = [
        "Tools for Cisco Modeling Labs (CML 2.x) — a network simulation platform.",
        "Object model: labs contain nodes (routers/switches/hosts); nodes have "
        "interfaces; links connect exactly two interfaces. All IDs are UUIDs — "
        "discover them with the list tools before calling get/by-id tools.",
        "Typical flows: cml_list_labs -> cml_get_lab_topology (summary first, "
        "then detail='full' to drill in) -> node/link tools. Troubleshooting: "
        "cml_get_node with include_diagnostics=true, cml_get_lab_element_state, "
        "cml_get_node_console_log, link packet captures.",
        "Lifecycle tools wait by default: cml_start_lab / cml_stop_lab / "
        "cml_set_node_state return once the lab or node has converged, so you do "
        "not need to poll (pass wait=false to return immediately).",
        "Run CLI on booted nodes with cml_run_commands (show/ping/traceroute/dir, "
        "several nodes and commands per call, genie-parsed JSON by default). "
        "New to a topology? cml_list_sample_labs + cml_load_sample_lab give you a "
        "ready-made lab in one call.",
        "CML returns full collections (no server-side pagination); list tools "
        "paginate client-side via limit/offset and support response_format "
        "'markdown' (default, human-readable) or 'json' (complete data).",
    ]
    if settings.enable_writes:
        lines.append(
            "Write tools are ENABLED and modify the live platform. Confirm intent "
            "before creating, changing, or deleting anything."
        )
    else:
        lines.append(
            "This server is READ-ONLY: write tools are not registered. To enable "
            f"them, set the {prefix}ENABLE_WRITES=true environment variable and restart."
        )
    return "\n".join(lines)


def build_server(settings: Settings | None = None) -> MCPServer:
    """Wire settings, auth, client, and tools into an MCPServer."""
    settings = settings or Settings()  # type: ignore[call-arg]  # env supplies base_url
    auth = create_auth(settings)
    client = ApiClient(settings, auth)
    ctx = AppContext(settings=settings, client=client)

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        try:
            yield ctx
        finally:
            await client.aclose()

    mcp = MCPServer(SERVER_NAME, instructions=build_instructions(settings), lifespan=lifespan)
    register_all_tools(mcp, ctx)
    register_prompts(mcp)
    return mcp


def main() -> None:
    """Console entry point (stdio transport)."""
    try:
        settings = Settings()  # type: ignore[call-arg]  # env supplies base_url
    except ValidationError as e:
        missing = ", ".join(str(err["loc"][0]).upper() for err in e.errors())
        prefix = Settings.model_config.get("env_prefix", "")
        print(
            f"Configuration error — check environment variables ({prefix}{missing}).\n{e}",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    logging.basicConfig(
        stream=sys.stderr,
        level=settings.log_level.upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logger.info("Starting %s (writes %s)", SERVER_NAME, "ON" if settings.enable_writes else "off")
    try:
        server = build_server(settings)
    except PlatformError as e:
        # Auth strategies raise PlatformError for incomplete credentials — fail fast
        # with a clean message, not a traceback.
        print(f"Configuration error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    server.run()


if __name__ == "__main__":
    main()
