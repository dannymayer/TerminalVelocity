"""MSAL-based Microsoft 365 authentication scaffolding."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from msal import ConfidentialClientApplication, PublicClientApplication, SerializableTokenCache

from .config import AuthConfig, ClientCredentialsAuthConfig, DeviceCodeAuthConfig

LOGGER = logging.getLogger(__name__)
TokenResult = dict[str, Any]


class AuthenticationError(RuntimeError):
    """Raised when MSAL cannot acquire a token."""


class M365Authenticator:
    """Build and execute MSAL authentication flows for M365 providers."""

    def __init__(self, auth_config: AuthConfig, token_cache: SerializableTokenCache | None = None) -> None:
        self.auth_config = auth_config
        self.token_cache = token_cache or SerializableTokenCache()

    @property
    def authority(self) -> str:
        """Return the fully-qualified Entra authority URL."""
        return f"{self.auth_config.authority_host.rstrip('/')}/{self.auth_config.tenant_id}"

    def _default_scopes(self) -> list[str]:
        return list(self.auth_config.default_scopes)

    def create_public_client(self, config: DeviceCodeAuthConfig) -> PublicClientApplication:
        """Create an MSAL public client for device code flow."""
        if not config.client_id:
            msg = "Device code authentication requires a client_id."
            raise AuthenticationError(msg)
        return PublicClientApplication(
            client_id=config.client_id,
            authority=self.authority,
            token_cache=self.token_cache,
        )

    def create_confidential_client(
        self,
        config: ClientCredentialsAuthConfig,
    ) -> ConfidentialClientApplication:
        """Create an MSAL confidential client for app-only auth."""
        if not config.client_id or config.client_secret is None:
            msg = "Client credentials authentication requires a client_id and client_secret."
            raise AuthenticationError(msg)
        return ConfidentialClientApplication(
            client_id=config.client_id,
            authority=self.authority,
            client_credential=config.client_secret.resolve().get_secret_value(),
            token_cache=self.token_cache,
        )

    def acquire_device_code_token(
        self,
        prompt_callback: Callable[[str], None] | None = None,
    ) -> TokenResult:
        """Acquire a delegated token using the MSAL device code flow."""
        config = self.auth_config.device_code
        if config is None or not config.enabled:
            msg = "Device code authentication is not enabled in configuration."
            raise AuthenticationError(msg)

        application = self.create_public_client(config)
        scopes = config.scopes or self._default_scopes()
        flow = application.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            msg = f"MSAL failed to initiate device flow: {flow!r}"
            raise AuthenticationError(msg)

        message = flow.get("message", "Complete device authentication in your browser.")
        LOGGER.info("Starting device code flow")
        if prompt_callback is not None:
            prompt_callback(message)
        else:
            LOGGER.warning(message)

        result = application.acquire_token_by_device_flow(flow)
        self._raise_for_error(result)
        return result

    def acquire_client_credentials_token(self, scopes: Sequence[str] | None = None) -> TokenResult:
        """Acquire an app-only token using confidential client credentials."""
        config = self.auth_config.client_credentials
        if config is None or not config.enabled:
            msg = "Client credentials authentication is not enabled in configuration."
            raise AuthenticationError(msg)

        application = self.create_confidential_client(config)
        resolved_scopes = list(scopes or config.scopes or self._default_scopes())
        result = application.acquire_token_for_client(scopes=resolved_scopes)
        self._raise_for_error(result)
        return result

    @staticmethod
    def access_token(token_result: TokenResult) -> str:
        """Extract an access token from an MSAL token result."""
        access_token = token_result.get("access_token")
        if not access_token:
            msg = f"Token result did not contain an access_token: {token_result!r}"
            raise AuthenticationError(msg)
        return str(access_token)

    @classmethod
    def authorization_header(cls, token_result: TokenResult) -> dict[str, str]:
        """Create an Authorization header from an MSAL token result."""
        return {"Authorization": "Bearer " + cls.access_token(token_result)}

    @staticmethod
    def _raise_for_error(result: TokenResult) -> None:
        """Raise a helpful exception when MSAL returns an error payload."""
        if "access_token" in result:
            return
        error = result.get("error", "unknown_error")
        description = result.get("error_description", "No error description returned.")
        correlation_id = result.get("correlation_id", "n/a")
        msg = (
            f"MSAL token acquisition failed: {error} - {description} "
            f"(correlation_id={correlation_id})"
        )
        raise AuthenticationError(msg)
