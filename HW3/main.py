"""NBA 追蹤小工具 — 主視窗（比分 / 戰績 / 賽程 / 球隊 / 設定）。"""

import base64
import queue
import sys
import threading
import urllib.request
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk

import alerts
import nba_api as api
import settings
import system

BG = "#12151c"
CARD = "#1c2130"
FG = "#e8ecf4"
MUTED = "#8b93a7"
ACCENT = "#f9a11b"
WIN = "#4ade80"
LOSS = "#f87171"
FONT = "Segoe UI"
TIPOFF_WINDOW = alerts.TIPOFF_WINDOW_MIN


def _sort_num(text, diff=False):
    """Best-effort number for sorting: '32' -> 32, '12-20' -> 12,
    '12:34' -> 12.57 minutes, '+5' -> 5, missing -> -inf (sinks)."""
    s = str(text).strip()
    if not s or s in ("-", "--", "—", "–"):
        return float("-inf")
    if diff and s.count("-") == 1 and not s.startswith("-"):
        a, b = s.split("-")
        try:
            return int(a) - int(b)
        except ValueError:
            pass
    if ":" in s:
        try:
            mm, ss = s.split(":")
            return int(mm) + int(ss) / 60
        except ValueError:
            pass
    first = s.split("-")[0].split("/")[0].strip().lstrip("+")
    try:
        return float(first)
    except ValueError:
        return float("-inf")


def _make_tree_sortable(tree, numeric=(), diff=()):
    """Click a heading to sort that column; click again to reverse.

    Numeric columns start descending (biggest first), text ascending.
    Rows tagged 'total' (team totals) always stay pinned on top.
    """
    numeric = set(numeric)
    diff = set(diff)
    state = {"col": None, "rev": False}

    def key_of(item, col):
        vals = tree.item(item, "values")
        idx = tree["columns"].index(col)
        text = vals[idx] if idx < len(vals) else ""
        if col in numeric or col in diff:
            return (0, _sort_num(text, diff=(col in diff)))
        return (1, str(text).lower())

    def sort_by(col):
        if state["col"] == col:
            state["rev"] = not state["rev"]
        else:
            state.update(col=col, rev=(col in numeric or col in diff))
        pinned = [it for it in tree.get_children("")
                  if "total" in tree.item(it, "tags")]
        rest = [it for it in tree.get_children("")
                if "total" not in tree.item(it, "tags")]
        rest.sort(key=lambda it: key_of(it, col), reverse=state["rev"])
        for pos, item in enumerate(pinned + rest):
            tree.move(item, "", pos)
        for c in tree["columns"]:
            tree.heading(c, text=tree.heading(c, "text").rstrip(" ▲▼"))
        mark = " ▼" if state["rev"] else " ▲"
        tree.heading(col, text=tree.heading(col, "text") + mark)

    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: sort_by(c))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NBA 追蹤小工具")
        self.geometry("1000x680")
        self.minsize(820, 560)
        self.configure(bg=BG)

        self.cfg = settings.load()
        self.seen = settings.load_state().get("games", {})
        self.day = date.today()
        self.season = None
        self.cache = api.Cache(ttl=45)
        self.worker = queue.Queue()
        self.seen_games: list[dict] = []
        self.detail_abbr: str | None = None
        self.widget = None
        self.current_games: list[dict] = []
        self.current_schedule: list[tuple] = []
        self.current_boxscore: dict = {}
        self.current_roster: dict = {}
        self.current_plays: list = []
        self.current_standings: list = []
        self._logos: dict = {}
        self._logo_asked: set = set()
        self._card_windows: dict = {}

        self.auto_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="載入中…")
        self._timers: dict[str, tk.After] = {}

        self._style()
        self._build()
        self.after(120, self._drain)
        self._load_scores()
        self._tick()
        self._sync_autostart()

    # ================= 版面 =================
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=CARD)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=MUTED,
                    padding=(16, 8), font=(FONT, 10, "bold"))
        s.map("TNotebook.Tab", background=[("selected", BG)],
              foreground=[("selected", FG)])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG,
                    rowheight=26, borderwidth=0, font=(FONT, 10))
        s.configure("Treeview.Heading", background="#252b3a", foreground=MUTED,
                    font=(FONT, 9, "bold"), relief="flat", padding=(6, 6))
        s.map("Treeview", background=[("selected", "#2f3852")],
              foreground=[("selected", FG)])
        s.configure("TButton", background="#2f3852", foreground=FG, relief="flat",
                    padding=(10, 5), font=(FONT, 9))
        s.map("TButton", background=[("active", "#3d4763")])
        s.configure("TEntry", fieldbackground=CARD, foreground=FG)
        s.configure("TCheckbutton", background=BG, foreground=MUTED, font=(FONT, 9))
        s.map("TCheckbutton", background=[("active", BG)], foreground=[("active", FG)])
        s.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=FG)
        s.configure("TSpinbox", fieldbackground=CARD, background=CARD, foreground=FG)
        s.configure("TLabel", background=BG, foreground=FG)

    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(head, text="NBA", bg=BG, fg=ACCENT,
                 font=(FONT, 20, "bold")).pack(side="left")
        tk.Label(head, text="追蹤小工具", bg=BG, fg=FG,
                 font=(FONT, 13, "bold")).pack(side="left", padx=(8, 0), pady=(6, 0))
        self.fav_lbl = tk.Label(head, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.fav_lbl.pack(side="right", pady=(6, 0))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14)
        self.tabs = {}
        for key, title in (("scores", "  比分明細  "), ("boxscore", "  單場數據  "),
                           ("schedule", "  未來賽程  "), ("standings", "  球隊戰績  "),
                           ("teams", "  球隊詳情  "), ("trend", "  賽季走勢  "),
                           ("settings", "  設定  ")):
            frame = tk.Frame(self.nb, bg=BG)
            self.nb.add(frame, text=title)
            self.tabs[key] = frame

        self.boxscore_game = None
        self.trend_data = None
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)

        self._build_scores()
        self._build_boxscore()
        self._build_schedule()
        self._build_standings()
        self._build_teams()
        self._build_trend()
        self._build_settings()

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=14, pady=(8, 10))
        ttk.Checkbutton(bar, text="自動刷新", variable=self.auto_var,
                        command=self._tick).pack(side="left")
        ttk.Button(bar, text="立即重新整理", command=self._manual).pack(side="left", padx=10)
        ttk.Button(bar, text="迷你小工具", command=self._toggle_widget).pack(side="left")
        tk.Label(bar, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="right")

        self.toast = None
        self._show_toast("歡迎使用", "已載入 NBA 即時資料", ACCENT, 4000)

    # ---------- 比分明細（功能 1：關注隊伍置頂 + 開賽倒數） ----------
    def _build_scores(self):
        parent = self.tabs["scores"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        ttk.Button(bar, text="◀", width=3, command=self._prev_day).pack(side="left")
        ttk.Button(bar, text="今天", width=6, command=self._today).pack(side="left", padx=6)
        ttk.Button(bar, text="▶", width=3, command=self._next_day).pack(side="left")
        self.date_lbl = tk.Label(bar, text="", bg=BG, fg=FG, font=(FONT, 11, "bold"))
        self.date_lbl.pack(side="left", padx=12)
        self.fav_filter_var = tk.BooleanVar(value=False)
        self.only_fav_btn = ttk.Button(bar, text="只看關注隊伍", width=12,
                                       command=self._toggle_fav_only)
        self.only_fav_btn.pack(side="right")
        ttk.Button(bar, text="示範", width=6,
                   command=self._demo).pack(side="left", padx=(10, 0))

        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True, padx=4)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    # ---------- 單場數據（功能 7：/summary boxscore） ----------
    def _build_boxscore(self):
        parent = self.tabs["boxscore"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        self.bx_hint = tk.Label(bar, text="點上方比分明細的「單場數據」查看逐人成績",
                                bg=BG, fg=MUTED, font=(FONT, 9))
        self.bx_hint.pack(side="left")

        panes = tk.Frame(parent, bg=BG)
        panes.pack(fill="both", expand=True, padx=4)
        self.bx_trees: list[ttk.Treeview] = []
        for side in (0, 1):
            col = tk.Frame(panes, bg=BG)
            col.pack(side="left", fill="both", expand=True, padx=(0, 3) if side == 0 else (3, 0))
            title = tk.Label(col, text="", bg=BG, fg=FG, font=(FONT, 11, "bold"), anchor="w")
            title.pack(fill="x", pady=(0, 4))
            tree = ttk.Treeview(col, columns=("no", "name") + api.BOX_COLUMNS,
                                show="headings", height=14)
            for key, label, width, anchor in (
                    ("no", "#", 38, "center"), ("name", "球員", 130, "w"),
                    ("MIN", "MIN", 46, "center"), ("PTS", "PTS", 42, "center"),
                    ("FG", "FG", 58, "center"), ("3PT", "3PT", 52, "center"),
                    ("FT", "FT", 52, "center"), ("REB", "REB", 42, "center"),
                    ("AST", "AST", 42, "center"), ("TO", "TO", 38, "center"),
                    ("STL", "STL", 42, "center"), ("BLK", "BLK", 42, "center"),
                    ("OREB", "OREB", 46, "center"), ("DREB", "DREB", 46, "center"),
                    ("PF", "PF", 38, "center"), ("+/-", "+/-", 46, "center")):
                tree.heading(key, text=label)
                tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
            tree.tag_configure("starter", foreground=FG)
            tree.tag_configure("bench", foreground=MUTED)
            tree.tag_configure("total", foreground=ACCENT)
            tree.tag_configure("ejected", foreground=LOSS)
            _make_tree_sortable(tree, numeric=set(api.BOX_COLUMNS))
            vsb = ttk.Scrollbar(col, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            setattr(self, f"bx_title_{side}", title)
            tree.bind("<Double-Button-1>", self._on_boxscore_open)
            self.bx_trees.append(tree)

        pb = tk.Frame(parent, bg=BG)
        pb.pack(fill="x", padx=4, pady=(6, 4))
        tk.Label(pb, text="比賽事件", bg=BG, fg=MUTED,
                 font=(FONT, 9, "bold")).pack(side="left")
        self.plays_scoring_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(pb, text="只看得分", variable=self.plays_scoring_only,
                        command=self._render_plays).pack(side="left", padx=10)
        self.plays_tree = ttk.Treeview(parent,
                                       columns=("q", "clock", "event", "score"),
                                       show="headings", height=7)
        for key, label, width, anchor in (("q", "節", 60, "center"),
                                         ("clock", "時間", 70, "center"),
                                         ("event", "事件", 400, "w"),
                                         ("score", "比分", 90, "center")):
            self.plays_tree.heading(key, text=label)
            self.plays_tree.column(key, width=width, anchor=anchor,
                                   stretch=(key == "event"))
        self.plays_tree.tag_configure("score", foreground=ACCENT)
        psb = ttk.Scrollbar(parent, orient="vertical",
                            command=self.plays_tree.yview)
        self.plays_tree.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y", padx=(0, 4))
        self.plays_tree.pack(fill="x", padx=4, pady=(0, 6))

    def _open_boxscore(self, game):
        self.boxscore_game = game["id"]
        self.boxscore_game_meta = game
        self.boxscore_shown = None
        self.boxscore_note = ""
        self.nb.select(self.tabs["boxscore"])
        self.bx_hint.config(text="載入中…")
        self._cached(f"bx:{game['id']}",
                     lambda: api.boxscore(game["id"]),
                     self._render_boxscore)

    # ---------- 未來賽程（功能 5） ----------
    def _build_schedule(self):
        parent = self.tabs["schedule"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        tk.Label(bar, text="往後天數", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.preview_days = tk.IntVar(value=self.cfg["preview_days"])
        ttk.Spinbox(bar, from_=1, to=14, width=4, textvariable=self.preview_days,
                    command=self._load_schedule).pack(side="left", padx=6)
        self.only_fav_upcoming = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="只看關注隊伍", variable=self.only_fav_upcoming,
                        command=self._redraw_schedule).pack(side="left", padx=10)
        ttk.Button(bar, text="重新載入", command=self._load_schedule).pack(side="left")

        self.sched_tree = ttk.Treeview(parent, columns=("day", "time", "matchup", "detail"),
                                       show="headings")
        for key, label, width, anchor in (("day", "日期", 110, "center"),
                                          ("time", "時間", 70, "center"),
                                          ("matchup", "對戰", 260, "w"),
                                          ("detail", "狀態", 160, "center")):
            self.sched_tree.heading(key, text=label)
            self.sched_tree.column(key, width=width, anchor=anchor,
                                   stretch=(key == "matchup"))
        sb = ttk.Scrollbar(parent, orient="vertical", command=self.sched_tree.yview)
        self.sched_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4))
        self.sched_tree.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.sched_tree.tag_configure("fav", background="#243049")
        _make_tree_sortable(self.sched_tree)

    # ---------- 戰績 ----------
    def _build_standings(self):
        parent = self.tabs["standings"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        self.season_var = tk.StringVar(value="本季")
        self.stand_scope = tk.StringVar(value="全聯盟")
        stand_conf = ttk.Combobox(bar, textvariable=self.stand_scope,
                                  state="readonly", width=8,
                                  values=["全聯盟", "東區", "西區"])
        stand_conf.pack(side="left", padx=(0, 10))
        stand_conf.bind("<<ComboboxSelected>>", lambda _e: self._draw_standings())
        self.season_box = ttk.Combobox(bar, textvariable=self.season_var, state="readonly",
                                      values=self._season_choices(), width=12)
        self.season_box.pack(side="left")
        self.season_box.bind("<<ComboboxSelected>>", self._on_season)
        ttk.Button(bar, text="更新戰績", command=self._load_standings).pack(side="left", padx=10)
        self.stand_note = tk.Label(bar, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.stand_note.pack(side="left")

        cols = ("seed", "team", "w", "l", "pct", "gb", "streak", "home", "road",
                "diff", "ppg")
        self.tree = ttk.Treeview(parent, columns=cols, show="tree headings")
        self.tree.column("#0", width=34, stretch=False)
        heads = {
            "seed": ("#", 40, "center"), "team": ("隊伍", 130, "w"),
            "w": ("勝", 45, "center"), "l": ("負", 45, "center"),
            "pct": ("勝率", 65, "center"), "gb": ("勝分", 65, "center"),
            "streak": ("連勝", 65, "center"), "home": ("主場", 70, "center"),
            "road": ("客場", 70, "center"), "diff": ("得失差", 70, "center"),
            "ppg": ("得分", 65, "center"),
        }
        for key, (label, width, anchor) in heads.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "team"))
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 4))
        self.tree.pack(fill="both", expand=True, padx=4)
        self.tree.tag_configure("fav", background="#243049")
        self.tree.tag_configure("playoff", foreground=WIN)
        _make_tree_sortable(self.tree, numeric={"seed", "w", "l", "pct", "gb",
                                                "home", "road", "diff", "ppg"})

    # ---------- 球隊詳情（功能 3） ----------
    def _build_teams(self):
        parent = self.tabs["teams"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        tk.Label(bar, text="球隊", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.team_var = tk.StringVar()
        self.team_box = ttk.Combobox(bar, textvariable=self.team_var, state="readonly",
                                     width=22)
        self.team_box.pack(side="left", padx=6)
        self.team_box.bind("<<ComboboxSelected>>", self._on_team_pick)
        self.team_fav_btn = ttk.Button(bar, text="加入關注", command=self._toggle_fav_team)
        self.team_fav_btn.pack(side="left", padx=8)
        ttk.Button(bar, text="載入", command=self._load_team).pack(side="left")
        self.team_note = tk.Label(bar, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.team_note.pack(side="left", padx=10)

        self.team_info = tk.Label(parent, text="", bg=BG, fg=FG,
                                  font=(FONT, 11, "bold"), anchor="w", justify="left")
        self.team_info.pack(fill="x", padx=8, pady=(4, 6))

        panes = tk.Frame(parent, bg=BG)
        panes.pack(fill="both", expand=True, padx=4)

        left = tk.Frame(panes, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="陣容", bg=BG, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w")
        self.roster_tree = ttk.Treeview(left, columns=("no", "name", "pos", "h", "w", "age"),
                                        show="headings", height=8)
        for key, label, width, anchor in (("no", "#", 34, "center"), ("name", "球員", 150, "w"),
                                          ("pos", "位置", 50, "center"), ("h", "身高", 60, "center"),
                                          ("w", "體重", 66, "center"), ("age", "年齡", 50, "center")):
            self.roster_tree.heading(key, text=label)
            self.roster_tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
        rb = ttk.Scrollbar(left, orient="vertical", command=self.roster_tree.yview)
        self.roster_tree.configure(yscrollcommand=rb.set)
        rb.pack(side="right", fill="y")
        self.roster_tree.pack(fill="both", expand=True, pady=(2, 8))
        self.roster_tree.tag_configure("injured", foreground=LOSS)
        self.roster_tree.bind("<Double-Button-1>", self._on_roster_open)
        _make_tree_sortable(self.roster_tree, numeric={"no", "age"})

        right = tk.Frame(panes, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(right, text="近期戰績", bg=BG, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w")
        self.recent_tree = ttk.Treeview(right, columns=("date", "opponent", "res", "score"),
                                        show="headings", height=8)
        for key, label, width, anchor in (("date", "日期", 90, "center"),
                                          ("opponent", "對手", 120, "w"),
                                          ("res", "結果", 60, "center"),
                                          ("score", "比分", 90, "center")):
            self.recent_tree.heading(key, text=label)
            self.recent_tree.column(key, width=width, anchor=anchor, stretch=(key == "opponent"))
        self.recent_tree.pack(fill="both", expand=True, pady=(2, 8))
        self.recent_tree.tag_configure("win", foreground=WIN)
        self.recent_tree.tag_configure("loss", foreground=LOSS)
        _make_tree_sortable(self.recent_tree, diff=("score",))

    # ---------- 賽季走勢（功能 8：Canvas 自繪圖表） ----------
    def _build_trend(self):
        parent = self.tabs["trend"]
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=4, pady=(8, 6))
        tk.Label(bar, text="球隊", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.trend_var = tk.StringVar()
        self.trend_box = ttk.Combobox(bar, textvariable=self.trend_var,
                                      state="readonly", width=20)
        self.trend_box.pack(side="left", padx=6)
        self.trend_box.bind("<<ComboboxSelected>>", self._load_trend)
        tk.Label(bar, text="賽季", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(8, 0))
        self.trend_season = tk.StringVar(value="本季")
        ttk.Combobox(bar, textvariable=self.trend_season, state="readonly",
                     width=7, values=self._season_choices()).pack(side="left", padx=6)
        self.trend_season.trace_add("write", lambda *_: self._load_trend())
        ttk.Button(bar, text="載入", command=self._load_trend).pack(side="left")

        self.trend_summary = tk.Label(parent, text="", bg=BG, fg=FG,
                                      font=(FONT, 10, "bold"), anchor="w")
        self.trend_summary.pack(fill="x", padx=8, pady=(2, 6))

        self.trend_prob = tk.Label(parent, text="", bg=BG, fg=ACCENT,
                                   font=(FONT, 9), anchor="w")
        self.trend_prob.pack(fill="x", padx=8, pady=(0, 4))

        self.trend_canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        self.trend_canvas.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        self.trend_canvas.bind("<Configure>", self._redraw_trend)

    def _load_trend(self, _event=None):
        raw = self.trend_var.get().strip()
        if not raw:
            return
        abbr = api.canon(raw.split("　")[0].split()[0])
        season = self._season_value(self.trend_season.get())
        self.trend_summary.config(text=f"載入 {abbr} 走勢…")
        self.trend_prob.config(text="計算晉級季後賽機率…")
        self._cached(f"tnd:{abbr}:{season}",
                     lambda: api.season_trend(abbr, season),
                     self._render_trend)
        self._cached(f"pl:{abbr}:{season}",
                     lambda: api.playoff_probability(abbr, season),
                     self._render_trend_playoff)

    def _season_value(self, label: str):
        return None if label == "本季" else int(label.split("-")[0]) + 1

    def _render_trend(self, data):
        self.trend_data = data
        text = f"{data['name']}　·　{data['record'][0]}-{data['record'][1]}"
        if data["games"]:
            text += f"　·　勝率 {data['pct']:.3f}"
            text += f"　·　連勝至多 {data['best_streak']} 場 / 連敗至多 {abs(data['worst_streak'])} 場"
            total = len(data["games"])
            text += f"　·　場均 {data['scored'] / total:.1f} 得 / {data['allowed'] / total:.1f} 失"
        else:
            text += "　·　此賽季尚無已完賽場次"
        self.trend_summary.config(text=text)
        self._redraw_trend()

    def _render_trend_playoff(self, data):
        if not data.get("available"):
            self.trend_prob.config(text="晉級季後賽機率　·　資料不足", fg=MUTED)
            return
        prob = data.get("probability")
        if prob is None:
            self.trend_prob.config(text="晉級季後賽機率　·　尚無法評估", fg=MUTED)
            return
        if data.get("finished"):
            result = ("直接晉級" if prob == 1.0 else
                      ("獲得附加賽資格" if data.get("playin") == 1.0 else "無緣季後賽"))
            color = WIN if prob == 1.0 else FG
            self.trend_prob.config(
                text=(f"季後賽　·　{data['conference'].split()[0]}區最終排名第 {data['seed']}"
                      f"　·　{result}"), fg=color)
            return
        pct = prob * 100
        playin = (data.get("playin") or 0) * 100
        color = ACCENT if prob >= 0.9 else (FG if prob >= 0.5 else MUTED)
        self.trend_prob.config(
            text=(f"晉級季後賽機率　·　前六種子 {pct:.0f}%"
                  f"　·　至少附加賽 {playin:.0f}%　·　剩 {data['remaining']} 場"),
            fg=color)

    def _redraw_trend(self, _event=None):
        c = self.trend_canvas
        c.delete("all")
        data = getattr(self, "trend_data", None)
        w = c.winfo_width()
        h = c.winfo_height()
        if data is None or w < 200 or h < 150:
            return
        games = data["games"]
        if not games:
            c.create_text(w // 2, h // 2, text="此賽季尚無已完賽場次",
                          fill=MUTED, font=(FONT, 12))
            return
        # 下半部：單場得失分；上半部：累積勝率。
        margin = games[-1]["margin"]
        playable = h - 84  # 底部保留圖例
        self._draw_winrate(c, games, margin_top=10, height=playable * 0.45, left=46)
        self._draw_margins(c, games, top=30 + playable * 0.45,
                           height=playable * 0.45, left=46)
        c.create_text(10, h - 12, anchor="w", text=(
            "橙線＝累積勝率　綠/紅柱＝單場淨勝分　·　"
            f"最後一場淨勝 {margin:+d}"), fill=MUTED, font=(FONT, 8))

    def _draw_winrate(self, c, games, margin_top, height, left):
        w = c.winfo_width()
        plot_w = w - left - 18
        top = margin_top
        bottom = top + height
        n = len(games)
        def x(i): return left + plot_w * (i / max(1, n - 1))
        def y(pct): return bottom - (pct / 1.0) * height
        for pct in (0.0, 0.25, 0.5, 0.75, 1.0):
            yy = y(pct)
            color = "#f87171" if pct == 0.5 else "#2a3145"
            dash = (4, 4) if pct == 0.5 else ()
            c.create_line(left, yy, w - 18, yy, fill=color, dash=dash)
            c.create_text(left - 6, yy, text=f"{pct:.0%}", anchor="e",
                          fill=MUTED, font=(FONT, 8))
        pts = [x(i) for i in range(n)] + [y(g["pct"]) for g in games]
        c.create_line(*(v for pair in zip(pts[:n], pts[n:]) for v in pair),
                      fill=ACCENT, width=2)
        c.create_text((left + w - 18) // 2, top - 2, text="累積勝率",
                      fill=MUTED, font=(FONT, 8, "bold"))

    def _draw_margins(self, c, games, top, height, left):
        w = c.winfo_width()
        plot_w = w - left - 18
        bottom = top + height
        n = len(games)
        lo = min(0, min(g["margin"] for g in games) - 2)
        hi = max(0, max(g["margin"] for g in games) + 2)
        span = max(1, hi - lo)
        def x(i): return left + plot_w * ((i + 0.5) / n)
        def y(m): return bottom - ((m - lo) / span) * height
        zero_y = y(0)
        c.create_line(left, zero_y, w - 18, zero_y, fill=MUTED, dash=(2, 3))
        c.create_text(left - 6, zero_y, text="0", anchor="e",
                      fill=MUTED, font=(FONT, 8))
        for step in (10, 25):
            for m in range(step, hi, step):
                yy = y(m)
                c.create_line(left, yy, w - 18, yy, fill="#222838")
                c.create_text(left - 6, yy, text=str(m), anchor="e",
                              fill=MUTED, font=(FONT, 8))
            break
        for i, g in enumerate(games):
            xx = x(i)
            m = g["margin"]
            yy = y(m)
            color = WIN if m > 0 else (LOSS if m < 0 else MUTED)
            c.create_line(xx, zero_y, xx, yy, fill=color, width=3)
            c.create_oval(xx - 1.5, (zero_y + yy) / 2 - 1.5, xx + 1.5,
                          (zero_y + yy) / 2 + 1.5, outline="", fill=color)
        c.create_text((left + w - 18) // 2, top + 2, text="單場淨勝分",
                      fill=MUTED, font=(FONT, 8, "bold"))

    # ---------- 設定（功能 2 / 6） ----------
    def _build_settings(self):
        parent = self.tabs["settings"]

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=8, pady=(10, 4))
        tk.Label(row, text="關注隊伍（可複選）", bg=BG, fg=FG,
                 font=(FONT, 10, "bold")).pack(anchor="w")

        self.fav_box = tk.Frame(parent, bg=BG)
        self.fav_box.pack(fill="x", padx=8, pady=(2, 8))
        self.fav_vars: dict[str, tk.BooleanVar] = {}
        self.fav_checks: list[ttk.Checkbutton] = []

        opts = tk.Frame(parent, bg=BG)
        opts.pack(fill="x", padx=8, pady=(6, 4))
        self.notify_enabled = tk.BooleanVar(value=self.cfg["notify_enabled"])
        self.notify_tipoff = tk.BooleanVar(value=self.cfg["notify_tipoff"])
        self.notify_result = tk.BooleanVar(value=self.cfg["notify_result"])
        self.autostart = tk.BooleanVar(value=self.cfg["autostart"])
        self.start_minimized = tk.BooleanVar(value=self.cfg["start_minimized"])
        self.refresh_var = tk.IntVar(value=self.cfg["refresh_seconds"])
        self.preview_var = tk.IntVar(value=self.cfg["preview_days"])

        ttk.Checkbutton(opts, text="啟用通知", variable=self.notify_enabled).pack(anchor="w")
        ttk.Checkbutton(opts, text="　開賽前提醒",
                        variable=self.notify_tipoff).pack(anchor="w")
        ttk.Checkbutton(opts, text="　比賽結果通知",
                        variable=self.notify_result).pack(anchor="w")
        ttk.Checkbutton(opts, text="開機自動啟動", variable=self.autostart,
                        command=self._apply_autostart).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(opts, text="啟動時縮到背景（不顯示主視窗）",
                        variable=self.start_minimized).pack(anchor="w")

        timing = tk.Frame(parent, bg=BG)
        timing.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(timing, text="刷新間隔（秒）", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")
        ttk.Spinbox(timing, from_=15, to=600, increment=15, width=6,
                    textvariable=self.refresh_var).pack(side="left", padx=8)
        tk.Label(timing, text="　往後預覽天數", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left")
        ttk.Spinbox(timing, from_=1, to=14, width=5,
                    textvariable=self.preview_var).pack(side="left", padx=8)

        acts = tk.Frame(parent, bg=BG)
        acts.pack(fill="x", padx=8, pady=(10, 4))
        ttk.Button(acts, text="儲存設定", command=self._save_settings).pack(side="left")
        ttk.Button(acts, text="立即測試通知", command=self._test_notify).pack(side="left", padx=8)
        self.save_note = tk.Label(acts, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.save_note.pack(side="left")

    def _fill_favorites(self):
        teams = api.teams()
        for chk in self.fav_checks:
            chk.destroy()
        self.fav_checks.clear()
        self.fav_vars.clear()
        favorites = set(self.cfg["favorites"])
        for i, t in enumerate(teams):
            var = tk.BooleanVar(value=t["abbr"] in favorites)
            self.fav_vars[t["abbr"]] = var
            chk = ttk.Checkbutton(self.fav_box, text=f"{t['city']} {t['name']}",
                                  variable=var, command=self._quick_save_favs)
            chk.grid(row=i // 5, column=i % 5, sticky="w", padx=(0, 14), pady=1)
            self.fav_checks.append(chk)
        self._fill_team_picker()
        self._update_fav_label()

    def _fill_team_picker(self):
        teams = api.teams()
        labels = [f"{t['abbr']}　{t['full_name']}" for t in teams]
        current = self.team_var.get()
        self.team_box.configure(values=labels)
        if hasattr(self, "trend_box"):
            self.trend_box.configure(values=labels)
            if not self.trend_var.get() and self.team_var.get():
                self.trend_var.set(self.team_var.get())
        if not current:
            favs = self.cfg["favorites"]
            if favs:
                first = next((f for f in favs if api.team_by_abbr(f)), None)
                if first:
                    self.team_var.set(f"{(first + '　' + api.team_by_abbr(first)['full_name'])}")

    # ================= 資料載入 =================
    def _async(self, fn, key=None):
        def run():
            try:
                result = ("ok", fn())
            except Exception as exc:
                result = ("err", str(exc))
            self.worker.put((key, result))
        threading.Thread(target=run, daemon=True).start()

    def _cached(self, key, loader, on_done):
        hit = self.cache.get(key)
        if hit is not None:
            on_done(hit)
            return
        self._async(loader, key)

    def _load_scores(self):
        d = self.day
        self._cached(f"sb:{d:%Y%m%d}", lambda: api.scoreboard(d),
                     lambda data: self._draw_scores(f"{d:%Y%m%d}", data))

    def _draw_scores(self, stamp, games):
        """只畫出目前要看的那一天。

        使用者快速按 ◀ ▶ 時，先發出的請求可能後回來；
        若不看日期就直接畫，會把舊資料畫成今天。
        """
        if stamp != f"{self.day:%Y%m%d}":
            return
        self._render_scores(games, self.day, check_alerts=self.day == date.today())

    def _load_standings(self):
        self._cached(f"st:{self.season}", lambda: api.standings(self.season),
                     self._render_standings)

    def _load_schedule(self):
        days = max(1, min(14, int(self.preview_days.get() or 7)))
        self.preview_days.set(days)
        self._set_status(f"載入未來 {days} 天賽程…")
        self._async(lambda: self._fetch_upcoming(days), "upcoming")

    def _fetch_upcoming(self, days):
        out = []
        for offset in range(1, days + 1):
            d = date.today() + timedelta(days=offset)
            try:
                out.extend((d, g) for g in api.scoreboard(d))
            except api.NBAError:
                continue  # 單日失敗不要讓整段預覽掛掉
        return out

    def _load_team(self):
        abbr = self._current_team_abbr()
        if not abbr:
            return
        self.detail_abbr = abbr
        self.team_note.config(text="載入中…")
        # teams() 有記憶體快取，直接在這裡組，不要丟進背景執行緒。
        info = api.team_by_abbr(abbr)
        self._async(lambda: (info, api.roster(abbr),
                             self._team_schedule_with_fallback(abbr), abbr), f"team:{abbr}")

    def _team_schedule_with_fallback(self, abbr: str) -> list[dict]:
        """本季還沒開打（回傳 0~6 場）就退回上一季，讓近期戰績有東西看。"""
        schedule = api.team_schedule(abbr, self.season)
        if self.season is None and not any(g["final"] for g in schedule):
            try:
                prev = api.team_schedule(abbr, self.season_year() - 1)
            except api.NBAError:
                prev = []
            if prev:
                return prev
        return schedule

    def _drain(self):
        try:
            while True:
                key, (state, payload) = self.worker.get_nowait()
                if state == "err":
                    self._set_status(f"錯誤：{payload}")
                    if key and key.startswith("team:"):
                        self.team_note.config(text=f"載入失敗：{payload}")
                    elif key and key.startswith("bx:"):
                        self.bx_hint.config(text=f"載入失敗：{payload}")
                    elif key and key.startswith("pc:"):
                        self._render_player_card(key, {"error": payload})
                    continue
                if not key:
                    continue
                self.cache.put(key, payload)
                try:
                    if key.startswith("sb:"):
                        self._draw_scores(key[3:], payload)
                    elif key.startswith("st:"):
                        self._render_standings(payload)
                    elif key.startswith("upcoming"):
                        self._render_schedule(payload)
                    elif key.startswith("team:"):
                        self._render_team(payload)
                    elif key.startswith("bx:"):
                        self._render_boxscore(payload)
                    elif key.startswith("tnd:"):
                        self._render_trend(payload)
                    elif key.startswith("pl:"):
                        self._render_trend_playoff(payload)
                    elif key == "demo":
                        self._finish_demo(payload)
                    elif key.startswith("pc:"):
                        self._render_player_card(key, payload)
                    elif key.startswith("logo:"):
                        self._render_logo(key[5:], payload)
                except Exception as exc:
                    # 單一頁面畫錯不能讓整個 event loop 停擺，
                    # 否則 after() 鏈一斷，之後所有頁都不會再更新。
                    self._set_status(f"畫面更新失敗：{exc}")
        except queue.Empty:
            pass
        except Exception as exc:
            self._set_status(f"背景處理失敗：{exc}")
        self.after(120, self._drain)

    # ================= 繪製 =================
    def _render_scores(self, games, day, check_alerts: bool = False):
        self.current_games = games
        for child in self.cards.winfo_children():
            child.destroy()
        label = "今天" if day == date.today() else f"{day:%Y-%m-%d}"
        self.date_lbl.config(text=f"{label}　{'一二三四五六日'[day.weekday()]}")

        favs = set(self.cfg["favorites"])
        if check_alerts:
            self._check_alerts(games)

        # 關注隊伍的卡片本身有 ★ 與橙色框，「只看關注」則真的把其他場次濾掉。
        shown = games
        if self.fav_filter_var.get() and favs:
            shown = [g for g in games if api.favorites_of(g, favs)]

        if not shown:
            tk.Label(self.cards, text="當日沒有賽事", bg=BG, fg=MUTED,
                     font=(FONT, 12)).pack(pady=40)
            self._set_status("當日沒有賽事")
            return

        for g in shown:
            self._card(g, bool(api.favorites_of(g, favs)))
        n_fav = sum(1 for g in shown if api.favorites_of(g, favs))
        self._set_status(f"{len(shown)} 場比賽"
                         f"（關注 {n_fav} 場）　·　{datetime.now():%H:%M:%S}")

    def _card(self, g, is_fav):
        outer = tk.Frame(self.cards, bg=BG)
        outer.pack(fill="x", pady=(0, 8))
        if is_fav:
            bar = tk.Frame(outer, bg=BG, height=2)
            bar.pack(fill="x")
            tk.Frame(bar, bg=ACCENT, height=2).pack(fill="x")
        card = tk.Frame(outer, bg=CARD, highlightthickness=1,
                        highlightbackground=ACCENT if is_fav else "#2a3145")
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=10)

        state_color = {"in": ACCENT, "post": WIN, "pre": MUTED}.get(g["state"], MUTED)
        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")
        left_txt = g["detail"]
        if is_fav:
            left_txt = "★ " + left_txt
        tk.Label(top, text=left_txt, bg=CARD, fg=state_color,
                 font=(FONT, 9, "bold")).pack(side="left")
        if g.get("date"):
            tip = _tipoff_text(g["date"])
            if tip:
                tk.Label(top, text=tip, bg=CARD, fg=ACCENT,
                         font=(FONT, 9)).pack(side="left", padx=10)
        ttk.Button(top, text="單場數據", width=9,
                   command=lambda: self._open_boxscore(g)).pack(side="right")
        tk.Label(top, text=g["venue"], bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="right", padx=(6, 10))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        self._side(row, g["away"], g)
        tk.Label(row, text="  @  ", bg=CARD, fg=MUTED,
                 font=(FONT, 11, "bold")).pack(side="left")
        self._side(row, g["home"], g)

    def _side(self, parent, side, game):
        favs = set(self.cfg["favorites"])
        box = tk.Frame(parent, bg=CARD)
        box.pack(side="left", fill="x", expand=(side["home"]))
        fg = ACCENT if side["abbr"] in favs else FG
        tk.Label(box, text=side["abbr"], bg=CARD, fg=fg,
                 font=(FONT, 15, "bold")).pack(side="left")
        tk.Label(box, text=side["name"], bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(6, 0))
        # 勝負提示：已結束時把贏的那隊標綠
        color = FG
        if game["final"] and side["has_score"]:
            _, other = self._sides(game, side["abbr"])
            if other is not None and other["has_score"] \
                    and other["score"] != side["score"]:
                color = WIN if side["score"] > other["score"] else MUTED
        score_txt = str(side["score"]) if side["has_score"] else "-"
        if side["wins"]:
            tk.Label(box, text=side["wins"], bg=CARD, fg=MUTED,
                     font=(FONT, 9)).pack(side="left", padx=(10, 0))
        tk.Label(box, text=score_txt, bg=CARD, fg=color,
                 font=(FONT, 18, "bold")).pack(side="left", padx=(10, 0))

    def _render_schedule(self, rows):
        self.current_schedule = rows
        for item in self.sched_tree.get_children():
            self.sched_tree.delete(item)
        favs = set(self.cfg["favorites"])
        count = 0
        for d, g in rows:
            hits = api.favorites_of(g, favs)
            if self.only_fav_upcoming.get() and favs and not hits:
                continue
            when = g.get("date")
            local = _to_local(when)
            tipoff = _tipoff_text(when) if not (g["live"] or g["final"]) else g["detail"]
            self.sched_tree.insert("", "end", values=(
                f"{d:%m/%d} {'一二三四五六日'[d.weekday()]}",
                f"{local:%H:%M}" if local else "",
                g["name"], tipoff,
            ), tags=("fav",) if hits else ())
            count += 1
        self._set_status(f"未來賽程 {count} 場　·　{datetime.now():%H:%M:%S}")

    def _render_standings(self, rows):
        self.current_standings = rows
        self._draw_standings()

    @staticmethod
    def _filter_standings(rows, scope):
        """scope: 'all' | 'E' | 'W'. Conference split, sorted by record."""
        if scope == "E":
            rows = [r for r in rows if r["conference"].startswith("East")]
        elif scope == "W":
            rows = [r for r in rows if r["conference"].startswith("West")]
        return sorted(rows, key=lambda r: (-r["wins"], r["losses"]))

    def _stand_scope(self):
        return {"全聯盟": "all", "東區": "E", "西區": "W"}.get(
            self.stand_scope.get(), "all")

    def _draw_standings(self):
        rows = self._filter_standings(self.current_standings, self._stand_scope())
        for item in self.tree.get_children():
            self.tree.delete(item)
        favs = set(self.cfg["favorites"])
        for pos, row in enumerate(rows):
            played = row["wins"] + row["losses"]
            tags = []
            if row["abbr"] in favs:
                tags.append("fav")
            if row["abbr"] in self.cfg.get("playoffs", []):
                tags.append("playoff")
            self.tree.insert("", "end", iid=row["abbr"], values=(
                pos + 1 if played else "-",
                row["team"], row["wins"], row["losses"], row["pct"], row["gb"],
                row["streak"], row["home"], row["road"], row["diff"], row["ppg"],
            ), tags=tuple(tags), image=self._logos.get(row["abbr"]) or "")
        played = sum(r["wins"] + r["losses"] for r in rows) / max(len(rows), 1)
        self.stand_note.config(text=f"東、西部　·　各隊平均已打 {played:.1f} 場")
        self._ensure_logos([r["abbr"] for r in rows])

    def _render_boxscore(self, data):
        if data["event_id"] != str(self.boxscore_game):
            return
        self.current_boxscore = data
        self.current_plays = data.get("plays", []) if data.get("available") else []
        self._render_plays()
        game_meta = getattr(self, "boxscore_game_meta", {})
        if not data["available"]:
            self.bx_hint.config(text="此場尚未開賽或數據未出（ESPN 尚未提供）")
            for i, tree in enumerate(self.bx_trees):
                title = getattr(self, f"bx_title_{i}")
                team = (game_meta.get("away") if i == 0 else game_meta.get("home")) or {}
                title.config(text=f"{team.get('name', '')}　·　{game_meta.get('name', '')}")
                for item in tree.get_children():
                    tree.delete(item)
            return

        away, home = data["teams"]
        win_abbr = None
        if game_meta.get("final"):
            a, b = game_meta.get("away", {}), game_meta.get("home", {})
            if a.get("has_score") and b.get("has_score"):
                win_abbr = a["abbr"] if a["score"] > b["score"] else b["abbr"]
        score_txt = f"{win_abbr} 勝" if win_abbr else "進行中"
        detail = data.get("detail") or game_meta.get("detail", "")
        self.bx_hint.config(
            text=f"{game_meta.get('name', '')}　·　{detail}　·　"
                 f"{away['abbr']} {game_meta.get('away', {}).get('score', '')}"
                 f" - {game_meta.get('home', {}).get('score', '')} {home['abbr']}　·　{score_txt}")

        for i, (team, is_away) in enumerate(((away, True), (home, False))):
            tree = self.bx_trees[i]
            title = getattr(self, f"bx_title_{i}")
            title.config(text=f"{team['abbr']} {team['name']}　·　"
                              f"{'客場' if is_away else '主場'}")
            for item in tree.get_children():
                tree.delete(item)
            # 球隊總計列（先放）。
            totals = team["totals"]
            tree.insert("", "end", values=self._totals_values(totals), tags=("total",))
            for p in team["players"]:
                tag = "ejected" if p.get("ejected") else ("starter" if p.get("starter") else "bench")
                name = p["name"] + (" ⚠" if p.get("ejected") else "")
                values = (self._team_index(p), name) + tuple(p.get(k, "-") for k in api.BOX_COLUMNS)
                kw = {"iid": str(p.get("id"))} if p.get("id") else {}
                tree.insert("", "end", values=values, tags=(tag,), **kw)

    def _render_plays(self):
        tree = self.plays_tree
        for item in tree.get_children():
            tree.delete(item)
        only = self.plays_scoring_only.get()
        for p in reversed(self.current_plays):
            if only and not p["scoring"]:
                continue
            q = p["period"]
            qtxt = (f"Q{q}" if isinstance(q, int) and 1 <= q <= 4
                    else (f"OT{q - 4}" if isinstance(q, int) and q > 4 else str(q)))
            tree.insert("", "end", values=(
                qtxt, p["clock"], p["text"], f"{p['away']}-{p['home']}"),
                tags=("score",) if p["scoring"] else ())
        tree.tag_configure("score", foreground=ACCENT)

    # ---------- player card ----------
    _CARD_LABELS = {"GP": "出賽", "MIN": "上場時間", "PTS": "得分",
                    "REB": "籃板", "AST": "助攻", "STL": "抄截",
                    "BLK": "阻攻", "TO": "失誤", "FGP": "FG%",
                    "TPP": "3P%", "FTP": "FT%"}

    def _on_roster_open(self, _event=None):
        sel = self.roster_tree.selection()
        if not sel or not sel[0].isdigit():
            return
        pid = sel[0]
        players = (self.current_roster or {}).get("players", [])
        bio = next((p for p in players if str(p.get("id")) == pid), None)
        if bio is None:
            return
        info = getattr(self, "_team_info", None) or {}
        self._open_player_card(pid, dict(bio), self._team_season,
                               info.get("full_name", ""))

    def _on_boxscore_open(self, event=None):
        tree = event.widget if event is not None else None
        if tree is None:
            return
        sel = tree.selection()
        if not sel or not sel[0].isdigit():
            return
        pid = sel[0]
        data = self.current_boxscore or {}
        abbrs = [t.get("abbr") for t in data.get("teams", [])]
        meta = getattr(self, "boxscore_game_meta", {}) or {}
        season = _last_game_year([meta]) or None
        self._open_player_card(pid, None, season, abbrs)

    def _open_player_card(self, pid, bio, season, teams):
        """teams: display string (roster path) or abbr list (boxscore path)."""
        win = tk.Toplevel(self)
        win.title("球員卡")
        win.configure(bg=BG)
        win.geometry("430x560")
        win.resizable(False, False)
        win.transient(self)
        loading = tk.Label(win, text="載入中…", bg=BG, fg=MUTED, font=(FONT, 11))
        loading.pack(expand=True)
        win.bind("<Escape>", lambda _e: win.destroy())
        key = f"pc:{pid}:{id(win)}"
        self._card_windows[key] = (win, loading)
        self._async(lambda: self._player_payload(pid, bio, season, teams), key)

    @staticmethod
    def _player_payload(pid, bio, season, teams):
        """Worker: resolve bio (roster lookup when missing), fetch season
        averages and headshot bytes. Never raises: errors come back as
        {"error": msg} so the card window can show them."""
        try:
            if bio is None:
                abbrs = teams if isinstance(teams, list) else [teams]
                for abbr in abbrs:
                    if not abbr:
                        continue
                    try:
                        roster = api.roster(abbr)
                    except api.NBAError:
                        continue
                    hit = next((p for p in roster.get("players", [])
                                if str(p.get("id")) == pid), None)
                    if hit is not None:
                        bio = hit
                        break
            if bio is None:
                return {"error": "找不到球員資料"}
            stats = api.player_season_stats(pid, season)
            photo = None
            if bio.get("headshot"):
                try:
                    req = urllib.request.Request(bio["headshot"])
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        photo = resp.read()
                except Exception:
                    photo = None
            team = teams if isinstance(teams, str) else ""
            return {"bio": bio, "stats": stats, "photo": photo,
                    "team": team, "injured": bool(bio.get("injured"))}
        except api.NBAError as exc:
            return {"error": f"讀取失敗：{exc}"}

    def _render_player_card(self, key, payload):
        entry = self._card_windows.pop(key, None)
        if entry is None:
            return
        win, loading = entry
        if not win.winfo_exists():
            return
        loading.destroy()
        if payload.get("error"):
            tk.Label(win, text=payload["error"], bg=BG, fg=LOSS,
                     font=(FONT, 11)).pack(expand=True)
            return
        bio, stats = payload["bio"], payload["stats"]
        name = bio.get("name") or "球員"
        win.title(f"{name} 球員卡")
        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 8))
        photo = payload.get("photo")
        if photo:
            try:
                img = tk.PhotoImage(data=base64.b64encode(photo).decode("ascii"))
                f = max(1, img.width() // 110)
                shown = img.subsample(f) if f > 1 else img
                tk.Label(top, image=shown, bg=BG).pack(side="left", padx=(0, 12))
                win._photo = shown
            except Exception:
                pass
        info = tk.Frame(top, bg=BG)
        info.pack(side="left", fill="both", expand=True)
        tk.Label(info, text=name, bg=BG, fg=FG,
                 font=(FONT, 14, "bold"), anchor="w").pack(fill="x")
        if payload.get("team"):
            tk.Label(info, text=payload["team"], bg=BG, fg=MUTED,
                     font=(FONT, 10), anchor="w").pack(fill="x")
        line2 = "　·　".join(x for x in [
            bio.get("position") or "",
            ("#" + str(bio.get("jersey"))) if bio.get("jersey") else "",
            bio.get("height") or "", bio.get("weight") or "",
            str(bio.get("age") or ""), bio.get("college") or ""] if x)
        if line2:
            tk.Label(info, text=line2, bg=BG, fg=MUTED,
                     font=(FONT, 9), anchor="w").pack(fill="x")
        if payload.get("injured"):
            tk.Label(info, text="傷兵名單", bg=BG, fg=LOSS,
                     font=(FONT, 9, "bold"), anchor="w").pack(fill="x")
        s = stats.get("season")
        sub = f"{_season_label(s)}賽季場均"
        vals = dict(stats.get("rows", []))
        body = tk.Frame(win, bg=BG)
        body.pack(fill="x", padx=14, pady=(2, 10))
        tk.Label(body, text=sub if vals else sub + "　·　資料不足", bg=BG,
                 fg=ACCENT, font=(FONT, 10, "bold"), anchor="w").pack(
                     fill="x", pady=(0, 6))
        for k in ("GP", "MIN", "PTS", "REB", "AST", "STL", "BLK",
                  "TO", "FGP", "TPP", "FTP"):
            if k not in vals:
                continue
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=self._CARD_LABELS[k], bg=BG, fg=MUTED,
                     font=(FONT, 10)).pack(side="left")
            tk.Label(row, text=vals[k], bg=BG, fg=FG,
                     font=(FONT, 11, "bold")).pack(side="right")

    @staticmethod
    def _totals_values(totals: dict) -> tuple:
        names = {
            "fieldGoalsMade-fieldGoalsAttempted": "FG",
            "threePointFieldGoalsMade-threePointFieldGoalsAttempted": "3PT",
            "freeThrowsMade-freeThrowsAttempted": "FT",
            "totalRebounds": "REB",
            "assists": "AST",
            "turnovers": "TO",
            "steals": "STL",
            "blocks": "BLK",
            "offensiveRebounds": "OREB",
            "defensiveRebounds": "DREB",
            "fouls": "PF",
        }
        def find(*keys, default="-"):
            for k in keys:
                if totals.get(k):
                    return totals[k]
            return default
        return ("", "　合計",
                find("minutesPlayed", default="-"),
                find("points", default="-"),
                find("fieldGoalsMade-fieldGoalsAttempted", default="-"),
                find("threePointFieldGoalsMade-threePointFieldGoalsAttempted", default="-"),
                find("freeThrowsMade-freeThrowsAttempted", default="-"),
                find("totalRebounds", default="-"),
                find("assists", default="-"),
                find("turnovers", default="-"),
                find("steals", default="-"),
                find("blocks", default="-"),
                find("offensiveRebounds", default="-"),
                find("defensiveRebounds", default="-"),
                find("fouls", default="-"),
                "")

    @staticmethod
    def _team_index(p: dict) -> str:
        return "★" if p.get("starter") else ""

    # ---------- team logos ----------
    def _logo_path(self, abbr):
        return settings.app_dir() / "logos" / f"{abbr.lower()}.png"

    def _ensure_logos(self, abbrs):
        """Download missing logos in background, one worker for all."""
        todo = [a for a in abbrs
                if a and a not in self._logos and a not in self._logo_asked]
        if not todo:
            return
        self._logo_asked.update(todo)

        def run():
            for abbr in todo:
                data = None
                path = self._logo_path(abbr)
                if path.exists():
                    try:
                        data = path.read_bytes()
                    except OSError:
                        data = None
                if data is None:
                    try:
                        req = urllib.request.Request(
                            "https://a.espncdn.com/i/teamlogos/nba/500/"
                            f"{abbr.lower()}.png",
                            headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            data = resp.read()
                    except Exception:
                        data = None
                if data:
                    try:
                        path.parent.mkdir(exist_ok=True)
                        path.write_bytes(data)
                    except OSError:
                        pass
                self.worker.put((f"logo:{abbr}", ("ok", data)))

        threading.Thread(target=run, daemon=True).start()

    def _render_logo(self, abbr, data):
        if not data:
            self._logos[abbr] = None
            return
        try:
            img = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            f = max(1, img.width() // 25)
            shown = img.subsample(f) if f > 1 else img
            self._logos[abbr] = shown
            if self.tree.exists(abbr):
                self.tree.item(abbr, image=shown)
        except Exception:
            self._logos[abbr] = None

    def _render_team(self, payload):
        info, roster, schedule, abbr = payload
        if info is None:
            info = {"full_name": abbr, "abbr": abbr}
        played = [g for g in schedule if g["final"]]
        wins = sum(1 for g in played if self._won(g, abbr))
        losses = len(played) - wins
        record = f"{wins}-{losses}" if played else "本季尚未開打"

        self.team_info.config(
            text=f"{info['full_name'] if info else abbr}　·　{record}　·　"
                 f"教練 {roster['coach'] or '—'}　·　陣容 {len(roster['players'])} 人")
        # 本季若還沒開打，_team_schedule_with_fallback 已改抓上一季，這裡要說清楚。
        actual = _last_game_year(schedule)
        if self.season is None and actual and actual < self.season_year():
            self.team_note.config(
                text=f"（{self.season_year() - 1} 賽季尚未開打，顯示 "
                     f"{_season_label(actual)} 成績）")
        else:
            self.team_note.config(text="")
        self.current_roster = roster
        self._team_season = (self.season if self.season is not None
                             else (actual or None))
        self._team_info = info

        for item in self.roster_tree.get_children():
            self.roster_tree.delete(item)
        for p in roster["players"]:
            tag = "injured" if p["injured"] else ""
            label = f"{p['name']}{' (傷)' if p['injured'] else ''}"
            kw = {"iid": str(p.get("id"))} if p.get("id") else {}
            self.roster_tree.insert("", "end", values=(
                p["jersey"], label, p["position"], p["height"],
                p["weight"], p["age"]), tags=(tag,) if tag else (), **kw)

        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        recent = played[-8:][::-1]
        for g in recent:
            side, other = self._sides(g, abbr)
            if side is None:
                continue
            won = side["score"] > other["score"]
            local = _to_local(g.get("date"))
            self.recent_tree.insert("", "end", values=(
                f"{local:%m/%d}" if local else "",
                f"{other['abbr']} ({'主' if other['home'] else '客'})",
                "勝" if won else "負",
                f"{side['score']}-{other['score']}",
            ), tags=("win",) if won else ("loss",))

    @staticmethod
    def _sides(game, abbr):
        """回傳 (自己那隊, 對手)。"""
        return alerts._sides(game, abbr)

    def _won(self, game, abbr):
        side, other = self._sides(game, abbr)
        if side is None or other is None:
            return False
        if not side["has_score"] or not other["has_score"]:
            return False
        return side["score"] > other["score"]

    # ================= 通知 =================
    def _check_alerts(self, games):
        favs = self.cfg["favorites"]
        if not favs or not self.cfg["notify_enabled"]:
            return
        events = alerts.detect(self.seen_games, games, favs, TIPOFF_WINDOW)
        self.seen_games = games
        self._remember(games)
        for ev in events:
            kind = ev["kind"]
            if kind in ("tipoff", "soon") and not self.cfg["notify_tipoff"]:
                continue
            if kind == "result" and not self.cfg["notify_result"]:
                continue
            self._notify(ev["title"], ev["body"])

    def _remember(self, games):
        self.seen = {g["id"]: g["state"] for g in games}
        try:
            settings.save_state({"games": self.seen})
        except OSError:
            pass

    def _notify(self, title, body):
        color = ACCENT
        if "贏" in title:
            color = WIN
        elif "輸" in title:
            color = LOSS
        self._show_toast(title, body, color, 8000)
        system.toast(title, body)
        system.flash_taskbar(self.winfo_id(), 4)

    def _test_notify(self):
        self._show_toast("測試通知", "通知功能正常，選項會存進 settings.json",
                         ACCENT, 6000)
        if system.toast("NBA 追蹤小工具", "測試通知：一切正常。"):
            self.save_note.config(text="已送出測試通知")
        else:
            self.save_note.config(text="系統通知送出失敗，看程式內提示即可")

    def _show_toast(self, title, body, color=ACCENT, ms=5000):
        if self.toast is not None and self.toast.winfo_exists():
            self.toast.destroy()
        frame = tk.Frame(self, bg="#20263a", highlightthickness=1,
                         highlightbackground=color)
        frame.pack(side="top", fill="x", padx=14, pady=(10, 0))
        tk.Frame(frame, bg=color, width=4).pack(side="left", fill="y")
        box = tk.Frame(frame, bg="#20263a")
        box.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        tk.Label(box, text=title, bg="#20263a", fg=color, font=(FONT, 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(box, text=body, bg="#20263a", fg=FG, font=(FONT, 9),
                 anchor="w").pack(fill="x")
        self.toast = frame
        self.after(ms, self._hide_toast)

    def _hide_toast(self):
        if self.toast is not None and self.toast.winfo_exists():
            self.toast.destroy()
            self.toast = None

    # ================= 設定 =================
    def _quick_save_favs(self):
        self.cfg["favorites"] = sorted(k for k, v in self.fav_vars.items() if v.get())
        self._save_config()
        self._update_fav_label()
        self._update_fav_button()
        self._load_scores()
        self._fill_team_picker()

    def _save_config(self):
        try:
            self.cfg = settings.save(self.cfg)
            return True
        except OSError as exc:
            self._set_status(f"設定無法寫入：{exc}")
            return False

    def _save_settings(self):
        self.cfg["favorites"] = sorted(k for k, v in self.fav_vars.items() if v.get())
        self.cfg["notify_enabled"] = self.notify_enabled.get()
        self.cfg["notify_tipoff"] = self.notify_tipoff.get()
        self.cfg["notify_result"] = self.notify_result.get()
        self.cfg["autostart"] = self.autostart.get()
        self.cfg["start_minimized"] = self.start_minimized.get()
        self.cfg["refresh_seconds"] = int(self.refresh_var.get() or 60)
        self.cfg["preview_days"] = int(self.preview_var.get() or 7)
        self.refresh_var.set(self.cfg["refresh_seconds"])
        self.preview_var.set(self.cfg["preview_days"])
        if self._apply_autostart(save=False):
            if self._save_config():
                self.save_note.config(text="已儲存")
                self._update_fav_label()
                self._update_fav_button()
                self._load_scores()

    def _apply_autostart(self, save: bool = True):
        want = self.autostart.get()
        ok = system.set_autostart(want)
        if not ok:
            self.autostart.set(not want)
            self.save_note.config(text="無法變更開機啟動設定")
            return False
        actual = system.is_autostart_enabled()
        self.autostart.set(actual)
        self.cfg["autostart"] = actual
        if save:
            self._save_config()
        return True

    def _sync_autostart(self):
        actual = system.is_autostart_enabled()
        if actual != self.cfg["autostart"]:
            self.cfg["autostart"] = actual
            self.autostart.set(actual)
            self._save_config()

    def _update_fav_label(self):
        favs = self.cfg["favorites"]
        names = []
        for abbr in favs[:6]:
            t = api.team_by_abbr(abbr)
            names.append(abbr if not t else f"{t['city']} {t['name']}")
        more = f" ＋{len(favs) - 6} 隊" if len(favs) > 6 else ""
        self.fav_lbl.config(text=("關注：" + "、".join(names) + more) if favs else "尚未設定關注隊伍")

    def _update_fav_button(self):
        abbr = self._current_team_abbr()
        on = abbr in self.cfg["favorites"] if abbr else False
        self.team_fav_btn.configure(text="取消關注" if on else "加入關注")

    def _current_team_abbr(self):
        raw = self.team_var.get().strip()
        if not raw:
            return None
        # 正規化成 ESPN 的縮寫，後面所有 == 比較才對得上。
        return api.canon(raw.split("　")[0].split()[0])

    def _on_team_pick(self, _event=None):
        self._update_fav_button()
        self._load_team()

    def _toggle_fav_team(self):
        abbr = self._current_team_abbr()
        if not abbr:
            return
        favs = set(self.cfg["favorites"])
        if abbr in favs:
            favs.discard(abbr)
        else:
            favs.add(abbr)
        self.cfg["favorites"] = sorted(favs)
        if abbr in self.fav_vars:
            self.fav_vars[abbr].set(abbr in favs)
        self._save_config()
        self._update_fav_label()
        self._update_fav_button()
        self._load_scores()

    def _toggle_fav_only(self):
        self.fav_filter_var.set(not self.fav_filter_var.get())
        self.only_fav_btn.configure(
            text="顯示全部" if self.fav_filter_var.get() else "只看關注")
        self._redraw_scores()

    def _redraw_scores(self):
        if getattr(self, "current_games", None) is not None:
            self._render_scores(self.current_games, self.day)

    def _redraw_schedule(self):
        if self.current_schedule:
            self._render_schedule(self.current_schedule)

    def _on_tab(self, _event=None):
        sel = self.nb.select()
        if sel == str(self.tabs["standings"]):
            self._load_standings()
        elif sel == str(self.tabs["schedule"]):
            self._load_schedule()
        elif sel == str(self.tabs["teams"]):
            if self.roster_tree.get_children() and self.team_var.get():
                pass
            else:
                self._load_team()
        elif sel == str(self.tabs["trend"]):
            if not self.trend_var.get():
                self.trend_var.set(self.team_var.get())
            if self.trend_var.get():
                self._load_trend()
        elif sel == str(self.tabs["settings"]):
            if not self.fav_checks:
                self._fill_favorites()

    # ================= 迷你小工具（功能 4） =================
    def _toggle_widget(self):
        import widget
        if self.widget is not None and self.widget.winfo_exists():
            self.widget.destroy()
            self.widget = None
            self.cfg["mini_widget"] = False
            self._save_config()
            return
        self.widget = widget.MiniWidget(self)
        self.cfg["mini_widget"] = True
        self._save_config()

    # ================= 計時器與其他 =================
    def _on_season(self, _event=None):
        value = self.season_var.get()
        # 下拉選單顯示 "2025-26"，ESPN 的 season year 用結束年 2026。
        self.season = None if value == "本季" else int(value.split("-")[0]) + 1
        self.cache.drop_prefix("st:")
        self._load_standings()
        # 有在看的球隊就順便換成該季的近期戰績與走勢。
        if self._current_team_abbr():
            self.cache.drop_prefix("team:")
            self._load_team()
        if self.trend_var.get() and self.trend_season.get() != value:
            self.cache.drop_prefix("tnd:")
            self.trend_season.set(value)

    def _demo(self):
        """示範模式：自動載入指定隊上一季最後一天的完賽場次。

        只做「切換日期再載入」這件主程式本來就會做的事，再回呼
        _draw_scores／_open_boxscore，不新增任何資料流，所以不可能
        影響其他功能。開季後按「今天」就會回到即時賽程。
        """
        abbr = self.cfg["favorites"][0] if self.cfg["favorites"] else "GS"
        season = self.season_year() - 1  # 上一季（已完整打完）
        self._set_status(f"示範：載入 {abbr} 上一季最後一天…")
        self._async(lambda: self._demo_payload(abbr, season), "demo")

    @staticmethod
    def _demo_payload(abbr, season):
        """Demo worker: schedule -> last final -> the scoreboard date that
        actually lists that game. ESPN scoreboard dates are US Eastern, so a
        UTC date near midnight can belong to the previous scoreboard."""
        schedule = api.team_schedule(abbr, season)
        finals = [g for g in schedule if g.get("final")]
        if not finals:
            return (schedule, abbr, None)
        last = finals[-1]
        try:
            utc_day = _to_local(last.get("date")).date()
        except Exception:
            return (schedule, abbr, None)
        board_day = None
        for cand in (utc_day, utc_day - timedelta(days=1)):
            try:
                games = api.scoreboard(cand)
            except api.NBAError:
                continue
            if any(g["id"] == last["id"] for g in games):
                board_day = cand
                break
        return (schedule, abbr, board_day)

    def _finish_demo(self, payload):
        schedule, abbr = payload[0], payload[1]
        board_day = payload[2] if len(payload) > 2 else None
        finals = [g for g in schedule if g.get("final")]
        if not finals:
            self._set_status("找不到已完賽的示範場次")
            return
        last_day = finals[-1]
        if board_day is not None:
            self.day = board_day
        else:
            try:
                d = _to_local(last_day["date"])
            except Exception:
                d = None
            if d is not None:
                self.day = d.date()
        self._load_scores()
        # 順便打開當天第一場的單場數據，示範 boxscore。
        games = [g for g in finals if g.get("date", "")[:10] ==
                 (last_day["date"] or "")[:10]]
        if not games:
            games = finals[-3:]
        demo_game = games[0] if games else last_day
        self._demo_note = f"示範（{abbr} {_season_label(self.season_year() - 1)} 季）"
        self._open_boxscore(demo_game)
        self.bx_hint.config(
            text=f"{self._demo_note}　·　按比分明細「今天」即可回到即時賽程　·　"
                 f"{datetime.now():%H:%M:%S}")

    # ================= 計時器與其他 =================
    def _prev_day(self):
        self.day -= timedelta(days=1)
        self._load_scores()

    def _next_day(self):
        self.day += timedelta(days=1)
        self._load_scores()

    def _today(self):
        self.day = date.today()
        self._load_scores()

    def _manual(self):
        self.cache.clear()
        self.seen_games = []
        self._load_scores()
        self._tick()

    def _tick(self):
        self.current_tab = self.nb.select()
        if self.auto_var.get():
            target = self.current_tab
            if target == str(self.tabs["scores"]):
                self._load_scores()
            elif target == str(self.tabs["schedule"]):
                self._load_schedule()
            elif target == str(self.tabs["standings"]):
                self._load_standings()
        if self.widget is not None and self.widget.winfo_exists():
            self.widget.refresh()
        delay = max(15, self.cfg["refresh_seconds"]) * 1000
        self.after(delay, self._tick)

    def _set_status(self, text):
        self.status_var.set(text)

    @staticmethod
    def season_year() -> int:
        """ESPN 的 season year 指賽季起始年（2026-27 = 2027）。"""
        today = date.today()
        return today.year + 1 if today.month >= 7 else today.year

    @classmethod
    def _season_choices(cls):
        start = cls.season_year()
        return ["本季"] + [_season_label(y) for y in (start - 1, start - 2, start - 3)]


def _season_label(season_year: int) -> str:
    """ESPN season year 2026 對應 2025-26 賽季。"""
    return f"{season_year - 1}-{str(season_year)[2:]}"


def _last_game_year(schedule) -> int:
    for game in schedule:
        local = _to_local(game.get("date"))
        if local:
            return local.year if local.month < 7 else local.year + 1
    return 0


def _to_local(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _tipoff_text(dt_str):
    """未開賽時顯示倒數，例如「約 2 小時 15 分後」。"""
    local = _to_local(dt_str)
    if local is None:
        return ""
    mins = (local - datetime.now(local.tzinfo)).total_seconds() / 60
    if mins <= 0:
        return ""
    if mins < 60:
        return f"約 {int(mins)} 分鐘後"
    hours = mins / 60
    if hours < 24:
        return f"約 {int(hours)} 小時 {int(mins % 60)} 分後"
    return f"{int(hours // 24)} 天後"


def _enable_dpi_awareness():
    """Tell Windows the app handles DPI scaling itself.

    Without this, Tk looks blurry or tiny on high-DPI (e.g. 4K projector)
    screens because Windows bitmap-scales the whole window. Best effort:
    failure keeps the old behavior.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()  # older fallback
    except Exception:
        pass


def main():
    _enable_dpi_awareness()
    cfg = settings.load()
    app = App()
    app._fill_favorites()
    if cfg["mini_widget"]:
        app._toggle_widget()
    if cfg["start_minimized"]:
        app.withdraw()
    app.mainloop()


if __name__ == "__main__":
    main()
