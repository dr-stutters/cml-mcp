"""Response formatting shared by all tools.

Every listing tool supports two output formats (agents pick via response_format):
- markdown: human-readable, curated fields, IDs in parentheses
- json: complete structured data for programmatic processing

Every tool response passes through finalize() so oversized payloads are
truncated with a note instead of flooding the agent's context.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from cml_mcp.config import Settings


class ResponseFormat(StrEnum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def to_json(data: Any) -> str:
    """Serialize API data for the agent (stable keys, non-JSON types stringified)."""
    return json.dumps(data, indent=2, default=str)


def pagination_envelope(
    items: list[Any], *, total: int | None, offset: int, limit: int
) -> dict[str, Any]:
    """Standard pagination wrapper for list responses.

    total may be None when the platform doesn't report an overall count; has_more
    then falls back to 'page came back full'.
    """
    count = len(items)
    if total is not None:
        has_more = offset + count < total
    else:
        has_more = count >= limit
    return {
        "total": total,
        "count": count,
        "offset": offset,
        "items": items,
        "has_more": has_more,
        "next_offset": offset + count if has_more else None,
    }


_GENERIC_HINT = "Narrow the query with filters, or page through results with limit/offset."


def _truncate_envelope(data: dict[str, Any], limit: int, hint: str) -> str | None:
    """Drop tail items from a pagination envelope until it serializes under limit.

    Returns the truncated JSON (still parseable, with a '_truncated' marker), or
    None if even an empty items list doesn't fit (caller falls back to text cut).
    """
    items = list(data["items"])
    total_items = len(items)
    best: str | None = None
    lo, hi = 0, total_items - 1  # number of items kept (full list is known too big)
    while lo <= hi:
        mid = (lo + hi) // 2
        data["items"] = items[:mid]
        data["_truncated"] = {"omitted": total_items - mid, "hint": hint}
        candidate = to_json(data)
        if len(candidate) <= limit:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def finalize(text: str, settings: Settings, truncation_hint: str | None = None) -> str:
    """Apply the response-size cap. Call as the last step of every tool.

    Oversized JSON envelopes (dict with an 'items' list) are truncated
    structure-preservingly: tail items are dropped and a '_truncated' marker
    ({"omitted": N, "hint": ...}) is added, so the output stays parseable.
    Other JSON falls back to a raw character cut with an honest note; plain
    text is cut at the last newline before the cap.

    truncation_hint, when given, names the tool's own narrowing parameters
    (e.g. "use limit/offset or detail='summary'") in the truncation marker/note.
    """
    limit = settings.max_response_chars
    if len(text) <= limit:
        return text
    hint = truncation_hint or _GENERIC_HINT
    note = f"\n\n[Truncated: response exceeded {limit} characters. {hint}]"

    if text.lstrip()[:1] in ("{", "["):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            truncated = _truncate_envelope(data, limit, hint)
            if truncated is not None:
                return truncated
        if data is not None:
            # Non-envelope JSON: raw cut breaks the JSON, so say so honestly.
            return text[:limit] + note
        # Fall through: looked like JSON but didn't parse — treat as plain text.

    cut = text[:limit]
    newline = cut.rfind("\n")
    if newline > 0:
        cut = cut[:newline]
    return cut + note
