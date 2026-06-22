"""Tests for the updated provider registry (all 8 providers registered)."""

from __future__ import annotations

import unittest

from terminalvelocity.providers.registry import registry as provider_registry

EXPECTED_ALIASES = {
    # Original 4
    "entra": "EntraIdProvider",
    "defender": "DefenderXdrProvider",
    "intune": "IntuneProvider",
    "ual": "UnifiedAuditLogProvider",
    # Newly added 4 providers + aliases
    "exchange": "ExchangeOnlineProvider",
    "exchange_online": "ExchangeOnlineProvider",
    "sharepoint": "SharePointOneDriveProvider",
    "sharepoint_onedrive": "SharePointOneDriveProvider",
    "teams": "TeamsProvider",
    "defender_cloud_apps": "DefenderCloudAppsProvider",
    "mcas": "DefenderCloudAppsProvider",
}


class RegistryTests(unittest.TestCase):
    def test_all_aliases_resolve(self) -> None:
        for alias, expected_class_name in EXPECTED_ALIASES.items():
            with self.subTest(alias=alias):
                cls = provider_registry.get(alias)
                self.assertIsNotNone(cls, f"{alias!r} returned None")
                self.assertEqual(cls.__name__, expected_class_name)

    def test_unknown_alias_raises(self) -> None:
        with self.assertRaises(KeyError):
            provider_registry.get("nonexistent_provider")
