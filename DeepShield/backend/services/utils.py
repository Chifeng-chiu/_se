"""共用工具: 音訊抽取 / base64 / 影像編碼.

設計原則: 在沒有系統 ffmpeg 的 Windows 機器上也能跑。
優先順序: 系統 ffmpeg → imageio-ffmpeg 內附二進位 → 直接失敗並回傳 None (上層降級)。
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tempfile

import cv2
import numpy as np


def find_ffmpeg() -> str | None:
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    try:
        import imageio_ffmpeg  # type: ignore

        cand = imageio_ffmpeg.get_ffmpeg_exe()
        if cand and os.path.exists(cand):
            return cand
    except Exception:
        pass
    return None


def extract_audio_to_wav(video_path: str, sr: int = 16000) -> str | None:
    """從影片抽出單聲道 wav, 回傳暫存檔路徑; 失敗回傳 None."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = [ffmpeg, "-y", "-v", "error", "-i", video_path,
           "-ac", "1", "-ar", str(sr), "-f", "wav", out]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
    except Exception:
        pass
    try:
        if os.path.exists(out):
            os.remove(out)
    except Exception:
        pass
    return None


def is_audio_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm")


def b64_of_bgr(img_bgr: np.ndarray) -> str:
    """BGR ndarray → JPEG base64 (給前端 <img src=data:...> 直接渲染)."""
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")


def fig_to_b64_png(fig) -> str:
    """matplotlib Figure → PNG base64, 並關閉 fig 避免記憶體洩漏."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                facecolor="#0b1220")
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass
    return base64.b64encode(buf.getvalue()).decode("ascii")


def decode_audio_b64_to_pcm(audio_b64: str, target_sr: int = 16000) -> tuple[np.ndarray, int] | tuple[None, None]:
    """把 WS 傳來的 audio chunk (wav/webm/raw base64) 解成 mono float32 PCM.

    策略: 先試 soundfile 讀 BytesIO (wav/flac/ogg); 失敗則試 raw int16; 再失敗回傳 (None, None).
    """
    import soundfile as sf
    raw = base64.b64decode(audio_b64)
    # 1) 當作容器格式讀
    try:
        y, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
        if getattr(y, "ndim", 1) == 2:
            y = np.mean(y, axis=1)
        if sr != target_sr and len(y) > 0:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        return np.asarray(y, dtype=np.float32), int(sr)
    except Exception:
        pass
    # 2) 當作 raw s16le 猜測 (extension 端 MediaRecorder 轉碼失敗時的退路)
    try:
        if len(raw) >= 320:
            y = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            return y, target_sr
    except Exception:
        pass
    return None, None


def decode_frame_b64_to_bgr(frame_b64: str) -> np.ndarray | None:
    try:
        raw = base64.b64decode(frame_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None
