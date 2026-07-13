"""Live end-to-end test for topology-as-code: spec -> lab -> spec -> lab.

Drives the MCP server over stdio against a live CML. Builds a scratch lab from
a YAML spec (pinned + auto links, annotation, group brief), verifies it,
exports it back to a spec, rebuilds from the export, then deletes both labs.
Labs are never started, so nothing touches the underlay.

Run:  uv run python tests/labspec_e2e_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PASS = 0
FAIL = 0

SPEC = """
version: 1
lab:
  title: labspec-e2e-scratch
  description: scratch lab created by tests/labspec_e2e_test.py - safe to delete
defaults: {definition: iol-xe}
nodes:
  R1:
    config: |
      hostname R1
      no ip domain-lookup
  R2:
    config: |
      hostname R2
      no ip domain-lookup
  EXT: {definition: external_connector, config: System Bridge}
links:
  - R1:Ethernet0/1 -- R2:e0/1
  - R1 -- R2
  - EXT -- R2
annotations:
  - {type: text, text_content: labspec e2e, x1: 0, y1: -60}
groups:
  routers:
    agent: catalyst-engineer
    nodes: [R1, R2]
    addressing: "R1 e0/1 10.0.0.1/30, R2 e0/1 10.0.0.2/30"
    tasks: "bring up the p2p link"
    acceptance: "R1 pings 10.0.0.2"
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{status}] {name}" + (f"  -- {detail[:200]}" if detail and not ok else ""))


async def call(session: ClientSession, tool: str, args: dict) -> str:
    result = await session.call_tool(tool, args)
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.isError:
        raise RuntimeError(f"{tool} failed: {text[:300]}")
    return text


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["run", "cml-mcp"])
    lab_ids: list[str] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                # --- validate (live) --------------------------------------
                v = json.loads(await call(session, "validate_lab_spec", {"spec": SPEC}))
                check("validate_lab_spec valid", v.get("valid") is True, str(v))
                check("validate reports pinned link",
                      v["links"][0]["a"]["pinned"] is True, str(v.get("links")))

                # --- dry run makes nothing --------------------------------
                d = json.loads(await call(session, "build_lab_from_spec",
                                          {"spec": SPEC, "dry_run": True}))
                check("dry_run flagged", d.get("dry_run") is True)
                check("dry_run renders brief",
                      any("catalyst-engineer" in b for b in d.get("briefs", [])))

                # --- build -------------------------------------------------
                r = json.loads(await call(session, "build_lab_from_spec", {"spec": SPEC}))
                check("build state built", r.get("state") == "built", str(r)[:300])
                lab_id = r.get("lab_id")
                if lab_id:
                    lab_ids.append(lab_id)
                check("3 nodes built", len(r.get("nodes", {})) == 3, str(r.get("nodes")))
                pinned = r["links"][0]
                check("pinned link resolved",
                      pinned["a"]["interface"] == "Ethernet0/1"
                      and pinned["b"]["interface"] == "Ethernet0/1", str(pinned))
                check("auto link allocated",
                      all(lk["a"]["interface"] and lk["b"]["interface"]
                          for lk in r["links"]), str(r["links"]))
                check("brief has lab_id",
                      any(lab_id in b for b in r.get("briefs", [])))
                check("external connector warning present",
                      any("DEFINED_ON_CORE" in w for w in r.get("warnings", [])))

                # --- verify against the live topology ----------------------
                topo = json.loads(await call(session, "get_lab_topology",
                                             {"lab_id": lab_id}))
                check("topology has 3 nodes + 3 links",
                      len(topo["nodes"]) == 3 and len(topo["links"]) == 3)
                r1 = next(n for n in topo["nodes"] if n["label"] == "R1")
                cfg = r1.get("configuration")
                cfg_text = cfg if isinstance(cfg, str) else (cfg or [{}])[0].get("content", "")
                check("day-0 config applied", "hostname R1" in cfg_text, str(cfg)[:120])

                # --- export -> rebuild round trip --------------------------
                exported = await call(session, "export_lab_spec", {"lab_id": lab_id})
                check("export contains pinned link",
                      "R1:Ethernet0/1 -- R2:Ethernet0/1" in exported, exported[:400])
                check("export contains bridge config",
                      "System Bridge" in exported)

                r2 = json.loads(await call(session, "build_lab_from_spec",
                                           {"spec": exported}))
                check("rebuild from export", r2.get("state") == "built", str(r2)[:300])
                if r2.get("lab_id"):
                    lab_ids.append(r2["lab_id"])
                check("rebuild node set matches",
                      set(r2.get("nodes", {})) == {"R1", "R2", "EXT"})
                check("rebuild link count matches", len(r2.get("links", [])) == 3)
            finally:
                for lid in lab_ids:
                    try:
                        await call(session, "delete_lab", {"lab_id": lid})
                        print(f"[cleanup] deleted lab {lid}")
                    except Exception as e:  # noqa: BLE001 - report, keep cleaning
                        print(f"[cleanup] FAILED to delete {lid}: {e}")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
