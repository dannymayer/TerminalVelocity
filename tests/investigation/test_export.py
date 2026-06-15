from __future__ import annotations

import csv
import io
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from terminalvelocity.investigation.export import EventExporter
from terminalvelocity.models import NormalizedEvent

REPO_ROOT = Path(__file__).resolve().parents[2]


class EventExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = [
            NormalizedEvent(
                timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
                provider='defender',
                service='identity',
                actor='user@contoso.com',
                action='PasswordReset',
                target='account-1',
                result='failure',
                severity='high',
                correlation_id='corr-1',
                raw={'message': 'reset failed'},
            )
        ]
        self.exporter = EventExporter()

    def test_exports_json_csv_and_markdown(self) -> None:
        json_payload = json.loads(self.exporter.export_json(self.events))
        self.assertEqual(json_payload[0]['action'], 'PasswordReset')

        csv_payload = self.exporter.export_csv(self.events)
        rows = list(csv.DictReader(io.StringIO(csv_payload)))
        self.assertEqual(rows[0]['result'], 'failure')

        markdown = self.exporter.export_markdown_report(self.events, summary='Investigation summary')
        self.assertIn('# Incident Report', markdown)
        self.assertIn('Investigation summary', markdown)
        self.assertIn('## Evidence', markdown)

    def test_writes_to_disk(self) -> None:
        output_path = REPO_ROOT / 'test-export.json'
        try:
            written_path = self.exporter.write(self.events, output_path, format='json')
            self.assertTrue(written_path.exists())
        finally:
            if output_path.exists():
                output_path.unlink()
