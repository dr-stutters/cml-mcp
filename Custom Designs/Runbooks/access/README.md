# Access — NAD + endpoints

The switch (RADIUS/802.1X/MAB closed-auth) and the endpoint side (wpa_supplicant). Driven by **ise-engineer** across the CML consoles.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`switch-radius-dot1x`](switch-radius-dot1x.md) | none | access.dot1x | cat9000v edge: 802.1X/MAB, closed-auth policy-map, RADIUS to ISE over the global SVI. |
| [`endpoint-hosts`](endpoint-hosts.md) | none | endpoints.authenticated | Alpine endpoints + wpa_supplicant supplicants (MAB / PEAP-AD; EAP-TLS is open item A1). |

## Example prompts
- "Configure closed-auth 802.1X on the fabric edges and prove a session authorizes"
- "Bring up the alpine endpoints and confirm alice lands in the Employees SGT"

## Category gotchas
- cat9000v SMD RADIUS needs a front-panel GLOBAL SVI (not Mgmt-vrf); iosvl2/ioll2-xe can't MAB.
- A wedged edge-auth SMD is cleared only by a RELOAD (the 'mystery outage' NAC fault).
- Under closed-auth the anycast SVI is autostate-tied to an authorized session on the port.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
