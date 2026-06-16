from __future__ import annotations

from typing import Any, Type

from terminalvelocity.providers.base import ProviderAdapter
from terminalvelocity.providers.defender_xdr import DefenderXdrProvider
from terminalvelocity.providers.entra_id import EntraIdProvider
from terminalvelocity.providers.intune import IntuneProvider
from terminalvelocity.providers.unified_audit_log import UnifiedAuditLogProvider

ProviderType = Type[ProviderAdapter]


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderType] = {}

    def register(self, name: str, provider_type: ProviderType) -> None:
        self._providers[name] = provider_type

    def get(self, name: str) -> ProviderType:
        try:
            return self._providers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers))
            raise KeyError(f"Unknown provider '{name}'. Available providers: {available}") from exc

    def create(self, name: str, **kwargs: Any) -> ProviderAdapter:
        return self.get(name)(**kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


registry = ProviderRegistry()
registry.register("ual", UnifiedAuditLogProvider)
registry.register("unified_audit_log", UnifiedAuditLogProvider)
registry.register("intune", IntuneProvider)
registry.register("defender", DefenderXdrProvider)
registry.register("defender_xdr", DefenderXdrProvider)
registry.register("entra", EntraIdProvider)
registry.register("entra_id", EntraIdProvider)


def create_provider(name: str, **kwargs: Any) -> ProviderAdapter:
    return registry.create(name, **kwargs)
