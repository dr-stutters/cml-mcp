---
id: foundation/windows-dns
category: foundation
agent: windows-engineer
human: none
requires: [ad.domain_up]
provides: [dns.core]
params: [ad.domain, dns.records]
est: 5m
---

# foundation/windows-dns

> Forward/reverse zones + A/PTR records for ISE, the CA, and devices that need resolvable names.

## Preflight — assert `requires`
- [ ] `ad.domain_up`

## Steps
1. **Verify the AD-integrated zones** — installing AD DS auto-creates the DNS role and a DS-integrated
   forward zone; the DC self-registers its own A/PTR. `win_list_dns_zones` → expect `AD_DOMAIN_NAME`
   (Primary, DS-integrated), `_msdcs.<domain>` (Primary, DS-integrated), and the reverse zones.
2. **Add extra records as later atoms need them** — for resolvable ISE CSR CNs, the CA CDP/AIA name, or
   device FQDNs: `win_add_dns_a_record` (adds A + auto PTR) and `win_add_dns_cname`. The base foundation
   needs none beyond the auto-registered DC record; ISE/device names get added when the `identity/*` /
   `catc/*` atoms require them.

## Verify — prove `provides`
`win_list_dns_zones` shows the DS-integrated forward + `_msdcs` + reverse zones. Any added name resolves
both ways (`win_get_dns_records`).

## Rollback
`win_remove_dns_record` for anything added. **Note:** it defaults to A-records — pass
`record_type="CNAME"` to delete a CNAME.

## Gotchas
- The forward zone is created **with AD DS**, not separately — this atom mostly *verifies* and adds records.
- `win_remove_dns_record` deletes A by default; specify `record_type="CNAME"` for CNAMEs.
