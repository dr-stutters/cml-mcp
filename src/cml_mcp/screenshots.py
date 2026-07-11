"""Headless-browser screenshots of web UIs reachable from the server.

Uses Playwright + headless Chromium to capture the CML web UI, a device's
management GUI (e.g. FMC/FDM), or any URL. Self-signed certs are accepted.

Optional dependency: install with `uv sync --extra browser` (or
`pip install 'cml-mcp[browser]'`) and then fetch the browser binary once with
`uv run playwright install chromium`. All entry points raise a clear,
actionable error if either piece is missing.
"""

from __future__ import annotations

import asyncio


class BrowserNotAvailable(RuntimeError):
    """Playwright or its Chromium binary is not installed."""


def _require_playwright():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ModuleNotFoundError as exc:
        raise BrowserNotAvailable(
            "Playwright is not installed. Install the browser extra with "
            "`uv sync --extra browser` (or `pip install 'cml-mcp[browser]'`), "
            "then run `uv run playwright install chromium`."
        ) from exc
    from playwright.async_api import async_playwright
    return async_playwright


async def capture(
    url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    wait_seconds: float = 6.0,
    full_page: bool = False,
    width: int = 1440,
    height: int = 900,
    end_existing_session: bool = True,
) -> bytes:
    """Load `url` in headless Chromium and return a PNG screenshot as bytes.

    If username/password are given and a login form is present, they are filled
    and submitted before the shot. `end_existing_session` clicks through the
    FMC "Session Exists" dialog (FMC allows the admin user only one session).
    """
    async_playwright = _require_playwright()
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True, args=["--ignore-certificate-errors", "--no-sandbox"]
            )
        except Exception as exc:  # binary missing / launch failure
            raise BrowserNotAvailable(
                "Chromium could not launch. Run `uv run playwright install "
                f"chromium` to fetch the browser binary. ({exc})"
            ) from exc
        try:
            ctx = await browser.new_context(
                ignore_https_errors=True, viewport={"width": width, "height": height}
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(wait_seconds)

            if username is not None:
                await _try_login(page, username, password or "", end_existing_session)
                await asyncio.sleep(wait_seconds)

            return await page.screenshot(full_page=full_page)
        finally:
            await browser.close()


async def _try_login(page, username: str, password: str, end_existing_session: bool) -> None:
    user_sel = ['input[name="username"]', "#username", 'input[type="text"]']
    pass_sel = ['input[name="password"]', "#password", 'input[type="password"]']
    filled = False
    for s in user_sel:
        if await page.query_selector(s):
            await page.fill(s, username)
            filled = True
            break
    if not filled:
        return  # no login form; nothing to do
    for s in pass_sel:
        if await page.query_selector(s):
            await page.fill(s, password)
            break
    for s in ('button:has-text("Log In")', 'button[type="submit"]',
              'input[type="submit"]', 'button:has-text("Login")'):
        el = await page.query_selector(s)
        if el:
            await el.click()
            break
    else:
        await page.keyboard.press("Enter")
    await asyncio.sleep(4)
    if end_existing_session:
        el = await page.query_selector('button:has-text("End Existing Session")')
        if el:
            await el.click()
