"""
Tests — ScriptWriter
stdlib unittest only — no external dependencies.
"""
import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))


def _mock_msg(spoken: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps({
        "spoken_text": spoken,
        "caption": "Test caption for FounderAIHub",
        "hashtags": ["#AITools", "#Entrepreneur"],
        "screen_items": ["Tool A", "Tool B", "Tool C"],
    }))]
    msg.usage = MagicMock(input_tokens=500, output_tokens=200)
    return msg


BASE_IDEA = {
    "title": "Top 3 AI tools every founder needs",
    "hook": "90% of founders waste 10 hours a week on tasks AI can automate",
    "angle": "time savings",
    "format": "ranking",
    "list_items": ["Notion AI", "Claude", "Make.com"],
    "structure": ["hook", "list items", "CTA"],
    "affiliate_angle": "Start with Notion AI free — link in bio",
}


class TestWriteScript(unittest.TestCase):
    def _run(self, idea, spoken):
        import channelos.agents.script_agent as sa
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_msg(spoken)
        mock_anthropic = MagicMock(return_value=mock_client)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(sa, "Anthropic", mock_anthropic):
                return sa.write_script(idea, "EN")

    def test_word_count_within_limit(self):
        spoken = " ".join(["word"] * 65)
        script, _ = self._run(dict(BASE_IDEA), spoken)
        self.assertLessEqual(len(script["spoken_text"].split()), 70)

    def test_spoken_text_not_empty(self):
        spoken = "This AI tool saves founders hours every single week."
        script, _ = self._run(dict(BASE_IDEA), spoken)
        self.assertGreater(len(script["spoken_text"].strip()), 0)

    def test_required_keys_present(self):
        spoken = " ".join(["word"] * 60)
        script, msg = self._run(dict(BASE_IDEA), spoken)
        for key in ("spoken_text", "caption", "hashtags", "screen_items"):
            self.assertIn(key, script)
        self.assertIsNotNone(msg)

    def test_hashtags_is_list_of_strings(self):
        script, _ = self._run(dict(BASE_IDEA), " ".join(["word"] * 58))
        self.assertIsInstance(script["hashtags"], list)
        for h in script["hashtags"]:
            self.assertIsInstance(h, str)

    def test_versus_format(self):
        idea = {**BASE_IDEA, "format": "versus", "versus": {"a": "Claude", "b": "ChatGPT"}}
        script, _ = self._run(idea, " ".join(["word"] * 55))
        self.assertIn("spoken_text", script)

    def test_single_format(self):
        idea = {**BASE_IDEA, "format": "single"}
        script, _ = self._run(idea, " ".join(["word"] * 60))
        self.assertIn("spoken_text", script)

    def test_ranking_format(self):
        script, _ = self._run(dict(BASE_IDEA), " ".join(["word"] * 62))
        self.assertIn("spoken_text", script)


if __name__ == "__main__":
    unittest.main()