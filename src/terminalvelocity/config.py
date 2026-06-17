"""Application configuration model for TerminalVelocity."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TenantConfig(BaseModel):
    """Configuration for a single Microsoft 365 tenant."""

    tenant_id: str
    client_id: str
    client_secret: str
    display_name: str | None = None


class ProviderConfig(BaseModel):
    """Per-provider enablement and polling settings."""

    name: str
    enabled: bool = True
    poll_interval_seconds: int = 60
    tenant: str | None = None  # references TenantConfig.tenant_id


class FieldMapping(BaseModel):
    """Map external JSON keys to NormalizedEvent fields for file ingestion."""

    provider: str = "imported"
    service: str = "imported"
    timestamp: str | None = None
    actor: str | None = None
    action: str | None = None
    target: str | None = None
    result: str | None = None
    severity: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    tenant_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return only the non-None field-to-source-key mappings."""
        return {dst: src for dst, src in self.model_dump().items() if src and dst not in {"provider", "service"}}


class AppConfig(BaseModel):
    """Root application configuration loaded from YAML."""

    highlight_rules_path: str | None = None
    retention_hours: int = 168  # 7 days default
    poll_interval_seconds: int = 60
    tenants: list[TenantConfig] = Field(default_factory=list)
    providers: list[ProviderConfig] = Field(default_factory=list)
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    log_file: str | None = None
    log_level: str = "WARNING"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """Load configuration from a YAML file."""
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    @classmethod
    def load_or_default(cls, path: str | Path | None = None) -> "AppConfig":
        """Load from *path*, then search default locations, or return defaults.

        Tenant credentials can be provided via environment variables:
        ``TERMINALVELOCITY_TENANT_ID``, ``TERMINALVELOCITY_CLIENT_ID``, and
        ``TERMINALVELOCITY_CLIENT_SECRET``.  When all three are set, a
        :class:`TenantConfig` is added automatically unless a tenant with that
        ID already exists in the YAML configuration.
        """
        candidates: list[Path] = []
        if path:
            candidates.append(Path(path))
        candidates.extend([
            Path("config/terminalvelocity.yaml"),
            Path("terminalvelocity.yaml"),
            Path.home() / ".terminalvelocity" / "config.yaml",
        ])
        cfg: AppConfig | None = None
        for candidate in candidates:
            if candidate.exists():
                cfg = cls.from_yaml(candidate)
                break
        if cfg is None:
            cfg = cls()

        # Overlay tenant credentials from environment variables when not already configured.
        env_tenant_id = os.environ.get("TERMINALVELOCITY_TENANT_ID")
        env_client_id = os.environ.get("TERMINALVELOCITY_CLIENT_ID")
        env_client_secret = os.environ.get("TERMINALVELOCITY_CLIENT_SECRET")
        if env_tenant_id and env_client_id and env_client_secret:
            existing_ids = {t.tenant_id for t in cfg.tenants}
            if env_tenant_id not in existing_ids:
                env_tenant = TenantConfig(
                    tenant_id=env_tenant_id,
                    client_id=env_client_id,
                    client_secret=env_client_secret,
                )
                cfg = cfg.model_copy(update={"tenants": [*cfg.tenants, env_tenant]})

        return cfg
