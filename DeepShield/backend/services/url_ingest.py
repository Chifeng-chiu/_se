"""URL 鑑定: 直接影音連結下載, YouTube 等影音平台經 yt-dlp 抓取.

支援:
  - 直連 .mp4/.mp3/.wav/.m4a/.webm (串流下載, 上限 200MB)
  - YouTube (watch / shorts / youtu.be, 需 yt-dlp, 抓 720p 以下單檔)
不支援需登入的平台 (如 Facebook 私人影片) — 會回傳清楚的錯誤訊息.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import subprocess
import tempfile
import urllib.parse

MAX_MB = 200

_DIRECT_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".avi",
                ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus")
_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com",
             "youtu.be", "www.youtu.be", "youtube-nocookie.com")


def _blocked_host(host: str) -> bool:
    h = (host or "").lower().strip("[]")
    if h in ("localhost",):
        return True
    try:
        infos = socket.getaddrinfo(h, 80, type=socket.SOCK_STREAM)
    except Exception:
        return True  # 解析不出來就不抓
    for fam, _, _, _, addr in infos:
        try:
            ip = ipaddress.ip_address(addr[0] if isinstance(addr, tuple) else addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except Exception:
            return True
    return False


def _is_youtube(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except Exception:
        return False
    return host.lower() in _YT_HOSTS


_CT_MAP = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/m4a": ".m4a", "audio/x-m4a": ".m4a",
    "audio/flac": ".flac", "audio/ogg": ".ogg", "audio/opus": ".opus",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
    "video/x-matroska": ".mkv", "video/x-msvideo": ".avi",
}


def _head_content_type(url: str) -> str:
    try:
        import httpx
        h = httpx.head(url, timeout=15, follow_redirects=True,
                       headers={"User-Agent": "DeepShield/0.1"})
        return h.headers.get("content-type", "").lower().split(";")[0].strip()
    except Exception:
        return ""


def _suffix_for(url: str) -> str:
    """依網址副檔名或 content-type 決定暫存檔副檔名 (副檔名錯誤會讓後端誤判影音類型)."""
    low = urllib.parse.urlsplit(url).path.lower()
    for ext in _DIRECT_EXTS:
        if low.endswith(ext):
            return ext
    ct = _head_content_type(url)
    if ct in _CT_MAP:
        return _CT_MAP[ct]
    if ct.startswith("video/"):
        return ".mp4"
    if ct.startswith("audio/"):
        return ".mp3"
    return ""


def _download_direct(url: str, max_mb: int = MAX_MB) -> str:
    import httpx
    suffix = _suffix_for(url) or ".media"
    fd, tmp = tempfile.mkstemp(prefix="ds_url_", suffix=suffix)
    os.close(fd)
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True,
                          headers={"User-Agent": "DeepShield/0.1"}) as r:
            r.raise_for_status()
            size = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1024 * 256):
                    size += len(chunk)
                    if size > max_mb * 1024 * 1024:
                        raise ValueError(f"檔案超過 {max_mb}MB 上限")
                    f.write(chunk)
        return tmp
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


_FFMPEG_SHIM_DIR: str | None = None


def _ffmpeg_dir() -> str | None:
    """回傳一個內含 ffmpeg.exe 的目錄 (供 yt-dlp 合併影音).
    優先系統 ffmpeg；否則把 imageio-ffmpeg 內附的二進位複製一份改名快取。"""
    global _FFMPEG_SHIM_DIR
    import shutil
    if shutil.which("ffmpeg"):
        return None  # 系統已有，yt-dlp 自己找得到
    if _FFMPEG_SHIM_DIR and os.path.exists(os.path.join(_FFMPEG_SHIM_DIR, "ffmpeg.exe")):
        return _FFMPEG_SHIM_DIR
    try:
        from .utils import find_ffmpeg
        src = find_ffmpeg()
    except Exception:
        src = None
    if not src or not os.path.exists(src):
        return None
    d = os.path.join(tempfile.gettempdir(), "ds-ffmpeg")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "ffmpeg.exe")
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copyfile(src, dst)
    _FFMPEG_SHIM_DIR = d
    return d


def _download_youtube(url: str, max_mb: int = MAX_MB) -> str:
    import sys
    # 用「同一個 Python 解譯器」跑 yt-dlp 模組，不依賴 PATH 上有 yt-dlp.exe
    # (venv 未 activate 時 subprocess 會找不到指令，這是之前報錯的主因)
    try:
        import yt_dlp  # type: ignore  # noqa: F401
    except ImportError:
        raise RuntimeError("後端 venv 缺少 yt-dlp，請執行 pip install yt-dlp 後重啟後端")
    fd, tmp = tempfile.mkstemp(prefix="ds_yt_", suffix=".mp4")
    os.close(fd)
    # mkstemp 會預建一個 0-byte 空檔，必須先刪掉，否則 yt-dlp 會誤判
    # "has already been downloaded" 而跳過下載，留下空檔導致後續失敗
    try:
        os.remove(tmp)
    except Exception:
        pass
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist",
           "--max-filesize", f"{max_mb}M",
           "-f", "bv*[height<=720]+ba/b[height<=720]/b/best",
           "--merge-output-format", "mp4",
           "--no-warnings", "-o", tmp, url]
    ffdir = _ffmpeg_dir()
    if ffdir:
        # 插在 "python -m yt_dlp" 之後 (index 3)，不能放最前面否則會被直譯器誤吃
        cmd[3:3] = ["--ffmpeg-location", ffdir]
    r = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
        # yt-dlp 習慣把訊息寫 stdout，錯誤只看 stderr 會撲空，兩邊都收
        blob = ((r.stdout or "") + "\n" + (r.stderr or ""))
        lines = [ln for ln in blob.splitlines() if ln.strip()]
        err = "\n".join(lines[-4:])[-400:] or f"exit={r.returncode}"
        raise RuntimeError(f"YouTube 下載失敗 (可能為私人/地區限制/需登入影片): {err}")
    return tmp


def fetch_media(url: str, max_mb: int = MAX_MB) -> tuple[str, str]:
    """下載網址影音 → (暫存檔路徑, 來源類型 direct|youtube). 失敗拋錯 (訊息已中文化)."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        raise ValueError("請貼上 http(s) 開頭的完整網址")
    parts = urllib.parse.urlsplit(u)
    if _blocked_host(parts.hostname or ""):
        raise ValueError("基於安全考量，不抓取內網 / 私有位址")
    if _is_youtube(u):
        return _download_youtube(u, max_mb), "youtube"
    # 直連: 副檔名像媒體就直接抓; 否則先 HEAD 看 content-type
    low = parts.path.lower()
    if low.endswith(_DIRECT_EXTS):
        return _download_direct(u, max_mb), "direct"
    ctype = ""
    try:
        import httpx
        h = httpx.head(u, timeout=15, follow_redirects=True,
                       headers={"User-Agent": "DeepShield/0.1"})
        ctype = h.headers.get("content-type", "").lower()
    except Exception:
        ctype = ""
    if ctype.startswith(("video/", "audio/")):
        return _download_direct(u, max_mb), "direct"
    raise ValueError("這個網址看起來不是直連影音檔；目前支援：直連 mp4/mp3 等，或 YouTube 連結")
