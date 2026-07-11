"""Node definition and image definition management tools."""

from __future__ import annotations

import os
from typing import Literal

import yaml
from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def list_node_definitions(full: bool = False) -> str:
        """List available node definitions (device types that can be simulated).

        By default returns a compact summary (id, description, nature, memory).
        Set full=True for complete definition documents (large output).
        """
        defs = await client.get("/node_definitions")
        if full:
            return dumps(defs)
        summary = []
        for d in defs:
            general = d.get("general", {})
            sim = d.get("sim", {}).get("linux_native", {}) or {}
            ui = d.get("ui", {})
            summary.append({
                "id": d.get("id"),
                "description": (general.get("description") or "").split("\n")[0][:120],
                "nature": general.get("nature"),
                "label": ui.get("label"),
                "ram_mb": sim.get("ram"),
                "cpus": sim.get("cpus"),
            })
        return dumps(summary)

    @mcp.tool()
    async def get_node_definition(def_id: str) -> str:
        """Get the full definition document for one node definition (interfaces, boot, sim resources, device naming)."""
        return dumps(await client.get(f"/node_definitions/{def_id}"))

    @mcp.tool()
    async def manage_node_definition(
        action: Literal["create", "update", "delete", "set_read_only", "reload"],
        definition: str | None = None,
        def_id: str | None = None,
        read_only: bool = True,
    ) -> str:
        """Administer node definitions.

        - create/update: 'definition' is the node definition document (YAML or JSON text).
        - delete: remove definition 'def_id'.
        - set_read_only: protect/unprotect definition 'def_id' (read_only flag).
        - reload: re-scan definitions from disk on the server.
        """
        if action == "reload":
            return dumps(await client.put("/reload_definitions"))
        if action in ("create", "update"):
            if not definition:
                raise ValueError("definition text is required for create/update")
            body = yaml.safe_load(definition)
            if action == "create":
                return dumps(await client.post("/node_definitions", json_body=body))
            return dumps(await client.put("/node_definitions", json_body=body))
        if not def_id:
            raise ValueError(f"def_id is required for {action}")
        if action == "delete":
            return dumps(await client.delete(f"/node_definitions/{def_id}"))
        return dumps(await client.put(
            f"/node_definitions/{def_id}/read_only", json_body=read_only
        ))

    @mcp.tool()
    async def list_image_definitions(node_definition: str | None = None) -> str:
        """List disk image definitions, optionally only those for one node definition (e.g. 'iosv')."""
        if node_definition:
            return dumps(await client.get(f"/node_definitions/{node_definition}/image_definitions"))
        return dumps(await client.get("/image_definitions"))

    @mcp.tool()
    async def get_image_definition(def_id: str) -> str:
        """Get one image definition (disk image file, node definition it belongs to, boot settings)."""
        return dumps(await client.get(f"/image_definitions/{def_id}"))

    @mcp.tool()
    async def manage_image_definition(
        action: Literal[
            "create", "update", "delete", "set_read_only",
            "list_dropfolder", "delete_dropfolder_file", "upload_image", "clone_node_image",
        ],
        definition: str | None = None,
        def_id: str | None = None,
        read_only: bool = True,
        filename: str | None = None,
        file_path: str | None = None,
        lab_id: str | None = None,
        node_id: str | None = None,
    ) -> str:
        """Administer image definitions and disk images.

        - create/update: 'definition' is an image definition document (YAML or
          JSON text; needs id, node_definition_id, disk_image reference).
        - delete / set_read_only: operate on image definition 'def_id'.
        - upload_image: upload a local disk image file ('file_path') to the
          server's drop folder.
        - list_dropfolder / delete_dropfolder_file: manage uploaded image files
          ('filename' for delete).
        - clone_node_image: create a new image definition from a node's current
          disk state (lab_id + node_id + definition with the new image's id/label).
        """
        if action in ("create", "update"):
            if not definition:
                raise ValueError("definition text is required for create/update")
            body = yaml.safe_load(definition)
            if action == "create":
                return dumps(await client.post("/image_definitions", json_body=body))
            return dumps(await client.put("/image_definitions", json_body=body))
        if action == "delete":
            if not def_id:
                raise ValueError("def_id is required for delete")
            return dumps(await client.delete(f"/image_definitions/{def_id}"))
        if action == "set_read_only":
            if not def_id:
                raise ValueError("def_id is required for set_read_only")
            return dumps(await client.put(f"/image_definitions/{def_id}/read_only", json_body=read_only))
        if action == "list_dropfolder":
            return dumps(await client.get("/list_image_definition_drop_folder"))
        if action == "delete_dropfolder_file":
            if not filename:
                raise ValueError("filename is required for delete_dropfolder_file")
            return dumps(await client.delete(f"/images/manage/{filename}"))
        if action == "upload_image":
            if not file_path or not os.path.isfile(file_path):
                raise ValueError("file_path must point to an existing local image file")
            name = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                data = f.read()
            return dumps(await client.post(
                "/images/upload",
                content=data,
                headers={
                    "x-original-file-name": name,
                    "X-File-Name": name,
                    "Content-Type": "application/octet-stream",
                },
            ))
        # clone_node_image
        if not (lab_id and node_id and definition):
            raise ValueError("lab_id, node_id and definition are required for clone_node_image")
        body = yaml.safe_load(definition)
        return dumps(await client.put(
            f"/labs/{lab_id}/nodes/{node_id}/clone_image", json_body=body
        ))

    @mcp.tool()
    async def get_definition_schema(kind: Literal["node", "image"] = "node") -> str:
        """Get the JSON schema that node or image definition documents must conform to."""
        path = "/node_definition_schema" if kind == "node" else "/image_definition_schema"
        return dumps(await client.get(path))
