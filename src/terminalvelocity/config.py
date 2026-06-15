"""Configuration loading and secret resolution for TerminalVelocity."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Mapping

import keyring
from keyring.errors import KeyringError, NoKeyringError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

DEFAULT_CONFIG_PATH = Path("config.toml")


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or resolved."""


class KeyringReference(BaseModel):
    """Reference to a secret stored in the local keyring backend."""

    model_config = ConfigDict(extra="forbid")

    service: str
    username: str


class SecretReference(BaseModel):
    """Reference to a secret that can be inline, environment-backed, or keyring-backed."""

    model_config = ConfigDict(extra="forbid")

    value: SecretStr | None = None
    env: str | None = None
    keyring: KeyringReference | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "SecretReference":
        """Ensure exactly one secret source is configured."""
        populated_sources = [
            self.value is not None,
            self.env is not None,
            self.keyring is not None,
        ]
        if sum(populated_sources) != 1:
            msg = "SecretReference requires exactly one of value, env, or keyring."
            raise ValueError(msg)
        return self

    def resolve(self) -> SecretStr:
        """Resolve the secret value from its configured backing store."""
        if self.value is not None:
            return self.value
        if self.env is not None:
            value = os.getenv(self.env)
            if not value:
                msg = f"Environment variable {self.env!r} is not set."
                raise ConfigError(msg)
            return SecretStr(value)
        if self.keyring is not None:
            try:
                value = keyring.get_password(self.keyring.service, self.keyring.username)
            except (KeyringError, NoKeyringError) as error:
                msg = (
                    "Unable to resolve secret from keyring "
                    f"for service={self.keyring.service!r} username={self.keyring.username!r}."
                )
                raise ConfigError(msg) from error
            if not value:
                msg = (
                    "No keyring secret found for "
                    f"service={self.keyring.service!r} username={self.keyring.username!r}."
                )
                raise ConfigError(msg)
            return SecretStr(value)
        msg = "No secret source configured."
        raise ConfigError(msg)


class AppSettings(BaseModel):
    """Top-level application settings."""

    model_config = ConfigDict(extra="forbid")

    log_level: str = "INFO"


class DatabaseConfig(BaseModel):
    """SQLite persistence configuration."""

    model_config = ConfigDict(extra="forbid")

    path: Path = Path("data/terminalvelocity.db")


class CacheConfig(BaseModel):
    """Raw event cache retention controls."""

    model_config = ConfigDict(extra="forbid")

    raw_event_ttl_hours: int = 24
    max_events: int = 50_000


class DeviceCodeAuthConfig(BaseModel):
    """Public client configuration for device code authentication."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    client_id: str | None = None
    scopes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_device_code(self) -> "DeviceCodeAuthConfig":
        """Require a client ID when device flow is enabled."""
        if self.enabled and not self.client_id:
            msg = "auth.device_code.client_id is required when device flow is enabled."
            raise ValueError(msg)
        return self


class ClientCredentialsAuthConfig(BaseModel):
    """Confidential client configuration for daemon-style auth."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: str | None = None
    client_secret: SecretReference | None = None
    scopes: list[str] = Field(default_factory=lambda: ["https://graph.microsoft.com/.default"])

    @model_validator(mode="after")
    def validate_client_credentials(self) -> "ClientCredentialsAuthConfig":
        """Require a complete credential set when client credentials are enabled."""
        if self.enabled and not self.client_id:
            msg = "auth.client_credentials.client_id is required when client credentials are enabled."
            raise ValueError(msg)
        if self.enabled and self.client_secret is None:
            msg = "auth.client_credentials.client_secret is required when client credentials are enabled."
            raise ValueError(msg)
        return self


class AuthConfig(BaseModel):
    """Shared M365 auth configuration."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = "common"
    authority_host: str = "https://login.microsoftonline.com"
    default_scopes: list[str] = Field(default_factory=lambda: ["https://graph.microsoft.com/.default"])
    device_code: DeviceCodeAuthConfig | None = None
    client_credentials: ClientCredentialsAuthConfig | None = None


class ProviderConfig(BaseModel):
    """Provider-specific toggles and free-form settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    service: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    """Complete application configuration tree."""

    model_config = ConfigDict(extra="forbid")

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


def _coerce_secret_reference(value: Any) -> Any:
    if isinstance(value, str):
        return {"value": value}
    return value


def _prepare_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize permissive TOML input into strict Pydantic models."""
    prepared = {key: value for key, value in payload.items()}
    auth = dict(prepared.get("auth", {}))

    device_code = auth.get("device_code")
    if isinstance(device_code, Mapping):
        auth["device_code"] = dict(device_code)

    client_credentials = auth.get("client_credentials")
    if isinstance(client_credentials, Mapping):
        client_credentials_payload = dict(client_credentials)
        if "client_secret" in client_credentials_payload:
            client_credentials_payload["client_secret"] = _coerce_secret_reference(
                client_credentials_payload["client_secret"]
            )
        auth["client_credentials"] = client_credentials_payload

    prepared["auth"] = auth
    return prepared


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load TerminalVelocity configuration from TOML."""
    config_path = Path(path or os.getenv("TERMINALVELOCITY_CONFIG") or DEFAULT_CONFIG_PATH)
    if not config_path.exists():
        msg = f"Configuration file {config_path} does not exist."
        raise ConfigError(msg)

    with config_path.open("rb") as config_file:
        payload = tomllib.load(config_file)

    try:
        return AppConfig.model_validate(_prepare_payload(payload))
    except Exception as error:  # pragma: no cover - Pydantic error formatting passthrough.
        msg = f"Failed to load configuration from {config_path}: {error}"
        raise ConfigError(msg) from error


def resolve_secret(value: str | Mapping[str, Any] | SecretReference) -> SecretStr:
    """Resolve a secret value from inline text or a secret reference mapping."""
    if isinstance(value, SecretReference):
        return value.resolve()
    if isinstance(value, str):
        return SecretStr(value)
    return SecretReference.model_validate(value).resolve()
