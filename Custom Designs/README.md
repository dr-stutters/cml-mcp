# Custom Designs library

A knowledge library of **our own** lab designs — the counterpart to
[`Cisco Validated Designs/`](../Cisco%20Validated%20Designs/). Where the CVD library distills
*official* Cisco reference designs from their PDFs, this one captures designs **we build and
validate ourselves** in CML, as **repeatable runbooks** the specialist agents in
[`.claude/agents/`](../.claude/agents/) execute end-to-end.

## Structure (composable atomic runbooks)

The lab is disposable; this library is the source of truth. It's organised as small,
independently-runnable **atoms** composed into **deployments** — read
**[`REBUILD.md`](REBUILD.md)** for the full convention (the atom contract, the
`requires`/`provides` state graph, the `human:` taxonomy, the `.env`/addressing boundary).

- **[`Runbooks/`](Runbooks/)** — the atomic library: 56 atoms across 9 categories
  (`foundation` · `identity` · `access` · `fabric` · `catc` · `firewall` · `observability` ·
  `wireless` · `validate`). Each atom is a contract — declares the state it needs, does one job,
  verifies its result — so any atom runs standalone. [`_scaffold.py`](Runbooks/_scaffold.py)
  generates the stubs + category READMEs and validates the dependency graph.
- **[`Deployments/`](Deployments/)** — a deployment = an ordered atom list +
  one gitignored `addressing.yaml` (the per-build IP/hostname/cert/credential-reference plan;
  copy from the committed `addressing.example.yaml`). First up:
  [`sda-ise-integration`](Deployments/sda-ise-integration/).
- **[`Old/`](Old/)** — the previous monolithic per-design runbooks, **archived**. They're the
  proven procedures we mine to fill each atom's `Steps` during the first clean-room rebuild;
  once an atom is proven, the atom is the truth and `Old/` is history.

## Archived designs (`Old/`)

Reference material — validated builds, now decomposed into atoms:

| Design | Runbook |
|---|---|
| [CatC Onboarding](Old/CatC%20Onboarding/runbook.md) | Catalyst Center discovery + siting |
| [SD-Access Fabric](Old/SD-Access%20Fabric/runbook.md) | CLI + CatC fabric, border L3 handoff |
| [SD-Access ISE Integration](Old/SD-Access%20ISE%20Integration/runbook.md) | the full stack (fabric + ISE + AD + CatC + firewall + Splunk) |
| [ISE NAC Lab](Old/ISE%20NAC%20Lab/runbook.md) | ISE 3.4/3.5 + cat9000v NAC |
| [Wireless NAC](Old/Wireless%20NAC/runbook.md) | cat9800 + hostapd → ISE |
| [Firepower SGT Enforcement](Old/Firepower%20SGT%20Enforcement/runbook.md) | ISE SGT → FTD Snort via pxGrid |
| [Windows DC Foundation](Old/Windows%20DC%20Foundation/runbook.md) | Server 2022 → DC + DNS + CA |
| [FMC-Managed FTD Registration](Old/FMC-Managed%20FTD%20Registration/runbook.md) | FTD → FMC register |
| [Secure Firewall SD-WAN Auto-VPN](Old/Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md) | route-based SD-WAN overlay |
| [FTD Dual-ISP ECMP + Failover](Old/FTD%20Dual-ISP%20ECMP%20+%20Failover/runbook.md) | multi-transport WAN |
| [FTD Overlay LAN Redistribution](Old/FTD%20Overlay%20LAN%20Redistribution/runbook.md) | IGP → BGP overlay |
| [FTD Dual-Hub Redundancy](Old/FTD%20Dual-Hub%20Redundancy/runbook.md) | secondary hub / RRs |
| [FTD HA Pair (FMC)](Old/FTD%20HA%20Pair%20(FMC)/runbook.md) | active/standby FTD |

## Working with the library

- **Add / edit an atom:** edit the catalog in [`Runbooks/_scaffold.py`](Runbooks/_scaffold.py),
  re-run it (`python3 "Custom Designs/Runbooks/_scaffold.py"`) to regenerate the stub + READMEs +
  `catalog.json` and re-validate the DAG, then fill the atom's `Steps`/`Rollback`.
- **Add a deployment:** create `Deployments/<name>/` with a `deployment.yaml` (ordered atoms +
  `human_touchpoints`), an `addressing.example.yaml`, and a `topology.yaml`.
- **Execute:** the main session fans atoms out to the matching specialist agents in
  `deployment.yaml` order — see the example prompts in [`REBUILD.md`](REBUILD.md).
