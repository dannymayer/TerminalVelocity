from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from terminalvelocity.investigation.replay import SessionRecorder, SessionReplayer
from terminalvelocity.models import NormalizedEvent

REPO_ROOT = Path(__file__).resolve().parents[2]


class SessionReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = SessionRecorder()
        self.replayer = SessionReplayer()
        self.started_at = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.session = self.recorder.start_session(session_id='session-1', started_at=self.started_at, metadata={'provider': 'entra'})
        self.first = NormalizedEvent(timestamp=self.started_at, provider='entra', service='identity', actor='user@contoso.com', action='SignIn', target='device-1', result='failure', raw={'step': 1})
        self.second = NormalizedEvent(timestamp=self.started_at + timedelta(seconds=10), provider='entra', service='identity', actor='user@contoso.com', action='MFAChallenge', target='device-1', result='success', raw={'step': 2})
        self.recorder.record_event(self.session, self.first, observed_at=self.started_at)
        self.recorder.record_event(self.session, self.second, observed_at=self.started_at + timedelta(seconds=10))
        self.recorder.finalize(self.session, ended_at=self.started_at + timedelta(seconds=15))

    def test_records_and_replays_sessions(self) -> None:
        frames = self.replayer.replay(self.session, speed=2.0)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[1].delay, timedelta(seconds=5))
        self.assertEqual([frame.event.action for frame in frames], ['SignIn', 'MFAChallenge'])

    def test_saves_and_loads_sessions(self) -> None:
        path = REPO_ROOT / 'test-session-replay.json'
        try:
            self.recorder.save(self.session, path)
            loaded = self.recorder.load(path)
            self.assertEqual(loaded.session_id, 'session-1')
            self.assertEqual(loaded.events[1].event.action, 'MFAChallenge')
        finally:
            if path.exists():
                path.unlink()
