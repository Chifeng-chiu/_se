"""置頂迷你比分小工具：只看關注隊伍，釘在工作角落。"""

import tkinter as tk

import alerts

BG = "#151922"
CARD = "#222838"
FG = "#e8ecf4"
MUTED = "#8b93a7"
ACCENT = "#f9a11b"
WIN = "#4ade80"
FONT = "Segoe UI"


class MiniWidget(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("NBA 迷你比分")
        self.configure(bg=BG)
        self.geometry("290x150")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.overrideredirect(False)
        self._place_corner()

        self.favs_lbl = tk.Label(self, text="", bg=BG, fg=MUTED, font=(FONT, 8, "bold"))
        self.favs_lbl.pack(anchor="w", padx=10, pady=(8, 2))
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(foot, text="拖曳移動　·　雙擊開主視窗", bg=BG, fg=MUTED,
                 font=(FONT, 7)).pack(side="left")
        tk.Button(foot, text="×", command=self.close_widget, bg="#2a3040",
                  fg=MUTED, relief="flat", bd=0, font=(FONT, 9),
                  activebackground="#3a4256", activeforeground=FG).pack(side="right")

        self.bind("<ButtonPress-1>", self._drag)
        self.bind("<Double-Button-1>", self._open_main)
        self.after(400, self.refresh)

    def _place_corner(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x, y = sw - self.winfo_width() - 30, sh - self.winfo_height() - 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _drag(self, event):
        self._offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _open_main(self, _event=None):
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()

    def close_widget(self):
        self.app._toggle_widget()

    def refresh(self):
        for child in self.body.winfo_children():
            child.destroy()

        games = getattr(self.app, "current_games", None) or []
        favs = set(self.app.cfg["favorites"])
        mine = [g for g in games if any(s["abbr"] in favs for s in (g["away"], g["home"]))]
        self.favs_lbl.config(text="關注：" + ("、".join(sorted(favs)) if favs else "未設定"))

        if not mine:
            tk.Label(self.body, text="今日沒有關注隊伍的比賽", bg=BG, fg=MUTED,
                     font=(FONT, 9)).pack(pady=18)
            return

        for game in mine[:4]:
            row = tk.Frame(self.body, bg=CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=game["detail"], bg=CARD, fg=ACCENT if game["live"] else MUTED,
                     font=(FONT, 7, "bold")).pack(anchor="w", padx=6, pady=(3, 0))
            line = tk.Frame(row, bg=CARD)
            line.pack(fill="x", padx=6, pady=(0, 4))
            self._team(line, game["away"], game)
            tk.Label(line, text=" @ ", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left")
            self._team(line, game["home"], game)

    @staticmethod
    def _team(parent, side, game):
        _, other = alerts._sides(game, side["abbr"])
        color = FG
        if game["final"] and side["has_score"] and other is not None \
                and other["has_score"] and side["score"] != other["score"]:
            color = WIN if side["score"] > other["score"] else MUTED
        tk.Label(parent, text=side["abbr"], bg=CARD, fg=color,
                 font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(parent, text=str(side["score"]) if side["has_score"] else "-",
                 bg=CARD, fg=color, font=(FONT, 10, "bold")).pack(side="left", padx=(3, 0))
