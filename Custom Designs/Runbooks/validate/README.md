# Validate — acceptance

Closes a deployment: the testing-agent authors/updates the Test Plan, runs the automated gate + live acceptance against the deployment's declared provides, and produces a PDF Test Report.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`deployment-acceptance`](deployment-acceptance.md) | none | validated | Author/update the Test Plan, run the automated gate + live acceptance against the deployment's provides, produce the PDF Test Report. |

## Example prompts
- "Run the testing-agent against the sda-ise-integration deployment and give me the report"

## Category gotchas
- Read-only + reversible round-trips only; failures come back as briefs, never auto-remediated.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
