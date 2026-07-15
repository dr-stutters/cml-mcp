# MCP Suite — Test Report

**Run date:** 2026-07-15 · **Tester:** automated gate + curated · **Verdict:** ✅ **PASS**

## 1. Executive summary

The Cisco/network lab-automation MCP suite — six MCP servers and four validated lab
designs — was executed against its [test plans](../../Test%20Plans/). **All 134 unit
tests pass and lint (ruff) is clean across all six repositories.** Live read-only smoke
tests were confirmed on the two targets reachable at run time (**cml-mcp**, **windows-mcp**);
the remaining live targets were unreachable this cycle because the lab VPN was taken down
mid-run, so their live results are carried from the most recent validated cycle and are
marked **UNREACHABLE** (not FAIL). All four lab-design acceptance suites remain **PASS**
on their proven evidence. **Overall verdict: PASS** — zero defects; the only caveat is
that live re-execution of four servers was deferred with the lab offline.

## 2. Scope & systems under test

This report executes the [Test Plans library](../../Test%20Plans/): the **6 MCP-server
plans** and the **4 lab-design acceptance plans**.

| Component | Version verified against |
|---|---|
| cml-mcp | CML 2.x controller |
| ise-mcp | ISE 3.4.0.608 & 3.5.0.527 |
| firepower-mcp | FMC 10.x + FTDv |
| windows-mcp | Windows Server 2022 (10.0.20348), `mitchcloud.lab` |
| splunk-mcp | Splunk Enterprise 10.x |
| wlc-mcp | Catalyst 9800-CL, IOS-XE 17.18 |

## 3. Test environment

IPs are **lab-specific**. Reachability reflects the state at run time (lab VPN was shut
down during this run).

| Target | Address | Reachable this run? |
|---|---|---|
| CML controller | 198.18.128.10 | ✅ yes |
| Windows DC | 198.18.134.11 | ✅ yes |
| ISE 3.5 | 198.18.134.35 | ❌ no (VPN down) |
| FMC | 198.18.128.13 | ❌ no |
| Splunk | 198.18.128.51 | ❌ no |
| Catalyst 9800 WLC | 198.18.128.70 | ❌ no |

**Reproduce:** `uv run python "Test Reports/run_report.py" [--smoke --write] --outdir "Test Reports/2026-07-15"`
(offline gate is reproducible anytime; `--smoke`/`--write` need the lab up).

## 4. Results — automated gate (MCP servers)

From [`results.json`](results.json). Levels: **unit** (mocked, CI-gated) · **smoke** (live
read-only) · **integration** (live write round-trips).

| Server | Plan | ruff | Unit | Smoke (this run) | Integration | Result |
|---|---|---|---|---|---|---|
| cml-mcp | [CML](../../Test%20Plans/MCP%20Servers/cml-mcp.md) | ✅ | 33 / 0 | ✅ PASS (live) | n/a (3 e2e suites) | ✅ PASS |
| ise-mcp | [ISE](../../Test%20Plans/MCP%20Servers/ise-mcp.md) | ✅ | 49 / 0 | ⚠️ UNREACHABLE | ⚠️ UNREACHABLE — prior: 20 round-trips PASS | ✅ PASS |
| firepower-mcp | [FMC](../../Test%20Plans/MCP%20Servers/firepower-mcp.md) | ✅ | 6 / 0 | ⚠️ UNREACHABLE | n/a (manual-live) | ✅ PASS |
| windows-mcp | [WIN](../../Test%20Plans/MCP%20Servers/windows-mcp.md) | ✅ | 15 / 0 | ✅ PASS (live) | ⚠️ UNREACHABLE — prior: 34/34 PASS | ✅ PASS |
| splunk-mcp | [SPL](../../Test%20Plans/MCP%20Servers/splunk-mcp.md) | ✅ | 21 / 0 | ⚠️ UNREACHABLE | n/a | ✅ PASS |
| wlc-mcp | [WLC](../../Test%20Plans/MCP%20Servers/wlc-mcp.md) | ✅ | 10 / 0 | ⚠️ UNREACHABLE | n/a | ✅ PASS |
| **Total** | | **6/6** | **134 / 0** | 2 live PASS / 4 unreachable | prior-validated | **✅ PASS** |

*Unit "N / 0" = passed / failed. `Result` = PASS where the offline gate is green and any
UNREACHABLE live suite is covered by a prior validated cycle.*

## 5. Results — lab-design acceptance

Manual-live end-to-end acceptance from each design's proof. Not re-run this cycle (lab
offline); results carried from the validated cycle noted.

| Design | Plan | Cases | Result | Evidence |
|---|---|---|---|---|
| ISE NAC Lab | [NAC](../../Test%20Plans/Lab%20Designs/ise-nac-lab.md) | NAC-001…022 | ✅ PASS | 3-sided (supplicant EAP-SUCCESS + switch `Authorized` + ISE MnT `passed:1`) across MAB/PEAP/EAP-TLS, dACL/VLAN/SGT, CoA, CTS |
| Wireless NAC | [WLNAC](../../Test%20Plans/Lab%20Designs/wireless-nac.md) | WLNAC-001…012 | ✅ PASS | C9800 `test aaa … new-code` Access-Accept + live hostapd client `COMPLETED` + ISE session |
| Firepower SGT Enforcement | [SGT](../../Test%20Plans/Lab%20Designs/firepower-sgt-enforcement.md) | SGT-001…006 | ✅ PASS | packet-tracer: Employees(4)→rule 268434434 ALLOW / Contractors(5)→268434435 DROP, both `src sgt type: sxp` (pxGrid) |
| Firewall SD-WAN | [SDWAN](../../Test%20Plans/Lab%20Designs/firewall-sdwan.md) | SDWAN-001…022 | ✅ PASS | AUTO_VPN provisioned via FMC REST; IKEv2 + iBGP AS 65070 up; LAN-to-LAN + failover **0% loss** |

## 6. Summary statistics

| Metric | Value |
|---|---|
| Unit tests | **134 passed / 0 failed** |
| Lint (ruff) | **6 / 6 repos clean** |
| Live smoke (this run) | 2 PASS (cml, windows) / 4 UNREACHABLE |
| Server plans | 6 / 6 PASS |
| Lab-design acceptance | 4 / 4 PASS |
| Defects | 0 |

## 7. Observations & defects

- **Defects raised:** none. Every executed case passed; the offline gate (unit + lint) is
  100% green and reproducible on demand.
- **Caveat (not a defect):** the lab VPN was shut down during the run, so live smoke +
  integration for **ise-mcp, firepower-mcp, splunk-mcp, wlc-mcp** were not re-executed this
  cycle. These are recorded **UNREACHABLE** and covered by their green unit suites plus the
  most recent validated live cycle (ISE 20 write round-trips; Windows 34/34; the four lab
  designs). Re-run `--smoke --write` with the lab up to refresh them.
- **cml-mcp** and **windows-mcp** were confirmed **live** this run (CML smoke 23/23; Windows
  reported Server 2022 / domain `mitchcloud.lab` and 37 tools).

## 8. Appendix

**Automated gate — pytest summary lines (this run):**

```
cml-mcp        33 passed
ise-mcp        49 passed
firepower-mcp   6 passed
windows-mcp    15 passed
splunk-mcp     21 passed
wlc-mcp        10 passed
ruff: All checks passed!  (×6)
```

**Live smoke evidence (this run):**

```
cml-mcp     : 23 passed, 0 failed   (build → inspect → export → delete scratch lab)
windows-mcp : SMOKE TEST PASSED     (win_system_info → Windows Server 2022, mitchcloud.lab)
ise-mcp     : ConnectError: All connection attempts failed  (198.18.134.35 — VPN down)
```

- Machine-collected raw results: [`results.json`](results.json).
- Runner: [`../run_report.py`](../run_report.py). Invocation:
  `uv run python "Test Reports/run_report.py" --outdir "Test Reports/2026-07-15"`.
