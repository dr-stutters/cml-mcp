#!/usr/bin/env python3
"""HTML -> PDF renderer for customer-facing test reports.

The `testing-agent` (and anyone rendering a report) uses this to turn the styled
report HTML — designed via the TypeUI MCP, or the fallback template — into the
committed `report.pdf`. It drives the headless Chromium that ships with the CML
MCP repo's Playwright (`.venv`), so there is no extra dependency to install.

Usage:
    .venv/bin/python "Test Reports/render_pdf.py" <input.html> <output.pdf>
    # or from the repo venv:
    uv run python "Test Reports/render_pdf.py" report.html "Test Reports/2026-07-17/report.pdf"

Notes:
- `print_background=True` keeps the TypeUI styling (accent bars, table shading).
- A4 with modest margins; the HTML controls page breaks via CSS
  (`@media print { .page-break { break-before: page; } }`).
- Local assets (the SVG topology diagram, the CML screenshot) must be referenced
  by absolute path or embedded as data: URIs so Chromium can load them under
  `file://`. Embedding is safest for a self-contained, committable PDF.
"""

from __future__ import annotations

import pathlib
import sys


def render(html_path: str, pdf_path: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        sys.stderr.write(
            "playwright not importable — run me with the repo venv "
            "(.venv/bin/python or `uv run python`).\n"
        )
        return 2

    src = pathlib.Path(html_path).resolve()
    if not src.is_file():
        sys.stderr.write(f"input HTML not found: {src}\n")
        return 2
    out = pathlib.Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        # file:// so relative asset paths (diagram/screenshot) resolve
        page.goto(src.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(out),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
            prefer_css_page_size=True,
        )
        browser.close()

    size = out.stat().st_size
    print(f"wrote {out} ({size:,} bytes)")
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__ or "")
        sys.stderr.write("\nerror: expected <input.html> <output.pdf>\n")
        return 2
    return render(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
