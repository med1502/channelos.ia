"""
Tests — TrendResearchAgent
stdlib unittest only — no external dependencies.
"""
import json
import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))


class TestFilterBrandSafety(unittest.TestCase):
    def _safe(self):
        return {
            "title": "Top 5 AI tools for entrepreneurs in 2024",
            "hook": "This AI tool saves solo founders 10 hours per week",
            "angle": "time savings",
            "affiliate_angle": "Try Notion AI — link in bio",
            "brand_safe": True, "viral_score": 80,
        }

    def _risky(self):
        return {
            "title": "How to hack your productivity with AI scam tools",
            "hook": "Get rich quick with AI in 2024",
            "angle": "money",
            "affiliate_angle": "100x guaranteed profit",
            "brand_safe": True, "viral_score": 90,
        }

    def test_safe_idea_passes(self):
        from channelos.agents.trend_agent import filter_brand_safety
        safe, flagged = filter_brand_safety([self._safe()])
        self.assertEqual(len(safe), 1)
        self.assertEqual(len(flagged), 0)

    def test_risky_idea_flagged_by_code_filter(self):
        from channelos.agents.trend_agent import filter_brand_safety
        safe, flagged = filter_brand_safety([self._risky()])
        self.assertEqual(len(safe), 0)
        self.assertEqual(len(flagged), 1)
        self.assertFalse(flagged[0]["brand_safe"])

    def test_pre_flagged_rejected(self):
        idea = self._safe()
        idea["brand_safe"] = False
        from channelos.agents.trend_agent import filter_brand_safety
        safe, _ = filter_brand_safety([idea])
        self.assertEqual(len(safe), 0)

    def test_mixed_list_preserves_safe(self):
        from channelos.agents.trend_agent import filter_brand_safety
        safe, flagged = filter_brand_safety([self._safe(), self._risky()])
        self.assertGreaterEqual(len(safe), 1)
        self.assertGreaterEqual(len(flagged), 1)


class TestSearchTrends(unittest.TestCase):
    def test_returns_empty_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "TAVILY_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import channelos.agents.trend_agent as ta
            results = ta.search_trends("AI tools no key")
        self.assertEqual(results, [])

    def test_returns_list_on_success(self):
        fake = [{"title": "AI news", "url": "https://x.com", "content": "test content"}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": fake}
        mock_resp.raise_for_status = lambda: None

        with tempfile.TemporaryDirectory() as tmp:
            orig = os.getcwd()
            os.chdir(tmp)
            try:
                with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
                    import channelos.agents.trend_agent as ta
                    with patch.object(ta.requests, "post", return_value=mock_resp):
                        results = ta.search_trends("AI tools entrepreneurs unique123")
            finally:
                os.chdir(orig)
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)

    def test_uses_cache_on_second_call(self):
        fake = [{"title": "Cached", "url": "https://x.com", "content": "ok"}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": fake}
        mock_resp.raise_for_status = lambda: None

        with tempfile.TemporaryDirectory() as tmp:
            orig = os.getcwd()
            os.chdir(tmp)
            try:
                with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
                    import channelos.agents.trend_agent as ta
                    with patch.object(ta.requests, "post", return_value=mock_resp) as mock_post:
                        ta.search_trends("cache test query unique xyz999")
                        ta.search_trends("cache test query unique xyz999")
                    # 3 POST calls on first call, 0 on second (cache hit)
                    self.assertEqual(mock_post.call_count, 3)
            finally:
                os.chdir(orig)


class TestGenerateIdeas(unittest.TestCase):
    def test_returns_ideas_sorted_by_score(self):
        fake_ideas = [
            {"title": "Top 3 AI tools", "hook": "AI saves hours",
             "angle": "time", "viral_score": 70, "format": "ranking",
             "list_items": ["A", "B", "C"], "structure": [],
             "broll_query": "AI", "affiliate_angle": "Notion",
             "based_on_trend": "AI growth", "brand_safe": True, "score_reason": "ok"},
            {"title": "Claude vs ChatGPT", "hook": "Which wins?",
             "angle": "comparison", "viral_score": 85, "format": "versus",
             "versus": {"a": "Claude", "b": "ChatGPT"}, "structure": [],
             "broll_query": "AI", "affiliate_angle": "Claude",
             "based_on_trend": "AI models", "brand_safe": True, "score_reason": "ok"},
        ]
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(fake_ideas))]

        import channelos.agents.trend_agent as ta
        mock_anthropic = MagicMock()
        mock_anthropic.return_value.messages.create.return_value = mock_msg

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(ta, "Anthropic", mock_anthropic):
                niche = {"name": "AI Tools", "audience": "Founders",
                         "angles": ["time"], "affiliates": ["Notion"]}
                ideas = ta.generate_ideas("AI tools", "EN", [], 2, niche, None)

        self.assertEqual(len(ideas), 2)
        self.assertGreaterEqual(ideas[0]["viral_score"], ideas[1]["viral_score"])


if __name__ == "__main__":
    unittest.main()
