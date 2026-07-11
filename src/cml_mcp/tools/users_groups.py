"""User and group administration tools."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def manage_users(
        action: Literal["list", "get", "create", "update", "delete", "get_id", "list_groups"],
        user_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        fullname: str | None = None,
        description: str | None = None,
        email: str | None = None,
        admin: bool | None = None,
        groups: list[str] | None = None,
        resource_pool: str | None = None,
        old_password: str | None = None,
    ) -> str:
        """Administer CML user accounts.

        - list: all users. get / list_groups / update / delete: need user_id.
        - get_id: look up a user's id by username.
        - create: needs username + password; optional fullname, email, admin,
          groups (group ids), resource_pool.
        - update: change any of the optional fields; to change a password supply
          password (+ old_password when changing your own).
        """
        if action == "list":
            return dumps(await client.get("/users"))
        if action == "get_id":
            if not username:
                raise ValueError("username is required for get_id")
            return dumps(await client.get(f"/users/{username}/id"))
        if action == "create":
            if not (username and password):
                raise ValueError("username and password are required for create")
            body: dict[str, Any] = {"username": username, "password": password}
            for k, v in (("fullname", fullname), ("description", description),
                         ("email", email), ("admin", admin), ("groups", groups),
                         ("resource_pool", resource_pool)):
                if v is not None:
                    body[k] = v
            return dumps(await client.post("/users", json_body=body))
        if not user_id:
            raise ValueError(f"user_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/users/{user_id}"))
        if action == "list_groups":
            return dumps(await client.get(f"/users/{user_id}/groups"))
        if action == "delete":
            return dumps(await client.delete(f"/users/{user_id}"))
        # update
        body = {}
        for k, v in (("username", username), ("fullname", fullname),
                     ("description", description), ("email", email),
                     ("admin", admin), ("groups", groups),
                     ("resource_pool", resource_pool)):
            if v is not None:
                body[k] = v
        if password is not None:
            body["password"] = (
                {"old_password": old_password, "new_password": password}
                if old_password else {"new_password": password}
            )
        return dumps(await client.patch(f"/users/{user_id}", json_body=body))

    @mcp.tool()
    async def manage_groups(
        action: Literal["list", "get", "create", "update", "delete", "get_id", "list_members", "list_labs"],
        group_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        members: list[str] | None = None,
        labs: list[dict[str, Any]] | None = None,
    ) -> str:
        """Administer CML user groups (used to share labs between users).

        - list: all groups. get / update / delete / list_members / list_labs: need group_id.
        - get_id: look up a group's id by name.
        - create: needs name; optional description, members (user ids), labs
          (list of {"id": lab_id, "permission": "read_only"|"read_write"}).
        - update: change name/description/members/labs.
        """
        if action == "list":
            return dumps(await client.get("/groups"))
        if action == "get_id":
            if not name:
                raise ValueError("name is required for get_id")
            return dumps(await client.get(f"/groups/{name}/id"))
        if action == "create":
            if not name:
                raise ValueError("name is required for create")
            body: dict[str, Any] = {"name": name}
            for k, v in (("description", description), ("members", members), ("labs", labs)):
                if v is not None:
                    body[k] = v
            return dumps(await client.post("/groups", json_body=body))
        if not group_id:
            raise ValueError(f"group_id is required for {action}")
        if action == "get":
            return dumps(await client.get(f"/groups/{group_id}"))
        if action == "list_members":
            return dumps(await client.get(f"/groups/{group_id}/members"))
        if action == "list_labs":
            return dumps(await client.get(f"/groups/{group_id}/labs"))
        if action == "delete":
            return dumps(await client.delete(f"/groups/{group_id}"))
        body = {}
        for k, v in (("name", name), ("description", description),
                     ("members", members), ("labs", labs)):
            if v is not None:
                body[k] = v
        return dumps(await client.patch(f"/groups/{group_id}", json_body=body))
