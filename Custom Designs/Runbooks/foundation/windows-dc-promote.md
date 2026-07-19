---
id: foundation/windows-dc-promote
category: foundation
agent: windows-engineer
human: none
requires: [mcp.connected]
provides: [ad.domain_up]
params: [ad.domain, dc.mgmt_ip]
est: 20m
---

# foundation/windows-dc-promote

> Build the Windows Server and promote it to an AD DS domain controller.

## Prerequisite (human, out-of-band)
`mcp.connected` for the Windows box means a **fresh Windows Server 2022 VM already exists** at
`dc.mgmt_ip`, powered on, with **WinRM enabled at the console once** (`Enable-PSRemoting -Force`;
set the NIC profile `Private` — a fresh box classifies as `Public` and 5985 stays blocked). The MCP
drives an *existing* box; it cannot create or power one on. Point `WINRM_HOST` in the master `../.env`
at the box's IP (the `apply-addressing` edit) and reload the `windows` MCP after the change (gotcha 1).

## Preflight — assert `requires`
- [ ] `mcp.connected` — `win_system_info` returns and shows `Domain: WORKGROUP`, `PartOfDomain: false`
      (a fresh, un-promoted box). If it already shows a domain, this atom is done.

## Steps
1. **Confirm the starting state** — `win_system_info` → expect `WORKGROUP` / `PartOfDomain:false`, Server 2022.
2. **Rename to the DC hostname BEFORE promoting** — `win_rename_computer("DC01")`. Renaming a DC after
   promotion is far more involved. This reboots (~1–2 min): **poll `win_system_info` until it answers with
   the new `CSName`** (still WORKGROUP) — do not `sleep` (gotcha B).
3. **Stage the AD DS role first** — `win_install_feature("AD-Domain-Services")` (pulls in AD DS +
   `RSAT-AD-PowerShell`). **Required:** without it `win_promote_to_dc` fails with
   `Install-ADDSForest … CommandNotFoundException` — the `ADDSDeployment` module isn't present until the
   role is staged (gotcha A).
4. **Promote to a new forest** — `win_promote_to_dc` (Install-ADDSForest) with `AD_DOMAIN_NAME` /
   `AD_NETBIOS_NAME` and the DSRM password from `AD_DSRM_PASSWORD` (all in `../.env`). This reboots and
   **WinRM drops for ~5–10 min**. **Wait by polling, not sleeping:** retry `win_ad_domain_info` directly
   until it returns the domain — it only succeeds once AD DS is actually up, so it naturally rides out the
   whole reboot + Netlogon-init window (gotcha B). Keep `WINRM_USERNAME` unqualified `Administrator`
   (gotcha 2).

## Verify — prove `provides`
`win_ad_domain_info` → domain = `AD_DOMAIN_NAME`, the new host is the sole DC (PDC / Schema / Infra
master), forest & domain functional level Windows2016. Box now `PartOfDomain: true`.

## Rollback
Demote with `Uninstall-ADDSDomainController` (via `win_run_powershell`). For a truly clean re-run, rebuild
the box from a fresh Server 2022 snapshot (fastest repeatable path).

## Gotchas
- **A — stage `AD-Domain-Services` before `win_promote_to_dc`**, or the promotion cmdlet is
  `CommandNotFound`. (Proven in the 2026-07-18 rebuild.)
- **B — never wait through a reboot with a foreground `sleep`.** This harness hangs long foreground
  `sleep` (the `sleep 150` used for the promote reboot hung the 2026-07-18 run and needed a manual stop).
  Instead **poll an MCP call until it succeeds** — `win_system_info` for the rename, `win_ad_domain_info`
  for the promote (it can't succeed until AD DS is up) — letting the agent's turn loop pace the retries.
  If pacing is genuinely required, run the wait with Bash `run_in_background`, never in the foreground.
- **2 — post-promote NTLM window:** for ~1 min after the reboot, WinRM as `Administrator` fails while AD
  DS / Netlogon initialize, then succeeds. Retry (see gotcha B); do **not** switch `WINRM_USERNAME` to
  `DOMAIN\Administrator` — the unqualified name resolves to the domain account on a DC (no local accounts
  remain).
- **1 — the MCP caches `../.env` at startup.** After changing `WINRM_HOST`, reload the `windows` MCP
  (`/mcp`) or it keeps dialing the old IP.
- **Rename before promote** (step 2).
