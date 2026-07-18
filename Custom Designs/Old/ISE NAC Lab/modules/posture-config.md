# Module — Posture (config-side)

Layers onto the [base runbook](../runbook.md). Adds ISE **posture** policy
configuration via the OpenAPI Posture surface. Config-validated live against ISE 3.5.
Driven by **ise-engineer** (`mcp__ise__ise_*posture*`).

> **Scope:** config only. A live posture *assessment* needs a posture-capable client
> (Cisco Secure Client / AnyConnect on Windows or macOS). CML's Linux endpoints can't
> complete an assessment, so this module builds and inspects posture policy — it does
> not run a live compliance check.

## The posture chain

`condition` → `requirement` → `posture policy`:

- **Conditions** (`ise_list/get_posture_conditions`, `condition_type=file|application|
  service|registry|generic|...`): the atomic checks. ISE ships ~100 predefined file
  conditions. Creates are **raw-first** (`ise_create_posture_condition_raw`) — pull an
  existing one with get, or `ise_get_definition("FileCondition")`, to see the exact
  shape, then POST the same structure.
- **Requirements** (`ise_list/get/create_posture_requirement_raw`): bundle
  conditions + remediations per OS (`osNameList`, `ruleList`). 30 predefined.
- **Policies** (`ise_list/get/create_posture_policy_raw`): bind a requirement to an
  identity group + OS + agent type (`postureType`, `complianceModule`). 18 predefined.
- **Settings** (`ise_get_posture_settings`, read): `general`, `reassessment`,
  `acceptableusepolicy`, `update`, `continuousmonitoring`.

## Gotchas (from live validation)

- **File-condition enums are strict.** `FilePath` is an enum, not a literal path:
  `root` / `home` for Linux, `SYSTEM_32` / `SYSTEM_DRIVE` / `SYSTEM_ROOT` etc. for
  Windows (the file name goes in `FilePathSuffix`). `FileCheckType` +
  `FileOperator` (`EXISTS`/`DOES_NOT_EXIST`) + a check-type-appropriate `Operator`
  are all required and cross-validated by ISE — a mismatched combo returns a terse
  `Invalid data` 400. **Reliable path: clone an existing condition of the same
  check-type**, rename it (drop `id`/`createdByUser`), and POST.
- **Creates are raw-first by design** — the bodies are large and type-specific, so
  the tools take a JSON `body`; don't hand-write from scratch, copy a real object.
- Requirements/policies reference conditions/remediations/identity-groups by id — build
  bottom-up (condition → requirement → policy) and tear down top-down.
