"""Generic polling helper for convergence-wait tools.

Async platform operations (boots, deployments, background tasks) otherwise
leave agents doing poll-sleep-poll loops through repeated tool calls. Wait
tools collapse that into one call: they poll server-side via wait_until() and
return the final state.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def wait_until(
    fetch: Callable[[], Awaitable[T]],
    done: Callable[[T], bool],
    *,
    timeout_seconds: float,
    interval_seconds: float = 5.0,
    on_poll: Callable[[T, float], Awaitable[None]] | None = None,
) -> tuple[bool, T, float]:
    """Poll fetch() until done(state) is true or the timeout elapses.

    on_poll, when given, is awaited after every fetch with
    (state, elapsed_seconds) — callers use it for MCP progress reporting.
    Any exception it raises is swallowed: a broken progress channel must
    never break the wait itself.

    Returns (finished, last_state, elapsed_seconds). Never raises on timeout —
    the caller reports the last observed state so the agent can decide what to
    do next.
    """
    start = time.monotonic()
    while True:
        state = await fetch()
        elapsed = time.monotonic() - start
        if on_poll is not None:
            try:
                await on_poll(state, elapsed)
            except Exception:
                pass  # progress reporting is best-effort only
        if done(state):
            return True, state, elapsed
        if elapsed + interval_seconds > timeout_seconds:
            return False, state, elapsed
        await asyncio.sleep(interval_seconds)
