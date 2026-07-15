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
  _TEMPLATE.md         # report skeleton (8 sections)
  <YYYY-MM-DD>/
    report.md          # the report (canonical, committed)
    results.json       # machine-collected raw results from run_report.py
```

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

## Result legend

**PASS** · **FAIL** · **SKIP** (version/feature not applicable) · **UNREACHABLE** (live
target not reachable this run → falls back to prior validated evidence).
