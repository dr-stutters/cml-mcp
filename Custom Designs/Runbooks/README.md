# Runbooks — the atomic library

Small, independently-runnable runbooks ("atoms") that compose into deployments. Each atom is a
**contract** — it declares the state it `requires`, does one job, and `provides` (verifies) a
result — so any atom runs standalone (its preflight just checks the state exists, however it got
there) and a deployment is a checkable, ordered list of atoms.

**Read [`../REBUILD.md`](../REBUILD.md) first** for the full convention (atom frontmatter, the
`requires`/`provides` state graph, the `human:` taxonomy, the `.env`/addressing boundary, and how
Deployments compose atoms).

## Categories

| category | owns | atoms |
|---|---|---|
| [`foundation/`](foundation/) | lab base + Windows AD/DNS/DHCP/PKI + `apply-addressing` | 7 |
| [`identity/`](identity/) | Cisco ISE: deploy, certs, AD-join, NADs, policy, TrustSec, ANC | 10 |
| [`access/`](access/) | switch 802.1X/MAB + endpoints | 2 |
| [`fabric/`](fabric/) | SD-Access underlay/overlay/border/fusion/host-onboard | 6 |
| [`catc/`](catc/) | Catalyst Center discovery/sites/settings/ISE/provision | 6 |
| [`firewall/`](firewall/) | FMC + FTD base + depth (IPS/malware/decrypt/URL-geo-app/EVE) + eStreamer | 11 |
| [`observability/`](observability/) | Splunk base/inputs/HEC/CIM/add-ons/dashboards | 9 |
| [`wireless/`](wireless/) | C9800 + hostapd 802.1X (optional) | 4 |
| [`validate/`](validate/) | testing-agent acceptance + PDF report | 1 |

**56 atoms.** Each category README lists its atoms with `human?` flags, `provides`, and example
prompts. [`catalog.json`](catalog.json) is the machine index; [`_scaffold.py`](_scaffold.py)
generates the stubs + READMEs and validates the DAG.

## Conventions at a glance

- **id** = `category/verb-noun`, kebab-case.
- **atom `Steps`** start as `_TODO_`; they're filled from the matching [`../Old/`](../Old/) design
  the first time the atom is proven in a clean-room rebuild, then the atom is the truth.
- **params** resolve from the deployment's `addressing.yaml` (gitignored); **secrets** only from
  the master `../.env`.
- edit the catalog in `_scaffold.py`, re-run it, commit the regenerated index + READMEs.
