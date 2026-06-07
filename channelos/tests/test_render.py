"""
Tests — VideoProducer (render pipeline)
stdlib unittest only — no external dependencies.
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))


def _j2v_mocks(video_url="https://cdn.json2video.com/test/video.mp4", duration=28.5):
    post = MagicMock()
    post.json.return_value = {"project": "proj_test"}
    post.raise_for_status = lambda: None

    get = MagicMock()
    get.json.return_value = {"movie": {"status": "done", "url": video_url, "duration": duration}}
    get.raise_for_status = lambda: None
    return post, get


class TestRenderVideo(unittest.TestCase):
    def setUp(self):
        os.environ["JSON2VIDEO_API_KEY"] = "test-key"

    def _render(self, **kwargs):
        post, get = _j2v_mocks()
        with patch("channelos.pipeline.render.requests.post", return_value=post), \
             patch("channelos.pipeline.render.requests.get", return_value=get), \
             patch("channelos.pipeline.render.time.sleep"):
            from channelos.pipeline import render
            return render.render_video(**kwargs)

    def test_returns_valid_url(self):
        url, _ = self._render(spoken_text="This AI tool saves 10h per week.", broll_url="")
        self.assertTrue(url.startswith("https://"))

    def test_returns_duration_float(self):
        _, duration = self._render(spoken_text="Short text.", broll_url="")
        self.assertIsInstance(duration, (int, float))
        self.assertGreaterEqual(duration, 0)

    def test_raises_on_render_error(self):
        post = MagicMock()
        post.json.return_value = {"project": "proj_err"}
        post.raise_for_status = lambda: None

        get = MagicMock()
        get.json.return_value = {"movie": {"status": "error", "message": "codec fail"}}
        get.raise_for_status = lambda: None

        with patch("channelos.pipeline.render.requests.post", return_value=post), \
             patch("channelos.pipeline.render.requests.get", return_value=get), \
             patch("channelos.pipeline.render.time.sleep"):
            from channelos.pipeline.render import render_video
            with self.assertRaises(RuntimeError):
                render_video(spoken_text="Test.", broll_url="")

    def test_ranking_format_produces_multi_scene_spec(self):
        captured = {}
        post = MagicMock()
        post.raise_for_status = lambda: None

        def capture(url, headers, json, timeout=None):
            captured.update(json)
            post.json.return_value = {"project": "proj_rank"}
            return post

        get = MagicMock()
        get.json.return_value = {"movie": {"status": "done", "url": "https://x.com/v.mp4", "duration": 30}}
        get.raise_for_status = lambda: None

        with patch("channelos.pipeline.render.requests.post", side_effect=capture), \
             patch("channelos.pipeline.render.requests.get", return_value=get), \
             patch("channelos.pipeline.render.time.sleep"):
            from channelos.pipeline.render import render_video
            render_video(
                spoken_text="One tool. Two tool. Three tool best.",
                broll_url="https://x.com/c1.mp4",
                broll_clips=["https://x.com/c1.mp4", "https://x.com/c2.mp4", "https://x.com/c3.mp4"],
                screen_items=["Tool One", "Tool Two", "Tool Three"],
                fmt="ranking",
            )
        # intro (1) + 3 content scenes = 4 minimum
        self.assertGreaterEqual(len(captured.get("scenes", [])), 3)


class TestFetchBrollMulti(unittest.TestCase):
    def test_returns_n_clips(self):
        def mock_search(query, count):
            return [f"https://p.com/{query.replace(' ','_')}_{i}.mp4" for i in range(count)]

        with patch("channelos.pipeline.render._pexels_search", side_effect=mock_search):
            from channelos.pipeline.render import fetch_broll_multi
            clips = fetch_broll_multi(["q1", "q2", "q3"], "fallback", n=3)
        self.assertEqual(len(clips), 3)

    def test_no_duplicate_clips(self):
        fixed = "https://p.com/same.mp4"
        with patch("channelos.pipeline.render._pexels_search", return_value=[fixed]):
            from channelos.pipeline.render import fetch_broll_multi
            clips = fetch_broll_multi(["q1", "q2", "q3"], "fallback", n=3)
        self.assertEqual(len(clips), len(set(clips)))

    def test_falls_back_to_general_query(self):
        counter = {"n": 0}
        def mock_search(query, count):
            counter["n"] += 1
            if "specific" in query:
                return []
            return [f"https://p.com/fallback_{counter['n']}_{i}.mp4" for i in range(count)]

        with patch("channelos.pipeline.render._pexels_search", side_effect=mock_search):
            from channelos.pipeline.render import fetch_broll_multi
            clips = fetch_broll_multi(["specific q1", "specific q2"], "AI productivity", n=2)
        self.assertEqual(len(clips), 2)


class TestRankOverlay(unittest.TestCase):
    def test_color_is_cyan(self):
        from channelos.pipeline.render import _rank_overlay
        self.assertEqual(_rank_overlay(3)["settings"]["color"], "#00E5FF")

    def test_text_matches_number(self):
        from channelos.pipeline.render import _rank_overlay
        for n in range(1, 6):
            self.assertEqual(_rank_overlay(n)["text"], str(n))

    def test_type_is_text(self):
        from channelos.pipeline.render import _rank_overlay
        self.assertEqual(_rank_overlay(1)["type"], "text")


if __name__ == "__main__":
    unittest.main()