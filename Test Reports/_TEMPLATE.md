<!--
Test-report template. Copy the dated folder pattern: Test Reports/<YYYY-MM-DD>/report.md.
The automated sections (§4) are filled from results.json produced by ../run_report.py;
§5 (lab-design acceptance) and the narrative/verdict (§1, §7) are curated. Keep the 8
headings so every report reads the same. Delete these comments in the copy.
Result legend: PASS · FAIL · SKIP · UNREACHABLE (live target not reachable this run —
distinct from FAIL; falls back to prior validated evidence).
-->

# MCP Suite — Test Report

**Run date:** <YYYY-MM-DD> · **Tester:** <name> · **Verdict:** <PASS / PASS-with-caveats / FAIL>

## 1. Executive summary

Two or three sentences: what was tested, the headline result (e.g. "134/134 unit tests
pass, lint clean; live smoke confirmed on reachable targets"), and the overall verdict
with any caveat (e.g. "lab offline at run time — live ISE/FMC results from the prior
validated cycle").

## 2. Scope & systems under test

Which test plans this report executes ([Test Plans/](../../Test%20Plans/)): the 6 MCP
servers and the 4 lab designs. Component versions verified against.

## 3. Test environment

| Target | Address (lab-specific) | Reachable this run? |
|---|---|---|
| <e.g. CML controller> | <ip> | yes / no |

Reproduce: `uv run python "Test Reports/run_report.py" [--smoke --write] --outdir <dir>`.

## 4. Results — automated gate (MCP servers)

From `results.json`. Levels: unit (mocked, CI) · smoke (live read-only) · integration
(live write).

| Server | Plan | ruff | Unit | Smoke | Integration | Result |
|---|---|---|---|---|---|---|
| <cml-mcp> | [CML](../../Test%20Plans/MCP%20Servers/cml-mcp.md) | ✅ | Np/0f | pass/unreachable | n/a | PASS |

## 5. Results — lab-design acceptance

Manual-live end-to-end acceptance, from each design's proof (packet-tracer matrices,
live-session lookups, pyATS pings). Cite the run/cycle each was validated in.

| Design | Plan | Cases | Result | Evidence |
|---|---|---|---|---|
| <Firepower SGT Enforcement> | [SGT](../../Test%20Plans/Lab%20Designs/firepower-sgt-enforcement.md) | SGT-001…006 | PASS | packet-tracer permit/deny matrix |

## 6. Summary statistics

| Metric | Value |
|---|---|
| Unit tests | N passed / 0 failed |
| Lint (ruff) | 6/6 clean |
| Live smoke (this run) | X pass / Y unreachable |
| Lab-design acceptance | 4/4 plans PASS |

## 7. Observations & defects

Defects raised (with severity + status), or "None — all executed cases passed." Note any
UNREACHABLE targets and the fallback evidence used.

## 8. Appendix

- `results.json` — machine-collected raw results.
- Per-suite output tails (pytest summary lines, smoke transcripts).
- Reproduce commands + the exact runner invocation used.
