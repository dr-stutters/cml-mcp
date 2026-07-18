# Foundation — the substrate

Stands up the lab itself and the AD/DNS/PKI backing every other stack leans on. Driven by **cml-lab-architect** and **windows-engineer**.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`cml-lab-base`](cml-lab-base.md) | none | lab.up, mgmt.net | Create the lab + mgmt network + external connector from the deployment topology.yaml (one build_lab_from_spec). |
| [`apply-addressing`](apply-addressing.md) | none | mcp.connected | Sync the deployment's mgmt IPs/hostnames from addressing.yaml into the master ../.env so every companion MCP can reach its box; reload configs. |
| [`windows-dc-promote`](windows-dc-promote.md) | none | ad.domain_up | Build the Windows Server and promote it to an AD DS domain controller. |
| [`windows-dns`](windows-dns.md) | none | dns.core | Forward/reverse zones + A/PTR records for ISE, the CA, and devices that need resolvable names. |
| [`windows-dhcp`](windows-dhcp.md) | none | dhcp.scopes | DHCP scopes for endpoints (optional — static host onboarding doesn't need it). |
| [`windows-adcs-ca`](windows-adcs-ca.md) | none | ca.online | Install the enterprise AD CS CA and export its root cert (feeds ISE + FTD decryption trust). |
| [`ad-users-groups`](ad-users-groups.md) | none | ad.users | OUs, test users (alice/bob/carol), and groups (Employees…) the identity + firewall stacks key off. |

## Example prompts
- "Build the lab base from the sda-ise-integration topology spec"
- "I already promoted the DC by hand — just run `foundation/windows-dns` and verify it"
- "Rebuild the whole foundation category against the current addressing.yaml"

## Category gotchas
- `build_lab_from_spec` from the deployment's topology.yaml; boot times vary wildly (IOL secs · IOSv 2-3m · cat9000v/CSR 4-6m · FTDv 5m + FDM 10-20m · FMCv 15-30m).
- Interfaces added to an already-running node come up STOPPED — start them before diagnosing.
- promote-to-DC + role installs reboot the box (WinRM drops → reconnect + re-check).
- AD CS: `certreq` hangs over WinRM → use the COM `ICertRequest`; EAP-TLS needs a custom clientAuth template (defaults give serverAuth OR clientAuth, not both).

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
