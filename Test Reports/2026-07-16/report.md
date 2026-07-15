# MCP Suite — Test Report: catalyst-center-mcp API Expansion (Overnight Run)

**Run date:** 2026-07-15 → 2026-07-16 (overnight) · **Tester:** Claude (autonomous, user-approved plan) · **Verdict:** PASS-with-caveats

## 1. Executive summary

Overnight execution of `catalyst-center-mcp/EXPANSION_PLAN.md`: grow the `catc` MCP
server from 19 to 100+ live-validated tools spanning the Catalyst Center Intent,
campus, and Assurance-data API surfaces, using the box's own 1,914-operation OpenAPI
spec as the catalog, the live appliance at 198.18.128.5 (3.2.2-75131) for validation,
and the CML `CatC-Onboarding` lab (enriched to 3 devices with OSPF/CDP fabric) as the
device fixture. Every write was an `OVN-`-prefixed disposable round-trip
(create → verify → delete). Final: **122 tools (19 → 122), 96/97 live checks PASS** — the single FAIL is a documented Catalyst Center 3.2.2 server-side defect; the Splunk demo leg was UNREACHABLE (target parked). Zero OVN- leftovers on the box (audited).

## 2. Scope & systems under test

- `catalyst-center-mcp` branch `feat/api-expansion` (local commits only, no push).
- Not the standard 6-repo gate — an ad-hoc expansion run governed by
  `EXPANSION_PLAN.md`; the standard plans still apply to the untouched repos.
- Catalyst Center 3.2.2-75131 · CML 198.18.128.10 lab `CatC-Onboarding`
  (CAT8K-R1 .61, CAT9K-SW1 .62, CAT8K-R2 .63).

## 3. Test environment

| Target | Address | Reachable this run? |
|---|---|---|
| Catalyst Center | 198.18.128.5 | yes |
| CML controller | 198.18.128.10 | yes (host-key rotation fixed in known_hosts) |
| CAT8K-R1 / CAT9K-SW1 / CAT8K-R2 | .61 / .62 / .63 | yes (SSH v2 + SNMP) |

Reproduce: `uv run python tests/live_expansion_test.py <phase1|phase1b|phase2|phase3|phase4>`
in `catalyst-center-mcp` (results append to `tests/live_results.json`).

## 4. Results — automated gate

| Phase | Deliverable | Tools | Live checks | Result | Commit |
|---|---|---|---|---|---|
| 0 | Spec catalog (1,914 ops, 0.14 MB packaged) + `catc_search_spec` / `catc_get_definition` / `catc_spec_tags` | +3 (21) | search→definition→live call | PASS | `d6b6efd` |
| 1 | Campus onboarding core: discovery, site design, network settings, templates, tags, topology, path trace | +46 (67) | 38/38 PASS | PASS | `c7685b8` |
| 1b | CML lab enrichment (agents) + discovery of R2 via new tools, topology, path trace | fixture | 8/8 PASS | PASS | `03f2b97` |
| 2 | Assurance data APIs (`/dna/data/api/v1`) | +15 (82) | 12/13 PASS (1 documented box defect) | PASS-with-caveat | `0373f01` |
| 3 | Lifecycle: compliance, SWIM reads, PnP reads, licenses, config archive, EoX, advisories | +20 (102) | 18/18 PASS | PASS | `2237d3b` |
| 4 | SDA reads (VN round-trip skipped: box-side NCSP11000 on a fabric-less appliance); wireless design objects (OPEN SSID round-trip; WPA2_PERSONAL 400s on 3.2.2) | +21 (122) | 20/20 PASS | PASS-with-caveats | `2237d3b` |
| 5 | Demo: template create→commit→deploy to CAT8K-R1 (variable substitution realized, per-device SUCCESS, banner verified on-box via command runner, wr mem). Splunk webhook leg UNREACHABLE (SPLUNK_URL parked on placeholder, both Splunk hosts down, and CatC webhooks lack a DELETE endpoint so a round-trip can't be honored). Suite integration: agent frontmatter (122 tools) + workflows, README table, CLAUDE.md ×2, server instructions. | — | demo PASS | PASS-with-caveats | `51dd3a3` |

Unit tests: 22 passed, ruff clean (every phase gate).

## 5. Results — lab-design acceptance (CatC-Onboarding enrichment)

| Case | Evidence | Result |
|---|---|---|
| CAT8K-R2 built + booted (cml-lab-architect) | node `3f5fa341`, 3 new links, all interfaces STARTED | PASS |
| Device config (catalyst-engineer) | R2 mgmt .63 SSH v2 enabled; OSPF area 0: SW1 sees 10.0.0.1 + 10.0.0.2 FULL; CDP 2 neighbors; mgmt untouched; wr mem + config extraction all 3 | PASS |
| R2 discovered into CatC via new `catc_start_discovery` | discovery Complete; .63 Managed; assigned to CML-Bldg-1 | PASS |
| CatC physical topology shows CDP links | 3 devices + links rendered after forced resync | PASS |
| Path trace 10.0.0.1 → 10.0.0.2 through SW1 | flow COMPLETED, hops via CAT9K-SW1 | PASS |

## 6. Summary statistics

| Metric | Value (so far) |
|---|---|
| New tools | 103 (19 → 122 registered) |
| Live checks | 96/97 PASS (1 FAIL = box defect #5 below) |
| Unit tests / lint | 22 passed / ruff clean (every phase gate) |
| OVN- leftovers on the box | 0 (final audit across sites/creds/pools/templates/tags/discoveries/SSIDs/profiles/VNs: CLEAN) |
| Branch commits | 6 on `feat/api-expansion` (local, not pushed) |

## 7. Observations & defects

1. **CML SSH host key rotated** — every pyATS console connect failed
   ("failed to connect via proxy"); fixed via `ssh-keygen -R 198.18.128.10`.
   Recorded in memory (`pyats-proxy-hostkey-gotcha`).
2. **cat8000v day-0 SSH silently disabled** — 17.18 requires a ≥3072-bit key;
   day-0 `ip ssh version 2` alone isn't enough. `crypto key generate rsa
   modulus 4096` fixed both R1 (earlier) and R2 (baked into the agent brief).
3. **v2 buildings API requires `country`** — 400 "request body is invalid"
   without it. Tool signature now requires it (severity: doc gap).
4. **Body-less writes 415** — `DELETE /dna/intent/api/v2/floors/{id}` requires
   a `Content-Type: application/json` header even with no body; client now
   always sends it on POST/PUT/DELETE (severity: API quirk, handled).
5. **DEFECT (box-side): `POST /dna/data/api/v1/networkDevices/{id}/trendAnalytics`**
   rejects every documented payload shape with errorCode 13209
   ("trendIntervalInMinutes was left empty") on 3.2.2 — 7 payload variants
   probed. Tool ships with the limitation documented; work around with
   `catc_data_device` over narrow windows. Severity: medium, upstream.
6. **Assurance data APIs use their own async-task flow** (`assuranceTasks` +
   `resultUrl`), distinct from Intent taskId polling — handled by a shared
   resolver in `assurance_data.py`.
7. **Range discovery rejects a bare IP** — "IPAddress for Range Discovery is
   invalid"; tool now normalizes `x` → `x-x`.
8. **`GET /network-device/ip-address/{ip}` 404s for unknown IPs** — tool now
   returns "no managed device..." instead of an error.

9. **WPA2_PERSONAL SSID creation 400s on 3.2.2** for every probed body
   (passphrase alone, +isAuthKeyPSK, plain passphrase); OPEN SSIDs work.
   Documented in `catc_create_ssid`. Severity: low (design objects only).
10. **L3 virtual-network creation fails on a fabric-less box** (NCSP11000
   'provision' error) - the SDA subsystem needs a fabric before VNs exist.
   Documented in `catc_create_layer3_virtual_network`; reads all work.
11. **v2 template deploy task only proves the deployment SPAWNED** - the real
   result lives at `template/deploy/status/{deploymentId}` (progress string
   carries "Deployemnt Id", Cisco's typo). `catc_deploy_template` now follows
   through to per-device terminal status.
12. **Splunk leg UNREACHABLE** - `SPLUNK_URL` parked on placeholder 192.0.2.51
   in the master `.env` and neither Splunk CML node is deployed; additionally
   CatC webhook destinations have no DELETE endpoint, so an OVN- webhook
   round-trip cannot be honored. Re-run the events→Splunk demo when the
   Splunk lab is rebuilt.

## 8. Appendix

- `results.json` (copy of `catalyst-center-mcp/tests/live_results.json`) — raw matrix.
- Branch: `catalyst-center-mcp` `feat/api-expansion` (local only).
- Plan: `catalyst-center-mcp/EXPANSION_PLAN.md`.

## 9. Morning checklist


1. Review this report + `git log feat/api-expansion` in catalyst-center-mcp.
2. `/mcp` reload, then smoke a few new tools through the live MCP interface
   (`catc_search_spec`, `catc_physical_topology`, `catc_data_devices`).
3. Approve push/merge of `feat/api-expansion`; commit the CML_MCP working-tree
   edits (agent, CLAUDE.md, this report).
4. CatC-Onboarding lab now has 3 devices + OSPF/CDP fabric and a CatC-deployed
   banner on CAT8K-R1 - it is the permanent CatC fixture (candidate for a
   Custom Designs runbook).
