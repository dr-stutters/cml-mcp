# SD-Access + ISE + AD Integration — build plan

**Status:** PLAN — awaiting approval. Becomes `runbook.md` + `modules/` once validated.
**Written:** 2026-07-16. Self-contained brief (a fresh session can execute cold).

## Mission

Turn the CatC-provisioned SD-Access fabric from **No-Authentication static onboarding**
into a **full identity-driven fabric**: a **fresh ISE (3.5, .35)** joined to the
**mitchcloud.lab** Active Directory, integrated with **Catalyst Center** (pxGrid +
ERS), doing **802.1X + MAB (Closed Authentication)** for fabric endpoints, with **full
TrustSec micro-segmentation** (SGTs + SGACLs / group-based policy, permit/deny proven).

## Approved decisions

| Decision | Choice |
|---|---|
| Fresh ISE | **ise35** (3.5) — already a fresh instance in this lab |
| Identity source | **existing mitchcloud.lab DC** (198.18.134.11 — AD DS + DNS + AD CS) |
| Endpoint auth | **802.1X + MAB fallback**, **Closed Authentication** |
| Policy depth | **Full TrustSec** — SGTs + SGACLs + group-based policy, prove enforcement |

## Fixed context (verify at Phase 0)

| Thing | Value |
|---|---|
| Catalyst Center | `198.18.128.5` (dCloud 3.2.2; SD Access app installed) — `catc` MCP |
| SD-Access fabric | CML lab `SDA-Fabric` id `77dd2fde-…`; fabricId `6559fad0-…`; BORDER-CP (CP + Layer-3 Border, .72) + EDGE1 (Edge, .73); VN `CAMPUS_VN` (inst-id 4099), anycast `172.16.10.1/24` (VLAN 1021); FUSION-R1 (.71) outside the fabric |
| Fresh ISE | **ise35** `198.18.134.35` (3.5) — up (443 open) but MCP creds stale → **401**; `ise35` MCP. Update `ISE_PASSWORD` in master `.env` + reload; then enable ERS/OpenAPI/pxGrid (fresh ISE has them off) |
| AD / DNS / CA | `mitchcloud.lab` DC **`DC01` = `198.18.130.11`** (verified; old memory said .134.11) — `windows` MCP (AD DS, DNS, **AD CS Enterprise Root CA `Mitchcloud-Lab-Root-CA`**) |
| Endpoints | HOST1 (alpine) on EDGE1 Gi1/0/3 (802.1X supplicant); add a 2nd endpoint for MAB |
| Underlay | fabric global/underlay = OSPF 10.1.0.x loopbacks; the 198.18.0.0/16 lab reaches the nodes only via **Mgmt-vrf** today |

## The crux — fabric→ISE RADIUS reachability (read first)

CatC↔ISE (pxGrid/ERS) is easy — both are on the /18 and reach each other directly.
The hard part: **the fabric edge/border source RADIUS from the *global* table**, but
today the fabric nodes only reach the 198.18.x network (where ISE lives) via
**Mgmt-vrf**, not the global table. So ISE is unreachable from where RADIUS sources.
**Fix = the deferred border L3 handoff** (Phase 1): BORDER-CP hands the fabric off to
FUSION-R1, and FUSION advertises a route to the **shared-services** subnet (ISE +
DC). Then the fabric nodes' global table (RADIUS source loopback) can reach ISE. This
is the single biggest risk/unknown in CML — if the handoff + shared-services route
can't be made to work, ISE-backed auth can't function even though every other piece
is configured.

---

## Phase 0 — Prerequisites & reachability audit

- **ISE .35 fresh state:** `ise_check_surfaces` + `ise_version` (confirm 3.5,
  reachable, ERS on 443, pxGrid available). Confirm exact IP.
- **DC .11:** `win_ad_domain_info`, DNS + AD CS up; note the CA (`win_adcs_ca_info`).
- **Fabric up:** CatC fabric healthy; HOST1 present.
- **Reachability matrix:** CatC↔ISE (443/pxGrid 8910/RADIUS), ISE↔DC (AD:
  389/636/88/445/123 + DNS), and the *planned* fabric-global↔ISE path.
- **Time:** ISE + DC NTP in sync (AD join fails on clock skew).

## Phase 1 — Border handoff + shared-services reachability  → catalyst-center-engineer + firewall/catalyst-engineer

> **✅ RESOLVED (roadmap "B1", 2026-07-16).** The full CatC-driven L3 handoff is validated:
> BORDER-CP holds the **`BORDER_NODE` (Layer-3)** role + IP-transit handoff (SVI-on-trunk on
> cat9000v), FUSION does eBGP + NAT `default-originate`; fabric host → ISE/Splunk/CatC 100%. This
> was the biggest CML unknown — it works. Details: [SD-Access Fabric CatC module](../SD-Access%20Fabric/modules/catc-provisioning.md) steps 11–12 + [ROADMAP](../ROADMAP.md) B1. The management-plane global-table route below is a separate, still-valid layer.

Make ISE reachable from the fabric's global table (the crux above):
- Add BORDER-CP **L3 handoff** to a transit + FUSION-R1
  (`/sda/fabricDevices/layer3Handoffs/ipTransits` — needs an **IP-based transit**
  network in CatC first), per-VN eBGP border↔fusion.
- FUSION-R1 advertises/routes the **shared-services** subnet (ISE `198.18.134.0/24` +
  DC) into the fabric's global table (and a return path).
- Verify a fabric node can `ping` ISE **from its global RADIUS-source loopback**.
- **Fallback if CatC handoff won't complete in CML:** hand-configure the border↔fusion
  eBGP + a global static route to the shared-services subnet (CLI), documented as a
  CML workaround.

## Phase 2 — Fresh ISE base setup  → ise-engineer

- **DNS/NTP** on ISE → point to DC `.11` (resolve `mitchcloud.lab`).
- **Personas/services:** enable **pxGrid** + **ERS** (both surfaces), Policy Service.
- **Certificates:** ISE admin/EAP/pxGrid system cert. Import the **mitchcloud.lab CA**
  (`win_get_ca_certificate` → `ise_import_trusted_cert`) so EAP-TLS + CatC trust
  chain to a known root. Generate/observe the pxGrid cert for CatC.
- **Allowed protocols:** enable PEAP-MSCHAPv2 (AD) + EAP-TLS (cert) + MAB.

## Phase 3 — ISE ↔ Active Directory  → ise-engineer + windows-engineer

- **DC side:** service account for the ISE join (or domain admin), DNS A record for
  ISE, and demo **groups → future SGTs** (e.g. `Employees`, `Contractors`, `IoT`) with
  a user in each (`win_create_ad_group` / `win_create_ad_user` / `win_add_group_member`).
- **ISE side:** add **Active Directory** as an external identity source, **join**
  `mitchcloud.lab`, retrieve groups (`ise_list_active_directory` + the AD join API).
- **Identity source sequence:** AD + internal, used by the auth policy.
- (EAP-TLS optional: machine/user certs from AD CS; PEAP-MSCHAPv2 against AD is the
  simpler primary.)

## Phase 4 — Catalyst Center ↔ ISE integration  → catalyst-center-engineer + ise-engineer

The pivotal step. In CatC **System → Settings → Authentication and Policy Servers**
add ISE (ERS creds + **pxGrid** + shared RADIUS secret):
- **Mutual cert trust:** CatC cert → ISE trusted; ISE pxGrid cert → CatC. (Common
  failure point — plan for cert export/import both ways.)
- **Approve** the CatC pxGrid client in ISE.
- Result: integration **Active**; CatC auto-pushes the fabric NADs (BORDER-CP/EDGE1)
  to ISE as RADIUS clients; groups/SGTs sync via pxGrid.
- Verify: `ise_list_network_devices` shows the fabric devices; CatC shows ISE Active.

## Phase 5 — TrustSec policy: SGTs + SGACLs + authorization  → catalyst-center-engineer + ise-engineer

- **Scalable Groups (SGTs)** in CatC Policy (sync to ISE): `Employees`, `Contractors`,
  `IoT`, `Shared-Services` (ise_list_sgts / create).
- **Group-based access policy (SGACLs)** in CatC: e.g. Employees→Shared permit,
  Contractors→Shared deny, IoT isolated — pushed to ISE egress matrix.
- **ISE authorization policy:** AD group → **SGT + VN/anycast pool** (Closed Auth:
  authenticate to AD, authorize to SGT + `CAMPUS_VN`). Map each AD group to its SGT.
- **Authorization profiles / DACLs** as needed for the fabric.

## Phase 6 — Switch fabric onboarding to ISE (Closed Auth)  → catalyst-center-engineer

- Change the **authentication template** on the fabric host ports / site from
  **No Authentication → Closed Authentication** (802.1X + MAB) — CatC pushes AAA →
  ISE, `dot1x`, and the closed-auth port template to EDGE1.
- Confirm EDGE1 is a RADIUS client to ISE and can reach it (Phase 1 path) — RADIUS
  test authentication.

## Phase 7 — Endpoints + end-to-end validation  → ise-engineer / catalyst-engineer

- **HOST1 (802.1X):** `wpa_supplicant` wired EAP (PEAP-MSCHAPv2 with an AD user) — the
  method proven in the [ISE NAC Lab](../ISE%20NAC%20Lab/runbook.md). Authenticates →
  ISE returns SGT + VN → lands in `CAMPUS_VN`, gets IP, reaches gateway.
- **2nd endpoint (MAB):** non-supplicant → MAB → its SGT (e.g. IoT).
- **Validate:** `ise_active_sessions` / `ise_session_by_mac` (user, SGT, authz);
  edge `show authentication sessions` (Closed Auth, dot1x/MAB, SGT); CatC Assurance
  shows the endpoint + identity; LISP EID registered.
- **TrustSec enforcement:** prove **permit/deny between SGTs** in the fabric (e.g.
  Employee reaches Shared-Services, Contractor is denied) — `show cts role-based
  permissions` / counters on the enforcing node.

## Risks

1. **Fabric-global → ISE reachability** (Phase 1) — highest; CML border handoff +
   shared-services routing is unproven. CLI fallback planned.
2. **CatC↔ISE cert trust / pxGrid approval** — fiddly, version-sensitive (ISE 3.5 ↔
   CatC 3.2.2 compatibility — verify supported).
3. **cat9000v as fabric RADIUS NAD** — MAB/dot1x on the CML cat9000v (proven standalone;
   the fabric edge context adds SGT/CTS). Global-table RADIUS source required.
4. **TrustSec enforcement fidelity** in the CML cat9000v data plane (SGACL programming)
   — may configure but not fully enforce; assert control-plane + document limits.
5. **AD join clock skew / DNS** — the usual ISE-AD gotchas.

## Orchestration

Main session fans out per phase to **ise-engineer** (ISE + AD-side + NAD 802.1X),
**windows-engineer** (AD/DNS/CA on the DC), **catalyst-center-engineer** (CatC↔ISE,
SGTs/SGACLs, fabric auth template + handoff), **catalyst-engineer** (device-side
verification). Reuses building blocks from `Custom Designs/ISE NAC Lab/`,
`Windows DC Foundation/`, and `SD-Access Fabric/`.

## If the night runs short — phase priority

Phase 0 → **1 (reachability — do first; everything depends on it)** → 2 → 3 (ISE+AD) →
4 (CatC↔ISE) → 5 (policy) → 6 (Closed Auth) → 7 (validate). Each phase leaves a
usable, documented increment.
