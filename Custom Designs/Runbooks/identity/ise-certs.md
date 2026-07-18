---
id: identity/ise-certs
category: identity
agent: ise-engineer
human: none
requires: [ise.reachable, ca.online, dns.core]
provides: [ise.certs]
params: [ca.name, ise.fqdn]
est: 20m
---

# identity/ise-certs

> CSR → CA-signed system cert; import the root as trusted for EAP + admin.

## Preflight — assert `requires`
- [ ] `ise.reachable`
- [ ] `ca.online`
- [ ] `dns.core`

## Steps (cross-agent: ISE + the Windows CA — the main session brokers the signing)
1. **Import the CA root as trusted** — `ise_import_trusted_cert` with the `ca.name` root PEM
   (`win_get_ca_certificate` on the DC). Set trustedFor **Infrastructure + Endpoints** (auth of Cisco
   services for EAP/LDAPS/pxGrid, plus client auth). Verify it's Enabled in the trusted store.
2. **Generate the system CSR** — `ise_generate_csr`: CN=`ise.fqdn`, SAN `DNS:ise.fqdn`, RSA 2048,
   **Multi-Use** (the single-cert way to serve Admin serverAuth + EAP). Add a distinguishing `OU`/`O` so the
   subject differs from the existing self-signed `CN=ise.fqdn` cert (avoids the 409 — gotcha below).
3. **Sign on the CA** (main session / Windows CA) — `win_sign_csr(csr, template="WebServer")` → a serverAuth
   cert issued by `ca.name`, honouring the CSR subject. Return the signed PEM to the ISE agent.
4. **Import + bind** — bind the signed cert to the pending CSR (`POST /api/v1/certs/signed-certificate/bind`)
   for **Admin + EAP Authentication**. The root is already trusted (step 1), so the chain validates.

## Verify — prove `provides`
`ise_list_system_certs` shows a cert `issuedBy=<ca.name>`, `issuedTo=ise.fqdn`, `usedBy="Admin, EAP
Authentication"`; the old self-signed cert drops to Portal / RADIUS-DTLS / TACACS only; surfaces green.

## Rollback
Rebind Admin/EAP to the default self-signed cert, then delete the CA-signed system cert (each rebind
restarts the app).

## Gotchas
- **The Admin bind RESTARTS the ISE app (~10–20 min).** Do it **last** in the phase (after AD join +
  idstores), so a slow/failed restart doesn't block the functional config. **Poll `ise_check_surfaces` for
  recovery — never foreground-`sleep`** (hangs the harness). And a recovery monitor must test for the **UP
  state directly** (surfaces green), NOT wait to witness a down→up transition — ISE can recover before the
  monitor sees the drop, so it never fires and the report handoff is lost (bit us 2026-07-18). See
  [[agents-poll-not-sleep-through-reboots]].
- **409 "subject matches existing cert"** — the stock self-signed cert already has `CN=ise.fqdn`; give the
  CSR a distinct `OU`/`O`.
- **`WebServer` template = serverAuth**, honours the CSR subject — correct for an Admin+EAP server cert.
  clientAuth (pxGrid) is a separate cert, not this one.
- Import the CA **root as trusted first** (step 1) or the bind can reject the chain.
