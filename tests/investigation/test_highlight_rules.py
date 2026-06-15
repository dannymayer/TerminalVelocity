from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from terminalvelocity.investigation.highlight_rules import HighlightRuleEngine
from terminalvelocity.models import NormalizedEvent

REPO_ROOT = Path(__file__).resolve().parents[2]


class HighlightRuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = NormalizedEvent(
            timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            provider='defender',
            service='identity',
            actor='admin@contoso.com',
            action='Add member to role',
            target='Global Administrator',
            result='success',
            severity='critical',
            raw={'source': 'test'},
        )

    def test_loads_example_rules_and_matches(self) -> None:
        engine = HighlightRuleEngine.from_path(REPO_ROOT / 'config' / 'highlight_rules.example.yaml')
        matches = engine.evaluate(self.event)
        self.assertEqual([match.rule_name for match in matches], ['Privileged role assignment', 'Defender critical incidents'])
        self.assertTrue(engine.should_alert(self.event))

    def test_matches_sequence_values_case_insensitively(self) -> None:
        engine = HighlightRuleEngine.from_yaml(
            """
            rules:
              - name: Test Rule
                match:
                  severity: [HIGH, critical]
                highlight: red
                alert: true
            """
        )
        matches = engine.evaluate(self.event)
        self.assertEqual(matches[0].highlight, 'red')
