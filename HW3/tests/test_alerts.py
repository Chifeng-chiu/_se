"""Unit tests for the notification engine (alerts.py).

Pure logic, no network, no GUI. Run from HW3:

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alerts  # noqa: E402


def _side(abbr, score, has_score=True, home=False):
    return {"abbr": abbr, "score": score, "has_score": has_score, "home": home}


def _game(gid="1", live=False, final=False, date=None,
          away=("GS", 115), home=("LAL", 120), detail="Final", venue="V"):
    return {
        "id": gid,
        "date": date or "2026-04-12T19:00:00Z",
        "live": live,
        "final": final,
        "detail": detail,
        "venue": venue,
        "away": _side(away[0], away[1], has_score=(away[1] != 0), home=False),
        "home": _side(home[0], home[1], has_score=(home[1] != 0), home=True),
    }


def _soon_date(minutes=10):
    return (datetime.now().astimezone()
            + timedelta(minutes=minutes)).isoformat()


class TestDetect(unittest.TestCase):
    def test_tipoff_once(self):
        live = _game(live=True, detail="Q1 5:00")
        evs = alerts.detect([], [live], ["LAL"])
        self.assertEqual([e["kind"] for e in evs], ["tipoff"])
        # Same snapshot twice -> no repeat.
        self.assertEqual(alerts.detect([live], [live], ["LAL"]), [])

    def test_soon_only_on_first_sight(self):
        pre = _game(date=_soon_date(10))
        evs = alerts.detect([], [pre], ["LAL"])
        self.assertEqual([e["kind"] for e in evs], ["soon"])
        self.assertEqual(evs[0]["game_id"], "1")
        self.assertEqual(alerts.detect([pre], [pre], ["LAL"]), [])

    def test_result_win(self):
        pre = _game(final=False)
        fin = _game(final=True)
        evs = alerts.detect([pre], [fin], ["LAL"])
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["kind"], "result")
        self.assertTrue(evs[0]["body"].startswith("120 - 115"))

    def test_result_loss(self):
        pre = _game(final=False, away=("GS", 0), home=("LAL", 0))
        fin = _game(final=True, away=("GS", 130), home=("LAL", 110))
        evs = alerts.detect([pre], [fin], ["LAL"])
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["body"].startswith("110 - 130"))

    def test_both_favs_single_event(self):
        fin = _game(final=True)
        evs = alerts.detect([], [fin], ["LAL", "GS"])
        self.assertEqual(len(evs), 1)
        self.assertIn("LAL", evs[0]["title"])
        self.assertIn("GS", evs[0]["title"])

    def test_non_fav_ignored(self):
        fin = _game(final=True)
        self.assertEqual(alerts.detect([], [fin], ["BOS"]), [])

    def test_no_favorites_no_events(self):
        fin = _game(final=True)
        self.assertEqual(alerts.detect([], [fin], []), [])

    def test_tie_is_data_error(self):
        # NBA has no ties in overtime; equal scores mean a missing feed.
        pre = _game(final=False)
        tie = _game(final=True, away=("GS", 110), home=("LAL", 110))
        self.assertEqual(alerts.detect([pre], [tie], ["LAL"]), [])

    def test_missing_side_score(self):
        pre = _game(final=False)
        half = _game(final=True, away=("GS", 0), home=("LAL", 120))
        half["away"]["has_score"] = False
        self.assertEqual(alerts.detect([pre], [half], ["LAL"]), [])

    def test_empty_lists(self):
        self.assertEqual(alerts.detect([], [], ["LAL"]), [])

    def test_vanished_game_no_crash(self):
        pre = _game(final=False)
        self.assertEqual(alerts.detect([pre], [], ["LAL"]), [])

    def test_final_score_helper(self):
        fin = _game(final=True)
        self.assertEqual(alerts._final_score(fin, "LAL"), ("win", 120, 115))
        self.assertEqual(alerts._final_score(fin, "GS"), ("loss", 115, 120))
        self.assertIsNone(alerts._final_score(fin, "BOS"))


if __name__ == "__main__":
    unittest.main()
