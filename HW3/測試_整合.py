"""整合驗證：六項功能逐項檢查。"""

import copy
import sys
import time
from datetime import date, datetime, timedelta

import alerts
import nba_api as api
import settings
import system

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))


def wait(app, seconds, ready):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        if ready():
            return True
        time.sleep(0.05)
    return False


print("=== 資料層 ===")
teams = api.teams()
check("球隊名單 30 隊", len(teams) == 30, f"{len(teams)}")
games = api.scoreboard(date(2026, 10, 5))
check("指定日期賽程", len(games) > 0, f"{len(games)} 場")
check("賽程欄位完整", all(
    g["away"]["abbr"] and g["home"]["abbr"] and "state" in g and "final" in g
    for g in games))
sched = api.team_schedule("bos", 2026)
check("單隊賽程 82 場", len(sched) == 82, f"{len(sched)}")
roster = api.roster("bos")
check("陣容解析", len(roster["players"]) > 10 and roster["coach"],
      f"{len(roster['players'])} 人 / {roster['coach']}")
stand = api.standings(2026)
check("戰績 30 隊", len(stand) == 30, f"{len(stand)}")

print("\n=== 功能 2：通知引擎 ===")
base = {"id": "x", "venue": "V", "live": False, "final": False, "date": None,
        "state": "pre",
        "away": {"abbr": "GSW", "score": 110, "has_score": True, "home": False},
        "home": {"abbr": "LAL", "score": 105, "has_score": True, "home": True},
        "detail": "Final"}
live = copy.deepcopy(base); live.update(live=True, state="in", detail="Q3 5:20")
kinds = [e["kind"] for e in alerts.detect([base], [live], ["GSW"])]
check("開打通知", "tipoff" in kinds, str(kinds))
fin = copy.deepcopy(base); fin.update(final=True)
kinds = [e["kind"] for e in alerts.detect([base], [fin], ["GSW"])]
check("勝負通知", "result" in kinds, str(kinds))
soon = copy.deepcopy(base)
soon["date"] = (datetime.now().astimezone() + timedelta(minutes=8)).isoformat().replace("+00:00", "Z")
kinds = [e["kind"] for e in alerts.detect([], [soon], ["GSW"])]
check("開賽前提醒", "soon" in kinds, str(kinds))
check("狀態沒變不重複通知", alerts.detect([fin], [fin], ["GSW"]) == [])
check("非關注隊伍不通知", alerts.detect([base], [fin], ["BOS"]) == [])
check("沒有關注清單不通知", alerts.detect([base], [fin], []) == [])

print("\n=== 功能 6：設定檔持久化 ===")
cfg = settings.load()
check("設定檔可讀", isinstance(cfg, dict), f"{len(cfg)} 個欄位")
cfg["favorites"] = ["GSW", "BOS"]
cfg["refresh_seconds"] = 9999
saved = settings.save(cfg)
check("寫入設定檔", saved["refresh_seconds"] == 600, "超出範圍自動修正為 600")
check("關注清單寫入（GSW 正規化為 GS）", saved["favorites"] == ["BOS", "GS"],
      str(saved["favorites"]))
reloaded = settings.load()
check("重新載入一致", reloaded["favorites"] == ["BOS", "GS"], str(reloaded["favorites"]))
settings.save_state({"games": {"abc": "post"}})
check("狀態檔可寫讀", settings.load_state().get("games", {}).get("abc") == "post")
before = system.is_autostart_enabled()
system.set_autostart(not before)
check("開機啟動可切換", system.is_autostart_enabled() == (not before),
      f"before={before} after={system.is_autostart_enabled()}")
system.set_autostart(before)
check("開機啟動可還原", system.is_autostart_enabled() == before)

print("\n=== GUI 整合 ===")
from main import App  # noqa: E402

# 用已知的關注清單測試，避免吃到上一輪殘留的設定。
settings.save({**settings.DEFAULTS, "favorites": ["ATL", "GSW"]})
app = App()
app._fill_favorites()
app.day = date(2026, 10, 5)
app._load_scores()  # 先清掉上一輪殘留的 current_games
app.team_var.set("GSW")
app._load_scores()
app._load_schedule()
app._load_standings()
app._load_team()
ok = wait(app, 90, lambda: app.tree.get_children() and app.sched_tree.get_children()
          and app.roster_tree.get_children() and app.recent_tree.get_children())
check("五個分頁都載入", ok, app.status_var.get())
check("分頁資料載入", ok)
check("比分卡片", len(app.cards.winfo_children()) == 5,
      f"{len(app.cards.winfo_children())} 張")
check("未來賽程列", len(app.sched_tree.get_children()) > 0,
      f"{len(app.sched_tree.get_children())} 列")
check("戰績列", len(app.tree.get_children()) == 30)
check("陣容列", len(app.roster_tree.get_children()) > 10,
      f"{len(app.roster_tree.get_children())} 人")
check("近期戰績列", len(app.recent_tree.get_children()) > 0,
      f"{len(app.recent_tree.get_children())} 場")

print("\n=== 縮寫正規化 ===")
check("GSW 自動對應 GS", api.canon("GSW") == "GS", api.canon("GSW"))
check("縮寫別名只有一份", settings.ABBR_ALIASES is api.ABBR_ALIASES)
check("team_by_abbr 接受 GSW", (api.team_by_abbr("GSW") or {}).get("abbr") == "GS")
check("關注清單正規化", settings._normalize({"favorites": ["GSW", "lal"]})["favorites"]
      == ["GS", "LAL"])

print("\n=== 功能 1：關注隊伍置頂 + 倒數 ===")
app.cfg["favorites"] = ["ATL"]
app.fav_filter_var.set(False)
app._redraw_scores()


def borders(w):
    """收集所有 frame 的 highlightborder（★ 隊伍會是橙色）。"""
    out = []
    for c in w.winfo_children():
        try:
            out.append(str(c.cget("highlightbackground")))
        except Exception:
            pass
        out.extend(borders(c))
    return out


labels = []


def walk(w):
    for c in w.winfo_children():
        if c.winfo_class() == "Label":
            labels.append(str(c.cget("text")))
        walk(c)


walk(app.cards)
check("關注隊伍有標記", "#f9a11b" in borders(app.cards),
      f"{borders(app.cards).count('#f9a11b')} 個橙色框")
check("關注隊伍有 ★ 標示", any(t.startswith("★") for t in labels),
      str([t for t in labels if t.startswith("★")]))

# 只看關注：設 ATL 當天篩選，應只剩 1 場（MEM@ATL）
app.fav_filter_var.set(True)
app._redraw_scores()
n_all = 5
check("只看關注隊伍可篩選",
      len(app.cards.winfo_children()) == 1,
      f"5 場 -> {len(app.cards.winfo_children())} 場")
app.fav_filter_var.set(False)
app._redraw_scores()
check("可切回顯示全部", len(app.cards.winfo_children()) == n_all,
      f"{len(app.cards.winfo_children())} 場")
app.cfg["favorites"] = ["GSW", "BOS"]

print("\n=== 日期快速切換 ===")
app.day = date(2026, 10, 3)  # 1 場
app._load_scores()
time.sleep(0.4)
app.day = date(2026, 10, 5)  # 5 場
app._load_scores()
app.day = date(2026, 10, 4)  # 2 場
app._load_scores()
ok3 = wait(app, 70, lambda: len(app.current_games) == 2)
check("舊回應不蓋掉新日期", ok3 and app.date_lbl.cget("text").startswith("2026-10-04"),
      f"{app.date_lbl.cget('text')} / {len(app.current_games)} 場")
app.day = date(2026, 10, 1)  # 0 場
app._load_scores()
wait(app, 40, lambda: app.date_lbl.cget("text").startswith("2026-10-01"))


def all_labels(w, out):
    for c in w.winfo_children():
        if c.winfo_class() == "Label":
            out.append(str(c.cget("text")))
        all_labels(c, out)
    return out


def classes(w, out):
    for c in w.winfo_children():
        out.append(c.winfo_class())
        classes(c, out)
    return out


check("空日顯示提示", all_labels(app.cards, []) == ["當日沒有賽事"],
      str(all_labels(app.cards, [])))
app.day = date(2026, 10, 5)
app._load_scores()
wait(app, 40, lambda: len(app.current_games) == 5)

print("\n=== 功能 4：迷你小工具 ===")
app._toggle_widget()
check("小工具可開啟", app.widget is not None and app.widget.winfo_exists())
app.widget.refresh()
check("小工具有內容", len(app.widget.body.winfo_children()) > 0)
check("小工具置頂", bool(app.widget.attributes("-topmost")))
app._toggle_widget()
check("小工具可關閉", app.widget is None)

print("\n=== 功能 2（GUI 層）：通知觸發 ===")
app.cfg["favorites"] = ["GSW"]
app.seen_games = [base]
app.current_games = [live]
called = []
app._notify = lambda t, b: called.append((t, b))
app._check_alerts([live])
check("狀態變化觸發通知", len(called) >= 1, str(called))
app._check_alerts([live])
check("同一狀態不重複通知", len(called) == 1, f"{len(called)} 次")

# 未來賽程篩選：關注 ATL 時，10/05 有 MEM@ATL 一場屬於關注
app.cfg["favorites"] = ["ATL"]
app.only_fav_upcoming.set(False)
app._redraw_schedule()
total = len(app.sched_tree.get_children())
app.only_fav_upcoming.set(True)
app._redraw_schedule()
fav_only = len(app.sched_tree.get_children())
check("未來賽程可篩選關注隊伍", 0 < fav_only < total, f"全部 {total} / 關注 {fav_only}")
app.only_fav_upcoming.set(False)

# 切換球隊會重新載入：GSW -> BOS
app.team_var.set("BOS　Boston Celtics")
app._load_team()
ok2 = wait(app, 60, lambda: "Boston" in app.team_info.cget("text"))
check("切換球隊會重新載入", ok2 and len(app.recent_tree.get_children()) > 0,
      app.team_info.cget("text"))
info = app.team_info.cget("text")
check("球隊標題含教練與戰績", "教練" in info and "陣容" in info, info)

# 切換賽季會更新戰績與近期戰績
check("下拉選單顯示 2025-26", app._season_choices()[1] == "2025-26", str(app._season_choices()))
app.season_var.set("2025-26")
app._on_season()
check("賽季選擇轉為 ESPN 年份", app.season == 2026, f"season={app.season}")
app.season_var.set("本季")
app._on_season()
check("回到本季 season=None", app.season is None)

print("\n=== 功能 7：單場數據（/summary boxscore） ===")
bx = api.boxscore(str(api.team_schedule("LAL", 2026)[-1]["id"]))
check("boxscore 有兩隊", len(bx["teams"]) == 2, f"{len(bx['teams'])} 隊")
filled = [t for t in bx["teams"] if t["players"]]
check("boxscore 有逐人數據", len(filled) == 2,
      "、".join(f"{t['abbr']} {len(t['players'])}人" for t in bx["teams"]))
p0 = bx["teams"][0]["players"][0]
check("數據欄位齊全", all(k in p0 for k in
      ("name", "PTS", "REB", "AST", "FG", "3PT", "FT", "MIN", "+/-")), str(list(p0)[:6]))
check("得分排序", all(a["points"] >= b["points"]
      for t in bx["teams"] for a, b in zip(t["players"], t["players"][1:])),
      f"{p0['name']} 最高分 {p0['points']}")
check("正負分保留正負號", any(p["plus_minus"] != 0 for t in bx["teams"]
      for p in t["players"]), str(p0["plus_minus"]))
check("主客場標記", any(t["home"] for t in bx["teams"])
      and any(not t["home"] for t in bx["teams"]))
pre = api.boxscore(str(api.scoreboard(date(2026, 10, 5))[0]["id"]))
check("未開賽回空 teams", pre["available"] is False and pre["teams"] == [],
      f"state={pre['state']}")

print("\n=== 功能 8：賽季走勢圖 ===")
tr = api.season_trend("GSW", 2026)
check("走勢有逐場資料", len(tr["games"]) == 82, f"{len(tr['games'])} 場")
g0, g1 = tr["games"][0], tr["games"][-1]
record = tr["record"]
check("累積勝率與勝場一致",
      g1["wins"] + g1["losses"] == len(tr["games"]) == record[0] + record[1],
      f"{g1['wins']}-{g1['losses']} / {len(tr['games'])} 場")
check("連勝與連敗越界", tr["best_streak"] >= 1 and tr["worst_streak"] <= -1,
      f"{tr['best_streak']} / {tr['worst_streak']}")
check("得失分平均值", tr["scored"] > 0 and tr["allowed"] > 0)
check("縮寫別名可用", api.season_trend("GSW", 2026)["abbr"] == "GS")
empty = api.season_trend("LAL", 2030)
check("無場次回空", empty["games"] == [] and empty["record"] == (0, 0), str(empty["record"]))
bad = api.season_trend("ZZZ", 2026)
check("未知代碼不拋例外", bad["games"] == [], f"games={len(bad['games'])}")

print("\n=== 功能 9：晉級季後賽機率 ===")
pp = api.playoff_probability("GS", 2026)
check("歷史賽季已完賽", pp["available"] and pp["finished"], str(pp))
check("機率不是 None", pp["probability"] in (1.0, 0.0) and pp["seed"] >= 1 and pp["seed"] <= 15,
      f"seed={pp['seed']}")
west = [r for r in api.standings(2026) if r["conference"] == "Western Conference"]
top = max(west, key=lambda r: (r["wins"], -r["losses"]))
worst = min(west, key=lambda r: (r["wins"], -r["losses"]))
pt = api.playoff_probability(top["abbr"], 2026)
pw = api.playoff_probability(worst["abbr"], 2026)
check("龍頭必晉級", pt["available"] and pt["seed"] <= 6 and pt["probability"] == 1.0,
      f"{top['abbr']} seed={pt['seed']}")
check("墊底無緣季後賽", pw["available"] and pw["probability"] == 0.0,
      f"{worst['abbr']} seed={pw['seed']}")
unknown = api.playoff_probability("ZZZ", 2026)
check("未知代碼不拋例外", unknown["available"] is False, str(unknown.get("available")))
live_pp = api.playoff_probability("GS", None)
check("本季走模擬賽程", live_pp["available"] and not live_pp["finished"]
      and 0 <= live_pp["probability"] <= 1 and live_pp["remaining"] > 0,
      f"prob={live_pp['probability']:.0%} 剩{live_pp['remaining']}場")

app.trend_var.set("GSW")
app.trend_season.set("2025-26")
app._load_trend()
okt = wait(app, 60, lambda: getattr(app, "trend_data", None)
            and len(app.trend_data["games"]) >= 82)
check("走勢分頁載入並繪製",
      okt and "Warriors" in app.trend_summary.cget("text"),
      app.trend_summary.cget("text"))
app.nb.select(app.tabs["trend"])
app.trend_canvas.update_idletasks()
app.trend_canvas.configure(width=900, height=400)
app._redraw_trend()
check("走勢圖有圖形", len(app.trend_canvas.find_all()) > 3 and okt,
      f"{len(app.trend_canvas.find_all())} 個圖元")
okp = wait(app, 60, lambda: "季後賽" in app.trend_prob.cget("text"))
check("晉級季後賽機率顯示", okp, app.trend_prob.cget("text"))

check("boxscore 按鈕存在", "TButton" in classes(app.cards, []), "")

print("\n=== 示範模式 ===")
app.cfg["favorites"] = ["LAL"]
app.day = date.today()
app._load_scores()
wait(app, 30, lambda: len(app.current_games) >= 0)  # 先等原本的今天載入
app._demo()
okd = wait(app, 60, lambda: getattr(app, "boxscore_game", None)
            and len(app.bx_trees[0].get_children()) > 0)
check("示範自動載入完賽單場數據",
      okd and app.boxscore_game_meta.get("final"),
      f"day={app.day} rows={len(app.bx_trees[0].get_children())}")
check("示範日為上一季", app.day.year == 2026, f"day={app.day}")
demo_rows = len(app.bx_trees[0].get_children())
check("示範 boxscore 有逐人列", demo_rows > 1, f"{demo_rows} 列")
# 回到今天的按鈕路徑
app._today()
wait(app, 30, lambda: app.date_lbl.cget("text").startswith("今天"))
check("示範後按今天可回到即時", "今天" in app.date_lbl.cget("text"),
      app.date_lbl.cget("text"))
app.destroy()
print(f"\n{'=' * 40}")
print(f"通過 {len(PASS)}　失敗 {len(FAIL)}")
if FAIL:
    print("失敗項目：")
    for f in FAIL:
        print("  -", f)
sys.exit(1 if FAIL else 0)
