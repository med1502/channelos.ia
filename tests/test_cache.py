"""
Tests — utils/cache.py
Covers: cache_key, cache_get, cache_set — TTL, namespace isolation, corruption.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from channelos.utils.cache import cache_get, cache_key, cache_set


class TestCacheKey(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(cache_key("hello"), cache_key("hello"))

    def test_different_inputs_differ(self):
        self.assertNotEqual(cache_key("a"), cache_key("b"))

    def test_returns_32_char_hex(self):
        k = cache_key("test")
        self.assertEqual(len(k), 32)
        int(k, 16)  # raises if not valid hex


class TestCacheGetSet(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _patch(self):
        return patch("channelos.utils.cache.CACHE_DIR", self._dir)

    def test_miss_on_empty_dir(self):
        with self._patch():
            self.assertIsNone(cache_get("nonexistent"))

    def test_roundtrip_dict(self):
        with self._patch():
            cache_set("k1", {"data": [1, 2, 3]})
            self.assertEqual(cache_get("k1"), {"data": [1, 2, 3]})

    def test_roundtrip_list(self):
        with self._patch():
            cache_set("k2", ["a", "b", "c"])
            self.assertEqual(cache_get("k2"), ["a", "b", "c"])

    def test_namespace_isolation(self):
        with self._patch():
            cache_set("k", {"ns": "a"}, namespace="ns_a")
            cache_set("k", {"ns": "b"}, namespace="ns_b")
            self.assertEqual(cache_get("k", namespace="ns_a"), {"ns": "a"})
            self.assertEqual(cache_get("k", namespace="ns_b"), {"ns": "b"})

    def test_expired_entry_returns_none(self):
        path = self._dir / "generic_stale.json"
        path.write_text(json.dumps({
            "expires_at": (datetime.now() - timedelta(hours=1)).isoformat(),
            "payload": {"stale": True},
        }), encoding="utf-8")
        with self._patch():
            self.assertIsNone(cache_get("stale"))

    def test_expired_file_is_deleted(self):
        path = self._dir / "generic_old.json"
        path.write_text(json.dumps({
            "expires_at": (datetime.now() - timedelta(hours=1)).isoformat(),
            "payload": {},
        }), encoding="utf-8")
        with self._patch():
            cache_get("old")
        self.assertFalse(path.exists())

    def test_corrupted_file_returns_none(self):
        (self._dir / "generic_bad.json").write_text("not-json", encoding="utf-8")
        with self._patch():
            self.assertIsNone(cache_get("bad"))
