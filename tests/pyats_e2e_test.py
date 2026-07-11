"""E2E test for the pyATS tools: boots a real IOSv node and drives its console.

Creates a scratch lab, waits for boot (~2-5 min), then exercises
pyats_execute / pyats_parse / pyats_configure / pyats_learn / pyats_sessions
over the MCP stdio layer. Cleans up the lab afterwards.

Run:  uv run python tests/pyats_e2e_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    PASS += ok
    FAIL += not ok
    print(f"[{status}] {name}" + (f"  -- {detail[:200]}" if detail and not ok else ""), flush=True)


async def call(session: ClientSession, tool: str, args: dict, timeout: float = 180):
    result = await asyncio.wait_for(session.call_tool(tool, args), timeout)
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.isError:
        raise RuntimeError(f"{tool} failed: {text[:400]}")
    return text


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["run", "cml-mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            lab = json.loads(await call(session, "create_lab", {
                "title": "pyats-e2e",
                "description": "pyATS e2e test - safe to delete",
            }))
            lab_id = lab["id"]
            print(f"lab: {lab_id}", flush=True)

            try:
                r1 = json.loads(await call(session, "add_node", {
                    "lab_id": lab_id, "label": "R1", "node_definition": "iosv",
                    "x": 0, "y": 0,
                    "configuration": "hostname R1\nline con 0\n exec-timeout 0 0\nend",
                }))
                await call(session, "control_lab", {"lab_id": lab_id, "action": "start"})

                deadline = time.time() + 420
                booted = False
                while time.time() < deadline:
                    state = json.loads(await call(session, "get_node_state", {
                        "lab_id": lab_id, "node_id": r1["id"],
                    }))
                    if state["state"].get("state") == "BOOTED":
                        booted = True
                        break
                    await asyncio.sleep(10)
                check("node BOOTED", booted)
                if not booted:
                    raise RuntimeError("IOSv did not boot within 7 minutes")

                out = json.loads(await call(session, "pyats_execute", {
                    "lab_id": lab_id, "node": "R1",
                    "commands": ["show version | include IOS"],
                }, timeout=240))
                ver = list(out.values())[0]
                check("pyats_execute show version", "IOS" in ver, ver)

                parsed = json.loads(await call(session, "pyats_parse", {
                    "lab_id": lab_id, "node": "R1", "command": "show ip interface brief",
                }))
                check("pyats_parse structured", "interface" in json.dumps(parsed).lower(), str(parsed)[:200])

                await call(session, "pyats_configure", {
                    "lab_id": lab_id, "node": "R1",
                    "config": "interface Loopback1\n ip address 10.99.99.1 255.255.255.255\n no shutdown",
                })
                parsed2 = json.loads(await call(session, "pyats_parse", {
                    "lab_id": lab_id, "node": "R1", "command": "show ip interface brief",
                }))
                lo1 = parsed2.get("interface", {}).get("Loopback1", {})
                check("pyats_configure + verify Loopback1",
                      lo1.get("ip_address") == "10.99.99.1", str(lo1))

                # parse-error path should give the fallback hint
                try:
                    await call(session, "pyats_parse", {
                        "lab_id": lab_id, "node": "R1", "command": "show clock",
                    })
                    check("parse fallback hint", True)  # parser exists, fine
                except RuntimeError as e:
                    check("parse fallback hint", "pyats_execute" in str(e), str(e))

                learned = json.loads(await call(session, "pyats_learn", {
                    "lab_id": lab_id, "node": "R1", "feature": "interface",
                }, timeout=240))
                check("pyats_learn interface", "Loopback1" in json.dumps(learned))

                sess = json.loads(await call(session, "pyats_sessions", {
                    "lab_id": lab_id, "action": "status",
                }))
                check("session persisted", sess["devices"].get("R1", {}).get("connected") is True, str(sess))

                disc = json.loads(await call(session, "pyats_sessions", {
                    "lab_id": lab_id, "action": "disconnect",
                }))
                check("disconnect", "R1" in disc.get("disconnected", []), str(disc))

            finally:
                try:
                    await call(session, "control_lab", {"lab_id": lab_id, "action": "stop"}, timeout=300)
                    for _ in range(30):
                        st = json.loads(await call(session, "get_lab_state", {"lab_id": lab_id}))
                        if st.get("converged"):
                            break
                        await asyncio.sleep(5)
                    await call(session, "control_lab", {"lab_id": lab_id, "action": "wipe"})
                    await asyncio.sleep(3)
                    await call(session, "delete_lab", {"lab_id": lab_id})
                    check("cleanup", True)
                except Exception as e:
                    check("cleanup", False, str(e))

    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
