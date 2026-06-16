"""Provider adapters for Microsoft 365 log ingestion."""

from terminalvelocity.providers.base import (
    APIRequestError,
    AuditLogQueryProvider,
    BaseProvider,
    BaseProviderAdapter,
    CheckpointStore,
    GraphAPIClient,
    MCASClient,
    ProviderAdapter,
    ProviderConnectionError,
    ProviderError,
    ProviderFetchError,
    RawLogCache,
)
from terminalvelocity.providers.defender_cloud_apps import DefenderCloudAppsProvider
from terminalvelocity.providers.defender_xdr import DefenderXdrProvider
from terminalvelocity.providers.entra_id import EntraIdProvider
from terminalvelocity.providers.exchange_online import ExchangeOnlineProvider
from terminalvelocity.providers.intune import IntuneProvider
from terminalvelocity.providers.registry import create_provider, registry
from terminalvelocity.providers.sharepoint_onedrive import SharePointOneDriveProvider
from terminalvelocity.providers.teams import TeamsProvider
from terminalvelocity.providers.unified_audit_log import UnifiedAuditLogProvider

__all__ = [
    "APIRequestError",
    "AuditLogQueryProvider",
    "BaseProvider",
    "BaseProviderAdapter",
    "CheckpointStore",
    "DefenderCloudAppsProvider",
    "DefenderXdrProvider",
    "EntraIdProvider",
    "ExchangeOnlineProvider",
    "GraphAPIClient",
    "IntuneProvider",
    "MCASClient",
    "ProviderAdapter",
    "ProviderConnectionError",
    "ProviderError",
    "ProviderFetchError",
    "RawLogCache",
    "SharePointOneDriveProvider",
    "TeamsProvider",
    "UnifiedAuditLogProvider",
    "create_provider",
    "registry",
]
