"""DeepShield backend 全域設定."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "DeepShield Forensics API"
    version: str = "0.1.0"
    # 上傳暫存
    upload_dir: str = os.path.join(os.path.dirname(__file__), "uploads")
    max_upload_mb: int = 200
    # 取樣
    audio_sr: int = 16000
    realtime_audio_sr: int = 16000
    # 即時掃描門檻
    warn_threshold: int = 60   # trust_score < 60 → WARNING
    danger_threshold: int = 40  # trust_score < 40 → DANGER
    # 深度鑑識融合權重 (總和=1)
    w_audio: float = 0.30
    w_visual: float = 0.30
    w_avsync: float = 0.15
    w_semantic: float = 0.25
    # 預留: 深度學習權重路徑 (有檔才載入, 無檔走啟發式 baseline)
    audio_model_path: str = os.environ.get("DEEPSHIELD_AUDIO_MODEL", "")
    visual_model_path: str = os.environ.get("DEEPSHIELD_VISUAL_MODEL", "")
    whisper_model: str = os.environ.get("DEEPSHIELD_WHISPER_MODEL", "tiny")


settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
