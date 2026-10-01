"""Offline demo launcher: zero changes to the app itself.

Replaces nba_api._get with a reader of demo_data/ snapshots, then starts
the real main window and auto-plays one finished game (score cards +
boxscore + result notification). Fully offline after recording.

Run inside HW3:

    python demo_offline.py

Re-record snapshots with:  python record_demo.py
"""

import copy
import json
import urllib.parse
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "demo_data"


def _load_store() -> dict:
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    store = {}
    for url, name in index.items():
        store[url] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return store


STORE = _load_store()
META = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))

import nba_api as api  # noqa: E402  (patched before main imports it)


def _offline_get(url: str, params: dict | None = None, **_kw):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    if url in STORE:
        return copy.deepcopy(STORE[url])
    # Core API (player cards) has no snapshots; report offline honestly.
    if "sports.core.api.espn.com" in url:
        raise api.NBAError("offline demo: player data needs network")
    raise api.NBAError("offline demo: no snapshot for this request")


api._get = _offline_get

import main as m  # noqa: E402


def _play_demo(app: "m.App") -> None:
    """Jump to the recorded game day, render cards, fire the result
    notification once, and open the boxscore -- same calls the UI uses."""
    day = date.fromisoformat(META["demo_day"])
    app.day = day
    games = api.scoreboard(day)
    app._render_scores(games, day, check_alerts=True)
    game = next((g for g in games if g["id"] == META["demo_event_id"]), None)
    if game is None:
        game = next((g for g in games if g.get("final")), games[0])
    app._open_boxscore(game)
    app._set_status(f"offline demo · {day.isoformat()} · "
                    f"{len(games)} games (no network)")


def _boot() -> None:
    # Same 7 lines as main.main(), plus the auto demo cue.
    m._enable_dpi_awareness()
    cfg = m.settings.load()
    app = m.App()
    app._fill_favorites()
    if cfg["mini_widget"]:
        app._toggle_widget()
    if cfg["start_minimized"]:
        app.withdraw()
    app.after(800, lambda: _play_demo(app))
    app.mainloop()


if __name__ == "__main__":
    _boot()
