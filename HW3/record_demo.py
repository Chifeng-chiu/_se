"""Record ESPN API snapshots into demo_data/ for the offline demo.

Run inside HW3 (needs network once):

    python record_demo.py

What it does:
  1. Wraps nba_api._get so every response is saved to demo_data/<sha1>.json,
     with demo_data/index.json mapping request URL -> file.
  2. Replays the exact requests the app makes during a demo:
     teams, standings, rosters, team schedules, one finished game day,
     that game's boxscore summary, and the coming week's scoreboards.
  3. Writes demo_data/meta.json (demo day + demo event id).

The app itself is untouched. Re-run this script to refresh snapshots
(e.g. at the start of a new season).
"""

import hashlib
import json
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import nba_api as api

HERE = Path(__file__).resolve().parent
DATA = HERE / "demo_data"

FAV_TEAMS = ("LAL", "GS")


def _season_year() -> int:
    """Same rule as App.season_year: ESPN season year is the starting year."""
    today = date.today()
    return today.year + 1 if today.month >= 7 else today.year


def main() -> None:
    DATA.mkdir(exist_ok=True)
    index: dict = {}

    def save(full_url: str, payload) -> None:
        name = hashlib.sha1(full_url.encode("utf-8")).hexdigest()[:16] + ".json"
        (DATA / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        index[full_url] = name

    orig = api._get

    def spy(url: str, params: dict | None = None):
        payload = orig(url, params)
        full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        save(full, payload)
        return payload

    api._get = spy
    try:
        season = _season_year() - 1  # last fully finished season
        api.teams()
        api.standings(None)
        api.standings(season)
        for abbr in FAV_TEAMS:
            api.roster(abbr)
            api.team_schedule(abbr, None)
            api.team_schedule(abbr, season)

        # Same logic as App._finish_demo: last finished game of the fav team.
        prev = api.team_schedule(FAV_TEAMS[0], season)
        finals = [g for g in prev if g.get("final")]
        if not finals:
            raise SystemExit("no finished games found for demo")
        last = finals[-1]
        # Scoreboard dates are US Eastern: resolve which board lists the game
        # (same rule as App._demo_payload).
        utc_day = date.fromisoformat((last.get("date") or "")[:10])
        demo_day = None
        games = []
        for cand in (utc_day, utc_day - timedelta(days=1)):
            cand_games = api.scoreboard(cand)
            if any(g["id"] == last["id"] for g in cand_games):
                demo_day, games = cand.isoformat(), cand_games
                break
        if demo_day is None:
            raise SystemExit("demo game not found on any scoreboard")
        same_day = [g for g in games if g.get("final")]
        demo_event = same_day[0]["id"]
        api.boxscore(demo_event)

        # Coming week, so the schedule tab also works offline.
        today = date.today()
        api.scoreboard(today)
        for i in range(1, 8):
            try:
                api.scoreboard(today + timedelta(days=i))
            except api.NBAError:
                pass
    finally:
        api._get = orig

    (DATA / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = {
        "demo_day": demo_day,
        "demo_event_id": str(demo_event),
        "demo_abbr": FAV_TEAMS[0],
        "season": season,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requests": len(index),
    }
    (DATA / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(p.stat().st_size for p in DATA.glob("*.json"))
    print(f"recorded {len(index)} requests -> {DATA} ({total / 1024:.0f} KB)")
    print(f"demo_day={demo_day} demo_event={demo_event} season={season}")


if __name__ == "__main__":
    main()
