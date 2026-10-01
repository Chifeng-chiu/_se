"""設定與狀態持久化（settings.json / state.json）。"""

import json
import os
import sys
import tempfile
from pathlib import Path


def app_dir() -> Path:
    """程式資料夾。打包成 exe 時用 exe 所在資料夾，開發時用腳本資料夾。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


SETTINGS_FILE = app_dir() / "settings.json"
STATE_FILE = app_dir() / "state.json"

DEFAULTS = {
    # ESPN 對勇士的縮寫是 GS（不是 GSW），這裡的值必須是 teams() 拿得到的縮寫。
    "favorites": ["GS", "LAL"],
    "notify_enabled": True,
    "notify_tipoff": True,
    "notify_result": True,
    "refresh_seconds": 60,
    "preview_days": 7,
    "autostart": False,
    "start_minimized": False,
    "mini_widget": False,
}

from nba_api import ABBR_ALIASES  # 縮寫正規化規則只有一份


# 存檔用暫存 + 置換，避免程式中途關掉時留下半個 JSON。
def _atomic_write(path: Path, payload: dict):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        # 檔案壞掉就當沒設定過，不要讓程式開不起來。
        return {}


def _normalize(cfg: dict) -> dict:
    """把值收斂到合法範圍，存檔與讀檔都走這裡。"""
    out = dict(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    favs = out.get("favorites")
    if not isinstance(favs, list):
        favs = []
    cleaned = {str(x).strip().upper() for x in favs if str(x).strip()}
    # 關聯縮寫，讓常見的 "GSW" 自動對應到 ESPN 實際使用的 "GS"。
    # 正規化後再去重一次，否則 "GSW" + "GS" 會留下兩個 "GS"。
    out["favorites"] = sorted({ABBR_ALIASES.get(f, f) for f in cleaned})[:30]
    # 用預設值時要判 None 而不是 falsy，否則 0 會被當成「沒設定」而跳成 60。
    out["refresh_seconds"] = _clamp(out.get("refresh_seconds"), 60, 15, 600)
    out["preview_days"] = _clamp(out.get("preview_days"), 7, 1, 14)
    return out


def _clamp(value, default: int, low: int, high: int) -> int:
    try:
        if value is None or value == "":
            return default
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def load() -> dict:
    return _normalize(_read(SETTINGS_FILE))


def save(cfg: dict) -> dict:
    merged = _normalize(cfg)
    _atomic_write(SETTINGS_FILE, merged)
    return merged


def load_state() -> dict:
    return _read(STATE_FILE)


def save_state(state: dict):
    _atomic_write(STATE_FILE, state)
