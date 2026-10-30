# DeepShield backend 測試 (pytest)
# 執行: pytest -q  (在 backend/ 下, 需先 pip install -r requirements.txt pytest)

import base64
import io
import json

import numpy as np


def _wav_bytes(sr=16000, secs=3, kind="sine"):
    import soundfile as sf
    t = np.arange(sr * secs) / sr
    if kind == "sine":
        y = 0.4 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    else:  # 合成風格: 過度平滑 + 高頻極少
        y = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    return buf.getvalue(), y, sr


def test_semantic_scan_flags_scam():
    from services import semantic_scam_analyzer as sem
    r = sem.scan_text("現在加入老師的群組保證獲利, 趕快匯款")
    assert r["risk"] > 50
    assert any(h["keyword"] == "保證獲利" for h in r["hits"])


def test_semantic_safe_text():
    from services import semantic_scam_analyzer as sem
    r = sem.scan_text("今天天氣很好, 我們去公園散步吧")
    assert r["risk"] < 35


def test_audio_quick_scan_runs():
    from services import audio_forensics as af
    _, y, sr = _wav_bytes()
    r = af.quick_scan_chunk(y, sr)
    assert "risk" in r and 0 <= r["risk"] <= 100


def test_realtime_scanner_json_contract():
    from services.realtime_scanner import scan_realtime
    raw, _, _ = _wav_bytes()
    payload = {"timestamp": 12.5,
               "audio_b64": base64.b64encode(raw).decode(),
               "frames_b64": [],
               "transcript_snippet": "現在加入老師的群組保證獲利"}
    out = scan_realtime(payload)
    assert set(["timestamp", "trust_score", "status", "alerts",
                "transcript_snippet"]) <= set(out.keys())
    assert out["status"] in ("SAFE", "WARNING", "DANGER")
