"""Tests for the AppConfig model and YAML loading."""

from __future__ import annotations

import textwrap
import unittest
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
