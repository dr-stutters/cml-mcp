"""Annotation tools (text/shapes on the lab canvas) and smart annotations."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps

# CML 2.10 requires every style field on annotation create; these mirror the
# UI's defaults so callers only need to supply type, coordinates, and content.
_BASE_DEFAULTS: dict[str, Any] = {
    "border_color": "#808080FF",
    "border_style": "",
    "color": "#FFFFFFFF",
    "thickness": 1,
    "x1": 0,
    "y1": 0,
    "z_index": 0,
}
_TYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "text": {
        "rotation": 0,
        "text_bold": False,
        "text_content": "",
        "text_font": "monospace",
        "text_italic": False,
        "text_size": 12,
        "text_unit": "pt",
        "color": "#000000FF",
        "border_color": "#00000000",
    },
    "rectangle": {"rotation": 0, "border_radius": 0, "x2": 100, "y2": 100},
    "ellipse": {"rotation": 0, "x2": 100, "y2": 100},
    "line": {"x2": 100, "y2": 100, "line_start": None, "line_end": None},
}


def _with_defaults(annotation: dict[str, Any]) -> dict[str, Any]:
    atype = annotation.get("type")
    if atype not in _TYPE_DEFAULTS:
        raise ValueError("annotation.type must be one of: text, rectangle, ellipse, line")
    merged = {**_BASE_DEFAULTS, **_TYPE_DEFAULTS[atype], **annotation}
    return merged


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def manage_annotations(
        lab_id: str,
        action: Literal["list", "get", "create", "update", "delete"],
        annotation_id: str | None = None,
        annotation: dict[str, Any] | None = None,
    ) -> str:
        """Manage canvas annotations (text, rectangle, ellipse, line) in a lab.

        For create/update, 'annotation' is the annotation object; sensible
        style defaults are filled in on create. Minimal create examples:
        - text: {"type": "text", "text_content": "...", "x1": 0, "y1": 0}
        - rectangle/ellipse: {"type": "rectangle", "x1": 0, "y1": 0, "x2": 200, "y2": 100}
        - line: {"type": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100}
        Common optional fields: color, border_color (both '#RRGGBBAA'),
        border_style ('' solid, '2,2' dotted, '4,2' dashed), thickness,
        rotation, z_index, text_size, text_font, text_bold, text_italic.
        """
        base = f"/labs/{lab_id}/annotations"
        if action == "list":
            return dumps(await client.get(base))
        if action == "create":
            if not annotation:
                raise ValueError("annotation object is required for create")
            return dumps(await client.post(base, json_body=_with_defaults(annotation)))
        if not annotation_id:
            raise ValueError(f"annotation_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"{base}/{annotation_id}"))
        if action == "update":
            if not annotation:
                raise ValueError("annotation object is required for update")
            return dumps(await client.patch(f"{base}/{annotation_id}", json_body=annotation))
        return dumps(await client.delete(f"{base}/{annotation_id}"))

    @mcp.tool()
    async def manage_smart_annotations(
        lab_id: str,
        action: Literal["list", "get", "update"],
        smart_annotation_id: str | None = None,
        update: dict[str, Any] | None = None,
    ) -> str:
        """Manage smart annotations (auto-generated colored regions grouping nodes by tag).

        Smart annotations are created automatically when nodes share a tag;
        'update' can change fields like label, color/fill opacity, border
        style, and padding.
        """
        base = f"/labs/{lab_id}/smart_annotations"
        if action == "list":
            return dumps(await client.get(base))
        if not smart_annotation_id:
            raise ValueError(f"smart_annotation_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"{base}/{smart_annotation_id}"))
        if not update:
            raise ValueError("update object is required for update")
        return dumps(await client.patch(f"{base}/{smart_annotation_id}", json_body=update))
