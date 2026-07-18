# C8 — TLS decryption (Decrypt-Resign)

**Goal:** the FTD **decrypts** outbound TLS, inspects it, and **re-signs** the server
certificate with an internal **resign CA** — so a CAMPUS client's HTTPS is transparently
MITM'd for inspection. Prereq: C1 (FTD inline). **DONE ✅ (2026-07-17), fully proven +
reversible client-trust.** Almost entirely **FMC REST API** (only the resign CA is generated
locally). Live-proven on HOST1 (`alice`) → ISE `198.18.134.35:443`.

## The proof (before → after)
`openssl s_client -connect 198.18.134.35:443` from HOST1, reading the presented cert's issuer:
1. **Baseline (no decryption):** `issuer = Mitchcloud-Lab-Root-CA` — ISE's real cert.
2. **Decryption on, ISE cert *untrusted* by the FTD:** `issuer = O=Firepower Untrusted Issuer`
   — the FTD resigns, but with its **built-in "untrusted" resign CA** (because ISE's issuer
   MitchcloudCA wasn't in the decryption policy's trusted CAs).
3. **Decryption on + MitchcloudCA trusted:** `issuer = CN=SDA-Decrypt-Resign-CA, O=SDA-Lab`
   (subject `ise.mitchcloud.lab` **preserved**) — the FTD validates ISE's real cert against
   MitchcloudCA and resigns with **our** CA.
4. **Client trust:** with `SDA-Decrypt-Resign-CA` installed on HOST1
   (`openssl s_client … -CAfile resignca.crt`) → **`Verify return code: 0 (ok)`** — the
   resigned cert validates → **transparent** decryption.

## Recipe (curl — all REST unless noted)
1. **Resign CA** (the one non-API step): `openssl` self-signed CA (`CN=SDA-Decrypt-Resign-CA`,
   `basicConstraints=CA:TRUE,pathlen:0`, `keyUsage=keyCertSign,cRLSign`), then import to FMC:
   `POST object/internalcas` with `{name, type:"InternalCA", cert:<PEM>, privateKey:<PEM>}`.
2. **Decryption policy:** `POST policy/decryptionpolicies` with
   `{name, defaultAction:{policyAction:"DO_NOT_DECRYPT", eventLogAction:"LOG_FLOW_END"}}`
   (the default-action field is **`policyAction`**, not `action`).
3. **Decrypt-Resign rule:** POST to the policy's **`decryptionpolicyrules`** sub-path (get it
   from the policy's `links.rules`): `{name, type:"DecryptionPolicyRule",
   ruleAction:"DECRYPT_RESIGN", decryptionCerts:{objects:[<internalCA ref>]},
   sourceNetworks:{objects:[net-campus10]}, destinationPorts:{literals:[443/tcp]},
   logging:{logEnd:true, sendEvents:true}}` (the logging flag is **`sendEvents`**, not
   `sendEventsToFMC`).
4. **Attach to the ACP:** the AccessPolicy has a **`decryptionPolicySetting`** field — set it
   to a **flat** reference `{type:"DecryptionPolicy", id, name}` (NOT nested under a
   `decryptionPolicy` key, despite the model). **PUT the ACP without the `rules` container**
   (else `Bulk parameter should be set to true`). *Unlike C3's identity-policy link, this one
   IS settable over REST* with the flat format + no-rules PUT.
5. **Trust the server CA** so the FTD resigns with *our* CA (not "Untrusted Issuer"):
   `POST object/externalcacertificates` with the MitchcloudCA root PEM (type
   `ExternalCACertificate`), then add it to the decryption policy's `trustedCAs.objects`
   (alongside the default `Cisco-Trusted-Authorities`), PUT the policy.
6. `fmc_deploy`. For transparent client trust, install the resign CA in the client's trust store.

## Gotchas
- **"O=Firepower Untrusted Issuer"** in the resigned cert = the server's cert issuer isn't in
  the decryption policy's **trustedCAs** → add it (step 5). This is the tell that decryption
  works but the server chain isn't trusted.
- Decryption is scoped to `src net-campus10 → dst 443/tcp`; UDP (RADIUS/CoA) and non-443 are
  untouched. A real client needs the resign CA in its **system** trust store or every HTTPS
  site shows a cert warning.

## End-state
`SDA-Decrypt` decryption policy (Decrypt-Resign for CAMPUS→443, resign CA `SDA-Decrypt-Resign-CA`,
MitchcloudCA trusted) is attached to `SDA-ACP` and deployed. Reversible: clear the ACP
`decryptionPolicySetting` (flat PUT, no rules) + redeploy to stop decrypting.
