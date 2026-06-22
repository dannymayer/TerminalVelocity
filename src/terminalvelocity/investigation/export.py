from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from terminalvelocity.models import NormalizedEvent

ExportFormat = Literal['json', 'csv', 'markdown']


class EventExporter:
    """Export normalized events into analyst-friendly formats."""

    def export_json(self, events: Iterable[NormalizedEvent], *, indent: int = 2) -> str:
        """Serialize events as JSON."""

        payload = [self._event_to_dict(event) for event in events]
        return json.dumps(payload, indent=indent, sort_keys=True, default=str)

    def export_csv(self, events: Iterable[NormalizedEvent]) -> str:
        """Serialize events as CSV."""

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(self._fieldnames()))
        writer.writeheader()
        for event in events:
            writer.writerow(self._event_to_dict(event, stringify_raw=True))
        return buffer.getvalue()

    def export_markdown_report(
        self,
        events: Iterable[NormalizedEvent],
        *,
        title: str = 'Incident Report',
        summary: str | None = None,
    ) -> str:
        """Build a markdown incident report from selected events."""

        ordered_events = sorted(events, key=lambda event: event.timestamp)
        lines = [f'# {title}', '']
        if summary:
            lines.extend([summary, ''])
        lines.extend([
            f'- Events: {len(ordered_events)}',
            f"- Start: {ordered_events[0].timestamp.isoformat() if ordered_events else 'n/a'}",
            f"- End: {ordered_events[-1].timestamp.isoformat() if ordered_events else 'n/a'}",
            '',
            '## Timeline',
            '',
        ])
        for event in ordered_events:
            lines.append(
                f"- **{event.timestamp.isoformat()}** `{event.provider}/{event.service}` "
                f"{event.actor or 'unknown actor'} -> {event.action} -> {event.target or 'unknown target'} "
                f"({event.result or 'unknown result'})"
            )
        lines.extend(['', '## Evidence', '', '```json', self.export_json(ordered_events), '```', ''])
        return '\n'.join(lines)

    def write(self, events: Iterable[NormalizedEvent], destination: str | Path, *, format: ExportFormat, **kwargs: object) -> Path:
        """Write exported events to disk and return the destination path."""

        destination_path = Path(destination)
        content = self._render(events, format=format, **kwargs)
        destination_path.write_text(content, encoding='utf-8')
        return destination_path

    def _render(self, events: Iterable[NormalizedEvent], *, format: ExportFormat, **kwargs: object) -> str:
        if format == 'json':
            return self.export_json(events, **kwargs)
        if format == 'csv':
            return self.export_csv(events)
        if format == 'markdown':
            return self.export_markdown_report(events, **kwargs)
        raise ValueError(f'Unsupported export format: {format}')

    @staticmethod
    def _fieldnames() -> tuple[str, ...]:
        return (
            'timestamp',
            'provider',
            'service',
            'tenant_id',
            'actor',
            'action',
            'target',
            'result',
            'severity',
            'correlation_id',
            'request_id',
            'raw',
        )

    def _event_to_dict(self, event: NormalizedEvent, *, stringify_raw: bool = False) -> dict[str, object]:
        return {
            'timestamp': event.timestamp.isoformat(),
            'provider': event.provider,
            'service': event.service,
            'tenant_id': event.tenant_id,
            'actor': event.actor,
            'action': event.action,
            'target': event.target,
            'result': event.result,
            'severity': event.severity,
            'correlation_id': event.correlation_id,
            'request_id': event.request_id,
            'raw': json.dumps(event.raw, sort_keys=True, default=str) if stringify_raw else event.raw,
        }
