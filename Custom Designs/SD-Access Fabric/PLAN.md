# SD-Access Fabric (no ISE) — build plan

**Status:** PLAN — awaiting approval. ("Plan now, build next.")
**Written:** 2026-07-15. Becomes `runbook.md` + `modules/` once validated.

## Mission

Stand up a **Cisco SD-Access fabric in CML without ISE**: underlay → fabric roles
(control-plane / border / edge) → one L3 virtual network → **static ("No
Authentication") host onboarding** of an endpoint → verify LISP registration +
end-to-end reachability + Catalyst Center fabric health. Deliver **two runbooks for
the same fabric** — a **Catalyst Center-driven** build and a **CLI-driven** build —
plus **roadmap modules** for a switch-only variant and a Fabric-in-a-Box variant.

**Why "without ISE" is fine:** the fabric itself (LISP control plane, VXLAN data
plane, VRF/VN handoff) needs no ISE. ISE only provides *dynamic* host onboarding
(802.1X/closed auth) and SGT policy. Without it we use **static port assignment**
into the VN — a complete, demoable fabric.

## Feasibility (already probed 2026-07-15, CML `cat9000v-uadp` 17.18)

- `dna-advantage` licensed ✓ · `show lisp session` → *"% LISP is not running"* (subsystem
  present, unconfigured) ✓ · `show cts environment-data` returns live CTS state ✓.
- **Conclusion:** CLI SDA control-plane is viable on this image → the **CLI runbook is a
  guaranteed deliverable**; CatC-driven provisioning is attempted on top (primary), with
  CLI as the documented fallback. Remaining unknowns resolved in Stage 0: does `router
  lisp` config commit, and does CatC actually push fabric config to CML nodes.

## Fixed context

| Thing | Value |
|---|---|
| CML | 198.18.128.10 (`cml` MCP); System Bridge → underlay 198.18.128.0/18; gw .1 |
| Catalyst Center | 198.18.128.5, v3.2.2, `catc` MCP (122 tools incl. SDA: `catc_fabric_sites/_devices/_zones/_health`, `catc_layer3_virtual_networks`, `catc_create_layer3_virtual_network`, `catc_anycast_gateways`, `catc_reserve_subpool`, `catc_port_assignments`, …) |
| Creds | device `cisco/cisco` priv-15, enable `cisco`; SNMP RO `public`; `CATC_*` in `../.env` |
| Free mgmt IPs | .71/.72/.73/.74 confirmed free on the /18 |
| Old lab | `CatC-Onboarding` (id `902597c7-…`) — **stop before building** (frees 1×cat9000v+2×cat8000v of host RAM; user-directed) |

## Topology (new lab `SDA-Fabric`) — "switches and routers"

```
        Catalyst Center 198.18.128.5   +   shared services (via fusion)
                     │
   ── underlay/OOB mgmt 198.18.128.0/18 (System Bridge) ──
        │            │              │
     Gi1 .71      Gi0/0 .72       Gi0/0 .73        (mgmt; cat9k on Mgmt-vrf)
  ┌──────────┐  ┌────────────┐  ┌──────────┐
  │ FUSION-R1│  │ BORDER-CP  │  │  EDGE1   │
  │ cat8000v │  │cat9000v-uadp│ │cat9000v-uadp│
  └────┬─────┘  └──┬──────┬──┘  └────┬─────┘
       │ 10.1.24.0/30│      │10.1.23.0/30 │
       └─────────────┘      └─────────────┘   ← underlay OSPF area 0 (RLOCs = Lo0)
   (VRF handoff / eBGP)                    │ Gi1/0/3 (fabric edge access port)
   FUSION = outside fabric              ┌──┴───┐
   BORDER-CP = Border + Control-Plane   │ HOST1│  alpine, 172.16.10.10/24
   EDGE1 = fabric Edge                  └──────┘  static onboarding into CAMPUS_VN
```

- **FUSION-R1** (cat8000v) — outside the fabric; per-VN VRF-lite/eBGP handoff from the
  border; reaches shared services + CatC on the /18. (The "router.")
- **BORDER-CP** (cat9000v-uadp) — collapsed **Border + Control-Plane** (LISP MS/MR).
- **EDGE1** (cat9000v-uadp) — **fabric Edge**; HOST1 attaches; registers EIDs to CP.
- **HOST1** (alpine) — endpoint for static host onboarding.
- **MGMT-SW** (unmanaged) + **EXT** (System Bridge) — OOB mgmt to the /18.

**Addressing:** underlay Lo0/RLOCs — BORDER-CP `10.1.0.2`, EDGE1 `10.1.0.3`, FUSION
`10.1.0.254`; underlay /30s EDGE↔BORDER `10.1.23.0/30`, BORDER↔FUSION `10.1.24.0/30`;
overlay VN **CAMPUS_VN** anycast GW `172.16.10.1`, HOST1 `172.16.10.10/24`; handoff eBGP
fabric AS 65001 ↔ fusion AS 65100. (All lab-specific — adjust per environment.)

## Ground rules

- **Two methods, one fabric.** Primary build = **CatC-driven** (exercises the SDA write
  tools — the point). Where CatC can't complete a step in CML, **fall back to CLI**,
  documented as such (hybrid). The **CLI-driven** runbook is authored from that fallback
  path so it stands alone.
- **Log-skip-continue** on any CatC/CML SDA balk; capture the exact error + the CLI
  workaround. Nothing halts the build.
- **Success = LISP control-plane** (edge↔CP session up, endpoint EID registered) **+
  reachability** (HOST1 → anycast GW → shared services via fusion) **+ CatC fabric health
  green**. Data-plane VXLAN forwarding fidelity in the CML sim is a **known risk** — if
  encap is limited, we record control-plane success honestly and note the limit.
- **Safety:** static host onboarding only (no ISE). No changes outside the new lab. New
  Custom Design files + the already-banked CatC-Onboarding files stay **uncommitted**
  pending your review.

## Stages (build-next)

**Stage 0 — Finish the feasibility spike (~15 min).** Confirm `router lisp` commits on a
cat9000v and `catc_fabric_sites` responds on the box. Go / hybrid / CLI-only decision.

**Stage 1 — Topology → cml-lab-architect.** `control_lab stop` on CatC-Onboarding. Build
`SDA-Fabric` from a validated `topology.yaml` (5 nodes + host + links). Start; confirm EXT
STARTED; wait BOOTED (cat9000v ~6–8 min ×2).

**Stage 2 — Underlay + enablement → catalyst-engineer.** Mgmt IPs (.71/.72/.73), the
**cat8000v RSA key gotcha** (`crypto key generate rsa modulus 4096` on FUSION-R1),
loopbacks, OSPF area 0 underlay, SSH/SNMP. Verify OSPF adjacency + RLOC reachability.

**Stage 3 — Discover into CatC.** Reuse the CatC-Onboarding flow (range discovery, SSH +
SNMPv2c) → 3 devices Managed/Reachable → site `Global/SDA-Lab/Fabric-Bldg` + assign.

**Stage 4 — Fabric provisioning (primary: CatC-driven).**
reserve IP pools (`catc_reserve_subpool`) → create fabric site (`catc_api_call` SDA
fabricSites) → add devices with roles (BORDER-CP = CONTROL_PLANE+BORDER, EDGE1 = EDGE) →
create L3 VN `CAMPUS_VN` (`catc_create_layer3_virtual_network`) + add to fabric → anycast
gateway `172.16.10.0/24` (`catc_anycast_gateways`) → L3 border handoff eBGP to FUSION-R1 →
static host onboarding / port assignment (`catc_port_assignments`) for HOST1. Hybrid CLI
fallback per step where CML/CatC balk.

**Stage 5 — Endpoint + verify.** HOST1 static IP; `show lisp session` (edge↔CP up),
`show lisp instance-id N ipv4 database`/`server` (HOST1 EID registered); HOST1 → anycast GW
→ shared-services ping; `catc_fabric_health`/`catc_fabric_devices`; path trace.

**Stage 6 — Bank as Custom Design `SD-Access Fabric`.** `runbook.md` (overview + topology +
validated path) → `modules/catc-provisioning.md` + `modules/cli-provisioning.md` (the two
methods) → **roadmap** `modules/switch-only.md` + `modules/fabric-in-a-box.md` (documented,
validated in a later pass) → `topology.yaml`. README index row + catalyst-center-engineer
agent pointer.

## Roadmap modules (documented in the build, validated later)

- **`switch-only.md`** — drop FUSION-R1; all-switch fabric (border does its own handoff to
  an L3 switch / external). Proves SDA without a dedicated fusion router.
- **`fabric-in-a-box.md`** — single cat9000v as **collapsed CP + Border + Edge**, HOST1
  directly attached. Smallest possible SDA footprint (1 switch + 1 host).

## Risks

1. **CatC can't fully provision SDA in CML** (highest) → hybrid CLI fallback; CLI runbook is
   a deliverable regardless.
2. **VXLAN data-plane fidelity** in the cat9000v sim → assert control-plane success; note
   forwarding limits honestly.
3. **Resource** (2× cat9000v) → stopping the old lab first covers it.
4. **Host onboarding without ISE** → static/No-Auth port assignment (supported); no dynamic
   auth attempted.
