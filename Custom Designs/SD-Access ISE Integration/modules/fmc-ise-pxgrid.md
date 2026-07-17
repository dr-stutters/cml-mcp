# Module — FMC ↔ ISE pxGrid (SGT sync into the firewall)  [C5]

Subscribe **FMCv** (`198.18.128.80`) to **ISE 3.5** (`198.18.134.35`) over **pxGrid 2.0**
so the firewall learns ISE's TrustSec **Security Group Tags** (and, later, session
identity) for use in Access Control Policy rules. This is the SGT-aware counterpart to
the source-PBR insertion in [`firewall-in-fabric.md`](firewall-in-fabric.md) (C1).

**Result achieved (2026-07-17):** FMC pulled **19 SGTs** from ISE
(`Employees, Contractors, Guests, Developers, Development_Servers, Production_Users,
Production_Servers, Test_Servers, PCI_Servers, Point_of_Sale_Systems, Network_Services,
BYOD, IoT, Auditors, Quarantined_Systems, TrustSec_Devices, Shared_Services, Unknown,
ANY`), verified with `GET .../object/isesecuritygrouptags` → `paging.count = 19`.

> **This whole flow is GUI-only** — the FMC ISE identity-source / pxGrid config is not in
> the FMC REST config API. Drive it in the browser (Integrations → Other Integrations →
> Identity Sources → **Identity Services Engine** → **Advanced Configuration (Old)**).
> Verify the *outcome* over the API (`isesecuritygrouptags`).

---

## The config (once the three walls below are cleared)

FMC → **Integrations → Identity Sources → Identity Services Engine → Advanced Configuration (Old)**:

| Field | Value |
|---|---|
| Primary Host Name/IP | `198.18.134.35` |
| pxGrid Client Certificate | `fmc-pxgrid-ca` (internal cert: MitchcloudCA-signed leaf **with clientAuth EKU** + its key) |
| MNT Server CA | `MitchcloudCA` |
| pxGrid Server CA | `MitchcloudCA` |
| Subscribe To | ☑ **Session Directory Topic** (leave **SXP Topic** off — ISE runs no SXP service) |

Then **Save** (not just Test — see wall 4). SGTs populate within ~30–60 s.

---

## Wall 1 — the pxGrid client cert needs **Client Authentication** EKU

FMC's "Test" first fails at the TLS handshake with, in Additional Logs:

```
HttpsStringRequest on_read for host 198.18.134.35:8910 failed.
error: 336151574: sslv3 alert certificate unknown (SSL routines, ssl3_read_bytes)
```

That alert is **ISE rejecting FMC's client cert** at mutual-TLS. A cert issued from the
Windows CA **WebServer** template has EKU = `serverAuth` **only**; ISE pxGrid requires the
client cert to carry **Client Authentication** (`1.3.6.1.5.5.7.3.2`), ideally
clientAuth + serverAuth. (ISE's *server* side is fine: its pxGrid cert
`ISE-MitchcloudCA-PXGRID` is MitchcloudCA-signed, so FMC's `pxGrid Server CA = MitchcloudCA`
validates it, and MitchcloudCA is already `trustedFor: Infrastructure,Endpoints` in ISE.)

**Fix — issue a MitchcloudCA leaf with both EKUs, keeping `CN=fmcv.mitchcloud.lab`.**
No built-in Windows template combines *supply-subject-in-request* **and** clientAuth
(WebServer = subject-in-request/serverAuth-only; Machine/User = client+serverAuth but
subject-built-from-AD, which clobbers the CN). Simplest lab move: **temporarily add
clientAuth to the WebServer template**, issue, then revert:

```powershell
$dn='CN=WebServer,CN=Certificate Templates,CN=Public Key Services,CN=Services,CN=Configuration,DC=mitchcloud,DC=lab'
Set-ADObject -Identity $dn -Add @{pKIExtendedKeyUsage='1.3.6.1.5.5.7.3.2'}   # add clientAuth
Restart-Service CertSvc                                                       # CA re-reads the template
# ... issue the cert (wall 2) ...
Set-ADObject -Identity $dn -Remove @{pKIExtendedKeyUsage='1.3.6.1.5.5.7.3.2'}; Restart-Service CertSvc   # revert
```

(For repeatability you may instead build a dedicated **v2 "pxGrid" template** =
supply-in-request subject + clientAuth&serverAuth EKU, and leave WebServer untouched.)

## Wall 2 — `certreq.exe` **hangs** over WinRM; use the CA **COM** interface

Over the Windows MCP (WinRM/pypsrp), **`certreq -new` and `certreq -submit` both hang**
(no interactive desktop) → the tool call idle-times-out after 1800 s. Don't shell out to
`certreq.exe`. Submit the CSR through the CA's **`ICertRequest`** COM object directly —
same underlying API, no hang, returns instantly:

```powershell
$r = New-Object -ComObject CertificateAuthority.Request
# 0x100 = CR_IN_BASE64HEADER|CR_IN_PKCS10 ; config = "<DC-FQDN>\<CA-CommonName>"
$disp = $r.Submit(0x100, (Get-Content C:\path\req.csr -Raw),
                  "CertificateTemplate:WebServer", "DC01.mitchcloud.lab\Mitchcloud-Lab-Root-CA")
# $disp = 3 (CR_DISP_ISSUED)
$r.GetCertificate(0) | Set-Content C:\path\cert.pem -Encoding Ascii   # 0 = CR_OUT_BASE64HEADER (PEM)
```

Combine the leaf `cert.pem` with the CSR's private key locally (`openssl`) — the cert's
modulus matches the key. Then import cert+key into FMC as an **internal certificate**
(Objects, or the `+` beside "pxGrid Client Certificate" → **Add Known Internal Certificate**:
paste cert, paste key, leave "Encrypted" unchecked for a PKCS#8 key).

> **Harness note (why this section exists):** the Windows MCP `win_sign_csr` tool and any
> **large** `win_run_powershell` payload can't be *approved* in the permission dialog —
> the oversized multi-line PEM/script breaks the prompt so it comes back "rejected". Keep
> every Windows **write** call **small** (≲ ~350 chars): stage the CSR onto the box in a few
> short `Add-Content` chunks, and run the COM submit as a compact one-liner. Read-only
> Windows MCP calls (they carry `readOnlyHint`) auto-approve and are unaffected. See
> [[cml-fmc-ise-pxgrid-recipe]].

## Wall 3 — pub/sub uses the ISE **FQDN**; FMC must resolve it (DNS)

After the cert is fixed the account activates but Test still fails — now with **empty**
Additional Logs (and `isesecuritygrouptags` stays 0). pxGrid **ServiceLookup** hands the
client the pub/sub node's **FQDN** (`ise.mitchcloud.lab`) to open the Session-Directory
WebSocket; the control channel only worked because it dials the **IP**. Two gaps:

- **No A record.** AD-join ≠ DNS registration — `ise.mitchcloud.lab` didn't exist even on
  DC01. Create it: `Add-DnsServerResourceRecordA -Name ise -ZoneName mitchcloud.lab -IPv4Address 198.18.134.35`.
- **FMC resolver wrong.** FMC's mgmt Primary DNS was `198.18.130.11` (not the lab AD DNS).
  Point it at DC01: FMC → **System → Configuration → Management Interfaces → Shared Settings**
  → Primary DNS `198.18.134.11` (keep `198.18.130.11` secondary). DC01 resolves both
  `mitchcloud.lab` and external names (root hints), so nothing else breaks. Changing DNS
  (not the mgmt IP) keeps the browser session.

## Wall 4 — approve the pxGrid client; ignore the flaky Test button

- On ISE → **Administration → pxGrid Services → Client Management → Clients** the FMC client
  (`t-fmc-…`) lands **Pending** — select it, **Approve**. Enable
  **Settings → "Automatically approve new certificate-based accounts"** so re-registrations
  self-approve. (The ISE approve-dialog OK button is a Dojo widget — if a coordinate click
  won't take, click it via JS: the `span.xwt-TextButtonText` with text "OK".)
- FMC's **"Test"** is unreliable — it can report `Primary host: Failure` with an **empty**
  log even after everything works. **Trust the data, not the button:** `Save` the config
  and confirm SGTs arrive via `GET .../object/isesecuritygrouptags`.

---

## Verify (the real proof)

```bash
FMC=198.18.128.80
hdr=$(curl -sk -D - -o /dev/null -X POST "https://$FMC/api/fmc_platform/v1/auth/generatetoken" -u "admin:Cisc01@3")
AT=$(printf '%s' "$hdr" | awk 'tolower($1)=="x-auth-access-token:"{print $2}' | tr -d '\r')
DOM=$(printf '%s' "$hdr" | awk 'tolower($1)=="domain_uuid:"{print $2}' | tr -d '\r')
curl -sk "https://$FMC/api/fmc_config/v1/domain/$DOM/object/isesecuritygrouptags?limit=200" \
  -H "X-auth-access-token: $AT" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("SGTs:",d["paging"]["count"])'
# → SGTs: 19
```

(FMC concurrent-token cap: if the API returns empty 200s, force a fresh `generatetoken`.)

## Next (build on this)

- **C3** — passive-identity user-based ACP (pxGrid Session Directory already subscribed →
  user→IP mappings drive user-aware FTD rules).
- **C2** — rapid threat containment (FMC correlation → ISE ANC quarantine → CoA).
- Author SGT-matching rules in `SDA-ACP` now that the 19 SGTs are selectable objects.
