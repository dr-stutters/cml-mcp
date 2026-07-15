<!--
Test-plan template. Copy this file, fill each section, keep the 8 headings and the
test-case table columns identical so every plan reads the same and the #40 report can
consume them uniformly. Delete these HTML comments in the copy.
Test-case IDs: <PREFIX>-NNN, unique within the plan (prefix per the Test Plans README).
-->

# Test Plan — <Component / Design Name>

**Plan ID prefix:** `<PREFIX>-` · **Version:** 1.0 · **Last updated:** <YYYY-MM-DD>

## 1. Scope & purpose

What this plan validates in one or two sentences, and what is **explicitly out of scope**
(e.g. "load/perf testing", "live agent posture on Linux clients").

## 2. System under test

| Item | Value |
|---|---|
| Component | <e.g. ise-mcp server / ISE NAC lab design> |
| Version(s) verified against | <e.g. ISE 3.4.0.608 & 3.5.0.527> |
| Environment | <lab / CML / external VM> — IPs are **lab-specific**, adjust for your environment |
| Dependencies | <e.g. reachable ISE with ERS enabled; a booted cat9000v NAD> |

## 3. Test approach / levels

This plan uses the suite's four standard levels (defined once in the
[library README](../README.md#test-levels)):

- **Unit** — mocked HTTP/transport, no live target; runs in CI (`ruff` + `pytest`).
- **Smoke** — live **read-only** pass (`tests/smoke_test.py`) confirming the target answers.
- **Integration** — live **write** round-trips (`tests/integration_test.py [--write]`),
  create → verify → delete on throwaway objects (lab targets only).
- **Manual/Live** — driven via the MCP tools / pyATS / packet-tracer / GUI; recorded by hand.

## 4. Preconditions & environment

- `.env` (or env vars) point at a reachable target: `<VAR_URL>`, `<VAR_USERNAME>`, `<VAR_PASSWORD>`.
- <any surface/feature that must be enabled first, e.g. "ISE ERS enabled", "HEC enabled">.
- <any topology precondition, e.g. "lab booted to BOOTED; NAD SVI up">.
- Credentials are **never** in this plan — only the `.env` variable names.

## 5. Test cases

Grouped by capability/tool-area. One case per capability (not per tool); the Steps name
the tools/commands it exercises.

### <Group name, e.g. Endpoints>

| ID | Objective | Steps | Expected result / pass criteria | Coverage |
|---|---|---|---|---|
| `<PREFIX>-001` | <capability under test> | <tool call / CLI / GUI action> | <observable outcome = PASS> | `unit` / `smoke` / `integration --write` / `manual-live` (+ tool or test fn) |

<!-- repeat a table per group -->

## 6. Pass/fail & exit criteria

- **Automated gate:** CI green (`ruff` + `pytest`) **and** `smoke_test.py` passes **and**
  `integration_test.py --write` reports no `FAIL` (version/feature `SKIP`s don't fail).
- **Manual/live gate:** every `manual-live` case reaches its expected result with evidence.
- **Plan pass =** all non-skipped cases PASS.

## 7. Traceability matrix

| Capability / tool-group | Case IDs | Automated? |
|---|---|---|
| <group> | `<PREFIX>-001…00N` | unit + integration / smoke only / manual-live |

Manual-only gaps (no automated coverage): <list, or "none">.

## 8. Execution record

Filled per run by the [customer test report (#40)](../README.md#the-40-bridge). Leave blank here.

| Run date | Tester | Result (P/F/skip counts) | Evidence | Defects raised |
|---|---|---|---|---|
| | | | | |
