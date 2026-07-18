# Identity — Cisco ISE

Everything ISE: deploy, certs, AD join, NAD onboarding, policy sets, TrustSec, and the ANC quarantine that anchors Rapid Threat Containment. Driven by **ise-engineer**.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`ise-deploy`](ise-deploy.md) | none | ise.reachable | Bring ISE up, base network settings, enable the API surfaces (incl. ERS). |
| [`ise-certs`](ise-certs.md) | none | ise.certs | CSR → CA-signed system cert; import the root as trusted (clientAuth) for EAP + admin. |
| [`ise-ad-join`](ise-ad-join.md) | none | ise.ad_joined | Join ISE to AD as an external identity source. |
| [`ise-nad-onboard`](ise-nad-onboard.md) | none | ise.nads | Add the switches/WLC as RADIUS clients (NADs) + device groups. |
| [`ise-idstores-protocols`](ise-idstores-protocols.md) | none | ise.idstores | Allowed protocols + the All_User_ID_Stores identity source sequence. |
| [`ise-policy-sets`](ise-policy-sets.md) | none | ise.policy_sets | Wired/wireless policy set(s) with authN + authZ rules (incl. the ANC_Quarantine authz rule). |
| [`ise-authz-profiles-dacls`](ise-authz-profiles-dacls.md) | none | ise.authz | Authorization profiles + downloadable ACLs referenced by the authZ rules. |
| [`ise-trustsec-sgt`](ise-trustsec-sgt.md) | none | trustsec.sgts | Security Group Tags (Employees, Quarantined_Systems, Shared-Services…). |
| [`ise-trustsec-sgacl`](ise-trustsec-sgacl.md) | none | trustsec.sgacls | SGACLs + the egress matrix that enforces segmentation between SGTs. |
| [`ise-anc`](ise-anc.md) | none | ise.anc | ANC Quarantine policy — the Rapid Threat Containment backbone (ANC apply → CoA). |

## Example prompts
- "Run the identity stack end to end against ise.mgmt_ip from addressing.yaml"
- "ISE is already AD-joined — pick up from `identity/ise-policy-sets`"
- "Just build TrustSec: sgt → sgacl → anc"

## Category gotchas
- ERS is off by default (GUI: Admin > System > Settings > API Settings; served on 443, not 9060).
- Certs: no pkcs12-terminal import; one server per IP; restart browser sessions after a cert swap; root must be `trustForClientAuth:true` for later EAP-TLS.
- Durable authN store = `All_User_ID_Stores`.

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
