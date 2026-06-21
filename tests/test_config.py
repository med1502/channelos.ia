"""
Tests — config/niches.py
Covers: get_niche fallback, list_niches shape, required keys on every niche.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from channelos.config.niches import DEFAULT_NICHE, NICHES, get_niche, list_niches

REQUIRED_KEYS = {"name", "audience", "angles", "affiliates", "languages", "voices"}


class TestGetNiche(unittest.TestCase):
    def test_known_key_returns_correct_niche(self):
        niche = get_niche("ai_entrepreneurs")
        self.assertEqual(niche["name"], "AI Tools for Entrepreneurs")

    def test_unknown_key_falls_back_to_default(self):
        self.assertEqual(get_niche("does_not_exist"), NICHES[DEFAULT_NICHE])

    def test_all_niches_have_required_keys(self):
        for key, niche in NICHES.items():
            for field in REQUIRED_KEYS:
                self.assertIn(field, niche, f"'{key}' missing '{field}'")

    def test_en_niches_have_en_voice(self):
        for key, niche in NICHES.items():
            if "EN" in niche.get("languages", []):
                self.assertIn("EN", niche["voices"], f"'{key}' missing EN voice")

    def test_fr_niches_have_fr_voice(self):
        for key, niche in NICHES.items():
            if "FR" in niche.get("languages", []):
                self.assertIn("FR", niche["voices"], f"'{key}' missing FR voice")


class TestListNiches(unittest.TestCase):
    def test_returns_all_niches(self):
        self.assertEqual(len(list_niches()), len(NICHES))

    def test_each_entry_is_two_strings(self):
        for k, name in list_niches():
            self.assertIsInstance(k, str)
            self.assertIsInstance(name, str)

    def test_keys_match_niches_dict(self):
        self.assertEqual({k for k, _ in list_niches()}, set(NICHES.keys()))
