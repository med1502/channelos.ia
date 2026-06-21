"""
Tests — main.py (_resolve_channel_id)
Covers: no channels, single channel, strict alternation between two channels.
DB calls are mocked — no real connection needed.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# main.py calls load_dotenv() at import time; mock dotenv so no .env required
sys.modules.setdefault("dotenv", MagicMock())

sys.path.insert(0, str(Path(__file__).parents[1]))

from channelos.main import _resolve_channel_id


def _mock_conn(channel_ids: list, last_used: int | None = None):
    """Psycopg2 connection mock for _resolve_channel_id.

    First cursor.fetchall() → list of channel IDs.
    First cursor.fetchone() → last used channel_id (or None).
    """
    cur = MagicMock()
    cur.fetchall.return_value = [(c,) for c in channel_ids]
    cur.fetchone.return_value = (last_used,) if last_used is not None else None
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


class TestResolveChannelId(unittest.TestCase):
    def _resolve(self, channels, last=None):
        with patch("channelos.main.db.connect", return_value=_mock_conn(channels, last)):
            return _resolve_channel_id("ai_entrepreneurs")

    def test_no_channels_returns_none(self):
        self.assertIsNone(self._resolve([]))

    def test_single_channel_always_returned(self):
        self.assertEqual(self._resolve([1]), 1)

    def test_first_run_returns_first_channel(self):
        self.assertEqual(self._resolve([1, 2], last=None), 1)

    def test_alternates_to_second_after_first(self):
        self.assertEqual(self._resolve([1, 2], last=1), 2)

    def test_wraps_back_to_first_after_second(self):
        self.assertEqual(self._resolve([1, 2], last=2), 1)

    def test_three_channels_rotate(self):
        self.assertEqual(self._resolve([1, 2, 3], last=1), 2)
        self.assertEqual(self._resolve([1, 2, 3], last=2), 3)
        self.assertEqual(self._resolve([1, 2, 3], last=3), 1)
