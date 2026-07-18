# Module — TLS 1.3 TACACS+ (secure device-admin transport)  [A3 hardening]

Harden the classic A3 TACACS+ (obfuscated TCP/49) to **TACACS+ over TLS 1.3** (TCP/**6049**),
the encrypted, certificate-authenticated device-admin transport (IETF
`draft-ietf-opsawg-tacacs-tls13`). Built on the working A3 identity/policy layer
([`tacacs-device-admin.md`](tacacs-device-admin.md)) + the MitchcloudCA PKI
([`mitchcloudca-certs.md`](mitchcloudca-certs.md)).

**Status (2026-07-17): feasibility PROVEN both sides; live login blocked by a cat9000v
virtual-image crypto limitation — see "The wall" below.** ISE 3.5.0.527 and IOS-XE 17.18.2
both natively support it; everything configured cleanly; the *virtual* switch just won't
negotiate certificate-based TLS ciphers.

---

## What works — both sides support it
- **IOS-XE 17.18 (cat9000v) client:** the full CLI is accepted and `show tacacs` grows a
  **"TACACS+ Secure Server Statistics"** block:
  ```
  tacacs server <name>
   address ipv4 <ise-ip>
   tls port 6049
   tls connection-timeout 15
   tls trustpoint client <nad-identity-tp>   ! the NAD's own cert (Client-Auth EKU)
   tls trustpoint server  <ca-tp>            ! trustpoint holding the CA that signed ISE's cert
  ```
- **ISE 3.5 server:** native **Administration → Network Devices → (device) →
  "TACACS over TLS Authentication Settings"** (cert-based; optional SAN validation), plus a
  global enable.

## ISE setup
1. **Enable the listener:** Work Centers → Device Administration → **Overview → Deployment**
   → tick **"TACACS Over TLS Port"** (default **6049**) → Save. Verify: `:6049` opens on the
   PSN (was closed until enabled).
2. **Trust the NAD's CA:** MitchcloudCA must be in ISE Trusted Certificates with
   *Trust for authentication within ISE* (already true from A1/pxGrid).
3. **⚠️ ISE's TACACS server cert must chain to a CA the NAD trusts.** By default the
   **`TACACS` usage is bound to ISE's *default self-signed* cert** (`GET .../certs/system-certificate/ise`
   → the self-signed shows `usedBy: "Portal, RADIUS DTLS, TACACS"`). A NAD that only trusts
   MitchcloudCA will **reject** that self-signed cert and tear down the handshake. **Fix:**
   reassign the TACACS usage onto the **MitchcloudCA-signed** system cert
   (`ISE-MitchcloudCA-MULTIUSE`) — GUI: edit that cert → tick **TACACS** → Save (2 clicks).
   > API note: `PUT /api/v1/certs/system-certificate/{host}/{id}` needs
   > `admin,eap,tacacs,allowRoleTransferForSameSubject,allowPortalTagTransferForSameSubject,allowReplacementOfPortalGroupTag`;
   > reassigning the **Admin** cert's roles returned a 400 "Server Exception" — the GUI is the
   > reliable path. (Also: the ise MCP `ise_openapi_call` double-encodes JSON bodies — use a
   > direct `curl` with the `ISE_*` creds from the shared `.env`.)
4. **Per-NAD TLS settings** ("TACACS over TLS Authentication Settings" on the device) are
   **GUI-only** (not in ERS — the ERS `tacacsSettings` only exposes `sharedSecret` +
   `connectModeOptions`). Optional SAN validation matches the NAD cert's IP/DNS SAN.

## Switch (cat9000v) setup
1. **Identity cert** — the NAD needs a **MitchcloudCA-signed cert with Client-Auth EKU**
   (mutual TLS; the NAD is the client). Reuse the C5 pipeline: openssl key+CSR → sign via the
   CA **COM `ICertRequest`** interface with clientAuth (temporarily add `1.3.6.1.5.5.7.3.2`
   to the WebServer template) → bundle a **PKCS12** (`-legacy -certpbe/keypbe PBE-SHA1-3DES`
   for IOS) containing cert+key+**CA chain**. See [[cml-fmc-ise-pxgrid-recipe]].
2. **Get it onto the switch — file/URL only.** **IOS-XE 17.18 removed `pkcs12 terminal`
   import** (`% Error: failed to open file`); it takes `flash:/http:/tftp:/scp:` etc.
   - Enable SCP server: `ip scp server enable`.
   - **SCP needs the `default` AAA lists** (not the vty ones): add
     `aaa authentication login default local group ISE_TACACS` +
     `aaa authorization exec default local group ISE_TACACS if-authenticated` or the copy
     drops right after the password ("closed by remote host").
   - `scp -O` from a host that reaches the mgmt IP (the ops host reaches BORDER-CP
     `198.18.128.72` over the tunnel; fabric *edges* can't route to ISE's subnet — only the
     border can, sourced from Loopback0).
   - `crypto pki import SW-TLS pkcs12 bootflash:sw-tls.p12 password <pw>` — **non-interactive**,
     imports identity **and** CA in one shot → `show crypto pki trustpoints SW-TLS status`
     shows both certs Available.
3. **Configure the server.** Either add a new `tacacs server` **or** convert the existing
   A3 one — **you can't have two tacacs servers at the same IP** (IOS silently drops the 2nd
   one's `address`; `show tacacs` shows `Server address: UNKNOWN`). ISE is one node/one IP, so
   convert `ISE_DA`: `no key` + the `tls …` lines above. The existing `ISE_TACACS` group / vty
   then rides TLS automatically. (Local-first vty + `local` fallback = no lockout risk.)

## The wall — cat9000v negotiates PSK-only TLS ciphers
With everything correct, the handshake still fails: `show tacacs` → **`Handshake Success: 0`**,
all **"Connection Reset due to other Errors"**. `debug ssl openssl errors/msg` reveals why:

```
CRYPTO_OPSSL: ciphersuites DHE-PSK-AES128-CBC-SHA:PSK-AES256-CBC-SHA:PSK-AES128-CBC-SHA
error:140E0197:SSL routines:SSL_shutdown:shutdown while in init
```

The **cat9000v offers only PSK (pre-shared-key) cipher suites**, never certificate-based
ones — so there's no common cipher with ISE's cert-based listener and the TLS aborts in init.
The config is right and ISE supports it; this is a **cat9000v (CAT9KV) virtual-image crypto
limitation** (same family as its L3-subinterface / SMD-RADIUS-needs-global-SVI / serial-collision
gaps). A **physical Cat9k** offers the full cert cipher set. There is no per-server `tls cipher`
knob (`show run all | section tacacs server` shows only port/timeout/retries/trustpoints).

**To actually demo a live TLS-1.3 admin login you'd need a platform whose crypto offers
cert-based ciphers** (physical Cat9k, or a cat8000v/CSR — verify its cipher list), plus the
ISE TACACS-cert reassignment (step 3 above).

## Verify (when on capable hardware)
- Switch: `show tacacs` → `Handshake Success` > 0, port 6049.
- Live: SSH admin login (AD `ISE-Admins` user) → authenticates over TLS; or
  `test aaa group ISE_TACACS <ad-user> <pw> new-code` → "successfully authenticated".
  (An *internal* test user is **rejected** — the A3 device-admin policy only matches the AD
  `ISE-Admins` group; use a real netadmin cred.)
- ISE: Operations → **TACACS Live Log** shows the auth with the TLS transport.

## Teardown / revert to classic A3
`no tacacs server ISE_DA` → recreate with `address ipv4 198.18.134.35` + `key SdaIseTacacs2026`.
The `SW-TLS` trustpoint, `bootflash:sw-tls.p12`, `ip scp server enable`, the `default` AAA
lists, and ISE's :6049 listener are harmless to leave for a future retry.
