"""Async HTTP client for the CML REST API.

Handles JWT authentication transparently: authenticates on first use and
re-authenticates once when the server returns 401 (expired/invalidated token).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .config import Settings


class CMLAPIError(Exception):
    """Raised when the CML API returns an error response."""

    def __init__(self, status_code: int, method: str, path: str, detail: str):
        self.status_code = status_code
        super().__init__(f"CML API error {status_code} on {method} {path}: {detail}")


class CMLClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._settings = settings
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            base_url=settings.api_url,
            verify=settings.verify_ssl,
            timeout=settings.timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _authenticate(self) -> None:
        resp = await self._http.post(
            "/authenticate",
            json={
                "username": self._settings.username,
                "password": self._settings.password,
            },
        )
        if resp.status_code != 200:
            raise CMLAPIError(
                resp.status_code, "POST", "/authenticate",
                f"authentication failed: {resp.text[:500]}",
            )
        self._token = resp.json()

    async def _ensure_token(self) -> None:
        if self._token is None:
            async with self._auth_lock:
                if self._token is None:
                    await self._authenticate()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        content: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        raw_response: bool = False,
    ) -> Any:
        """Issue an authenticated request against the CML API.

        Returns parsed JSON for JSON responses, text for text responses, or the
        httpx.Response itself when raw_response=True (for binary downloads).
        """
        await self._ensure_token()
        if not path.startswith("/"):
            path = "/" + path
        # Drop None-valued query params so callers can pass optionals directly.
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        for attempt in (1, 2):
            req_headers = {"Authorization": f"Bearer {self._token}"}
            if headers:
                req_headers.update(headers)
            resp = await self._http.request(
                method,
                path,
                params=params or None,
                json=json_body,
                content=content,
                headers=req_headers,
            )
            if resp.status_code == 401 and attempt == 1:
                async with self._auth_lock:
                    await self._authenticate()
                continue
            break

        if resp.status_code >= 400:
            detail = resp.text[:2000]
            try:
                err = resp.json()
                if isinstance(err, dict):
                    detail = err.get("description") or err.get("detail") or detail
                    if not isinstance(detail, str):
                        detail = json.dumps(detail)[:2000]
            except Exception:
                pass
            raise CMLAPIError(resp.status_code, method.upper(), path, detail)

        if raw_response:
            return resp
        if resp.status_code == 204 or not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            return resp.json()
        return resp.text

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.request("POST", path, **kw)

    async def put(self, path: str, **kw: Any) -> Any:
        return await self.request("PUT", path, **kw)

    async def patch(self, path: str, **kw: Any) -> Any:
        return await self.request("PATCH", path, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, **kw)

    # ------------------------------------------------------------------
    # Helpers used by multiple tools
    # ------------------------------------------------------------------

    async def resolve_node_interface(self, lab_id: str, node_or_iface_id: str) -> str:
        """Return a connectable interface id.

        Accepts either an interface id (returned unchanged if it exists as an
        interface) or a node id, in which case the first free physical
        interface on that node is used - creating a new one if all are taken.
        """
        nodes = await self.get(f"/labs/{lab_id}/nodes")
        if node_or_iface_id not in nodes:
            return node_or_iface_id  # assume it's already an interface id

        ifaces = await self.get(
            f"/labs/{lab_id}/nodes/{node_or_iface_id}/interfaces",
            params={"data": True},
        )
        for iface in ifaces:
            if iface.get("type") == "physical" and not iface.get("is_connected"):
                return iface["id"]

        created = await self.post(
            f"/labs/{lab_id}/interfaces", json_body={"node": node_or_iface_id}
        )
        # The API may return a single interface object or a list of them.
        if isinstance(created, list):
            for iface in created:
                if iface.get("type", "physical") == "physical" and not iface.get("is_connected"):
                    return iface["id"]
            created = created[0]
        return created["id"]
