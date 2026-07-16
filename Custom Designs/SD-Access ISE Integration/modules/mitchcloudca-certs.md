# Module — ISE system certs from MitchcloudCA + CatC trust

Make every cross-device cert chain to the AD **`Mitchcloud-Lab-Root-CA`** so CatC↔ISE trust
(ERS + pxGrid) and the 802.1X EAP server cert all validate to one root. `curl` is used against
ISE because the MCP body params get JSON-coerced.

## 1. Trust MitchcloudCA in CatC (non-disruptive)

```bash
# export the CA root (windows MCP): win_get_ca_certificate  → PEM
# get a CatC token, then multipart-import:
curl -sk -H "X-Auth-Token: $TOKEN" \
  -F "certFileImport=@mitchcloudca.pem;type=application/x-x509-ca-cert" \
  -X POST "$CATC_URL/dna/intent/api/v1/trustedCertificates/import"   # → HTTP 200
```
ISE already trusts MitchcloudCA if the DC's CA was imported earlier (`ise_list_trusted_certs`
shows `Mitchcloud-Lab-Root-CA`, trustedFor Infrastructure).

## 2. Re-issue the ISE Admin+EAP cert (⚠ restarts ISE ~5 min)

```bash
# CSR — unique OU avoids "subject matches existing cert" 409; field is digestType not digest
curl -sk -u "$ISE_USERNAME:$ISE_PASSWORD" -X POST "$ISE_URL/api/v1/certs/certificate-signing-request" \
  -H 'Content-Type: application/json' -d '{"allowWildCardCerts":false,"digestType":"SHA-256",
  "hostnames":["ise"],"keyLength":"2048","keyType":"RSA","sanDNS":["ise.mitchcloud.lab"],
  "subjectCommonName":"ise.mitchcloud.lab","subjectOrgUnit":"SDA-ISE","subjectOrg":"Mitchcloud",
  "usedFor":"MULTI-USE"}'
# export the CSR:  GET /api/v1/certs/certificate-signing-request/export/ise/{id}
# sign it (windows MCP): win_sign_csr(csr_pem, template="WebServer")   → serverAuth cert
# bind to Admin+EAP:
curl -sk -u … -X POST "$ISE_URL/api/v1/certs/signed-certificate/bind" -H 'Content-Type: application/json' \
  -d '{"admin":true,"eap":true,"radius":false,"pxgrid":false,"portal":false,"saml":false,
  "allowReplacementOfCertificates":true,"allowRoleTransferForSameSubject":true,
  "allowExtendedValidity":true,"allowOutOfDateCert":true,"validateCertificateExtensions":false,
  "data":"<signed PEM>","hostName":"ise","id":"<CSR id>","name":"ISE-MitchcloudCA-MULTIUSE"}'
# → "Certificate binding was successful.The system will now restart"
```
Poll until ISE is back **and** serving the new cert:
`echo | openssl s_client -connect 198.18.134.35:443 2>/dev/null | openssl x509 -noout -issuer`
→ `CN=Mitchcloud-Lab-Root-CA`.

## 3. Re-issue the pxGrid cert (the dCloud-rename gotcha)

This ISE was renamed `ise.demo.dcloud.cisco.com → ise.mitchcloud.lab`; its internal-CA pxGrid
cert kept the **old CN**, so CatC rejects the add with `FQDN ise.mitchcloud.lab doesn't match
the common name contained in the system certificate`. Probe to confirm:
```bash
echo | openssl s_client -connect 198.18.134.35:8910 2>/dev/null | openssl x509 -noout -subject
# → CN = ise.demo.dcloud.cisco.com   (443 + 9060 already = ise.mitchcloud.lab from step 2)
```
Fix: a **second** CSR (`subjectOrgUnit:SDA-PXGRID`, `usedFor:PXGRID`), sign with WebServer,
bind `pxgrid:true` (serverAuth-only is accepted for the pxGrid controller cert). Re-probe 8910
→ `CN=ise.mitchcloud.lab`, issuer MitchcloudCA. Now all three surfaces present MitchcloudCA
certs with the correct CN and the CatC add reaches `trustState: TRUSTED`.

> Keeping pxGrid on a separate cert (not the MULTI-USE one) avoids the pxGrid dual-EKU debate;
> serverAuth suffices because CatC is the pxGrid *client*. For full EAP-TLS later, re-enable
> **client-auth trust** on the MitchcloudCA trusted-cert in ISE (deferred).
