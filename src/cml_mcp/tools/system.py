"""System administration tools: status, compute hosts, connectors, pools, repos."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def get_system_status(
        include: Literal["information", "health", "stats", "all"] = "information",
    ) -> str:
        """Get CML server status.

        - information: version, ready state, OpenAPI/UI versions.
        - health: component health (controller, compute hosts, low-level drivers).
        - stats: CPU/memory/disk utilization per compute host.
        - all: everything above combined.
        """
        result: dict[str, Any] = {}
        if include in ("information", "all"):
            result["information"] = await client.get("/system_information")
        if include in ("health", "all"):
            result["health"] = await client.get("/system_health")
        if include in ("stats", "all"):
            result["stats"] = await client.get("/system_stats")
        return dumps(result if include == "all" else next(iter(result.values())))

    @mcp.tool()
    async def manage_compute_hosts(
        action: Literal["list", "get", "update", "delete", "get_config", "set_config"] = "list",
        compute_id: str | None = None,
        update: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """Manage cluster compute hosts.

        - list/get: view compute hosts and their capacity.
        - update: change admission state etc. (update object, needs compute_id).
        - delete: remove an orphaned compute host from the cluster.
        - get_config/set_config: global compute host configuration (e.g.
          admission mode for new hosts).
        """
        if action == "list":
            return dumps(await client.get("/system/compute_hosts"))
        if action == "get_config":
            return dumps(await client.get("/system/compute_hosts/configuration"))
        if action == "set_config":
            if not config:
                raise ValueError("config object is required for set_config")
            return dumps(await client.patch("/system/compute_hosts/configuration", json_body=config))
        if not compute_id:
            raise ValueError(f"compute_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/system/compute_hosts/{compute_id}"))
        if action == "delete":
            return dumps(await client.delete(f"/system/compute_hosts/{compute_id}"))
        if not update:
            raise ValueError("update object is required for update")
        return dumps(await client.patch(f"/system/compute_hosts/{compute_id}", json_body=update))

    @mcp.tool()
    async def manage_external_connectors(
        action: Literal["list", "get", "update", "delete", "sync"] = "list",
        connector_id: str | None = None,
        update: dict[str, Any] | None = None,
    ) -> str:
        """Manage external connectors (bridges from labs to the outside network, e.g. NAT / bridged).

        'sync' re-scans the host's network devices; 'update' can change label
        and tags (update object, needs connector_id).
        """
        if action == "list":
            return dumps(await client.get("/system/external_connectors"))
        if action == "sync":
            return dumps(await client.put("/system/external_connectors"))
        if not connector_id:
            raise ValueError(f"connector_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/system/external_connectors/{connector_id}"))
        if action == "delete":
            return dumps(await client.delete(f"/system/external_connectors/{connector_id}"))
        if not update:
            raise ValueError("update object is required for update")
        return dumps(await client.patch(f"/system/external_connectors/{connector_id}", json_body=update))

    @mcp.tool()
    async def manage_resource_pools(
        action: Literal["list", "get", "create", "update", "delete", "usage"] = "list",
        resource_pool_id: str | None = None,
        pool: dict[str, Any] | None = None,
    ) -> str:
        """Manage resource pools (CPU/RAM/node quotas assignable to users).

        - create/update: 'pool' object, e.g. {"label": "students", "cpus": 16,
          "ram": 32768, "external_connectors": [...]}; template pools have
          shared limits, user pools set 'user_pool' fields.
        - usage: show pool utilization (all pools, or one with resource_pool_id).
        """
        if action == "list":
            return dumps(await client.get("/resource_pools", params={"data": True}))
        if action == "usage":
            if resource_pool_id:
                return dumps(await client.get(f"/resource_pool_usage/{resource_pool_id}"))
            return dumps(await client.get("/resource_pool_usage"))
        if action == "create":
            if not pool:
                raise ValueError("pool object is required for create")
            return dumps(await client.post("/resource_pools", json_body=pool))
        if not resource_pool_id:
            raise ValueError(f"resource_pool_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/resource_pools/{resource_pool_id}"))
        if action == "delete":
            return dumps(await client.delete(f"/resource_pools/{resource_pool_id}"))
        if not pool:
            raise ValueError("pool object is required for update")
        return dumps(await client.patch(f"/resource_pools/{resource_pool_id}", json_body=pool))

    @mcp.tool()
    async def manage_lab_repos(
        action: Literal["list", "get", "create", "delete", "refresh"] = "list",
        repo_id: str | None = None,
        repo: dict[str, Any] | None = None,
    ) -> str:
        """Manage lab repositories (git repos of sample/shared topologies).

        - create: 'repo' object with repository details (e.g. {"url": ...}).
        - refresh: re-sync all repos, or one if repo_id is given.
        """
        if action == "list":
            return dumps(await client.get("/lab_repos"))
        if action == "create":
            if not repo:
                raise ValueError("repo object is required for create")
            return dumps(await client.post("/lab_repos", json_body=repo))
        if action == "refresh":
            if repo_id:
                return dumps(await client.put(f"/lab_repos/{repo_id}/refresh"))
            return dumps(await client.put("/lab_repos/refresh"))
        if not repo_id:
            raise ValueError(f"repo_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/lab_repos/{repo_id}"))
        return dumps(await client.delete(f"/lab_repos/{repo_id}"))

    @mcp.tool()
    async def manage_system_notices(
        action: Literal["list", "get", "create", "update", "delete"] = "list",
        notice_id: str | None = None,
        notice: dict[str, Any] | None = None,
    ) -> str:
        """Manage system notices (banners/messages shown to CML users).

        For create/update, 'notice' is e.g. {"label": "...", "content": "...",
        "level": "info"|"warning"|"error", "enabled": true, "acknowledgement_required": false}.
        """
        if action == "list":
            return dumps(await client.get("/system/notices"))
        if action == "create":
            if not notice:
                raise ValueError("notice object is required for create")
            return dumps(await client.post("/system/notices", json_body=notice))
        if not notice_id:
            raise ValueError(f"notice_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/system/notices/{notice_id}"))
        if action == "delete":
            return dumps(await client.delete(f"/system/notices/{notice_id}"))
        if not notice:
            raise ValueError("notice object is required for update")
        return dumps(await client.patch(f"/system/notices/{notice_id}", json_body=notice))

    @mcp.tool()
    async def manage_maintenance_mode(
        action: Literal["get", "set"] = "get",
        enabled: bool | None = None,
        notice_id: str | None = None,
    ) -> str:
        """Get or set system maintenance mode (blocks non-admin logins; optionally tie to a notice)."""
        if action == "get":
            return dumps(await client.get("/system/maintenance_mode"))
        if enabled is None:
            raise ValueError("enabled is required for set")
        body: dict[str, Any] = {"enabled": enabled}
        if notice_id is not None:
            body["notice"] = notice_id
        return dumps(await client.patch("/system/maintenance_mode", json_body=body))

    @mcp.tool()
    async def get_diagnostics(
        category: Literal[
            "computes", "labs", "lab_events", "licensing", "node_definitions",
            "node_launch_queue", "services", "startup_scheduler", "user_list",
        ] = "labs",
    ) -> str:
        """Get low-level controller diagnostics for a category (troubleshooting aid)."""
        return dumps(await client.get(f"/diagnostics/{category}"))
