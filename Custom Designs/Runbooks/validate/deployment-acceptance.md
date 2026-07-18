---
id: validate/deployment-acceptance
category: validate
agent: testing-agent
human: none
requires: []
provides: [validated]
params: [deployment]
est: 30m
---

# validate/deployment-acceptance

> Author/update the Test Plan, run the automated gate + live acceptance against the deployment's provides, produce the PDF Test Report.

## Preflight — assert `requires`
- none — this is a root atom

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Report PASS verdict; any FAIL returned as a brief.

## Rollback
_TODO_

## Gotchas
- Consumes the whole deployment graph (requires handled specially); read-only + reversible only.
