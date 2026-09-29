"""ESPN NBA 公開 API 資料層：賽程比分、戰績榜、球隊資訊。"""

import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://site.api.espn.com/apis"
NBA = f"{BASE}/site/v2/sports/basketball/nba"
API_VERSION2 = f"{BASE}/v2/sports/basketball/nba"

# ESPN 的 WAF 會擋掉自訂 User-Agent，沿用 urllib 預設最穩。
USER_AGENT = None

TIMEOUT = 20


class NBAError(Exception):
    pass


def _get(url: str, params: dict | None = None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}
                                 if USER_AGENT else {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise NBAError(f"伺服器回應 {exc.code}") from exc
    except Exception as exc:
        raise NBAError(f"連線失敗：{exc}") from exc


def _as_int(value) -> int:
    """score 在 scoreboard 是 int，在 team/schedule 卻是 {'value':..} 兩種都收。"""
    if isinstance(value, dict):
        value = value.get("value")
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _competitor(comp: dict) -> dict:
    team = comp["team"]
    raw_score = _as_int(comp.get("score"))
    lines = [_as_int(line.get("value")) for line in (comp.get("linescores") or [])]
    lines = [v for v in lines if v]
    # 未開賽時 ESPN 給 score="0" 而 linescores=None，
    # 只看 score is not None 會把 0-0 誤判成已有比分。
    has_score = raw_score != 0 or bool(lines)
    return {
        "name": team.get("shortDisplayName") or team.get("displayName"),
        "full_name": team.get("displayName"),
        "abbr": team.get("abbreviation"),
        "score": raw_score or sum(lines),
        "has_score": has_score,
        "wins": comp.get("records", [{}])[0].get("summary", "") if comp.get("records") else "",
        "color": team.get("color") or "444444",
        "home": comp.get("homeAway") == "home",
    }


def _parse_event(event: dict) -> dict:
    comps = event["competitions"][0]
    home = next(c for c in comps["competitors"] if c["homeAway"] == "home")
    away = next(c for c in comps["competitors"] if c["homeAway"] == "away")
    status = comps["status"]
    state = status["type"]["state"]
    return {
        "id": event["id"],
        "name": event.get("name", ""),
        "date": event.get("date"),
        "state": state,
        "detail": status["type"].get("shortDetail") or status["type"].get("detail", ""),
        "clock": status.get("displayClock"),
        "period": status.get("period"),
        "away": _competitor(away),
        "home": _competitor(home),
        "venue": comps.get("venue", {}).get("fullName", ""),
        "final": state == "post",
        "live": state == "in",
    }


def favorites_of(game: dict, favs) -> list[dict]:
    """這場比賽裡屬於關注清單的球隊資料。"""
    return [s for s in (game["away"], game["home"]) if s["abbr"] in favs]



def scoreboard(day: date | None = None) -> list[dict]:
    """指定日期（預設今天）的所有比賽。"""
    params = {}
    if day is not None:
        params["dates"] = day.strftime("%Y%m%d")
    data = _get(f"{NBA}/scoreboard", params)
    return [_parse_event(e) for e in data.get("events", [])]


def standings(season: int | None = None) -> list[dict]:
    """回傳兩大分區戰績，每筆含隊伍與勝負場資料。"""
    data = _get(f"{API_VERSION2}/standings", {"season": season} if season else None)
    out = []
    for conf in data.get("children", []):
        for entry in conf["standings"]["entries"]:
            stats = {s["name"]: s for s in entry.get("stats", [])}

            def val(name, default="-"):
                return stats.get(name, {}).get("displayValue", default)

            overall = stats.get("overall", {}).get("summary", "-")
            out.append(
                {
                    "conference": conf["name"],
                    "team": entry["team"].get("shortDisplayName")
                    or entry["team"].get("displayName"),
                    "abbr": entry["team"].get("abbreviation"),
                    "wins": int(val("wins", 0) or 0),
                    "losses": int(val("losses", 0) or 0),
                    "pct": val("winPercent"),
                    "gb": val("gamesBehind"),
                    "streak": val("streak"),
                    "home": stats.get("home", {}).get("displayValue", "-"),
                    "road": stats.get("road", {}).get("displayValue", "-"),
                    "diff": val("differential"),
                    "ppg": val("avgPointsFor"),
                    "appa": val("avgPointsAgainst"),
                    "overall": overall,
                    "color": entry["team"].get("color") or "444444",
                }
            )
    return out


def team_standings(abbr: str, season: int | None = None) -> dict | None:
    for row in standings(season):
        if row["abbr"] == abbr:
            return row
    return None


# ESPN 自己對勇士用 "GS"，但很多人習慣寫 "GSW"。
# 統一在這裡正規化，之後所有比較都只會看到 ESPN 的寫法。
ABBR_ALIASES = {
    "GSW": "GS",
    "GSV": "GS",
    "WAS": "WSH",
    "UTH": "UTAH",
    "PHO": "PHX",
    "NOP": "NO",
    "NOR": "NO",
    "UTA": "UTAH",
}


def canon(abbr: str) -> str:
    key = str(abbr or "").strip().upper()
    return ABBR_ALIASES.get(key, key)


_teams_cache: dict | None = None


def teams(force: bool = False) -> list[dict]:
    """30 隊基本資料（含 ESPN 的 team id），結果常駐記憶體。"""
    global _teams_cache
    if _teams_cache is not None and not force:
        return _teams_cache
    data = _get(f"{NBA}/teams")
    out = []
    for entry in data["sports"][0]["leagues"][0]["teams"]:
        t = entry["team"]
        out.append(
            {
                "id": t["id"],
                "abbr": t.get("abbreviation"),
                "name": t.get("shortDisplayName") or t.get("displayName"),
                "full_name": t.get("displayName"),
                "city": t.get("location"),
                "color": t.get("color") or "444444",
                "record": (entry.get("record") or {}).get("summary", ""),
            }
        )
    out.sort(key=lambda x: x["full_name"] or "")
    _teams_cache = out
    return out


def team_by_abbr(abbr: str) -> dict | None:
    target = canon(abbr)
    return next((t for t in teams() if t["abbr"] == target), None)


def roster(abbr: str) -> dict:
    """單隊陣容（球員 + 主教練）。"""
    data = _get(f"{NBA}/teams/{abbr.lower()}/roster")
    players = []
    for a in data.get("athletes", []):
        status = (a.get("status") or {})
        status = status.get("type") if isinstance(status, dict) else str(status)
        college = a.get("college")
        college = college.get("displayName", "") if isinstance(college, dict) else (college or "")
        players.append(
            {
                "id": a.get("id"),
                "name": a.get("displayName"),
                "short": a.get("shortName"),
                "jersey": a.get("jersey", ""),
                "position": (a.get("position") or {}).get("abbreviation", ""),
                "height": a.get("displayHeight", ""),
                "weight": a.get("displayWeight", ""),
                "age": a.get("age", ""),
                "college": college,
                "injured": status not in ("active", ""),
                "headshot": ((a.get("headshot") or {}).get("href") or ""),
            }
        )
    players.sort(key=lambda p: (p["jersey"] == "", int(p["jersey"] or 99)
                                if str(p["jersey"]).isdigit() else 99))
    coach = next((c.get("fullName") or f"{c.get('firstName','')} {c.get('lastName','')}"
                  for c in data.get("coach", []) if c.get("lastName")), "")
    return {
        "team": (data.get("team") or {}).get("displayName", abbr.upper()),
        "coach": coach,
        "players": players,
    }


def team_schedule(abbr: str, season: int | None = None) -> list[dict]:
    """單隊整季賽程（已賽／未賽都在）。"""
    params = {"season": season} if season else None
    data = _get(f"{NBA}/teams/{abbr.lower()}/schedule", params)
    return [_parse_event(e) for e in data.get("events", [])]


BOX_COLUMNS = ("MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK",
               "OREB", "DREB", "PF", "+/-")


def season_trend(abbr: str, season: int | None = None) -> dict:
    """賽季走勢：逐場累積勝率、得失分與勝負。

    team_schedule 的 events 沒有 result 欄位，勝負要自己用 abbr 比對比分算。
    """
    abbr = canon(abbr)
    try:
        games = [g for g in team_schedule(abbr, season) if g.get("final")]
    except NBAError:
        # 未知球隊代碼 ESPN 會回 400，這裡回空資料讓 UI 自己顯示提示。
        games = []
    games.sort(key=lambda g: g.get("date") or "")
    points = []
    wins = losses = 0
    streak = 0
    best = worst = 0
    for n, game in enumerate(games, 1):
        home = game.get("home") or {}
        away = game.get("away") or {}
        mine = home if home.get("abbr") == abbr else away
        theirs = away if home.get("abbr") == abbr else home
        if not mine.get("has_score") or not theirs.get("has_score"):
            continue
        scored = int(mine["score"])
        allowed = int(theirs["score"])
        won = scored > allowed
        wins += won
        losses += not won
        streak = streak + 1 if won else (streak - 1 if streak > 0 else -1)
        best = max(best, streak)
        worst = min(worst, streak)
        points.append({
            "n": n,
            "date": (game.get("date") or "")[:10],
            "id": game.get("id"),
            "won": won,
            "scored": scored,
            "allowed": allowed,
            "margin": scored - allowed,
            "opponent": theirs.get("abbr", ""),
            "wins": wins,
            "losses": losses,
            "pct": wins / (wins + losses),
        })

    full_name = ""
    for game in games:
        for side in ("home", "away"):
            if (game.get(side) or {}).get("abbr") == abbr:
                full_name = game[side].get("full_name") or ""
        if full_name:
            break

    return {
        "abbr": abbr,
        "name": full_name or abbr,
        "games": points,
        "record": (wins, losses),
        "pct": wins / (wins + losses) if (wins + losses) else 0.0,
        "scored": sum(p["scored"] for p in points),
        "allowed": sum(p["allowed"] for p in points),
        "best_streak": best,
        "worst_streak": worst,
    }


def playoff_probability(abbr: str, season: int | None = None) -> dict:
    """晉級季後賽機率：以各隊目前戰績當勝率做剩餘賽程的蒙地卡羅模擬。

    season 給完整已結束賽季時直接看最終排名；
    進行中的賽季則抓分區所有隊伍剩餘賽程做 2000 次模擬。
    """
    abbr = canon(abbr)
    try:
        rows = standings(season)
    except NBAError:
        return {
            "abbr": abbr,
            "name": abbr,
            "available": False,
            "seed": None,
            "probability": None,
            "playin": None,
            "finished": False,
            "remaining": 0,
        }
    mine = next((r for r in rows if r["abbr"] == abbr), None)
    if mine is None:
        return {
            "abbr": abbr,
            "name": abbr,
            "available": False,
            "seed": None,
            "probability": None,
            "playin": None,
            "finished": False,
            "remaining": 0,
        }
    conf = [[r for r in rows if r["conference"] == mine["conference"]]
            or [mine]][0]
    # 已完賽的賽季：直接看排名。自己算排名，不要依賴 ESPN 欄位。
    conf_sorted = sorted(conf, key=lambda r: (-r["wins"], -r["losses"]))
    rank = next(i + 1 for i, r in enumerate(conf_sorted) if r["abbr"] == abbr)
    finished = _season_finished(season)
    if finished:
        return {
            "abbr": abbr,
            "name": mine["team"],
            "conference": mine["conference"],
            "available": True,
            "seed": rank,
            "probability": 1.0 if rank <= 6 else 0.0,
            "playin": 1.0 if rank <= 10 else 0.0,
            "finished": True,
            "remaining": 0,
            "record": (mine["wins"], mine["losses"]),
        }
    # 進行中的賽季：抓剩餘賽程。只抓這個分區裡每隊剩下的比賽。
    remaining: list[tuple[str, str]] = []
    try:
        for r in conf:
            for g in team_schedule(r["abbr"], season):
                if g.get("final"):
                    continue
                home = (g.get("home") or {}).get("abbr")
                away = (g.get("away") or {}).get("abbr")
                if home and away and home != away:
                    remaining.append((home, away))
    except NBAError:
        remaining = []
    remaining = list(dict.fromkeys(
        (a, b) if a <= b else (b, a) for a, b in remaining))
    strength = {r["abbr"]: r["wins"] / max(1, r["wins"] + r["losses"])
                for r in rows}
    makes = 0
    playin = 0
    sims = 2000
    for _ in range(sims):
        wins = {r["abbr"]: r["wins"] for r in rows}
        for home, away in remaining:
            s_home, s_away = strength.get(home, 0.5), strength.get(away, 0.5)
            p = (1 + (s_home - s_away)) / 2
            p = max(0.05, min(0.95, p))
            winner = home if random.random() < p else away
            wins[winner] = wins.get(winner, 0) + 1
        seed = sorted(conf, key=lambda r: (-wins[r["abbr"]],
                                           -r["wins"] / max(1, r["wins"] + r["losses"])))
        pos = next(i for i, r in enumerate(seed) if r["abbr"] == abbr)
        makes += pos < 6
        playin += pos < 10
    return {
        "abbr": abbr,
        "name": mine["team"],
        "conference": mine["conference"],
        "available": True,
        "seed": rank,
        "probability": makes / sims,
        "playin": playin / sims,
        "finished": False,
        "remaining": len(remaining),
        "record": (mine["wins"], mine["losses"]),
    }


def _season_finished(season: int | None) -> bool:
    """給定 ESPN 的 season year，判斷該賽季是否已經全部打完。

    ESPN 賽季年是起始年（2026 代表 2025-26）。
    參考今天日期，當年 6 月底前為止、且 season 小於本年 → 已結束。
    """
    if season is None:
        return False
    today = date.today()
    current = today.year + 1 if today.month >= 7 else today.year
    return season < current


def boxscore(event_id: str) -> dict:
    """單場比賽詳情：兩隊球員逐項數據 + 球隊總計。

    未開賽時 ESPN 會回空 players，呼叫端要自己處理。
    """
    data = _get(f"{NBA}/summary", {"event": event_id})
    bs = data.get("boxscore", {})
    comps = data.get("header", {}).get("competitions", [{}])
    state = comps[0].get("status", {}).get("type", {}).get("name", "")
    status = comps[0].get("status", {}).get("type", {})
    # boxscore.players 沒有 homeAway 欄位，要從 header.competitors 補。
    home_abbrs = {c.get("team", {}).get("abbreviation", "")
                  for c in comps[0].get("competitors", [])
                  if c.get("homeAway") == "home"}
    # boxscore.teams 是球隊總計，boxscore.players 是逐人數據，兩個分開拿。
    totals_by_abbr = {}
    for entry in bs.get("teams", []) or []:
        abbr = entry.get("team", {}).get("abbreviation", "")
        totals_by_abbr[abbr] = _team_totals(entry.get("statistics") or [])
    teams = []
    for entry in bs.get("players", []):
        team = entry.get("team", {})
        groups = entry.get("statistics", []) or []
        if not groups:
            continue
        abbr = team.get("abbreviation", "")
        labels = list(groups[0].get("labels") or BOX_COLUMNS)
        rows = []
        for group in groups:
            for athlete in group.get("athletes", []):
                stats = athlete.get("stats") or []
                # stats 是與 labels 等長的字串陣列，未上場會是空陣列。
                if not stats:
                    continue
                row = dict(zip(labels, stats))
                row["name"] = athlete.get("athlete", {}).get("displayName", "")
                row["starter"] = bool(athlete.get("starter"))
                row["ejected"] = bool(athlete.get("ejected"))
                row["minutes"] = _to_minutes(row.get("MIN", "0"))
                row["points"] = _to_int(row.get("PTS"))
                row["plus_minus"] = _to_signed(row.get("+/-"))
                rows.append(row)
        rows.sort(key=lambda r: (-r["points"], -r["minutes"]))
        teams.append({
            "abbr": abbr,
            "name": team.get("displayName", ""),
            "home": abbr in home_abbrs,
            "labels": labels,
            "players": rows,
            "totals": totals_by_abbr.get(abbr, {}),
        })

    return {
        "event_id": str(event_id),
        "state": state,
        "detail": status.get("shortDetail") or status.get("detail", ""),
        "available": bool(teams),
        "teams": teams,
        "venue": comps[0].get("venue", {}).get("fullName", ""),
        "attendance": comps[0].get("attendance"),
        "leaders": _parse_leaders(data.get("leaders", [])),
    }


def _to_int(value) -> int:
    try:
        return int(str(value).strip().lstrip("+-"))
    except (TypeError, ValueError):
        return 0


def _to_signed(value) -> int:
    """保留正負號，籃球 +／- 欄位會是 '+3'、'-13'。"""
    try:
        return int(str(value).strip().lstrip("+"))
    except (TypeError, ValueError):
        return 0


def _to_minutes(value) -> float:
    """'38' -> 38.0，'12:34' -> 12.57。"""
    text = str(value or "0").strip()
    if not text:
        return 0.0
    if ":" in text:
        mm, _, ss = text.partition(":")
        try:
            return int(mm or 0) + int(ss or 0) / 60
        except ValueError:
            return 0.0
    return _to_int(text)


def _team_totals(statistics: list) -> dict:
    """boxscore.teams[].statistics 是 {name, label, displayValue} 物件的陣列。"""
    out = {}
    for stat in statistics or []:
        if isinstance(stat, dict) and stat.get("name"):
            out[stat["name"]] = stat.get("displayValue", "")
    return out


def _parse_leaders(blocks: list) -> list[dict]:
    """ESPN leaders 結構：每個 block 是 {team, leaders:[{name, displayName, leaders:[...]}]}。"""
    out = []
    for block in blocks or []:
        abbr = (block.get("team") or {}).get("abbreviation", "")
        for group in block.get("leaders", []) or []:
            entries = group.get("leaders", []) or []
            if not entries:
                continue
            lead = max(entries, key=lambda e: float(e.get("value") or 0))
            out.append({
                "team": abbr,
                "name": group.get("name", ""),
                "label": group.get("displayName", group.get("name", "")),
                "athlete": lead.get("athlete", {}).get("displayName", ""),
                "value": lead.get("displayValue", ""),
            })
    return out


def days_of_season(start: date, end: date) -> list[date]:
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


class Cache:
    """簡單的 TTL 記憶體快取，避免重複打 API。"""

    def __init__(self, ttl: int = 60):
        self.ttl = ttl
        self._store: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._store.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        return None

    def put(self, key, value):
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._store.clear()

    def drop_prefix(self, prefix: str):
        """只清掉某類 key（例如換日期時清掉舊的賽程快取）。"""
        with self._lock:
            for key in [k for k in self._store if k.startswith(prefix)]:
                del self._store[key]
