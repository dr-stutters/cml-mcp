"""Configuration for the CML MCP server, loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    base_url: str
    username: str
    password: str
    verify_ssl: bool
    timeout: float

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v0"


def load_settings() -> Settings:
    """Build settings from CML_* environment variables (a local .env is honored)."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv()  # also honor .env in the current working directory

    host = os.environ.get("CML_URL") or os.environ.get("CML_HOST", "")
    if not host:
        raise RuntimeError(
            "CML_URL is not set. Set CML_URL (e.g. https://192.0.2.10), "
            "CML_USERNAME and CML_PASSWORD in the environment or a .env file."
        )
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    host = host.rstrip("/")
    if host.endswith("/api/v0"):
        host = host[: -len("/api/v0")]

    username = os.environ.get("CML_USERNAME", "")
    password = os.environ.get("CML_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("CML_USERNAME and CML_PASSWORD must be set.")

    verify = os.environ.get("CML_VERIFY_SSL", "false").strip().lower() in ("1", "true", "yes")
    timeout = float(os.environ.get("CML_TIMEOUT", "60"))

    return Settings(
        base_url=host,
        username=username,
        password=password,
        verify_ssl=verify,
        timeout=timeout,
    )
