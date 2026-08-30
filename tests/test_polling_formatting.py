"""Core helpers: polling.wait_until and structure-preserving truncation."""

from __future__ import annotations

import json

from cml_mcp.formatting import finalize
from cml_mcp.polling import wait_until


async def test_wait_until_returns_on_first_success():
    calls = []

    async def fetch() -> str:
        calls.append(1)
        return "BOOTED"

    finished, state, elapsed = await wait_until(
        fetch, lambda s: s == "BOOTED", timeout_seconds=30, interval_seconds=1
    )
    assert finished is True
    assert state == "BOOTED"
    assert elapsed >= 0
    assert len(calls) == 1  # polls at least once, stops immediately when done


async def test_wait_until_times_out_without_raising():
    finished, state, _ = await wait_until(
        _const("STARTED"), lambda s: s == "BOOTED", timeout_seconds=1, interval_seconds=5
    )
    assert finished is False
    assert state == "STARTED"  # caller reports the last observed state


async def test_wait_until_calls_on_poll_and_swallows_its_errors():
    seen: list[tuple[str, float]] = []

    async def on_poll(state: str, elapsed: float) -> None:
        seen.append((state, elapsed))
        raise RuntimeError("progress channel died")  # must not break the wait

    finished, _, _ = await wait_until(
        _const("BOOTED"),
        lambda s: s == "BOOTED",
        timeout_seconds=10,
        interval_seconds=1,
        on_poll=on_poll,
    )
    assert finished is True
    assert len(seen) == 1


def _const(value: str):
    async def fetch() -> str:
        return value

    return fetch


def test_finalize_passes_short_text_through(settings):
    assert finalize("hello", settings) == "hello"


def test_finalize_keeps_truncated_envelope_parseable(make_settings):
    settings = make_settings(max_response_chars=1_200)
    envelope = {
        "total": 50,
        "count": 50,
        "offset": 0,
        "items": [{"id": f"n{i}", "label": "x" * 60} for i in range(50)],
        "has_more": False,
        "next_offset": None,
    }
    out = finalize(json.dumps(envelope, indent=2), settings)
    data = json.loads(out)  # still valid JSON, not a blind slice
    assert len(data["items"]) < 50
    assert data["_truncated"]["omitted"] == 50 - len(data["items"])
    assert "hint" in data["_truncated"]


def test_finalize_truncation_hint_is_customizable(make_settings):
    settings = make_settings(max_response_chars=1_200)
    envelope = {"items": [{"id": f"n{i}", "blob": "y" * 80} for i in range(40)]}
    out = finalize(
        json.dumps(envelope, indent=2), settings, truncation_hint="use detail='summary'"
    )
    assert "use detail='summary'" in json.loads(out)["_truncated"]["hint"]


def test_finalize_cuts_plain_text_at_a_line_boundary(make_settings):
    settings = make_settings(max_response_chars=1_000)
    text = "\n".join(f"line {i} " + "z" * 60 for i in range(80))
    out = finalize(text, settings)
    assert len(out) < len(text)
    body = out.split("[Truncated")[0] if "[Truncated" in out else out
    # No half-line: every retained line is one of the originals.
    originals = set(text.split("\n"))
    assert all(line in originals for line in body.rstrip("\n").split("\n") if line)
