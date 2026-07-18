#!/usr/bin/env python3
"""Test-report runner for the MCP suite.

Executes the automated test gate across the six sibling MCP repos and writes a
structured results.json (+ a summary to stdout). This is the machine-collected
half of the customer-facing test report (roadmap #40); the narrative/verdict and
the manual-live lab-design results are curated on top in report.md.

Levels (see ../Test Plans/README.md):
  offline (default) : `uv run ruff check` + `uv run pytest -q`   — no live target
  --smoke           : also `uv run python tests/smoke_test.py`     — live read-only
  --write           : also `tests/integration_test.py --write`     — live write (lab only)

Usage:
    uv run python "Test Reports/run_report.py"                    # offline gate
    uv run python "Test Reports/run_report.py" --smoke            # + live smoke
    uv run python "Test Reports/run_report.py" --smoke --write    # + integration
    uv run python "Test Reports/run_report.py" --outdir "Test Reports/2026-07-15"

Live targets may be unreachable from the runner host (lab VPN); such suites are
recorded as `unreachable`, not `fail` — the report distinguishes them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# repo dir (under the MCP base) -> plan prefix + which live suites exist
REPOS = [
    {"name": "cml-mcp", "dir": "CML_MCP", "plan": "CML", "integration": False},
    {"name": "ise-mcp", "dir": "ISE_MCP", "plan": "ISE", "integration": True},
    {"name": "firepower-mcp", "dir": "Firepower_MCP", "plan": "FMC", "integration": False},
    {"name": "windows-mcp", "dir": "Windows_MCP", "plan": "WIN", "integration": True},
    {"name": "splunk-mcp", "dir": "Splunk_MCP", "plan": "SPL", "integration": False},
    {"name": "wlc-mcp", "dir": "WLC_MCP", "plan": "WLC", "integration": False},
]

BASE = Path(__file__).resolve().parents[2]  # .../Test Reports -> CML_MCP -> MCP


def _as_text(value: object) -> str:
    """Coerce subprocess output (None | str | bytes) to str.

    On TimeoutExpired the stdout/stderr attributes can come back as bytes even
    under text=True (the timeout fires before decoding), so mixing them with a
    str default would raise TypeError on concatenation — normalise each first.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int | None, str]:
    """Run a command, return (returncode|None-on-timeout, combined output)."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired as e:
        return None, _as_text(e.stdout) + _as_text(e.stderr)


def _pytest_counts(text: str) -> dict:
    counts = {k: 0 for k in ("passed", "failed", "skipped", "error")}
    for key in counts:
        m = re.search(rf"(\d+) {key}", text)
        if m:
            counts[key] = int(m.group(1))
    return counts


def _classify_live(rc: int | None, out: str) -> dict:
    low = out.lower()
    unreachable = (
        rc is None
        or "connection attempts failed" in low
        or "connecterror" in low
        or "connection refused" in low
        or "timed out" in low
        or (rc != 0 and not out.strip())
    )
    status = "unreachable" if unreachable else ("pass" if rc == 0 else "fail")
    return {"rc": rc, "status": status, "tail": out.strip().splitlines()[-4:]}


def check_repo(repo: dict, *, smoke: bool, write: bool, timeout: int) -> dict:
    cwd = BASE / repo["dir"]
    res: dict = {"name": repo["name"], "plan": repo["plan"], "dir": repo["dir"]}
    if not cwd.exists():
        res["error"] = f"repo not found: {cwd}"
        return res

    # ruff (offline)
    rc, out = _run(["uv", "run", "ruff", "check", "src/", "tests/"], cwd, timeout)
    res["ruff"] = {"rc": rc, "passed": rc == 0, "tail": (out.strip().splitlines()[-1:] or [""])}

    # pytest (offline)
    rc, out = _run(["uv", "run", "pytest", "-q"], cwd, timeout)
    counts = _pytest_counts(out)
    res["unit"] = {
        "rc": rc,
        "passed": counts["passed"],
        "failed": counts["failed"] + counts["error"],
        "skipped": counts["skipped"],
        "ok": rc == 0 and counts["failed"] == 0 and counts["error"] == 0,
        "tail": (out.strip().splitlines()[-1:] or [""]),
    }

    # smoke (live, read-only)
    if smoke:
        rc, out = _run(["uv", "run", "python", "tests/smoke_test.py"], cwd, timeout)
        res["smoke"] = _classify_live(rc, out)

    # integration --write (live, write) where the suite exists
    if write and repo["integration"]:
        rc, out = _run(
            ["uv", "run", "python", "tests/integration_test.py", "--write"], cwd, timeout
        )
        res["integration"] = _classify_live(rc, out)

    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the MCP-suite test gate.")
    ap.add_argument("--smoke", action="store_true", help="also run live smoke tests")
    ap.add_argument("--write", action="store_true", help="also run integration --write (lab only)")
    ap.add_argument("--timeout", type=int, default=90, help="per-suite timeout seconds")
    ap.add_argument("--outdir", default=None, help="dir to write results.json into")
    args = ap.parse_args()

    started = datetime.now(timezone.utc)
    results = [
        check_repo(r, smoke=args.smoke, write=args.write, timeout=args.timeout)
        for r in REPOS
    ]
    report = {
        "generated": started.isoformat(timespec="seconds"),
        "host_base": str(BASE),
        "levels": {"offline": True, "smoke": args.smoke, "write": args.write},
        "repos": results,
    }
    tot_unit = sum(r.get("unit", {}).get("passed", 0) for r in results)
    fail_unit = sum(r.get("unit", {}).get("failed", 0) for r in results)
    report["totals"] = {"unit_passed": tot_unit, "unit_failed": fail_unit}

    outdir = Path(args.outdir) if args.outdir else Path(__file__).resolve().parent
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "results.json").write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n=== MCP test gate @ {report['generated']} ===")
    for r in results:
        u = r.get("unit", {})
        line = f"{r['name']:14} ruff={'ok' if r.get('ruff', {}).get('passed') else 'X'}"
        line += f"  unit={u.get('passed', 0)}p/{u.get('failed', 0)}f"
        if "smoke" in r:
            line += f"  smoke={r['smoke']['status']}"
        if "integration" in r:
            line += f"  integ={r['integration']['status']}"
        print(line)
    print(f"TOTAL unit: {tot_unit} passed, {fail_unit} failed")
    print(f"results.json -> {outdir / 'results.json'}")
    return 1 if fail_unit else 0


if __name__ == "__main__":
    sys.exit(main())
