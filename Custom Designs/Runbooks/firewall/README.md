# Firewall — FMC + FTD

FMCv base, FTDv registration, interfaces/zones, the access-control policy and every depth feature (identity, IPS, malware, decryption, URL/geo/app, EVE) + the eStreamer client. Driven by **firewall-engineer**.

## Atoms

| atom | human | provides | purpose |
|---|---|---|---|
| [`fmc-base`](fmc-base.md) | none | fmc.api | FMCv up, licensing, domain confirmed. |
| [`ftd-register`](ftd-register.md) | none | ftd.registered | Register the FTDv to FMC (day-0 mode fixed up front). |
| [`ftd-interfaces-zones`](ftd-interfaces-zones.md) | none | ftd.interfaces | Physical interfaces, security zones, routing. |
| [`ftd-acp-base`](ftd-acp-base.md) | none | ftd.acp | Access-control policy + base permit/deny rules + network/host objects. |
| [`ftd-identity-realm`](ftd-identity-realm.md) | none | ftd.identity | FMC↔AD realm + identity policy for user-based rules. |
| [`ftd-ips`](ftd-ips.md) | none | ftd.ips | Intrusion policy (SDA-IPS) attached to the ACP. |
| [`ftd-malware-file`](ftd-malware-file.md) | none | ftd.files | File/malware policy (C9-Malware). |
| [`ftd-decryption`](ftd-decryption.md) | none | ftd.decrypt | TLS decryption: resign CA + Decrypt-Resign rule (C8) and Do-Not-Decrypt bypass (C16). |
| [`ftd-url-geo-app`](ftd-url-geo-app.md) | none | ftd.depth | URL filtering (C12), application/AVC (C13), geolocation (C15) rules. |
| [`ftd-eve`](ftd-eve.md) | none | ftd.eve | Encrypted Visibility Engine (C14) — classify encrypted apps/threats without decryption. |
| [`ftd-estreamer-client`](ftd-estreamer-client.md) | gui | ftd.estreamer_client | eStreamer client cert for the Splunk box (feeds splunk-security-cloud). |

## Example prompts
- "Register the FTDv to FMC and build the base ACP"
- "Add the depth features: ips, malware, decryption, url-geo-app, eve"
- "Create the eStreamer client for the Splunk box"

## Category gotchas
- Fix FTD day-0 mode up front (ManageLocally/FmcIp); gate registration on TCP 8305, not the API.
- `fmc_api_call` double-parses object bodies → curl for writes; tokens expire ~30 min.
- Decryption logging uses `logEnd` (not logBegin → 422); `insertBefore=1` works despite a false 500.
- Applications endpoint ignores name filters → page the catalog (HTTP=676, HTTPS=1122); Country objects go straight into destinationNetworks (China=156).

---
See [../../REBUILD.md](../../REBUILD.md) for the atom contract, the `human:` taxonomy, and how Deployments compose atoms.
