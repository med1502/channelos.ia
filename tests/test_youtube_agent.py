"""
Tests — agents/youtube_agent.py
Covers: graceful degradation without API key, cache hit, API response parsing.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from channelos.agents.youtube_agent import _recent_iso, get_youtube_insights


class TestRecentIso(unittest.TestCase):
    def test_parses_as_datetime(self):
        datetime.strptime(_recent_iso(days=90), "%Y-%m-%dT%H:%M:%SZ")

    def test_is_in_the_past(self):
        dt = datetime.strptime(_recent_iso(days=1), "%Y-%m-%dT%H:%M:%SZ")
        self.assertLess(dt, datetime.utcnow())


class TestGetYoutubeInsights(unittest.TestCase):
    def test_returns_none_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(get_youtube_insights("AI tools"))

    def test_returns_cached_result(self):
        cached = {"title_patterns": [], "power_words": [], "_sample_count": 5}
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "key"}), \
             patch("channelos.agents.youtube_agent._cache_get", return_value=cached):
            result = get_youtube_insights("AI tools")
        self.assertEqual(result, cached)

    def test_extracts_insights_from_api_response(self):
        search_resp = {"items": [{"id": {"videoId": "abc123"}}]}
        stats_resp = {"items": [{
            "snippet": {"title": "5 Best AI Tools for Entrepreneurs"},
            "contentDetails": {"duration": "PT1M30S"},
            "statistics": {},
        }]}

        search_list = MagicMock()
        search_list.execute.return_value = search_resp
        videos_list = MagicMock()
        videos_list.execute.return_value = stats_resp

        yt = MagicMock()
        yt.search.return_value.list.return_value = search_list
        yt.videos.return_value.list.return_value = videos_list

        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "key"}), \
             patch("channelos.agents.youtube_agent._cache_get", return_value=None), \
             patch("channelos.agents.youtube_agent._cache_set"), \
             patch("googleapiclient.discovery.build", return_value=yt):
            result = get_youtube_insights("AI tools")

        self.assertIsNotNone(result)
        self.assertIn("title_patterns", result)
        self.assertIn("power_words", result)
        self.assertEqual(result["_sample_count"], 1)

    def test_returns_none_on_empty_search_results(self):
        search_list = MagicMock()
        search_list.execute.return_value = {"items": []}

        yt = MagicMock()
        yt.search.return_value.list.return_value = search_list

        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "key"}), \
             patch("channelos.agents.youtube_agent._cache_get", return_value=None), \
             patch("googleapiclient.discovery.build", return_value=yt):
            result = get_youtube_insights("AI tools")

        self.assertIsNone(result)

    def test_returns_none_on_api_exception(self):
        yt = MagicMock()
        yt.search.return_value.list.return_value.execute.side_effect = Exception("quota")

        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "key"}), \
             patch("channelos.agents.youtube_agent._cache_get", return_value=None), \
             patch("googleapiclient.discovery.build", return_value=yt):
            result = get_youtube_insights("AI tools")

        self.assertIsNone(result)
