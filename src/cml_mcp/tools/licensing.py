"""Smart Licensing tools: status, registration, and offline reservation (SLR)."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..client import CMLClient
from . import dumps


def register(mcp: FastMCP, client: CMLClient) -> None:
    @mcp.tool()
    async def get_licensing_status() -> str:
        """Get Smart Licensing status: registration, authorization (EVAL/registered), active product license, feature counts, transport settings, and reservation mode."""
        return dumps(await client.get("/licensing"))

    @mcp.tool()
    async def manage_licensing(
        action: Literal[
            "register", "deregister", "renew_authorization", "renew_registration",
            "set_transport", "set_features", "set_product_license", "tech_support",
        ],
        token: str | None = None,
        reregister: bool = False,
        ssms: str | None = None,
        proxy_server: str | None = None,
        proxy_port: int | None = None,
        features: list[dict] | None = None,
        product_license: str | None = None,
    ) -> str:
        """Administer online Smart Licensing.

        Typical online registration flow: set_product_license -> set_transport
        (if not using Cisco's public smart receiver) -> register(token) ->
        verify with get_licensing_status.

        - register: needs 'token' (from your CSSM Smart Account); set
          reregister=True to force re-registration.
        - deregister: release the license back to the Smart Account.
        - renew_authorization / renew_registration: refresh with CSSM.
        - set_transport: 'ssms' URL (CSSM or on-prem SSMS satellite), optional
          proxy_server/proxy_port.
        - set_features: list of {"id": <feature id>, "count": N} (feature ids
          from get_licensing_status; e.g. expand Enterprise node count).
        - set_product_license: e.g. 'CML_Enterprise', 'CML_Education',
          'CML_Personal', 'CML_Personal40'.
        - tech_support: licensing tech-support dump for TAC.
        """
        if action == "register":
            if not token:
                raise ValueError("token is required for register")
            return dumps(await client.post(
                "/licensing/registration",
                json_body={"token": token, "reregister": reregister},
            ))
        if action == "deregister":
            return dumps(await client.delete("/licensing/deregistration"))
        if action == "renew_authorization":
            return dumps(await client.put("/licensing/authorization/renew"))
        if action == "renew_registration":
            return dumps(await client.put("/licensing/registration/renew"))
        if action == "set_transport":
            body = {
                "ssms": ssms or "https://smartreceiver.cisco.com/licservice/license",
                "proxy": {"server": proxy_server, "port": proxy_port},
            }
            return dumps(await client.put("/licensing/transport", json_body=body))
        if action == "set_features":
            if not features:
                raise ValueError(
                    'features is required: [{"id": <feature id>, "count": N}, ...]'
                )
            return dumps(await client.patch("/licensing/features", json_body=features))
        if action == "set_product_license":
            if not product_license:
                raise ValueError("product_license is required for set_product_license")
            return dumps(await client.put("/licensing/product_license", json_body=product_license))
        return dumps(await client.get("/licensing/tech_support"))

    @mcp.tool()
    async def manage_license_reservation(
        action: Literal[
            "enable_mode", "disable_mode", "request", "complete", "discard",
            "cancel", "release", "get_confirmation_code", "delete_confirmation_code",
            "get_return_code", "delete_return_code",
        ],
        code: str | None = None,
    ) -> str:
        """Orchestrate offline Smart License Reservation (SLR) for air-gapped CML servers.

        Reservation flow:
        1. enable_mode - turn on reservation mode.
        2. request - generate a reservation REQUEST code (take it to CSSM at
           software.cisco.com to produce an authorization code).
        3. complete - install the CSSM AUTHORIZATION code ('code' param);
           get_confirmation_code afterwards if needed.
        To undo: cancel (before completion), or release (after completion,
        returns a RETURN code to enter in CSSM), then disable_mode.
        discard removes an authorization code that was never installed
        ('code' param).
        """
        base = "/licensing/reservation"
        if action == "enable_mode":
            return dumps(await client.put(f"{base}/mode", json_body=True))
        if action == "disable_mode":
            return dumps(await client.put(f"{base}/mode", json_body=False))
        if action == "request":
            return dumps(await client.post(f"{base}/request"))
        if action == "complete":
            if not code:
                raise ValueError("code (CSSM authorization code) is required for complete")
            return dumps(await client.post(f"{base}/complete", json_body=code))
        if action == "discard":
            if not code:
                raise ValueError("code (CSSM authorization code) is required for discard")
            return dumps(await client.post(f"{base}/discard", json_body=code))
        if action == "cancel":
            return dumps(await client.delete(f"{base}/cancel"))
        if action == "release":
            return dumps(await client.delete(f"{base}/release"))
        if action == "get_confirmation_code":
            return dumps(await client.get(f"{base}/confirmation_code"))
        if action == "delete_confirmation_code":
            return dumps(await client.delete(f"{base}/confirmation_code"))
        if action == "get_return_code":
            return dumps(await client.get(f"{base}/return_code"))
        return dumps(await client.delete(f"{base}/return_code"))
