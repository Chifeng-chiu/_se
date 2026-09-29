"""通知比對引擎：比對前後兩次比分快照，找出該通知的變化。"""

from datetime import datetime

import nba_api as api

TIPOFF_WINDOW_MIN = 20


def _local(dt_str: str) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _sides(game: dict, abbr: str) -> tuple[dict | None, dict | None]:
    """回傳 (自己那隊, 對手)。主客隊欄位要翻轉，不要搞混。"""
    side = next((s for s in (game["away"], game["home"]) if s["abbr"] == abbr), None)
    if side is None:
        return None, None
    return side, (game["away"] if side["home"] else game["home"])


def _final_score(game: dict, abbr: str) -> tuple[str, int, int] | None:
    """回傳 (結果, 我方得分, 對手得分)。"""
    side, other = _sides(game, abbr)
    if side is None or other is None:
        return None
    # NBA 加時不會平手，出現平手代表資料異常（通常是其中一隊比分沒抓到）。
    if side["score"] == other["score"]:
        return None
    return ("win" if side["score"] > other["score"] else "loss",
            side["score"], other["score"])


def detect(games_before: list[dict], games_after: list[dict],
           favorites: list[str], tipoff_minutes: int = TIPOFF_WINDOW_MIN,
           now: datetime | None = None) -> list[dict]:
    """回傳要通知的事件清單。

    比對邏輯刻意只認「狀態真的變了」或「第一次進入開賽前時段」，
    避免每次刷新都重複通知同一場。
    """
    if not favorites:
        return []

    now = now or datetime.now()
    if now.tzinfo is None:
        now = now.astimezone()
    before = {g["id"]: g for g in games_before}
    events: list[dict] = []

    for game in games_after:
        favs = api.favorites_of(game, set(favorites))
        if not favs:
            continue
        side = favs[0]
        old = before.get(game["id"])
        tipoff = _local(game.get("date"))

        # 1) 關注球隊的比賽開打了
        if game["live"] and (old is None or not old["live"]):
            names = "、".join(f["abbr"] for f in favs)
            events.append({
                "kind": "tipoff",
                "game_id": game["id"],
                "title": f"{names} 比賽開打",
                "body": f"{game['away']['abbr']} {game['away']['score']} - "
                        f"{game['home']['score']} {game['home']['abbr']}"
                        f"　·　{game['detail']}",
            })

        # 2) 進入開賽前時段（只在首次進入時通知）
        elif tipoff and not old and not game["live"] and not game["final"]:
            mins = (tipoff - now).total_seconds() / 60
            if 0 < mins <= tipoff_minutes:
                names = "、".join(f["abbr"] for f in favs)
                _, rival = _sides(game, side["abbr"])
                events.append({
                    "kind": "soon",
                    "game_id": game["id"],
                    "title": f"{names} 即將開賽",
                    "body": f"對手 {rival['abbr']}　·　約 {int(mins) + 1} 分鐘後"
                            f"（{tipoff:%H:%M}）",
                })

        # 3) 比賽結束，通知勝負（兩隊都在關注時一起報）
        if game["final"] and (old is None or not old["final"]):
            if not all(g["has_score"] for g in (game["away"], game["home"])):
                continue
            score = _final_score(game, side["abbr"])
            if not score:
                continue
            result, mine, theirs = score
            win = result == "win"
            names = "、".join(f["abbr"] for f in favs)
            tail = "贏球！" if win else "輸球"
            # 兩隊都關注時輸贏相反，寫成對戰結果最不會講錯。
            if len(favs) == 2:
                head = f"{names} 對戰：{game['away']['abbr']} " \
                       f"{mine if not side['home'] else theirs} - " \
                       f"{theirs if not side['home'] else mine} " \
                       f"{game['home']['abbr']}"
                events.append({
                    "kind": "result",
                    "game_id": game["id"],
                    "title": "🏀 " + head,
                    "body": f"{tail}　·　{game['venue'] or ''}",
                })
            else:
                events.append({
                    "kind": "result",
                    "game_id": game["id"],
                    "title": f"{'🏀 ' if win else ''}{names} {tail}",
                    "body": f"{mine} - {theirs}　·　{game['venue'] or ''}",
                })

    return events
