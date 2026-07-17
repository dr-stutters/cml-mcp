# Module — Catalyst Center CLI config templates (SDA + non-SDA)

Day-N CLI template deployment via Catalyst Center's template engine, proven on **both** a
fabric (SDA) device and a non-fabric (non-SDA) managed device. Validated 2026-07-17.

## Workflow (all via the `catc` MCP)
1. **Project** — `catc_create_template_project` (e.g. `Lab-Test-Templates`). Avoid the
   built-in **"Onboarding Configuration"** project for Day-N work — templates there get
   Day-0/PnP semantics; a regular project deploys via the Day-N API.
2. **Template** — `catc_create_template` with `template_content`, `device_family`,
   `software_type`, `language` (VELOCITY `${var}` or JINJA `{{var}}`). **Templates are
   family-specific**: a "Switches and Hubs" template only deploys to switches, "Routers" only
   to routers — so covering a switch *and* a router (our SDA vs non-SDA split) needs **two
   templates** with the same content.
3. **Commit** — `catc_commit_template` (versions it; required before deploy).
4. **Deploy** — `catc_deploy_template(template_id, target_device_ids, params, force_push=True)`.
   `params` are the variable values (same for all targets in one call). It waits for the
   per-device result (`realizedClis` shows the rendered config).
5. **Verify** — `catc_run_command(['show running-config interface …'], device_ids)` reads it
   back live from the box.

## SDA vs non-SDA — the only real difference is device *family*
The "SDA vs non-SDA" distinction is about **fabric membership**, and CatC deploys templates
the same way to both — the practical difference is just the family (switch template vs router
template):

| Context | Device | Family | Result |
|---|---|---|---|
| **SDA** (fabric edge) | EDGE1 (cat9000v) | Switches and Hubs | ✅ `interface Loopback199 / description SDA-Fabric-Edge-…` |
| **Non-SDA** (managed, not in fabric) | FUSION-R1 (cat8000v) | Routers | ✅ `interface Loopback199 / description NonSDA-Fusion-…` |

FUSION-R1 is discovered/managed by CatC but never added as a fabric device → a clean non-SDA
target. Both deploys succeeded in ~5 s with per-device variable substitution, confirmed on the
devices.

## Gotchas
- **`POTENTIAL_CONFLICT` lint** — CatC flags interface-level commands (`description`,
  `no ip address`) as *"reserved to be used by Cisco Catalyst Center"*. It's **advisory only**
  (`isError:false`); the template still commits and deploys fine.
- Use `force_push=True` if CatC thinks the config is unchanged.
- Deploys are effectively synchronous via `catc_deploy_template` (it follows the task and
  returns per-device `realizedClis` + status).
