"""Tests for file-based event ingestion."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from terminalvelocity.ingestion import FileIngestionError, ingest_file
from terminalvelocity.models import NormalizedEvent


def _write_temp(suffix: str, content: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        return f.name


class IngestJSONLTests(unittest.TestCase):
    def test_ingest_valid_jsonl(self) -> None:
        event = NormalizedEvent.model_validate(
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "provider": "entra",
                "service": "audit",
                "actor": "user@contoso.com",
                "action": "sign-in",
                "result": "success",
                "severity": "low",
                "raw": {},
            }
        )
        line = event.model_dump_json() + "\n"
        path = _write_temp(".jsonl", line)
        try:
            events = ingest_file(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].actor, "user@contoso.com")
        finally:
            Path(path).unlink()

    def test_ingest_empty_lines_skipped(self) -> None:
        content = (
            '{"timestamp":"2024-01-01T00:00:00Z","provider":"entra","service":"audit",'
            '"actor":"a@b.com","action":"x","result":"success","severity":"low","raw":{}}\n'
            "\n"
            "   \n"
        )
        path = _write_temp(".jsonl", content)
        try:
            events = ingest_file(path)
            self.assertEqual(len(events), 1)
        finally:
            Path(path).unlink()

    def test_provider_override(self) -> None:
        content = (
            '{"timestamp":"2024-01-01T00:00:00Z","provider":"entra","service":"audit",'
            '"actor":"a@b.com","action":"x","result":"success","severity":"low","raw":{}}\n'
        )
        path = _write_temp(".jsonl", content)
        try:
            events = ingest_file(path, provider_override="defender")
            self.assertEqual(events[0].provider, "defender")
        finally:
            Path(path).unlink()


class IngestJSONArrayTests(unittest.TestCase):
    def test_ingest_json_array(self) -> None:
        events_data = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "provider": "defender",
                "service": "alert",
                "actor": "user@corp.com",
                "action": "malware-detected",
                "result": "failure",
                "severity": "high",
                "raw": {},
            }
        ]
        path = _write_temp(".json", json.dumps(events_data))
        try:
            events = ingest_file(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].provider, "defender")
        finally:
            Path(path).unlink()

    def test_ingest_json_object_field_mapping(self) -> None:
        # Raw M365-style object with non-standard keys; field_mappings format is {dst_field: src_key}
        data = [{"UserId": "admin@corp.com", "Operation": "FileAccessed", "CreationTime": "2024-01-01T00:00:00Z"}]
        field_mappings = {"actor": "UserId", "action": "Operation", "timestamp": "CreationTime"}
        path = _write_temp(".json", json.dumps(data))
        try:
            events = ingest_file(path, field_mappings=field_mappings, provider_override="sharepoint")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].actor, "admin@corp.com")
            self.assertEqual(events[0].action, "FileAccessed")
        finally:
            Path(path).unlink()


class IngestCSVTests(unittest.TestCase):
    def test_ingest_csv(self) -> None:
        import os

        rows = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "provider": "intune",
                "service": "compliance",
                "actor": "device@corp.com",
                "action": "policy-check",
                "result": "success",
                "severity": "low",
                "raw": "{}",
            }
        ]
        path = _write_temp(".csv", "")
        os.unlink(path)
        path = _write_temp(".csv", "")
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        try:
            events = ingest_file(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].provider, "intune")
        finally:
            Path(path).unlink()


class IngestErrorTests(unittest.TestCase):
    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileIngestionError):
            ingest_file("/tmp/nonexistent_file_xyz.jsonl")

    def test_unknown_extension_tries_jsonl(self) -> None:
        # A file with unknown extension but valid JSONL content should parse
        content = (
            '{"timestamp":"2024-01-01T00:00:00Z","provider":"entra","service":"audit",'
            '"actor":"a@b.com","action":"x","result":"success","severity":"low","raw":{}}\n'
        )
        path = _write_temp(".txt", content)
        try:
            events = ingest_file(path)
            self.assertEqual(len(events), 1)
        finally:
            Path(path).unlink()
