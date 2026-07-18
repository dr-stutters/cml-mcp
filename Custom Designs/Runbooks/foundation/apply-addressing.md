---
id: foundation/apply-addressing
category: foundation
agent: cml-lab-architect
human: none
requires: [lab.up]
provides: [mcp.connected]
params: [addressing.yaml]
est: 5m
---

# foundation/apply-addressing

> Sync the deployment's mgmt IPs/hostnames from addressing.yaml into the master ../.env so every companion MCP can reach its box; reload configs.

## Preflight — assert `requires`
- [ ] `lab.up`

## Steps
_TODO: fill during the first clean-room build — mine `Old/` for the proven procedure._

## Verify — prove `provides`
Each MCP server (ise/fmc/splunk/catc/wlc/windows) answers its check tool.

## Rollback
_TODO_

## Gotchas
- THE single choke point where 'new IPs everywhere' is applied — one file (addressing.yaml) drives ../.env.
- Secrets are set once by hand in ../.env (gitignored); this atom only writes mgmt IPs/hostnames.
