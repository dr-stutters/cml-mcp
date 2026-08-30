"""Server configuration.

All settings come from environment variables with the ``CML_MCP_`` prefix,
or from a ``.env`` file in the working directory. The specialize script renames
the prefix per platform (e.g. ``CML_MCP_BASE_URL``).

Secrets (password, api_token, device_password, enable_password) must only ever
arrive via environment variables — never hardcode them and never log them.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, environment-driven and validated at startup."""

    model_config = SettingsConfigDict(
        env_prefix="CML_MCP_",
        env_file=".env",
        extra="ignore",
    )

    base_url: str = Field(
        description="CML API base URL including the /api/v0 prefix, e.g. "
        "'https://cml.example.com/api/v0'. Required."
    )
    username: str = Field(default="", description="Username for basic or login-token auth.")
    password: str = Field(default="", description="Password for basic or login-token auth.")
    api_token: str = Field(
        default="", description="Static API token, for platforms that issue long-lived tokens."
    )
    device_username: str = Field(
        default="",
        description=(
            "Optional. Console login username for the lab's DEVICES (not the CML account). "
            "Set it when a lab's day-0 configuration replaces the default local user, "
            "otherwise console logins hang at the prompt. Empty means 'use whatever CML "
            "generated in the pyATS testbed'."
        ),
    )
    device_password: str = Field(
        default="",
        description=(
            "Optional. Console login password for the lab's DEVICES, paired with "
            "device_username. Empty means 'use whatever CML generated in the pyATS testbed'."
        ),
    )
    enable_password: str = Field(
        default="",
        description=(
            "Optional. Enable secret for the lab's DEVICES, used when a node drops into "
            "user EXEC and Unicon has to escalate to privileged EXEC. Empty means 'use "
            "whatever CML generated in the pyATS testbed'."
        ),
    )
    verify_tls: bool = Field(
        default=True,
        description="Verify TLS certificates. Set false for lab gear with self-signed certs.",
    )
    timeout_seconds: float = Field(default=30.0, ge=1, description="Per-request read timeout.")
    connect_timeout_seconds: float = Field(default=10.0, ge=1, description="Connect timeout.")
    max_retries: int = Field(
        default=3, ge=0, le=10, description="Retries for 429/5xx/transport errors."
    )
    retry_backoff_seconds: float = Field(
        default=1.0, ge=0, description="Base delay for exponential backoff between retries."
    )
    max_concurrent_requests: int = Field(
        default=5, ge=1, le=50, description="Cap on concurrent requests to the platform."
    )
    enable_writes: bool = Field(
        default=False,
        description="When false (default), tools that modify the platform are not registered.",
    )
    max_response_chars: int = Field(
        default=40_000, ge=1_000, description="Tool responses longer than this are truncated."
    )
    log_level: str = Field(default="INFO", description="Python logging level (stderr only).")

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v
