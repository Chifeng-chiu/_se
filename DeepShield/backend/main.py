"""DeepShield FastAPI 入口.

- GET  /api/v1/health
- POST /api/v1/analyze/deep        (模式 A: 上傳 mp4/mp3/wav)
- WS   /api/v1/ws/realtime-scan    (模式 B: 每 2 秒 JSON 切片)
- POST /api/v1/session/{id}        (模式 B→A 交接: 暫存攔截報告 30 分鐘)
- GET  /api/v1/session/{id}        (模式 A: 讀取交接報告, 解跨網域 localStorage 問題)

啟動: uvicorn main:app --reload --port 8000  (在 backend/ 下執行)
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from services.orchestrator import run_deep_analysis
from services.realtime_scanner import scan_realtime

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開發期全開; 上線請收斂為 dashboard / extension origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi",
                ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}


@app.get("/api/v1/health")
def health():
    feats = {}
    for mod, pkg in [("opencv", "cv2"), ("librosa", "librosa"),
                     ("mediapipe", "mediapipe"), ("whisper", "faster_whisper"),
                     ("onnx", "onnxruntime")]:
        try:
            __import__(pkg)
            feats[mod] = True
        except Exception:
            feats[mod] = False
    try:
        from services.utils import find_ffmpeg
        feats["ffmpeg"] = find_ffmpeg() or "missing (visual ok, audio-from-video degraded)"
    except Exception:
        feats["ffmpeg"] = False
    return {"status": "ok", "version": settings.version, "features": feats}


@app.post("/api/v1/analyze/deep")
async def analyze_deep(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支援的格式 {ext}, 支援: {sorted(ALLOWED_EXTS)}")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"檔案超過 {settings.max_upload_mb}MB 上限")
    tmp = os.path.join(settings.upload_dir, f"{uuid.uuid4().hex}{ext}")
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        report = run_deep_analysis(tmp)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    report["filename"] = file.filename
    return JSONResponse(report)


class UrlRequest(BaseModel):
    url: str
    max_mb: int = 200


@app.post("/api/v1/analyze/url")
async def analyze_url(body: UrlRequest):
    """用網址鑑定: 直連影音檔或 YouTube 連結, 下載後走同一套深度鑑識."""
    from services.url_ingest import fetch_media
    max_mb = max(5, min(body.max_mb or 200, settings.max_upload_mb))
    try:
        tmp, kind = fetch_media(body.url, max_mb=max_mb)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"下載失敗: {str(e)[:150]}")
    try:
        report = run_deep_analysis(tmp)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    report["filename"] = body.url
    report["source"] = f"url:{kind}"
    return JSONResponse(report)


@app.websocket("/api/v1/ws/realtime-scan")
async def realtime_scan(ws: WebSocket):
    await ws.accept()
    t0 = time.time()
    try:
        while True:
            try:
                payload = await ws.receive_json()
            except Exception:
                # 二進位/純文字訊息: 忽略並提示
                try:
                    await ws.send_json({"timestamp": round(time.time() - t0, 2),
                                        "trust_score": 100.0, "status": "SAFE",
                                        "alerts": ["請傳送 JSON {audio_b64, frames_b64, transcript_snippet}"],
                                        "transcript_snippet": ""})
                    continue
                except Exception:
                    break
            try:
                result = scan_realtime(payload if isinstance(payload, dict) else {},
                                       t0=t0)
                # 若 client 沒帶 timestamp, 用 server elapsed
                if not isinstance(payload.get("timestamp"), (int, float)):
                    result["timestamp"] = round(time.time() - t0, 2)
                await ws.send_json(result)
            except Exception as e:
                await ws.send_json({"timestamp": round(time.time() - t0, 2),
                                    "trust_score": 50.0, "status": "WARNING",
                                    "alerts": [f"掃描失敗: {str(e)[:120]}"],
                                    "transcript_snippet": ""})
    except WebSocketDisconnect:
        pass


# ---------- 模式 B→A 交接: 輕量記憶體暫存 (解跨網域 localStorage 問題) ----------
class SessionPayload(BaseModel):
    report: dict
    mediaKind: str = "video"
    label: str = ""

_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()
SESSION_TTL_SEC = 30 * 60
SESSION_MAX = 200
_SID_RX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _prune_sessions() -> None:
    now = time.time()
    dead = [k for k, v in _sessions.items() if now - v["savedAt"] > SESSION_TTL_SEC]
    for k in dead:
        _sessions.pop(k, None)
    while len(_sessions) > SESSION_MAX:  # 太多時淘汰最舊
        oldest = min(_sessions, key=lambda k: _sessions[k]["savedAt"])
        _sessions.pop(oldest, None)


@app.post("/api/v1/session/{session_id}")
def save_session(session_id: str, payload: SessionPayload):
    if not _SID_RX.match(session_id):
        raise HTTPException(400, "invalid session_id")
    if not isinstance(payload.report, dict) or "fake_probability" not in payload.report:
        raise HTTPException(400, "report must be a DeepReport-like object")
    with _sessions_lock:
        _prune_sessions()
        _sessions[session_id] = {"report": payload.report,
                                 "mediaKind": payload.mediaKind,
                                 "label": payload.label,
                                 "savedAt": time.time()}
    return {"ok": True, "session_id": session_id}


@app.get("/api/v1/session/{session_id}")
def load_session(session_id: str):
    if not _SID_RX.match(session_id):
        raise HTTPException(400, "invalid session_id")
    with _sessions_lock:
        item = _sessions.get(session_id)
        if item and time.time() - item["savedAt"] > SESSION_TTL_SEC:
            _sessions.pop(session_id, None)
            item = None
        if not item:
            raise HTTPException(404, "session not found or expired")
        return {"report": item["report"], "mediaKind": item["mediaKind"],
                "label": item["label"], "savedAt": item["savedAt"]}
