from terminalvelocity.providers.defender_xdr import DefenderXdrProvider
from terminalvelocity.providers.registry import create_provider, registry


def test_registry_exposes_all_mvp_providers() -> None:
    assert {"defender_xdr", "entra_id", "intune", "ual", "unified_audit_log"}.issubset(set(registry.names()))


def test_registry_factory_creates_provider() -> None:
    provider = create_provider(
        "defender_xdr",
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
    )
    assert isinstance(provider, DefenderXdrProvider)
