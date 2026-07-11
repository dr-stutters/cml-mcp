"""Firepower two-mode validation against live CML.

Builds lab 'firepower-e2e':
  SW (unmanaged_switch) mgmt segment 10.10.10.0/24
  FTD-L  (ftdv, day0 ManageLocally=Yes)  mgmt 10.10.10.10  -> validate FDM local mode
  FTD-M  (ftdv, day0 FmcIp/FmcRegKey)    mgmt 10.10.10.11  -> validate FMC managed mode
  FMC1   (fmcv, day0 static ip)          mgmt 10.10.10.20
  TOOLS  (net-tools)                     mgmt 10.10.10.30  -> in-lab curl driver

Logs to stdout continuously. Cleans up the lab at the end unless KEEP=1.

Managed-mode key step: a fresh day-0 FMC has no active license and will reject
device registration until Evaluation Mode is enabled
(POST /api/fmc_platform/v1/license/smartlicenses {"registrationType":"EVALUATION"});
the test does this before pre-provisioning the FTD.

Heavy test: needs ~48 GB free RAM on the CML host and runs 45-75 minutes
(FMCv boot dominates). Run:  uv run python tests/firepower_e2e_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time

import yaml

from cml_mcp.client import CMLClient
from cml_mcp.config import load_settings
from cml_mcp.pyats_manager import PyatsManager

MGMT = {"FTD-L": "10.10.10.10", "FTD-M": "10.10.10.11", "FMC1": "10.10.10.20", "TOOLS": "10.10.10.30"}
PW = "Cisc01@3"
REGKEY = "cisco123key"
RESULTS: list[tuple[str, bool, str]] = []


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" -- {detail[:300]}" if detail else ""))


def ftd_day0(hostname: str, ip: str, manage_locally: str, fmc_ip: str = "", reg_key: str = "") -> str:
    return json.dumps({
        "EULA": "accept", "Hostname": hostname, "AdminPassword": PW,
        "FirewallMode": "routed", "DNS1": "", "DNS2": "", "DNS3": "",
        "IPv4Mode": "manual", "IPv4Addr": ip, "IPv4Mask": "255.255.255.0",
        "IPv4Gw": "10.10.10.1", "IPv6Mode": "disabled", "IPv6Addr": "",
        "IPv6Mask": "", "IPv6Gw": "",
        "FmcIp": fmc_ip, "FmcRegKey": reg_key, "FmcNatId": "",
        "ManageLocally": manage_locally,
    }, indent=2)


def fmc_day0(hostname: str, ip: str) -> str:
    return json.dumps({
        "EULA": "accept", "Hostname": hostname, "AdminPassword": PW,
        "DNS1": "", "DNS2": "", "IPv4Mode": "manual", "IPv4Addr": ip,
        "IPv4Mask": "255.255.255.0", "IPv4Gw": "10.10.10.1",
        "IPv6Mode": "disabled", "IPv6Addr": "", "IPv6Mask": "", "IPv6Gw": "",
    }, indent=2)


async def main() -> None:
    c = CMLClient(load_settings())
    mgr = PyatsManager(c)
    lab_id = None
    try:
        # ---------------- build ----------------
        lab = await c.post("/labs", json_body={
            "title": "firepower-e2e",
            "description": "FTD local+managed mode validation - safe to delete",
        })
        lab_id = lab["id"]
        log(f"lab created: {lab_id}")

        nodes = {}
        specs = [
            ("SW", "unmanaged_switch", 300, 0, None),
            ("FTD-L", "ftdv", 0, 150, ftd_day0("ftd-local", MGMT["FTD-L"], "Yes")),
            ("FTD-M", "ftdv", 200, 150, ftd_day0("ftd-managed", MGMT["FTD-M"], "No", MGMT["FMC1"], REGKEY)),
            ("FMC1", "fmcv", 400, 150, fmc_day0("fmc1", MGMT["FMC1"])),
            ("TOOLS", "net-tools", 600, 150, None),
        ]
        for label, nd, x, y, cfg in specs:
            body = {"label": label, "node_definition": nd, "x": x, "y": y}
            if cfg:
                body["configuration"] = cfg
            n = await c.post(f"/labs/{lab_id}/nodes", json_body=body,
                             params={"populate_interfaces": True})
            nodes[label] = n["id"]
        log("nodes created")

        async def iface(label: str, want: str) -> str:
            for i in await c.get(f"/labs/{lab_id}/nodes/{nodes[label]}/interfaces",
                                 params={"data": True}):
                if i["label"] == want and not i["is_connected"]:
                    return i["id"]
            raise RuntimeError(f"no free interface {want} on {label}")

        async def sw_port() -> str:
            for i in await c.get(f"/labs/{lab_id}/nodes/{nodes['SW']}/interfaces",
                                 params={"data": True}):
                if not i["is_connected"]:
                    return i["id"]
            raise RuntimeError("switch full")

        for label, mgmt_if in (("FTD-L", "Management0/0"), ("FTD-M", "Management0/0"),
                               ("FMC1", "eth0"), ("TOOLS", "eth0")):
            await c.post(f"/labs/{lab_id}/links", json_body={
                "src_int": await iface(label, mgmt_if), "dst_int": await sw_port()})
        log("mgmt links created (Management0/0 / eth0 -> SW)")

        await c.put(f"/labs/{lab_id}/start")
        log("lab started; FTD BOOTED ~5 min (FDM +10-20 min), FMC ~15-30 min")

        async def node_state(label: str) -> str:
            s = await c.get(f"/labs/{lab_id}/nodes/{nodes[label]}/state")
            return s.get("state", "?")

        async def wait_booted(label: str, timeout: float) -> bool:
            t0 = time.time()
            while time.time() - t0 < timeout:
                st = await node_state(label)
                if st == "BOOTED":
                    log(f"{label} BOOTED after {int(time.time()-t0)}s")
                    return True
                await asyncio.sleep(20)
            record(f"{label} boot", False, f"state={await node_state(label)} after {int(timeout)}s")
            return False

        # ---------------- TOOLS ----------------
        assert await wait_booted("TOOLS", 300)
        tb = await mgr.get_testbed(lab_id)

        async def run_on(label: str, cmds: list[str], timeout: float = 90) -> dict[str, str]:
            name = await mgr.resolve_device(lab_id, label)
            return await asyncio.to_thread(mgr.run_execute, tb, lab_id, name, cmds, timeout)

        out = await run_on("TOOLS", [
            "ip addr flush dev eth0",
            f"ip addr add {MGMT['TOOLS']}/24 dev eth0",
            "ip link set eth0 up",
            "which curl || echo NOCURL",
        ])
        has_curl = "NOCURL" not in out["which curl || echo NOCURL"]
        record("TOOLS console + ip config", True)
        record("TOOLS has curl", has_curl, out["which curl || echo NOCURL"])

        curl_seq = 0

        async def tools_curl(args: str, timeout: float = 120) -> str:
            """Marker-delimited curl on TOOLS - immune to console buffer noise."""
            nonlocal curl_seq
            curl_seq += 1
            b, e = f"BM{curl_seq}K", f"EM{curl_seq}K"
            out = await run_on(
                "TOOLS", [f"echo {b}; curl -sk -m 45 {args}; echo {e}"], timeout)
            text = list(out.values())[0]
            m = re.search(rf"\n{b}\r?\n(.*?)\r?\n{e}", text, re.DOTALL)
            return m.group(1).strip() if m else text

        # ---------------- FTD local mode (FDM) ----------------
        if await wait_booted("FTD-L", 1500):
            # console check (fxos plugin) - non-fatal if unicon struggles
            managers_out = ""
            try:
                mo = await run_on("FTD-L", ["show managers"], 180)
                managers_out = list(mo.values())[0]
                record("FTD-L console via pyATS (os=fxos)", True)
            except Exception as exc:
                record("FTD-L console via pyATS (os=fxos)", False, str(exc)[:200])
            if managers_out:
                record("FTD-L show managers = local", "local" in managers_out.lower(),
                       managers_out.strip()[:200])

            # FDM API from TOOLS; it comes up ~10-20 min AFTER the node reaches
            # BOOTED (observed live) - poll up to 25 min
            token = ""
            t0 = time.time()
            while time.time() - t0 < 1500 and not token:
                resp = await tools_curl(
                    f"-X POST https://{MGMT['FTD-L']}/api/fdm/latest/fdm/token "
                    f"-H 'Content-Type: application/json' "
                    f"-d '{{\"grant_type\":\"password\",\"username\":\"admin\",\"password\":\"{PW}\"}}'")
                m = re.search(r'"access_token"\s*:\s*"([^"]+)"', resp)
                if m:
                    token = m.group(1)
                else:
                    await asyncio.sleep(30)
            record("FDM token (local mode auth)", bool(token))
            if token:
                # fresh devices must complete initial provisioning first
                await tools_curl(
                    f"-X POST https://{MGMT['FTD-L']}/api/fdm/latest/devices/default/action/provision "
                    f"-H 'Authorization: Bearer {token}' -H 'Content-Type: application/json' "
                    f"-d '{{\"acceptEULA\":true,\"type\":\"initialprovision\"}}'")
                await asyncio.sleep(10)
                pol = await tools_curl(
                    f"https://{MGMT['FTD-L']}/api/fdm/latest/policy/accesspolicies "
                    f"-H 'Authorization: Bearer {token}'")
                record("FDM access policy list", '"items"' in pol and "ccess" in pol,
                       pol[:200])

        # ---------------- FMC managed mode ----------------
        if await wait_booted("FMC1", 3300) and await wait_booted("FTD-M", 1500):
            # poll FMC API readiness (can lag BOOTED by many minutes)
            hdrs = ""
            t0 = time.time()
            while time.time() - t0 < 2400:
                hdrs = await tools_curl(
                    f"-D - -o /dev/null -X POST -u admin:{PW} "
                    f"https://{MGMT['FMC1']}/api/fmc_platform/v1/auth/generatetoken")
                if "x-auth-access-token" in hdrs.lower():
                    break
                await asyncio.sleep(60)
            tok = re.search(r"[Xx]-auth-access-token:\s*(\S+)", hdrs)
            dom = re.search(r"DOMAIN_UUID:\s*(\S+)", hdrs)
            record("FMC API auth token", bool(tok and dom), hdrs[:200])

            if tok and dom:
                token, domain = tok.group(1), dom.group(1)
                plat = f"https://{MGMT['FMC1']}/api/fmc_platform/v1"
                base = f"https://{MGMT['FMC1']}/api/fmc_config/v1/domain/{domain}"
                H = f"-H 'X-auth-access-token: {token}' -H 'Content-Type: application/json'"

                # PREREQUISITE (the #1 gotcha): a fresh day-0 FMC is UNREGISTERED
                # with no active license and does NOT auto-start eval. Device
                # registration fails fast with REGISTRATION_FAILED (record
                # discarded) until Evaluation Mode is enabled. This one call is
                # what makes managed-mode onboarding work.
                evl = await tools_curl(
                    f"-X POST {plat}/license/smartlicenses {H} "
                    f"-d '{{\"registrationType\":\"EVALUATION\"}}'")
                record("FMC evaluation mode enabled", "EVALUATION" in evl, evl[:200])

                pol = await tools_curl(
                    f"-X POST {base}/policy/accesspolicies {H} "
                    f"-d '{{\"name\":\"LabPolicy\",\"defaultAction\":{{\"action\":\"PERMIT\"}}}}'")
                pid = re.search(r'"id"\s*:\s*"([0-9a-fA-F-]{36})"', pol)
                record("FMC access policy created", bool(pid), pol[:200])

                if pid:
                    # pre-provision (register) the device; the day-0-wired FTD
                    # is already dialing in, so with eval active this completes.
                    reg = await tools_curl(
                        f"-X POST {base}/devices/devicerecords {H} -d '"
                        + json.dumps({
                            "name": "ftd-managed", "hostName": MGMT["FTD-M"],
                            "regKey": REGKEY, "type": "Device",
                            "license_caps": ["ESSENTIALS"],
                            "accessPolicy": {"id": pid.group(1), "type": "AccessPolicy"},
                        }) + "'")
                    task = re.search(r'"task"\s*:\s*\{[^}]*"id"\s*:\s*"([^"]+)"', reg, re.DOTALL)
                    record("FMC registration submitted",
                           "ftd-managed" in reg and bool(task), reg[:250])

                    # poll the registration TASK to a terminal state (~1 min)
                    task_ok = False
                    if task:
                        t0 = time.time()
                        while time.time() - t0 < 900:
                            ts = await tools_curl(f"'{base}/job/taskstatuses/{task.group(1)}' {H}")
                            st = re.search(r'"status"\s*:\s*"([^"]+)"', ts)
                            stv = st.group(1).upper() if st else "?"
                            if stv in ("SUCCESS", "COMPLETED", "DEPLOYED"):
                                task_ok = True
                                break
                            if stv == "FAILED":
                                record("FMC registration task", False, ts[:250])
                                break
                            await asyncio.sleep(30)
                    record("FMC registration task SUCCESS", task_ok)

                    lst = await tools_curl(f"'{base}/devices/devicerecords' {H}")
                    record("FMC device record persists", '"ftd-managed"' in lst, lst[:200])

                    try:
                        mo = await run_on("FTD-M", ["show managers"], 180)
                        mtext = list(mo.values())[0]
                        record("FTD-M show managers = Completed",
                               "ompleted" in mtext, mtext.strip()[:300])
                    except Exception as exc:
                        record("FTD-M show managers = Completed", False, str(exc)[:200])

    except Exception as exc:
        record("unexpected error", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            await mgr.disconnect(lab_id) if lab_id else None
        except Exception:
            pass
        if lab_id and os.environ.get("KEEP") != "1":
            log("cleaning up lab")
            try:
                await c.put(f"/labs/{lab_id}/stop")
                for _ in range(60):
                    if await c.get(f"/labs/{lab_id}/check_if_converged"):
                        break
                    await asyncio.sleep(5)
                await c.put(f"/labs/{lab_id}/wipe")
                await asyncio.sleep(3)
                await c.delete(f"/labs/{lab_id}")
                log("lab deleted")
            except Exception as exc:
                log(f"CLEANUP FAILED for lab {lab_id}: {exc}")
        await c.aclose()

    print("\n===== SUMMARY =====", flush=True)
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail[:160]}" if detail and not ok else ""), flush=True)
    fails = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"{len(RESULTS)-fails} passed, {fails} failed", flush=True)
    sys.exit(1 if fails else 0)


asyncio.run(main())
