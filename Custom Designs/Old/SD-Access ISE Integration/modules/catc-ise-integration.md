# Module — Catalyst Center ↔ ISE integration

Register ISE as CatC's auth/policy server so ERS + pxGrid trust establish and CatC can drive
the fabric's identity onboarding. Prereq: all ISE certs chain to MitchcloudCA and CatC trusts
MitchcloudCA (see [mitchcloudca-certs.md](mitchcloudca-certs.md)).

```bash
TOKEN=$(curl -sk -u "$CATC_USERNAME:$CATC_PASSWORD" -X POST "$CATC_URL/dna/system/api/v1/auth/token" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['Token'])")
curl -sk -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' -H 'Accept: application/json' \
  -X POST "$CATC_URL/dna/intent/api/v1/authentication-policy-servers" -d '{
   "ipAddress":"198.18.134.35","sharedSecret":"SdaIseRadius2026","protocol":"RADIUS_TACACS",
   "role":"primary","retries":"3","timeoutSeconds":"4",
   "port":49,"authenticationPort":1812,"accountingPort":1813,
   "pxgridEnabled":true,"useDnacCertForPxgrid":false,"isIseEnabled":true,
   "ciscoIseDtos":[{"fqdn":"ise.mitchcloud.lab","ipAddress":"198.18.134.35",
     "userName":"admin","password":"<ERS pw>","subscriberName":"catalyst-center",
     "description":"ISE 3.5 mitchcloud.lab"}]}'   # → 202 taskId
```

- **Must include the top-level `port:49`** (TACACS+ port) — omitting it → `406 NCND00041 port=0`.
- Poll `GET /dna/intent/api/v1/authentication-policy-servers`: `state` **INPROGRESS → ACTIVE**;
  each `ciscoIseDtos[]` (PRIMARY = ERS, PXGRID) → `trustState: TRUSTED`, `failureReason: ""`.
- **`trustState: INIT` forever** = CatC can't trust ISE's cert → fix certs (MitchcloudCA).
  **`FQDN…doesn't match CN`** = the pxGrid cert still has the old dCloud CN → re-issue it.
- A stuck/**FAILED** entry: `DELETE …/authentication-policy-servers/{instanceUuid}` then re-add
  (the ISE cert cutover means the old trust attempt is moot).
- pxGrid client shows `catalyst-center<epoch>`; the ACTIVE state means the pxGrid session is up
  (approve the client in ISE if your deployment isn't auto-approving cert-based accounts).

NADs are **not** pushed here — that happens when ISE is assigned as the site AAA server and a
device is (re-)provisioned (see [closed-auth.md](closed-auth.md)).
