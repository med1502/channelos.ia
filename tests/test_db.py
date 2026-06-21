"""
Tests — db/client.py
Covers: estimate_cost, save_idea, save_video (arm validation), mark_published,
        log_cost, log_anthropic. DB calls are mocked via psycopg2.connect.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

import channelos.db.client as client


# ── Helper ────────────────────────────────────────────────────────────────────

def _mock_conn(fetchone=None, fetchall=None):
    """Return (conn_mock, cursor_mock) that behave as psycopg2 context managers."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


# ── estimate_cost ─────────────────────────────────────────────────────────────

class TestEstimateCost(unittest.TestCase):
    def test_anthropic_dict_units(self):
        cost = client.estimate_cost("anthropic", "tokens",
                                    {"input": 1_000_000, "output": 1_000_000})
        self.assertAlmostEqual(cost, 18.0, places=4)  # 3 + 15

    def test_anthropic_scalar_units_returns_zero(self):
        self.assertEqual(client.estimate_cost("anthropic", "tokens", 100), 0.0)

    def test_tavily_per_credit(self):
        cost = client.estimate_cost("tavily", "credits", 3)
        self.assertAlmostEqual(cost, 0.024, places=6)

    def test_json2video_per_second(self):
        cost = client.estimate_cost("json2video", "seconds", 30)
        self.assertAlmostEqual(cost, 0.12, places=6)

    def test_pexels_always_free(self):
        self.assertEqual(client.estimate_cost("pexels", "request", 99), 0.0)

    def test_unknown_provider_returns_zero(self):
        self.assertEqual(client.estimate_cost("mystery_api", "units", 5), 0.0)


# ── save_idea ─────────────────────────────────────────────────────────────────

class TestSaveIdea(unittest.TestCase):
    def test_returns_db_id(self):
        conn, _ = _mock_conn(fetchone=(42,))
        with patch("channelos.db.client.connect", return_value=conn):
            idea_id = client.save_idea(
                {"title": "Test", "viral_score": 80, "brand_safe": True, "format": "ranking"}
            )
        self.assertEqual(idea_id, 42)


# ── save_video ────────────────────────────────────────────────────────────────

class TestSaveVideo(unittest.TestCase):
    def _save(self, arm="baseline"):
        conn, _ = _mock_conn(fetchone=(7,))
        with patch("channelos.db.client.connect", return_value=conn):
            return client.save_video(
                1,
                {"spoken_text": "hi", "caption": "cap", "hashtags": []},
                "https://p.com/v.mp4", "https://j2v.com/v.mp4", "/tmp/v.mp4",
                hook_pattern="question", format="single",
                niche="ai_entrepreneurs", lang="EN",
                channel_id=1, arm=arm,
            )

    def test_returns_video_id(self):
        self.assertEqual(self._save(), 7)

    def test_rejects_invalid_arm(self):
        with self.assertRaises(ValueError):
            self._save(arm="invalid")

    def test_accepts_bandit_arm(self):
        self.assertEqual(self._save(arm="bandit"), 7)


# ── mark_published ────────────────────────────────────────────────────────────

class TestMarkPublished(unittest.TestCase):
    def test_issues_update_sql(self):
        conn, cur = _mock_conn()
        with patch("channelos.db.client.connect", return_value=conn):
            client.mark_published(5, "yt_abc123")
        sql = cur.execute.call_args[0][0]
        self.assertIn("UPDATE videos", sql)
        self.assertIn("published", sql)


# ── log_cost ──────────────────────────────────────────────────────────────────

class TestLogCost(unittest.TestCase):
    def test_returns_computed_cost(self):
        conn, _ = _mock_conn()
        with patch("channelos.db.client.connect", return_value=conn):
            cost = client.log_cost("tavily", "search", 3, "credits")
        self.assertAlmostEqual(cost, 0.024, places=6)

    def test_accepts_dict_units(self):
        conn, _ = _mock_conn()
        with patch("channelos.db.client.connect", return_value=conn):
            cost = client.log_cost(
                "anthropic", "ideas",
                {"input": 1000, "output": 500}, "tokens",
            )
        self.assertGreater(cost, 0)


# ── log_anthropic ─────────────────────────────────────────────────────────────

class TestLogAnthropic(unittest.TestCase):
    def _msg(self, inp=1000, out=500):
        msg = MagicMock()
        msg.usage.input_tokens = inp
        msg.usage.output_tokens = out
        return msg

    def test_returns_positive_cost(self):
        conn, _ = _mock_conn()
        with patch("channelos.db.client.connect", return_value=conn):
            cost = client.log_anthropic(self._msg(), "ideas")
        self.assertGreater(cost, 0)

    def test_returns_zero_when_no_usage(self):
        msg = MagicMock()
        msg.usage = None
        self.assertEqual(client.log_anthropic(msg, "ideas"), 0.0)
