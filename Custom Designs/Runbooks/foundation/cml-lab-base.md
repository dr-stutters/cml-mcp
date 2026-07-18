---
id: foundation/cml-lab-base
category: foundation
agent: cml-lab-architect
human: none
requires: []
provides: [lab.up, mgmt.net]
params: [topology_spec]
est: 15-40m
---

# foundation/cml-lab-base

> Create the lab + mgmt network + external connector from the deployment topology.yaml (one build_lab_from_spec).

## Preflight — assert `requires`
- none — this is a root atom

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Every node BOOTED, every link/interface STARTED, mgmt reachable.

## Rollback
_TODO_

## Gotchas
- _none banked yet_
