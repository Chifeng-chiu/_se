"""Unit tests for settings persistence (settings.py).

SETTINGS_FILE/STATE_FILE are patched to a temp dir so the real
settings.json is never touched. No network, no GUI.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settings  # noqa: E402


class TestSettings(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp.name, "settings.json")
        self.state_path = os.path.join(self.tmp.name, "state.json")
        self._p1 = mock.patch.object(settings, "SETTINGS_FILE",
                                     Path(self.cfg_path))
        self._p2 = mock.patch.object(settings, "STATE_FILE",
                                     Path(self.state_path))
        self._p1.start()
        self._p2.start()

    def tearDown(self):
        self._p1.stop()
        self._p2.stop()
        self.tmp.cleanup()

    def test_defaults_when_missing(self):
        cfg = settings.load()
        self.assertEqual(cfg["favorites"], ["GS", "LAL"])
        self.assertEqual(cfg["refresh_seconds"], 60)
        self.assertEqual(cfg["preview_days"], 7)

    def test_alias_and_dedupe(self):
        saved = settings.save({"favorites": ["GSW", "lal", "  ", "GS"]})
        self.assertEqual(saved["favorites"], ["GS", "LAL"])
        self.assertEqual(settings.load()["favorites"], ["GS", "LAL"])

    def test_blank_favorites(self):
        out = settings._normalize({"favorites": ["  ", ""]})
        self.assertEqual(out["favorites"], [])

    def test_favorites_capped(self):
        many = [f"T{i:02d}" for i in range(40)]
        out = settings._normalize({"favorites": many})
        self.assertEqual(len(out["favorites"]), 30)

    def test_refresh_bounds(self):
        self.assertEqual(
            settings._normalize({"refresh_seconds": 0})["refresh_seconds"], 15)
        self.assertEqual(
            settings._normalize({"refresh_seconds": 9999})["refresh_seconds"], 600)
        self.assertEqual(
            settings._normalize({"refresh_seconds": None})["refresh_seconds"], 60)
        self.assertEqual(
            settings._normalize({"preview_days": -5})["preview_days"], 1)

    def test_unknown_keys_dropped(self):
        out = settings._normalize({"hacker": 1})
        self.assertNotIn("hacker", out)

    def test_corrupt_file_falls_back(self):
        with open(self.cfg_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        cfg = settings.load()
        self.assertEqual(cfg["refresh_seconds"], 60)

    def test_state_roundtrip(self):
        settings.save_state({"games": {"abc": "post"}})
        self.assertEqual(settings.load_state(), {"games": {"abc": "post"}})

    def test_save_is_valid_json(self):
        settings.save({"favorites": ["BOS"]})
        with open(self.cfg_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["favorites"], ["BOS"])


if __name__ == "__main__":
    unittest.main()
