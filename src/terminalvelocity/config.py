"""Application configuration model for TerminalVelocity."""

from __future__ import annotations

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

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """Load configuration from a YAML file."""
        data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    @classmethod
    def load_or_default(cls, path: str | Path | None = None) -> "AppConfig":
        """Load from *path*, then search default locations, or return defaults."""
        candidates: list[Path] = []
        if path:
            candidates.append(Path(path))
        candidates.extend([
            Path("config/terminalvelocity.yaml"),
            Path("terminalvelocity.yaml"),
            Path.home() / ".terminalvelocity" / "config.yaml",
        ])
        for candidate in candidates:
            if candidate.exists():
                return cls.from_yaml(candidate)
        return cls()
