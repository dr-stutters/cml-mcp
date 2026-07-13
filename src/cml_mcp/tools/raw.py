"""Raw API passthrough - guarantees coverage of every CML API endpoint."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def cml_api_call(
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        path: str,
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | list[Any] | str | None = None,
        save_response_to: str | None = None,
    ) -> str:
        """Call any CML REST API endpoint directly (authenticated).

        Escape hatch for the few endpoints without a dedicated tool (e.g.
        /system_archive, /telemetry, /wireless/pcap, /keys/console,
        /licensing/reservation/*, /auth_extended, /ai/mcp/configuration).

        Args:
            method: HTTP method.
            path: API path relative to /api/v0, e.g. '/labs' or '/system_health'.
            query_params: Optional query parameters.
            body: Optional request body. Pass a JSON object/array directly, or a
                string (parsed as JSON, else sent as plain text for text endpoints).
            save_response_to: If set, write the raw response bytes to this local
                file path instead of returning them (for binary downloads).
        """
        json_body: Any = None
        content: str | None = None
        if body is not None:
            if isinstance(body, (dict, list)):
                json_body = body
            else:
                try:
                    json_body = json.loads(body)
                except (json.JSONDecodeError, TypeError):
                    content = body
        if save_response_to:
            resp = await client.request(
                method, path, params=query_params,
                json_body=json_body, content=content, raw_response=True,
            )
            with open(save_response_to, "wb") as f:
                f.write(resp.content)
            return dumps(f"Saved {len(resp.content)} bytes to {save_response_to}")
        return dumps(await client.request(
            method, path, params=query_params, json_body=json_body, content=content,
        ))

    @mcp.tool()
    async def list_api_endpoints(filter: str | None = None) -> str:
        """List all CML REST API operations (method + path + summary), optionally filtered by substring.

        Use this to discover endpoints for cml_api_call.
        """
        spec = await client.get("/openapi.json")
        lines = []
        for path, ops in spec.get("paths", {}).items():
            for method, op in ops.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                summary = op.get("summary") or op.get("description") or ""
                line = f"{method.upper():6s} {path}  {summary.splitlines()[0][:90] if summary else ''}"
                if filter and filter.lower() not in line.lower():
                    continue
                lines.append(line)
        return dumps("\n".join(sorted(lines)))
