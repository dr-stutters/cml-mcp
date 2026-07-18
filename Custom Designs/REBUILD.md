# Rebuild & the composable-runbook model

The lab is disposable; **this library is the source of truth.** After a total lab loss we
rebuild from atoms — small, independently-runnable runbooks — composed into deployments.
This doc is the convention; the atoms live in [`Runbooks/`](Runbooks/), the compositions in
[`Deployments/`](Deployments/), and the old monolithic designs are archived under
[`Old/`](Old/) (mine them for the proven procedures as we fill atom `Steps`).

## The atom contract

An atom is **a contract, not a step in a script.** It declares the state it needs, checks
that state is true before it runs (it doesn't care whether an agent or a human produced it),
does one job, and verifies its own result. That's what lets any atom run **standalone** — if
you already did something by hand, the atom's preflight just confirms the state exists.

```yaml
---
id: identity/ise-ad-join          # category/verb-noun
agent: ise-engineer               # which specialist executes the brief
human: none                       # none | gui | file-transfer | external-download
requires: [ise.certs, ad.domain_up, dns.core]   # preflight asserts (state keys)
provides: [ise.ad_joined]         # what this atom leaves behind
params: [ad.domain, ad.join_user] # resolved from the deployment's addressing.yaml
est: 5m
---
## Preflight — assert every `requires` (fail fast, name what's missing)
## Steps     — the config work, idempotent where it can be
## Verify    — prove every `provides` (the acceptance check)
## Rollback  — clean undo, so re-runs are safe
## Human steps (⚠) — only when `human:` ≠ none
## Gotchas   — the hard-won notes, owned by the atom that hits them
```

**State keys** (`ise.ad_joined`, `fabric.overlay`, …) are the currency: `requires` names them,
`provides` produces them. The set is validated by the generator — every `requires` must be
`provides`d by some atom, and the graph must be acyclic.

## `human:` — when *you* are in the loop

Most atoms are fully agent-driven over MCP. The ones that need a human carry a `human:` value
and a **Human steps** block. Where an automatable path exists it's written alongside, so an
operator without your GUI access still has a route; where there's genuinely none it's called out.

| value | meaning | examples in this library |
|---|---|---|
| `none` | fully agent-automatable | most atoms |
| `gui` | a console you log into that agents can't drive | FMC eStreamer client, CatC pxGrid approve, ISE remote-logging-target, Splunk Web upload |
| `file-transfer` | you hand a file into the session | the eStreamer pkcs12 |
| `external-download` | you fetch something gated | Splunkbase add-ons (login) |

A deployment surfaces its human touchpoints **up front** (from the atoms where `human` ≠ none),
so there are no mid-run surprises — see the manifest's `human_touchpoints` summary.

## Composition — deployments

A deployment is an **ordered atom list + one addressing file**:

- [`Deployments/<name>/deployment.yaml`](Deployments/) — the ordered atoms (phased), plus a
  `human_touchpoints` summary and a pointer to its addressing file.
- `Deployments/<name>/addressing.yaml` — **gitignored** (real IPs/hostnames/plan).
- `Deployments/<name>/addressing.example.yaml` — the committed template.

Because atoms declare `requires`/`provides`, a composition is **checkable before a single node
boots**, and a smaller lab is just a shorter list drawn from the same catalog (an ISE-NAC-only
build reuses the foundation + identity atoms verbatim).

## The `.env` boundary — secrets vs plan

Two files, two jobs, **no overlap**:

| | `addressing.yaml` (per-deployment, committed as `.example`) | master `../.env` (gitignored, never committed) |
|---|---|---|
| holds | the *logical plan*: subnets, per-node mgmt-IP + hostname, VLAN/VNI/SGT numbers, CA/cert names, credential **references** (keys) | the *secrets + live connection config*: `ISE_PASSWORD`, `FMC_PASSWORD`, `WINRM_*`, the MCP `*_URL`/`*_USERNAME` |
| changes when | you design a new addressing scheme | the lab comes back with new IPs |
| read by | atoms (params substituted into the brief) | the MCP servers at startup |

The link is [`foundation/apply-addressing`](Runbooks/foundation/apply-addressing.md) — the
**single choke point** where "new IPs everywhere" is applied: it reads `addressing.yaml`, writes
the mgmt IPs/hostnames into `../.env`, you reload MCP configs (`/mcp`), and it verifies every
server answers. Secrets themselves you set once by hand in `../.env`; **no real password is ever
written to a committed file** (`.env` stays gitignored across all six repos — standing rule).

## The generator

[`Runbooks/_scaffold.py`](Runbooks/_scaffold.py) is the single machine source: it holds the atom
catalog, writes any missing atom stub (never clobbers a hand-edited atom), (re)writes each
category README + [`catalog.json`](Runbooks/catalog.json), and **validates the DAG** (missing
`requires`, cycles) printing the topological build order. Run it after editing the catalog:

```
python3 "Custom Designs/Runbooks/_scaffold.py"        # scaffold + validate
python3 "Custom Designs/Runbooks/_scaffold.py" --force-atoms   # rewrite all stubs (careful)
```

## Executing a rebuild

The main session fans atoms out to the specialist agents in `deployment.yaml` order (parallel
only where node-sets are disjoint), each brief = the atom. Example prompts:

- *"Apply the sda-ise-integration addressing, then run the foundation category."*
- *"Run `identity/ise-ad-join` against the current lab and verify it."*
- *"I built ISE by hand — just run the identity atoms' preflight+verify to confirm state."*
- *"Rebuild sda-ise-integration end to end, then hand it to the testing-agent."*

Each atom fills its `Steps` from the matching `Old/` design the first time it's proven in the
clean-room rebuild — after that, the atom is the truth and `Old/` is history.
