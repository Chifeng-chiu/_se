"""真實資料下的邊界情況。"""

import copy
from datetime import date, datetime, timedelta

import alerts
import nba_api as api
import main as m
import settings

FAIL = []


def check(name, cond, detail=""):
    if not cond:
        FAIL.append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))


print("=== 真實賽程（10/03~10/06 季前賽）===")
games = api.scoreboard(date(2026, 10, 5))
check("未開賽比賽比分為 0", all(g["away"]["score"] == 0 and g["home"]["score"] == 0
                                for g in games))
check("未開賽 has_score 為 False 或 0", not any(g["away"]["has_score"] for g in games))
check("全部 not final / not live", not any(g["final"] or g["live"] for g in games))

print("\n=== 倒數文字 ===")
soon = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
check("30 分鐘 -> 分鐘", "分鐘" in m._tipoff_text(soon), m._tipoff_text(soon))
h2 = (datetime.now().astimezone() + timedelta(hours=2, minutes=20)).isoformat().replace("+00:00", "Z")
check("2 小時 -> 小時", "小時" in m._tipoff_text(h2), m._tipoff_text(h2))
d3 = (datetime.now().astimezone() + timedelta(days=3)).isoformat().replace("+00:00", "Z")
check("3 天 -> 天", "天後" in m._tipoff_text(d3), m._tipoff_text(d3))
past = (datetime.now().astimezone() - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
check("已過時間不顯示", m._tipoff_text(past) == "", repr(m._tipoff_text(past)))
check("空字串安全", m._tipoff_text(None) == "" and m._tipoff_text("") == "")
check("壞格式安全", m._tipoff_text("not-a-date") == "")
check("無時區安全", m._tipoff_text("2026-10-05T19:00:00") != "")

print("\n=== 通知邊界 ===")
base = {"id": "b", "venue": "V", "live": False, "final": False, "date": None, "state": "pre",
        "away": {"abbr": "GS", "score": 0, "has_score": False, "home": False},
        "home": {"abbr": "LAL", "score": 0, "has_score": False, "home": True},
        "detail": "10/5 - 7:00 PM EDT"}
check("未開賽不發通知", alerts.detect([], [base], ["GS"]) == [])
fin0 = copy.deepcopy(base)
fin0.update(final=True, detail="Final")
check("0 比 0 結束不發通知", alerts.detect([fin0], [fin0], ["GS"]) == [])
tie = copy.deepcopy(base)
tie.update(final=True,
           away={"abbr": "GS", "score": 110, "has_score": True, "home": False},
           home={"abbr": "LAL", "score": 110, "has_score": True, "home": True})
check("平手不誤判", alerts.detect([base], [tie], ["GS"]) == [],
      str([e["title"] for e in alerts.detect([base], [tie], ["GS"])]))
half = copy.deepcopy(base)
half.update(final=True,
            away={"abbr": "GS", "score": 0, "has_score": False, "home": False},
            home={"abbr": "LAL", "score": 110, "has_score": True, "home": True})
check("自己隊伍比分缺失不通知", alerts.detect([base], [half], ["GS"]) == [],
      str([e["title"] for e in alerts.detect([base], [half], ["GS"])]))
half2 = copy.deepcopy(base)
half2.update(final=True,
             away={"abbr": "GS", "score": 110, "has_score": True, "home": False},
             home={"abbr": "LAL", "score": 0, "has_score": False, "home": True})
check("對手比分缺失不通知", alerts.detect([base], [half2], ["GS"]) == [],
      str([e["title"] for e in alerts.detect([base], [half2], ["GS"])]))
bigwin = copy.deepcopy(base)
bigwin.update(final=True,
              away={"abbr": "GS", "score": 140, "has_score": True, "home": False},
              home={"abbr": "LAL", "score": 101, "has_score": True, "home": True})
res = alerts.detect([base], [bigwin], ["GS"])
check("贏球標題正確", res and res[0]["title"].endswith("贏球！"),
      res[0]["title"] if res else "無")
check("贏球 body 含比分與球場", res and res[0]["body"] == "140 - 101　·　V",
      res[0]["body"] if res else "")
check("兩隊都在關注清單不會重複",
      len(alerts.detect([], [fin0], ["GS", "LAL"])) == 0)
multi = copy.deepcopy(base)
multi.update(final=True,
             away={"abbr": "GS", "score": 120, "has_score": True, "home": False},
             home={"abbr": "LAL", "score": 115, "has_score": True, "home": True})
check("兩隊都在關注清單時只發一則（報兩隊）",
      len(alerts.detect([base], [multi], ["GS", "LAL"])) == 1,
      str([e["title"] for e in alerts.detect([base], [multi], ["GS", "LAL"])]))
check("報出的標題含兩個縮寫",
      all(t in alerts.detect([base], [multi], ["GS", "LAL"])[0]["title"]
          for t in ("GS", "LAL")),
      alerts.detect([base], [multi], ["GS", "LAL"])[0]["title"])
check("空比分清單不報錯", alerts.detect([], [], ["GS"]) == [])
check("舊快照有但新的沒有", alerts.detect([multi], [], ["GS"]) == [])

print("\n=== 賽季切換 ===")
check("_season_label(2026)", m._season_label(2026) == "2025-26", m._season_label(2026))
check("season_year 正確", m.App.season_year() == 2027, str(m.App.season_year()))
check("choices 長度", len(m.App._season_choices()) == 4, str(m.App._season_choices()))
check("_last_game_year 空清單", m._last_game_year([]) == 0)

print("\n=== 設定邊界 ===")
check("favorites 過濾空白", settings._normalize({"favorites": ["  ", ""]})["favorites"] == [])
check("favorites 去重", settings._normalize({"favorites": ["GS", "GS"]})["favorites"] == ["GS"])
check("favorites 上限 30", len(settings._normalize(
    {"favorites": [f"T{i}" for i in range(50)]})["favorites"]) == 30)
check("refresh 下限 15", settings._normalize({"refresh_seconds": 0})["refresh_seconds"] == 15)
check("preview 下限 1", settings._normalize({"preview_days": -5})["preview_days"] == 1)
check("None 欄位不爆", settings._normalize({"refresh_seconds": None})["refresh_seconds"] == 60)
check("未知欄位被丟掉", "hacker" not in settings._normalize({"hacker": 1}))

print("\n=== 單隊賽程 ===")
for abbr in ("GS", "LAL", "BOS"):
    sch = api.team_schedule(abbr, 2026)
    check(f"{abbr} 82+ 場", len(sch) >= 82, f"{len(sch)}")

print(f"\n{'=' * 40}")
print(f"失敗 {len(FAIL)}")
for f in FAIL:
    print("  -", f)
