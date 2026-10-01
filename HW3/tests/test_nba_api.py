"""Unit tests for the ESPN data layer (nba_api.py).

Network calls are mocked; parsers run against small hand-built fixtures
shaped like real ESPN responses. No GUI.
"""

import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nba_api as api  # noqa: E402


def _competitor(abbr, score, home, name=None):
    return {
        "homeAway": "home" if home else "away",
        "score": score,
        "linescores": [{"value": 30}, {"value": 28}],
        "team": {
            "shortDisplayName": name or abbr,
            "displayName": f"Full {abbr}",
            "abbreviation": abbr,
            "color": "111111",
        },
        "records": [{"summary": "50-32"}],
    }


def _event(eid="1", state="post", detail="Final", day="2026-04-12T19:00:00Z",
           away_score=115, home_score=120):
    return {
        "id": eid,
        "name": "GS vs LAL",
        "date": day,
        "competitions": [{
            "venue": {"fullName": "V"},
            "status": {"type": {"state": state, "shortDetail": detail,
                                "detail": detail},
                       "displayClock": "0.0", "period": 4},
            "competitors": [
                _competitor("GS", away_score, False, "Warriors"),
                _competitor("LAL", home_score, True, "Lakers"),
            ],
        }],
    }


def _trend_game(gid, day, mine, theirs, won):
    ms, ts = (120, 110) if won else (100, 110)
    return {
        "id": gid, "date": day, "final": True,
        "home": {"abbr": mine, "score": ms, "has_score": True,
                 "full_name": "Los Angeles Lakers"},
        "away": {"abbr": theirs, "score": ts, "has_score": True,
                 "full_name": theirs},
    }


def _standings_row(abbr, wins, losses, conf="Eastern"):
    return {"conference": conf, "team": abbr, "abbr": abbr,
            "wins": wins, "losses": losses}


class TestParse(unittest.TestCase):
    def test_parse_event(self):
        g = api._parse_event(_event())
        self.assertEqual(g["id"], "1")
        self.assertTrue(g["final"])
        self.assertFalse(g["live"])
        self.assertEqual(g["away"]["abbr"], "GS")
        self.assertEqual(g["home"]["score"], 120)
        self.assertEqual(g["venue"], "V")

    def test_dict_form_score(self):
        # team/schedule endpoints wrap scores as {"value": ..}.
        ev = _event(away_score={"value": "115"})
        g = api._parse_event(ev)
        self.assertEqual(g["away"]["score"], 115)

    def test_pregame_has_no_score(self):
        ev = _event(state="pre", detail="7:00 PM",
                    away_score=0, home_score=0)
        ev["competitions"][0]["competitors"][0]["linescores"] = None
        ev["competitions"][0]["competitors"][1]["linescores"] = None
        g = api._parse_event(ev)
        self.assertFalse(g["final"])
        self.assertFalse(g["away"]["has_score"])
        self.assertFalse(g["home"]["has_score"])

    def test_favorites_of(self):
        g = api._parse_event(_event())
        favs = api.favorites_of(g, {"LAL"})
        self.assertEqual([s["abbr"] for s in favs], ["LAL"])
        self.assertEqual(api.favorites_of(g, {"BOS"}), [])

    def test_canon(self):
        self.assertEqual(api.canon("GSW"), "GS")
        self.assertEqual(api.canon("phx"), "PHX")
        self.assertEqual(api.canon("lal"), "LAL")

    def test_scoreboard_uses_dates_param(self):
        with mock.patch.object(api, "_get",
                               return_value={"events": [_event()]}) as m:
            games = api.scoreboard(date(2026, 4, 12))
            called_url, called_params = m.call_args[0]
            self.assertIn("scoreboard", called_url)
            self.assertEqual(called_params, {"dates": "20260412"})
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["home"]["abbr"], "LAL")


class TestTrend(unittest.TestCase):
    def test_record_and_margins(self):
        sched = [
            _trend_game("1", "2026-01-01", "LAL", "BOS", True),
            _trend_game("2", "2026-01-03", "LAL", "NY", False),
            _trend_game("3", "2026-01-05", "LAL", "MIA", True),
        ]
        with mock.patch.object(api, "team_schedule", return_value=sched):
            tr = api.season_trend("LAL", 2026)
        self.assertEqual(tr["record"], (2, 1))
        self.assertAlmostEqual(tr["pct"], 2 / 3)
        self.assertEqual([p["margin"] for p in tr["games"]], [10, -10, 10])
        self.assertEqual(tr["best_streak"], 1)

    def test_unknown_team_no_crash(self):
        with mock.patch.object(api, "team_schedule",
                               side_effect=api.NBAError("400")):
            tr = api.season_trend("ZZZ", 2026)
        self.assertEqual(tr["games"], [])
        self.assertEqual(tr["record"], (0, 0))

    def test_playoff_finished_season(self):
        rows = [_standings_row(f"E{i}", w, 82 - w)
                for i, w in enumerate([60, 55, 50, 45, 40, 35, 30, 25], 1)]
        with mock.patch.object(api, "standings", return_value=rows):
            pp = api.playoff_probability("E3", season=2000)
        self.assertTrue(pp["available"])
        self.assertTrue(pp["finished"])
        self.assertEqual(pp["seed"], 3)
        self.assertEqual(pp["probability"], 1.0)

    def test_playoff_unknown_team(self):
        with mock.patch.object(api, "standings", return_value=[]):
            pp = api.playoff_probability("ZZZ", season=2000)
        self.assertFalse(pp["available"])


class TestBoxscore(unittest.TestCase):
    STATS = ["38", "32", "12-20", "2-5", "6-7", "8", "9", "2",
             "1", "1", "2", "6", "3", "+5"]

    def _athlete(self, name, stats, starter=True):
        return {"athlete": {"displayName": name}, "stats": stats,
                "starter": starter, "ejected": False}

    def _summary(self):
        def side(abbr, players):
            return {
                "team": {"abbreviation": abbr, "displayName": abbr},
                "statistics": [{"labels": list(api.BOX_COLUMNS),
                                "athletes": players}],
            }
        star = self._athlete("Star Player", self.STATS)
        bench = self._athlete("Bench Player",
                              ["15", "8", "3-8", "0-2", "2-2", "3", "2", "1",
                               "0", "0", "1", "2", "2", "-3"])
        dnp = self._athlete("DNP Player", [])
        return {
            "boxscore": {
                "teams": [
                    {"team": {"abbreviation": "LAL"},
                     "statistics": [{"name": "points", "displayValue": "120"}]},
                    {"team": {"abbreviation": "GS"},
                     "statistics": [{"name": "points", "displayValue": "115"}]},
                ],
                "players": [side("LAL", [star, bench, dnp]),
                            side("GS", [star, bench])],
            },
            "header": {"competitions": [{
                "status": {"type": {"name": "STATUS_FINAL",
                                    "shortDetail": "Final",
                                    "detail": "LAL 120 - GS 115"}},
                "competitors": [
                    {"team": {"abbreviation": "LAL"}, "homeAway": "home"},
                    {"team": {"abbreviation": "GS"}, "homeAway": "away"}],
                "venue": {"fullName": "V"},
                "attendance": 18000,
            }]},
            "leaders": [],
        }

    def test_players_sorted_and_signed(self):
        with mock.patch.object(api, "_get", return_value=self._summary()):
            bx = api.boxscore("1")
        self.assertTrue(bx["available"])
        self.assertEqual(len(bx["teams"]), 2)
        lal = next(t for t in bx["teams"] if t["abbr"] == "LAL")
        self.assertTrue(lal["home"])
        # DNP (empty stats) skipped, sorted by points desc.
        self.assertEqual([p["name"] for p in lal["players"]],
                         ["Star Player", "Bench Player"])
        self.assertEqual(lal["players"][0]["plus_minus"], 5)
        self.assertEqual(lal["players"][1]["plus_minus"], -3)
        self.assertEqual(lal["totals"]["points"], "120")


class TestCache(unittest.TestCase):
    def test_put_get_clear(self):
        c = api.Cache(ttl=60)
        self.assertIsNone(c.get("k"))
        c.put("k", [1])
        self.assertEqual(c.get("k"), [1])
        c.clear()
        self.assertIsNone(c.get("k"))

    def test_drop_prefix(self):
        c = api.Cache(ttl=60)
        c.put("sb:20260412", 1)
        c.put("st:None", 2)
        c.drop_prefix("sb:")
        self.assertIsNone(c.get("sb:20260412"))
        self.assertEqual(c.get("st:None"), 2)


if __name__ == "__main__":
    unittest.main()
