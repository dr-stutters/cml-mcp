# Catalyst Center

Discovery into inventory, site hierarchy, network settings, ISE integration (pxGrid), and fabric provisioning (with a CLI fallback). Driven by **catalyst-center-engineer**.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`catc-reachability`](catc-reachability.md) | none | catc.reachable | Token auth + reachability (catc_check). |
| [`catc-discovery`](catc-discovery.md) | none | catc.inventory | SSH/SNMP discovery of the fabric nodes into inventory. |
| [`catc-site-hierarchy`](catc-site-hierarchy.md) | none | catc.sites | Areas/buildings/floors + assign devices to sites. |
| [`catc-network-settings`](catc-network-settings.md) | none | catc.settings | Credentials, IP pools, per-site servers (DNS/DHCP/AAA). |
| [`catc-ise-integration`](catc-ise-integration.md) | gui | catc.ise_integrated | CatC ↔ ISE integration (pxGrid + ERS). |
| [`catc-fabric-provision`](catc-fabric-provision.md) | none | catc.provisioned | Provision the fabric via CatC (fabric site, roles, VNs) — with the CLI path as fallback. |

## Example prompts
- "Discover the fabric nodes into CatC inventory and get them to Managed"
- "Wire CatC to ISE and confirm ISE shows Active"

## Category gotchas
- Every CML cat9000v defaults to serial CMLUADP → CatC dedups by serial → set a unique prod_serial_number per vswitch.xml BEFORE boot; cat8000v needs a manual >=3072-bit RSA key for SSH.
- pxGrid: clientAuth EKU + FQDN/DNS-resolvable CN + manual approve; watch the old-CN gotcha.
- CatC provisioning can block (NCSP11008) → the CLI fabric path is the verified fallback.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
