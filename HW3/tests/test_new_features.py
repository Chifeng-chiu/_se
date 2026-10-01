"""Unit tests for sorting helper, player stats and plays parsing.

No network (all endpoints mocked), no GUI (no Tk objects created).
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as m  # noqa: E402  (import only; creates no windows)
import nba_api as api  # noqa: E402


class TestSortNum(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(m._sort_num("32"), 32.0)
        self.assertEqual(m._sort_num("+5"), 5.0)
        self.assertEqual(m._sort_num(".625"), 0.625)

    def test_made_of_attempts(self):
        self.assertEqual(m._sort_num("12-20"), 12.0)

    def test_minutes(self):
        self.assertAlmostEqual(m._sort_num("12:34"), 12 + 34 / 60)

    def test_missing_sinks(self):
        self.assertEqual(m._sort_num("-"), float("-inf"))
        self.assertEqual(m._sort_num(""), float("-inf"))
        self.assertEqual(m._sort_num("W3"), float("-inf"))

    def test_diff(self):
        self.assertEqual(m._sort_num("120-115", diff=True), 5)
        self.assertEqual(m._sort_num("100-110", diff=True), -10)
        # FG-style values are NOT diffs unless asked.
        self.assertEqual(m._sort_num("12-20"), 12.0)


def _stats_fixture(names_values):
    cats = [{"displayName": "General",
             "stats": [{"name": n, "displayValue": v}
                       for n, v in names_values]}]
    return {"splits": {"categories": cats}}


class TestPlayerStats(unittest.TestCase):
    FIX = [("gamesPlayed", "41"), ("avgMinutes", "8.9"),
           ("avgPoints", "2.9"), ("avgRebounds", "0.5"),
           ("avgAssists", "1.2"), ("avgSteals", "0.5"),
           ("avgBlocks", "0.1"), ("avgTurnovers", "0.6"),
           ("avgFieldGoalsMade", "1.1"), ("avgFieldGoalsAttempted", "2.7"),
           ("avgThreePointFieldGoalsMade", "0.5"),
           ("avgThreePointFieldGoalsAttempted", "1.4"),
           ("avgFreeThrowsMade", "0.1"), ("avgFreeThrowsAttempted", "0.2")]

    def test_averages_and_pct(self):
        with mock.patch.object(api, "_core_get",
                               return_value=_stats_fixture(self.FIX)):
            out = api.player_season_stats("4683774", 2026)
        self.assertEqual(out["season"], 2026)
        vals = dict(out["rows"])
        self.assertEqual(vals["GP"], "41")
        self.assertEqual(vals["PTS"], "2.9")
        self.assertEqual(vals["FGP"], f"{1.1 / 2.7 * 100:.1f}%")
        self.assertEqual(vals["TPP"], f"{0.5 / 1.4 * 100:.1f}%")
        self.assertEqual(vals["FTP"], f"{0.1 / 0.2 * 100:.1f}%")

    def test_failure_gives_empty(self):
        with mock.patch.object(api, "_core_get",
                               side_effect=api.NBAError("down")):
            out = api.player_season_stats("1", 2026)
        self.assertEqual(out["rows"], [])

    def test_zero_attempts_no_crash(self):
        fix = [("avgFieldGoalsMade", "0"), ("avgFieldGoalsAttempted", "0")]
        with mock.patch.object(api, "_core_get",
                               return_value=_stats_fixture(fix)):
            out = api.player_season_stats("1", 2026)
        self.assertNotIn("FGP", dict(out["rows"]))


class TestPlays(unittest.TestCase):
    def _summary(self):
        return {
            "boxscore": {"teams": [], "players": []},
            "header": {"competitions": [{
                "status": {"type": {"name": "STATUS_FINAL",
                                    "shortDetail": "Final", "detail": "d"}},
                "competitors": [],
                "venue": {"fullName": "V"}}]},
            "leaders": [],
            "plays": [
                {"period": {"number": 1, "displayValue": "1st"},
                 "clock": {"displayValue": "12:00"},
                 "text": "Jump Ball", "scoringPlay": False,
                 "awayScore": 0, "homeScore": 0},
                {"period": {"number": 4, "displayValue": "4th"},
                 "clock": {"displayValue": "0.0"},
                 "text": "Three pointer", "scoringPlay": True,
                 "awayScore": 108, "homeScore": 113},
            ],
        }

    def test_plays_parsed(self):
        with mock.patch.object(api, "_get", return_value=self._summary()):
            bx = api.boxscore("1")
        self.assertEqual(len(bx["plays"]), 2)
        self.assertFalse(bx["plays"][0]["scoring"])
        self.assertTrue(bx["plays"][1]["scoring"])
        self.assertEqual(bx["plays"][1]["home"], 113)
        self.assertEqual(bx["plays"][1]["period"], 4)


class TestStandingsFilter(unittest.TestCase):
    ROWS = [
        {"conference": "Eastern Conference", "team": "A", "abbr": "A",
         "wins": 50, "losses": 32},
        {"conference": "Eastern Conference", "team": "B", "abbr": "B",
         "wins": 60, "losses": 22},
        {"conference": "Western Conference", "team": "C", "abbr": "C",
         "wins": 55, "losses": 27},
    ]

    def test_all_sorted_by_record(self):
        out = m.App._filter_standings(self.ROWS, "all")
        self.assertEqual([r["abbr"] for r in out], ["B", "C", "A"])

    def test_east_only(self):
        out = m.App._filter_standings(self.ROWS, "E")
        self.assertEqual([r["abbr"] for r in out], ["B", "A"])

    def test_west_only(self):
        out = m.App._filter_standings(self.ROWS, "W")
        self.assertEqual([r["abbr"] for r in out], ["C"])

    def test_unknown_scope_falls_back_to_all(self):
        out = m.App._filter_standings(self.ROWS, "??")
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
