# Test Reports library

Customer-facing **test reports** — the *results* side of the
[Test Plans library](../Test%20Plans/). Where a test plan says *what* is tested and the
pass/fail criteria, a report records *what happened* on a given run: the executed
results, the verdict, and the evidence. Each report is a dated snapshot suitable to hand
to a customer.

## Layout

```
Test Reports/
  README.md            # this file
  run_report.py        # the runner — executes the automated gate across the 6 repos
  render_pdf.py        # HTML -> report.pdf via the repo's headless Chromium (Playwright)
  _TEMPLATE.md         # report skeleton (8 sections)
  <YYYY-MM-DD>/
    report.md          # the report (canonical, committed)
    results.json       # machine-collected raw results from run_report.py
    report.pdf         # customer-facing PDF (self-styled HTML, committed) — when produced
```

> **Owned by [`testing-agent`](../.claude/agents/testing-agent.md).** The QA agent authors the
> plan, executes the suite, and produces the **customer-facing PDF**: it builds a self-styled,
> print-ready HTML report and renders it with `render_pdf.py`
> (`.venv/bin/python "Test Reports/render_pdf.py" <report.html> "Test Reports/<date>/report.pdf"`).
> No external design service — the built-in template stands alone (a design-system MCP could
> style the same HTML later, but is never required). You can still hand-curate a report
> yourself — the agent just makes it one delegable step.

## How a report is produced

1. **Automated gate** — `run_report.py` runs each repo's `ruff` + `pytest` (offline,
   always) and, with flags, the live `smoke_test.py` / `integration_test.py --write`:

   ```bash
   uv run python "Test Reports/run_report.py"                 # offline gate (ruff + unit)
   uv run python "Test Reports/run_report.py" --smoke         # + live read-only smoke
   uv run python "Test Reports/run_report.py" --smoke --write # + live write round-trips
   uv run python "Test Reports/run_report.py" --outdir "Test Reports/$(date +%F)"
   ```

   It writes `results.json`. Live targets that don't answer (lab VPN down) are recorded
   as **`unreachable`** — distinct from **`fail`** — so a report never conflates "not run"
   with "broken".

2. **Curated narrative** — copy `_TEMPLATE.md` to `<date>/report.md`, fold in
   `results.json` (§4), add the lab-design acceptance results from their proofs (§5), and
   write the executive summary + verdict (§1, §7).

3. **Presentable copies** — the committed `report.md` is the source of truth. A shareable
   **HTML** copy is published as a private Artifact from `report.md`. **Word (.docx)**
   export is roadmap (#41): `report.md` → `report.docx` via `pypandoc-binary`.

## Runs

| Date | Verdict | Unit | Live smoke | Lab designs | Report |
|---|---|---|---|---|---|
| 2026-07-15 | ✅ PASS | 134/134 | CML + Windows live; others prior-validated | 4/4 PASS | [report](2026-07-15/report.md) |
| 2026-07-16 | ⚠️ PASS-with-caveats | 22/22 (catc) | CatC live 96/97 checks | CatC-Onboarding PASS | [report](2026-07-16/report.md) |
| 2026-07-17 | ⚠️ PASS-with-caveats | n/a (manual-live) | ISE 3.5 + FMC/FTD + SDA fabric live | RTC Stage A+B 12 PASS / 1 partial | [report](2026-07-17/report-ANC.pdf) |
| 2026-07-17 | ✅ PASS | n/a (manual-live) | ISE 3.5 + FMC/FTD (Snort 3) + SDA fabric live | C6 IPS-RTC (Stage C) 6 PASS / 0 fail | [report](2026-07-17/report-C6-IPS-RTC.pdf) |

## Result legend

**PASS** · **FAIL** · **SKIP** (version/feature not applicable) · **UNREACHABLE** (live
target not reachable this run → falls back to prior validated evidence).
