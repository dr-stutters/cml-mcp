"""Screenshot tools: capture web UIs (CML, device GUIs, any URL) via headless
Chromium and return the image inline.

Requires the optional 'browser' extra (Playwright + Chromium). Tools degrade
gracefully with an actionable message when it is not installed.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP, Image

from ..client import CMLClient
from ..screenshots import BrowserNotAvailable, capture
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def screenshot_web_ui(
        url: str,
        username: str | None = None,
        password: str | None = None,
        full_page: bool = False,
        wait_seconds: float = 6.0,
        save_path: str | None = None,
    ):
        """Capture a screenshot of a web UI reachable from the server and return the image.

        Works for the CML web UI, a device management GUI (FMC/FDM), or any
        URL. Self-signed TLS is accepted. If username/password are given and a
        login form is present, it logs in first (and clicks through the FMC
        "Session Exists" dialog).

        Args:
            url: Full URL, e.g. https://<cml-host> or https://<fmc-ip>.
            username/password: Optional credentials for a login form.
            full_page: Capture the entire scrollable page instead of the viewport.
            wait_seconds: Settle time after navigation/login (raise for slow SPAs).
            save_path: If set, also write the PNG to this local path.

        Note: requires the 'browser' extra (`uv sync --extra browser` then
        `uv run playwright install chromium`). FMC allows the admin user only
        one session, so screenshotting the FMC GUI as admin ends other admin
        GUI sessions - use a dedicated read-only account where possible.
        """
        try:
            png = await capture(
                url, username=username, password=password,
                full_page=full_page, wait_seconds=wait_seconds,
            )
        except BrowserNotAvailable as exc:
            return dumps(f"Screenshot unavailable: {exc}")
        if save_path:
            with open(save_path, "wb") as f:
                f.write(png)
        return Image(data=png, format="png")

    @mcp.tool()
    async def screenshot_cml_ui(
        full_page: bool = False,
        save_path: str | None = None,
    ):
        """Screenshot the CML web UI dashboard (logs in with the configured CML credentials).

        Returns the CML home/dashboard view. To capture a specific lab's
        canvas, use screenshot_web_ui with the lab's URL
        (https://<cml-host>/lab/<lab_id>) once logged in.
        """
        try:
            png = await capture(
                client.settings.base_url,
                username=client.settings.username,
                password=client.settings.password,
                full_page=full_page,
                wait_seconds=7.0,
            )
        except BrowserNotAvailable as exc:
            return dumps(f"Screenshot unavailable: {exc}")
        if save_path:
            with open(save_path, "wb") as f:
                f.write(png)
        return Image(data=png, format="png")
