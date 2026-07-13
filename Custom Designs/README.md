# Custom Designs library

A knowledge library of **our own** lab designs — the counterpart to
[`Cisco Validated Designs/`](../Cisco%20Validated%20Designs/). Where the CVD
library distills *official* Cisco reference designs from their PDFs, this one
captures designs **we build and validate ourselves** in CML, written up as
**repeatable runbooks** so the specialist agents in
[`.claude/agents/`](../.claude/agents/) can rebuild them end-to-end.

## How it works

- **One subfolder per design.** No source PDFs to gitignore here — everything is
  our own content, so it's all committed.
- **`runbook.md`** in each folder is the end-to-end, repeatable build: prerequisites,
  topology, stage-by-stage config (ISE / switch / endpoint), verification, teardown,
  and the hard-won gotchas. Written for an agent (or a human) to execute top to
  bottom.
- **`modules/`** (optional) holds focused per-capability runbooks that layer onto
  the base build — mix in only what you need. The `runbook.md` links to them.
- The relevant **specialist agent** is updated with a pointer to the runbook, so
  "rebuild the X lab" pulls straight from here.

> Runbooks are grounded in a real, validated build — the commands, object names,
> and lab IPs are what actually worked. Treat the **IPs/ids as lab-specific**
> (adjust for your environment); treat the **sequence, gotchas, and API shapes**
> as the reusable part.

## Index

**Full lab designs**

| Design | Runbook | Status | Related agents |
|---|---|---|---|
| [ISE NAC Lab](ISE%20NAC%20Lab/) | [runbook.md](ISE%20NAC%20Lab/runbook.md) + 4 modules | ✅ validated (ISE 3.4/3.5, cat9000v) | ise-engineer, catalyst-engineer, windows-engineer |

**Reusable components** — building blocks the end-to-end
[Firewall SD-WAN](../Cisco%20Validated%20Designs/Firewall%20SD-WAN/runbook.md) CVD
stitches together (usable on their own in any FMC/FTD lab):

| Component | Reuse | Agent |
|---|---|---|
| [FMC-Managed FTD Registration](FMC-Managed%20FTD%20Registration/runbook.md) | any FMC-managed FTD lab | firewall-engineer |
| [Secure Firewall SD-WAN Auto-VPN](Secure%20Firewall%20SD-WAN%20Auto-VPN/runbook.md) | route-based SD-WAN overlay | firewall-engineer |
| [FTD Dual-ISP ECMP + Failover](FTD%20Dual-ISP%20ECMP%20+%20Failover/runbook.md) | multi-transport WAN | firewall-engineer |
| [FTD Overlay LAN Redistribution](FTD%20Overlay%20LAN%20Redistribution/runbook.md) | OSPF/EIGRP/eBGP → BGP overlay | firewall-engineer |
| [FTD Dual-Hub Redundancy](FTD%20Dual-Hub%20Redundancy/runbook.md) | secondary hub / route reflectors | firewall-engineer |
| [FTD HA Pair (FMC)](FTD%20HA%20Pair%20(FMC)/runbook.md) | active/standby FTD | firewall-engineer |

## How to add a design

1. Create `Custom Designs/<Design Name>/`.
2. Write `runbook.md` — grounded in an actual build: **Prerequisites · Topology ·
   Stage-by-stage config · Verification · Teardown · Gotchas.** Use real commands
   and note which values are lab-specific.
3. Optionally split advanced capabilities into `modules/<capability>.md` and link
   them from `runbook.md`.
4. Update the relevant agent(s) in `.claude/agents/` with a pointer to the runbook,
   and extend the frontmatter `description` if it should trigger on new keywords.
5. Add a row to the index table above.
