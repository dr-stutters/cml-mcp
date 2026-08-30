"""CML convergence-wait tools: block in one call until a lab or node settles.

After cml_start_lab / cml_stop_lab / cml_set_node_state, agents otherwise sit in a
poll-sleep-poll loop over cml_get_lab_element_state — many tool round trips.
These tools collapse that into a single call: they poll CML's
GET .../check_if_converged endpoint server-side (via polling.wait_until) and
return a final-state summary. Both are read-only — they only ever GET.

A timeout is NOT an error: the tool returns converged=false plus the current
states so the calling agent can decide whether to keep waiting.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from cml_mcp.client import ApiClient
from cml_mcp.errors import format_error
from cml_mcp.formatting import finalize, to_json
from cml_mcp.polling import wait_until
from cml_mcp.safety import AppContext, register_tool

# States in which a lab/node is settled enough to wipe then delete.
STOPPED_STATES = {"STOPPED", "DEFINED_ON_CORE"}


# Progress callback shape shared with polling.wait_until: (state, elapsed_seconds).
OnPoll = Callable[[Any, float], Awaitable[None]]


async def wait_for_lab_stopped(
    client: ApiClient,
    lab_id: str,
    *,
    timeout_seconds: float = 120.0,
    on_poll: OnPoll | None = None,
) -> tuple[bool, str]:
    """Poll a lab's overall state until it is stopped. Returns (stopped, last_state).

    CML's stop is asynchronous, so force-delete flows must wait here before
    wiping — otherwise the wipe/delete can 400 with 'not stopped'. on_poll is
    passed through to wait_until for progress reporting (exceptions swallowed).
    """
    finished, state, _ = await wait_until(
        lambda: client.request_json("GET", f"/labs/{lab_id}/state"),
        lambda s: s in STOPPED_STATES,
        timeout_seconds=timeout_seconds,
        interval_seconds=3.0,
        on_poll=on_poll,
    )
    return finished, str(state)


async def wait_for_node_stopped(
    client: ApiClient,
    lab_id: str,
    node_id: str,
    *,
    timeout_seconds: float = 120.0,
    on_poll: OnPoll | None = None,
) -> tuple[bool, str]:
    """Poll a node's state until it is stopped. Returns (stopped, last_state).

    on_poll is passed through to wait_until for progress reporting
    (exceptions swallowed).
    """

    async def _fetch() -> str:
        data = await client.request_json("GET", f"/labs/{lab_id}/nodes/{node_id}/state")
        return data.get("state", "") if isinstance(data, dict) else str(data)

    finished, state, _ = await wait_until(
        _fetch,
        lambda s: s in STOPPED_STATES,
        timeout_seconds=timeout_seconds,
        interval_seconds=3.0,
        on_poll=on_poll,
    )
    return finished, str(state)


LAB_ID_DESC = "Lab ID (UUID, e.g. '90f84e38-a71c-4d57-8d90-00fa8a197385')."
NODE_ID_DESC = "Node ID (UUID, e.g. '26f677f3-fcb2-47ef-9171-dc112d80b54f')."
TIMEOUT_DESC = (
    "Maximum seconds to wait before reporting not-converged-yet (e.g. 240). "
    "A full lab of IOS nodes can take several minutes to boot."
)
INTERVAL_DESC = "Seconds between convergence checks against CML (e.g. 5)."

_NOT_CONVERGED_NOTE = (
    "Not converged yet — the timeout elapsed while elements were still settling. "
    "This is NOT an API failure. Call this tool again to keep waiting, or "
    "inspect slow nodes with cml_get_node_console_log."
)


def register(mcp: MCPServer, ctx: AppContext) -> None:
    settings, client = ctx.settings, ctx.client

    @register_tool(
        mcp,
        ctx,
        name="cml_wait_for_lab_converged",
        title="Wait for Lab Convergence",
        read_only=True,
        idempotent=True,
    )
    async def cml_wait_for_lab_converged(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        timeout_seconds: Annotated[
            int, Field(description=TIMEOUT_DESC, ge=10, le=900)
        ] = 240,
        interval_seconds: Annotated[
            float, Field(description=INTERVAL_DESC, ge=1, le=60)
        ] = 5,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Wait until every element in a lab has converged (finished its transition).

        Read-only. Call this ONCE right after cml_start_lab or cml_stop_lab
        instead of polling cml_get_lab_element_state in a loop — it polls CML
        server-side every interval_seconds and returns when the lab converges
        or timeout_seconds elapses. For a single node use
        cml_wait_for_node_converged instead.

        A timeout is not an error: the response then has "converged": false and
        a note, plus the current node states, so you can decide to call again
        (keep waiting) or investigate stuck nodes.

        Returns:
            str: JSON {"lab_id": str, "converged": bool, "elapsed_seconds": float,
            "node_states": {node_id: state, ...}}; when not converged also
            "timeout_seconds" and a "note" explaining it is not an API failure.
            On failure: "Error: ..." (404 -> lab_id doesn't exist).
        """
        try:

            async def fetch() -> bool:
                data = await client.request_json("GET", f"/labs/{lab_id}/check_if_converged")
                return bool(data)

            async def on_poll(state: bool, elapsed: float) -> None:
                try:
                    if ctx is not None:
                        await ctx.report_progress(
                            elapsed,
                            timeout_seconds,
                            f"Waiting for lab {lab_id} to converge "
                            f"(converged={state}, {elapsed:.0f}s elapsed)",
                        )
                except Exception:
                    pass  # progress reporting must never break the wait

            converged, _, elapsed = await wait_until(
                fetch,
                lambda done: done,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
                on_poll=on_poll,
            )
            states = await client.request_json("GET", f"/labs/{lab_id}/lab_element_state")
            summary: dict[str, Any] = {
                "lab_id": lab_id,
                "converged": converged,
                "elapsed_seconds": round(elapsed, 1),
                "node_states": (states or {}).get("nodes", {}),
            }
            if not converged:
                summary["timeout_seconds"] = timeout_seconds
                summary["note"] = _NOT_CONVERGED_NOTE
            return finalize(to_json(summary), settings)
        except Exception as e:
            return format_error(e)

    @register_tool(
        mcp,
        ctx,
        name="cml_wait_for_node_converged",
        title="Wait for Node Convergence",
        read_only=True,
        idempotent=True,
    )
    async def cml_wait_for_node_converged(
        lab_id: Annotated[
            str, Field(description=LAB_ID_DESC, min_length=1, max_length=100)
        ],
        node_id: Annotated[
            str, Field(description=NODE_ID_DESC, min_length=1, max_length=100)
        ],
        timeout_seconds: Annotated[
            int, Field(description=TIMEOUT_DESC, ge=10, le=900)
        ] = 240,
        interval_seconds: Annotated[
            float, Field(description=INTERVAL_DESC, ge=1, le=60)
        ] = 5,
        ctx: Context | None = None,  # injected by the SDK; not part of the input schema
    ) -> str:
        """Wait until one node has converged (finished starting or stopping).

        Read-only. Call this ONCE right after cml_set_node_state
        instead of polling cml_get_node in a loop — it polls CML server-side
        every interval_seconds and returns when the node converges or
        timeout_seconds elapses. For a whole lab use cml_wait_for_lab_converged.

        A timeout is not an error: the response then has "converged": false and
        a note, plus the node's current state, so you can decide to call again
        (keep waiting) or check cml_get_node_console_log.

        Returns:
            str: JSON {"lab_id": str, "node_id": str, "converged": bool,
            "elapsed_seconds": float, "state": str, "progress": str}; when not
            converged also "timeout_seconds" and a "note" explaining it is not
            an API failure. On failure: "Error: ..."
            (404 -> lab_id or node_id doesn't exist).
        """
        try:

            async def fetch() -> bool:
                data = await client.request_json(
                    "GET", f"/labs/{lab_id}/nodes/{node_id}/check_if_converged"
                )
                return bool(data)

            async def on_poll(state: bool, elapsed: float) -> None:
                try:
                    if ctx is not None:
                        await ctx.report_progress(
                            elapsed,
                            timeout_seconds,
                            f"Waiting for node {node_id} to converge "
                            f"(converged={state}, {elapsed:.0f}s elapsed)",
                        )
                except Exception:
                    pass  # progress reporting must never break the wait

            converged, _, elapsed = await wait_until(
                fetch,
                lambda done: done,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
                on_poll=on_poll,
            )
            state = await client.request_json(
                "GET", f"/labs/{lab_id}/nodes/{node_id}/state"
            )
            state = state or {}
            summary: dict[str, Any] = {
                "lab_id": lab_id,
                "node_id": node_id,
                "converged": converged,
                "elapsed_seconds": round(elapsed, 1),
                "state": state.get("state"),
                "progress": state.get("progress"),
            }
            if not converged:
                summary["timeout_seconds"] = timeout_seconds
                summary["note"] = _NOT_CONVERGED_NOTE
            return finalize(to_json(summary), settings)
        except Exception as e:
            return format_error(e)
