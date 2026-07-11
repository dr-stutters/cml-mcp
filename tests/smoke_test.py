"""End-to-end smoke test: drives the MCP server over stdio against a live CML.

Builds a scratch lab (2 IOSv routers, linked), inspects it, exports it, and
deletes it. Read-only system tools are exercised along the way.

Run:  uv run python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{status}] {name}" + (f"  -- {detail[:160]}" if detail and not ok else ""))


async def call(session: ClientSession, tool: str, args: dict) -> str:
    result = await session.call_tool(tool, args)
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.isError:
        raise RuntimeError(f"{tool} failed: {text[:300]}")
    return text


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["run", "cml-mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"Server exposes {len(names)} tools")
            check("tool count >= 50", len(names) >= 50)

            # --- read-only system checks -------------------------------
            info = await call(session, "get_system_status", {"include": "information"})
            check("system information", "version" in info, info)

            lic = await call(session, "get_licensing_status", {})
            check("licensing status", "registration" in lic, lic)

            defs = json.loads(await call(session, "list_node_definitions", {}))
            check("node definitions", isinstance(defs, list) and len(defs) > 0)
            def_ids = {d["id"] for d in defs}
            node_def = "iosv" if "iosv" in def_ids else sorted(def_ids)[0]
            print(f"       using node_definition={node_def}")

            eps = await call(session, "list_api_endpoints", {"filter": "wipe"})
            check("list_api_endpoints", "wipe" in eps.lower(), eps)

            # --- lab build workflow -------------------------------------
            lab = json.loads(await call(session, "create_lab", {
                "title": "mcp-smoke-test",
                "description": "created by cml-mcp smoke test - safe to delete",
            }))
            lab_id = lab["id"]
            check("create_lab", bool(lab_id))

            try:
                r1 = json.loads(await call(session, "add_node", {
                    "lab_id": lab_id, "label": "R1", "node_definition": node_def,
                    "x": 0, "y": 0,
                    "configuration": "hostname R1",
                }))
                r2 = json.loads(await call(session, "add_node", {
                    "lab_id": lab_id, "label": "R2", "node_definition": node_def,
                    "x": 200, "y": 0,
                }))
                check("add_node x2", bool(r1.get("id")) and bool(r2.get("id")))

                link = json.loads(await call(session, "create_link", {
                    "lab_id": lab_id, "src": r1["id"], "dst": r2["id"],
                }))
                check("create_link by node ids", bool(link.get("id")), str(link))

                nodes = json.loads(await call(session, "list_nodes", {"lab_id": lab_id}))
                check("list_nodes", len(nodes) == 2, str(nodes)[:200])

                links = json.loads(await call(session, "list_links", {"lab_id": lab_id}))
                check("list_links", len(links) == 1)

                state = json.loads(await call(session, "get_lab_state", {"lab_id": lab_id}))
                check("get_lab_state", state.get("state") in ("DEFINED_ON_CORE", "STOPPED"))

                topo = json.loads(await call(session, "get_lab_topology", {"lab_id": lab_id}))
                check("get_lab_topology", len(topo.get("nodes", [])) == 2)

                yaml_export = await call(session, "export_lab", {"lab_id": lab_id})
                check("export_lab yaml", "mcp-smoke-test" in yaml_export)

                # re-import the exported lab, then delete the copy
                copy = json.loads(await call(session, "import_lab", {
                    "topology": yaml_export, "title": "mcp-smoke-test-copy",
                }))
                copy_id = copy.get("id")
                check("import_lab roundtrip", bool(copy_id), str(copy))
                if copy_id:
                    await call(session, "delete_lab", {"lab_id": copy_id})

                iface = json.loads(await call(session, "list_interfaces", {
                    "lab_id": lab_id, "node_id": r1["id"],
                }))
                check("list_interfaces", isinstance(iface, list) and len(iface) > 0)

                cond = await call(session, "configure_link_condition", {
                    "lab_id": lab_id, "link_id": link["id"], "action": "set",
                    "latency": 10, "loss": 0.5,
                })
                cond_get = json.loads(await call(session, "configure_link_condition", {
                    "lab_id": lab_id, "link_id": link["id"], "action": "get",
                }))
                check("link conditioning set/get", cond_get and cond_get.get("latency") == 10,
                      f"set={cond} get={cond_get}")

                ann = json.loads(await call(session, "manage_annotations", {
                    "lab_id": lab_id, "action": "create",
                    "annotation": {"type": "text", "text_content": "smoke", "x1": 10, "y1": 10},
                }))
                check("annotation create", bool(ann.get("id")), str(ann))

                raw = await call(session, "cml_api_call", {
                    "method": "GET", "path": f"/labs/{lab_id}/events",
                })
                check("cml_api_call raw", raw is not None)

            finally:
                await call(session, "delete_lab", {"lab_id": lab_id})
                labs = await call(session, "list_labs", {"show_all": True, "with_data": False})
                check("cleanup delete_lab", lab_id not in labs)

            # --- users/groups read paths --------------------------------
            users = await call(session, "manage_users", {"action": "list"})
            check("manage_users list", "admin" in users)
            groups = await call(session, "manage_groups", {"action": "list"})
            check("manage_groups list", groups is not None)
            pools = await call(session, "manage_resource_pools", {"action": "list"})
            check("resource pools list", pools is not None)
            conns = await call(session, "manage_external_connectors", {"action": "list"})
            check("external connectors list", conns is not None)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
