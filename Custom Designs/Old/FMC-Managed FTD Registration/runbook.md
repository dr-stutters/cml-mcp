# Component — FMC-Managed FTD Registration

Register an **FTDv** to an **FMCv** (managed mode) over the REST API. The foundation
for any FMC-driven FTD lab (SD-WAN, HA, VPN…). Used by the
[Firewall SD-WAN runbook](../../Cisco%20Validated%20Designs/Firewall%20SD-WAN/runbook.md).

Driven by **firewall-engineer** (`mcp__fmc__*`). Registration is a two-sided handshake:
the FTD is told *where* the FMC is (day-0), and the FMC is told to *expect* the FTD.

## FTD day-0 (managed mode)

The FTDv day-0 must set `ManageLocally:"No"` and point at the FMC:
`FmcIp`, `FmcRegKey` (a shared secret you choose, e.g. `cisco123key`), and mgmt
addressing. **Do not pass day-0 via MCP `add_node(configuration=)`** — it
double-escapes the JSON and provisioning silently fails (no mgmt IP, no registration).
Instead create the node, then set day-0 via the CML REST API while
**`DEFINED_ON_CORE`**: `PATCH /api/v0/labs/{lab}/nodes/{id}` body
`{"configuration": json.dumps(day0dict)}` (stop → `wipe_disks` → patch → start;
a STOPPED-after-run node is **not** editable).

## FMC side

```
fmc_register_device(name='nyc-fw', host='198.18.128.21', reg_key='cisco123key',
                    access_policy='SDWAN-AC', licenses=['ESSENTIALS'])
# ≡ POST /devices/devicerecords {name, hostName:<mgmt ip>, regKey, type:'Device',
#     license_caps:['ESSENTIALS'], performanceTier:'FTDv50', accessPolicy:{id}}
```
Registration is asynchronous and slow: the FTDv reaches **BOOTED** in ~5 min but its
sftunnel/registration takes **10-20 min more**. **Gate readiness on TCP 8305**
(the sftunnel port) opening, *not* on the API answering — a fresh FMC answers its API
long before it can register a device.

## License gotcha

A brand-new FMC won't register anything until it's **licensed**: enable Evaluation
Mode first (`fmc_register_eval_license` ≡ `POST /license/smartlicenses
{registrationType:"EVALUATION"}`) or registration fails fast and the device record is
discarded. (SD-WAN specifically needs export-controlled features beyond eval — see the
auto-VPN component.)

## Verify

```
fmc_list_devices                      → the device, status normal
fmc_device_health(id)                 → green (cosmetic sftunnel-flap red is OK if managed)
# on the FTD console:  show managers   → Registration: Completed
```
