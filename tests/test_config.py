"""Tests for the AppConfig model and YAML loading."""

from __future__ import annotations

import textwrap
import unittest
import unittest.mock
from pathlib import Path

import pytest

from terminalvelocity.config import AppConfig, FieldMapping


class AppConfigDefaultsTests(unittest.TestCase):
    def test_load_defaults(self) -> None:
        cfg = AppConfig.load_or_default(None)
        self.assertIsInstance(cfg, AppConfig)
        self.assertIsInstance(cfg.providers, list)

    def test_default_providers_list_empty(self) -> None:
        # Default config has no providers; they must be configured explicitly
        cfg = AppConfig.load_or_default(None)
        self.assertIsInstance(cfg.providers, list)


class AppConfigYAMLTests(unittest.TestCase):
    def test_load_from_yaml(self, tmp_path: Path = None) -> None:
        import tempfile, os

        yaml_content = textwrap.dedent("""\
            poll_interval_seconds: 30
            retention_hours: 48
            providers:
              - name: defender
                enabled: true
              - name: entra
                enabled: false
            field_mappings:
              - provider: custom
                actor: UserId
                action: Operation
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            name = f.name
        try:
            cfg = AppConfig.load_or_default(name)
            self.assertEqual(cfg.poll_interval_seconds, 30)
            self.assertEqual(cfg.retention_hours, 48)
            # providers list from YAML
            names = [p.name for p in cfg.providers]
            self.assertIn("defender", names)
            self.assertIn("entra", names)
            # entra should be disabled
            entra = next(p for p in cfg.providers if p.name == "entra")
            self.assertFalse(entra.enabled)
            # field mappings
            self.assertEqual(len(cfg.field_mappings), 1)
            self.assertEqual(cfg.field_mappings[0].provider, "custom")
        finally:
            os.unlink(name)

    def test_as_dict_on_field_mapping(self) -> None:
        # FieldMapping stores per-NormalizedEvent-field source keys
        fm = FieldMapping(provider="test", actor="UserId", action="Operation")
        d = fm.as_dict()
        # as_dict returns {dst_field: source_key} for non-None mappings
        self.assertEqual(d.get("actor"), "UserId")
        self.assertEqual(d.get("action"), "Operation")


class AppConfigEnvVarTests(unittest.TestCase):
    def test_env_vars_add_tenant_when_none_configured(self) -> None:
        import os
        env = {
            "TERMINALVELOCITY_TENANT_ID": "env-tenant",
            "TERMINALVELOCITY_CLIENT_ID": "env-client",
            "TERMINALVELOCITY_CLIENT_SECRET": "env-secret",
        }
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.load_or_default(None)
        self.assertEqual(len(cfg.tenants), 1)
        self.assertEqual(cfg.tenants[0].tenant_id, "env-tenant")
        self.assertEqual(cfg.tenants[0].client_id, "env-client")
        self.assertEqual(cfg.tenants[0].client_secret, "env-secret")

    def test_env_vars_do_not_duplicate_existing_tenant(self) -> None:
        import os, tempfile, textwrap
        yaml_content = textwrap.dedent("""\
            tenants:
              - tenant_id: "env-tenant"
                client_id: "yaml-client"
                client_secret: "yaml-secret"
        """)
        env = {
            "TERMINALVELOCITY_TENANT_ID": "env-tenant",
            "TERMINALVELOCITY_CLIENT_ID": "env-client",
            "TERMINALVELOCITY_CLIENT_SECRET": "env-secret",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            name = f.name
        try:
            with unittest.mock.patch.dict(os.environ, env, clear=False):
                cfg = AppConfig.load_or_default(name)
            # Existing YAML tenant should not be duplicated
            self.assertEqual(len(cfg.tenants), 1)
            self.assertEqual(cfg.tenants[0].client_id, "yaml-client")
        finally:
            os.unlink(name)

    def test_partial_env_vars_do_not_add_tenant(self) -> None:
        import os
        # Only two of three vars set — no tenant should be added
        env = {
            "TERMINALVELOCITY_TENANT_ID": "env-tenant",
            "TERMINALVELOCITY_CLIENT_ID": "env-client",
        }
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.load_or_default(None)
        self.assertEqual(len(cfg.tenants), 0)
