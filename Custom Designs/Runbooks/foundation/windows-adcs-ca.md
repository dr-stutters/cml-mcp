---
id: foundation/windows-adcs-ca
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up, dns.core]
provides: [ca.online]
params: [ca.name]
est: 10m
---

# foundation/windows-adcs-ca

> Install the enterprise AD CS CA and export its root cert (feeds ISE + FTD decryption trust).

## Preflight — assert `requires`
- [ ] `ad.domain_up`
- [ ] `dns.core`

## Steps
1. **Stage the AD CS role** — `win_install_feature("ADCS-Cert-Authority")`. It may report `RestartNeeded`,
   but the CA configuration proceeds without a reboot.
2. **Configure the enterprise root CA** — `win_install_adcs_ca(common_name=<CA_COMMON_NAME>,
   ca_type="EnterpriseRootCA")` → `CA installed`. (An Enterprise CA needs Enterprise/Domain Admin —
   satisfied when run on the DC.)
3. **Export the root cert** — `win_get_ca_certificate` → PEM. Feeds ISE `ise_import_trusted_cert`
   (EAP-TLS / pxGrid / portal trust) and FTD decryption trust; `win_sign_csr` signs ISE CSRs. The cert is
   public — re-export it any time rather than persisting it (clean-room principle).

## Verify — prove `provides`
`win_adcs_ca_info` (rc 0) → `Enterprise Root CA`, CA cert **Valid**, CRL **published**, CertSvc `Running`.
`win_get_ca_certificate` → a valid PEM; note its from→to validity window (~5 yr).

## Rollback
`Uninstall-AdcsCertificationAuthority`, then remove the `ADCS-Cert-Authority` feature (via
`win_run_powershell`).

## Gotchas
- **3 — CertSvc start race:** right after `win_install_adcs_ca`, `win_adcs_ca_info` / `certutil -CAInfo`
  can return `0x800706ba RPC_S_SERVER_UNAVAILABLE` while `CertSvc` is still starting.
  `win_get_ca_certificate` reads the cert straight from the machine store and works immediately regardless;
  re-check `win_adcs_ca_info` once `CertSvc` is `Running`. (Proven 2026-07-18.)
