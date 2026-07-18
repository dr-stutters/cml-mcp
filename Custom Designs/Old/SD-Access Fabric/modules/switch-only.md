# SD-Access Fabric — switch-only variant (roadmap)

**Status:** roadmap — designed, not yet validated. A variant of the base
[SD-Access Fabric](../runbook.md) that drops the `cat8000v` fusion **router**, so the
whole fabric is `cat9000v` switches.

## Why

The base build uses a cat8000v as the fusion device (external VRF/eBGP handoff). In
many real campus deployments the border does its handoff to an L3 switch, or a
dedicated fusion **switch** — no router involved. This variant proves the fabric on
an all-switch footprint.

## Topology delta from the base

- **Remove** FUSION-R1 (cat8000v).
- **Add** FUSION-SW (`cat9000v-uadp`) as the fusion device — remember a **unique
  `prod_serial_number`** in its `conf/vswitch.xml` (3rd distinct serial, e.g.
  `CMLFUSN001`; see the [serial-collision gotcha](../runbook.md#stage-1--topology--cml-lab-architect)).
- BORDER-CP ↔ FUSION-SW handoff over a routed `no switchport` /30, same as the base.
- BORDER-CP + EDGE1 roles unchanged (collapsed Border+CP, Edge).

## Build

Same as the base runbook Stages 1–5, with FUSION-SW in place of FUSION-R1:
- FUSION-SW needs `ip routing` and the handoff SVI/routed port; **no** RSA-key step
  (cat9000v self-generates SSH keys, unlike the cat8000v).
- Per-VN eBGP handoff runs BORDER-CP ↔ FUSION-SW (both switches).

## Open questions to validate

- cat9000v as a pure fusion/handoff device (VRF-lite + eBGP) — expected to work
  (standard L3 switching), but confirm the per-VN handoff on the UADP sim.
- Host capacity: 3× cat9000v (~18 GB each) — check `get_system_status` before build.

## Provisioning

Same fork as the base: [CLI](cli-provisioning.md) (expected to work) or
[Catalyst Center](catc-provisioning.md) (blocked by NCSP11008 until the SD-Access
microservice is enabled).
