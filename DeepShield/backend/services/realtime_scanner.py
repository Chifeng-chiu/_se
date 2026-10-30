"""即時掃描 (模式 B 輕量路徑): <300ms 內回傳 trust_score + alerts."""
from __future__ import annotations

import time

import numpy as np

try:
    from config import settings
except ImportError:
    from ..config import settings  # type: ignore[no-redef]
try:
    from services.utils import decode_audio_b64_to_pcm, decode_frame_b64_to_bgr
except ImportError:
    from .utils import decode_audio_b64_to_pcm, decode_frame_b64_to_bgr  # type: ignore[no-redef]


def scan_realtime(payload: dict, t0: float | None = None) -> dict:
    from . import audio_forensics, semantic_scam_analyzer, visual_forensics

    ts = round(time.time() - (t0 or time.time()), 2) if t0 else 0.0
    # 呼叫端可傳 timestamp; 沒傳就用 server elapsed=0
    if isinstance(payload.get("timestamp"), (int, float)):
        ts = float(payload["timestamp"])

    alerts: list[str] = []
    risks: list[tuple[float, float]] = []  # (risk, weight)

    # —— 音訊快掃 ——
    if payload.get("audio_b64"):
        y, sr = decode_audio_b64_to_pcm(payload["audio_b64"],
                                        target_sr=settings.realtime_audio_sr)
        if y is not None and len(y) > 0:
            r = audio_forensics.quick_scan_chunk(np.asarray(y), sr or 16000)
            risks.append((r["risk"], 0.5))
            alerts.extend(r.get("alerts", []))
    # —— 影像快掃 ——
    frames = []
    for fb in (payload.get("frames_b64") or [])[:4]:
        img = decode_frame_b64_to_bgr(fb)
        if img is not None:
            frames.append(img)
    if frames:
        r = visual_forensics.quick_scan_frames(frames)
        risks.append((r["risk"], 0.3))
        alerts.extend(r.get("alerts", []))
    # —— 語意快掃 ——
    snippet = (payload.get("transcript_snippet") or "").strip()
    if snippet:
        r = semantic_scam_analyzer.scan_text(snippet)
        risks.append((r["risk"], 0.6 if r["risk"] >= 50 else 0.2))
        for h in r.get("hits", [])[:5]:
            alerts.append(f"觸發高風險詐騙詞彙: {h['keyword']}")

    if not risks:
        return {"timestamp": ts, "trust_score": 100.0, "status": "SAFE",
                "alerts": ["等待影音輸入..."], "transcript_snippet": snippet}

    wsum = sum(w for _, w in risks)
    fake = sum(r * w for r, w in risks) / wsum
    trust = round(100 - fake, 1)
    status = ("SAFE" if trust >= settings.warn_threshold else
              ("WARNING" if trust >= settings.danger_threshold else "DANGER"))
    if not alerts and status == "SAFE":
        alerts = ["目前無異常"]
    return {"timestamp": ts, "trust_score": trust, "status": status,
            "alerts": alerts[:8], "transcript_snippet": snippet}
