"""模組 1: 語音鑑識分析器 (audio_forensics.py)

三個物理特徵子模組, 各回傳 0-100 風險:
  1. 高頻截斷 (High-Frequency Roll-off / Energy Ratio)
  2. 底噪連續性 (Noise Floor Consistency / Digital Zero)
  3. 微韻律與生理特徵 (Micro-prosody Jitter + Breath intervals)

並產生梅爾頻譜圖 (異常窗以紅框標示) 的 PNG base64 + 2 秒窗異常時間軸.

預留 DL 接口: `load_deep_model(path)` / `AUDIO_MODEL_PATH` env — 有 onnx/torch
權重時 `deep_score()` 會被 orchestrator 加權融合, 無權重時自動略過.
"""
from __future__ import annotations

import os

import numpy as np

MODEL_PATH = os.environ.get("DEEPSHIELD_AUDIO_MODEL", "")
_deep_model = None


def load_deep_model(path: str = MODEL_PATH):
    """預留: 載入語音深偽檢測權重 (onnx / torch). 無檔回傳 None."""
    global _deep_model
    if not path or not os.path.exists(path):
        return None
    try:
        if path.endswith(".onnx"):
            import onnxruntime as ort  # type: ignore
            _deep_model = ort.InferenceSession(path)
            return _deep_model
    except Exception:
        pass
    try:
        import torch  # type: ignore
        _deep_model = torch.load(path, map_location="cpu")
        return _deep_model
    except Exception:
        return None


def _mel_spectrogram_fig(logmel: np.ndarray, sr: int, hop: int,
                         anomaly_windows: list[dict], duration: float):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 3.2))
    fig.patch.set_facecolor("#0b1220")
    ax.set_facecolor("#0b1220")
    im = ax.imshow(logmel, origin="lower", aspect="auto", cmap="magma",
                   extent=[0, duration, 0, sr / 2])
    for w in anomaly_windows:
        ax.axvspan(w["start"], w["end"], color="red", alpha=0.22)
    ax.set_xlabel("time (s)", color="#9fb3c8")
    ax.set_ylabel("freq (Hz)", color="#9fb3c8")
    ax.set_title("Mel-Spectrogram (red = suspected anomaly window)",
                 color="#e2e8f0", fontsize=10)
    ax.tick_params(colors="#9fb3c8")
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("dB", color="#9fb3c8")
    cb.ax.yaxis.set_tick_params(color="#9fb3c8")
    fig.tight_layout()
    return fig


def _high_freq_risk(y: np.ndarray, sr: int) -> dict:
    """高頻能量比: AI 合成音常在 8kHz(或 Nyquist*0.75) 以上出現能量斷層."""
    import librosa
    nyq = sr / 2
    cutoff = min(8000.0, nyq * 0.75)
    S = np.abs(librosa.stft(y, n_fft=2048)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    hi = freqs >= cutoff
    total = float(S.sum()) + 1e-12
    hi_ratio = float(S[hi].sum() / total)
    # 經驗映射: 自然語音 hi_ratio 常見 0.03~0.15; <0.015 極可疑, <0.03 可疑
    if hi_ratio < 0.008:
        risk = 92.0
    elif hi_ratio < 0.015:
        risk = 75.0
    elif hi_ratio < 0.03:
        risk = 50.0
    elif hi_ratio < 0.06:
        risk = 20.0
    else:
        risk = 8.0
    roll = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
    return {"risk": risk, "hi_energy_ratio": round(hi_ratio, 5),
            "cutoff_hz": cutoff, "rolloff_mean_hz": round(roll, 1)}


def _noise_floor_risk(y: np.ndarray, sr: int) -> dict:
    """停頓底噪: 真實錄音停頓處仍有環境噪聲; 全零 digital silence 成片出現即為合成/剪接痕跡."""
    import librosa
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    if rms.size == 0 or float(rms.max()) <= 1e-9:
        return {"risk": 50.0, "note": "全靜音輸入", "digital_zero_ratio": 1.0}
    thresh = float(rms.max()) * 0.02
    quiet = rms < thresh
    quiet_ratio = float(quiet.mean())
    # 靜音幀中有多少是「數位絕對零」
    abs_y = np.abs(y)
    dzr = float((abs_y < 2e-4).mean())
    # 風險: 靜音佔比極高 + 絕對零佔比高 → 剪接/合成
    risk = 10.0
    if quiet_ratio > 0.55 and dzr > 0.35:
        risk = 85.0
    elif dzr > 0.35:
        risk = 65.0
    elif quiet_ratio > 0.6:
        risk = 45.0
    elif dzr > 0.15:
        risk = 35.0
    return {"risk": risk, "quiet_ratio": round(quiet_ratio, 3),
            "digital_zero_ratio": round(dzr, 4)}


def _prosody_risk(y: np.ndarray, sr: int, duration: float) -> dict:
    """F0 jitter 過度平滑 + 長句無換氣 → TTS/VC 可疑."""
    import librosa
    risk_parts: dict = {}
    try:
        try:  # librosa >= 0.11 / 1.x
            f0 = librosa.yin(y, fmin=50, fmax=500, sr=sr)
        except TypeError:  # librosa <= 0.10 舊參數名
            f0 = librosa.yin(y, f_min=50, f_max=500, sr=sr)
        voiced = f0[(f0 > 55) & (f0 < 490)]
        if voiced.size > 40:
            diffs = np.abs(np.diff(voiced)) / (np.mean(voiced) + 1e-9)
            jitter = float(np.median(diffs))
            f0std = float(np.std(voiced))
            # 自然 jitter 中位數約 0.01~0.06; <0.004 過度平滑
            if jitter < 0.002:
                jr = 80.0
            elif jitter < 0.004:
                jr = 60.0
            elif jitter < 0.008:
                jr = 30.0
            else:
                jr = 10.0
            if f0std < 8:
                jr = min(95.0, jr + 25)
            risk_parts.update(jitter=round(jitter, 5), f0_std=round(f0std, 1),
                              jitter_risk=jr)
        else:
            risk_parts.update(jitter=None, f0_std=None, jitter_risk=50.0,
                              note="voiced frames too few")
            jr = 50.0
    except Exception as e:  # yin 在極短音檔可能失敗
        risk_parts.update(error=str(e)[:120], jitter_risk=50.0)
        jr = 50.0
    # 換氣停頓: >0.35s 的靜音間隔
    try:
        intervals = librosa.effects.split(y, top_db=38)
        sr_f = float(sr)
        gaps = []
        prev_end = 0
        for s, e in intervals:
            if s - prev_end > int(0.35 * sr_f):
                gaps.append((prev_end / sr_f, s / sr_f))
            prev_end = e
        if duration - prev_end / sr_f > 0.35:
            gaps.append((prev_end / sr_f, duration))
        breath_per_min = len(gaps) / max(duration / 60.0, 1e-3)
        if duration > 18 and len(gaps) == 0:
            br = 70.0
        elif duration > 18 and breath_per_min < 1.5:
            br = 50.0
        else:
            br = 10.0
        risk_parts.update(breath_gaps=len(gaps),
                          breath_per_min=round(breath_per_min, 2),
                          breath_risk=br)
    except Exception:
        br = 50.0
        risk_parts.update(breath_risk=br)
    risk = round(0.6 * jr + 0.4 * br, 1)
    risk_parts["risk"] = risk
    return risk_parts


def _topk_mean(vals: list[float], frac: float = 0.25) -> float:
    """Top-K 聚合：取最高風險的前 frac 個視窗平均，避免長片平均稀釋峰值。"""
    import math
    if not vals:
        return 0.0
    k = max(1, int(math.ceil(len(vals) * frac)))
    top = sorted(vals, reverse=True)[:k]
    return float(sum(top) / len(top))


def analyze_audio_file(path: str, sr: int = 16000) -> dict:
    """主入口: 音檔路徑 → 風險 + XAI 證據. 永不拋錯 (失敗回傳 error 欄位)."""
    import librosa
    from .utils import fig_to_b64_png
    try:
        y, _sr = librosa.load(path, sr=sr, mono=True)
    except Exception as e:
        return {"risk": 0.0, "error": f"audio load failed: {e}"[:200],
                "subscores": {}, "anomalies": [], "spectrogram_b64": "",
                "duration": 0.0}
    duration = round(float(len(y)) / sr, 2)
    if len(y) < sr // 2:
        return {"risk": 0.0, "error": "audio too short (<0.5s)",
                "subscores": {}, "anomalies": [], "spectrogram_b64": "",
                "duration": duration}
    # —— 三子模組 (全域統計，供證據展示) ——
    hf = _high_freq_risk(y, sr)
    nf = _noise_floor_risk(y, sr)
    pr = _prosody_risk(y, sr, duration)

    # —— 2 秒窗時間軸 + 逐窗風險 (Top-K 聚合用) ——
    import librosa as _lb
    win, hop = sr * 2, sr * 2
    anomalies: list[dict] = []
    window_risks: list[float] = []
    S = np.abs(_lb.stft(y, n_fft=2048)) ** 2
    freqs = _lb.fft_frequencies(sr=sr, n_fft=2048)
    hi_mask = freqs >= min(8000.0, (sr / 2) * 0.75)
    n_frames_total = S.shape[1]
    for i, s0 in enumerate(range(0, len(y), hop)):
        seg = y[s0:s0 + win]
        if len(seg) < sr // 2:
            break
        # 該窗對應的頻譜幀
        f0 = int(s0 / len(y) * n_frames_total)
        f1 = max(f0 + 1, int(min(n_frames_total, (s0 + len(seg)) / len(y) * n_frames_total)))
        segS = S[:, f0:f1]
        tot = float(segS.sum()) + 1e-12
        hi_r = float(segS[hi_mask].sum() / tot)
        rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
        reasons = []
        w_risk = 8.0
        if hi_r < 0.015 and rms > 0.01:
            reasons.append(f"高頻能量異常低 (hi_ratio={hi_r:.4f})")
            w_risk = max(w_risk, 75.0)
        if rms < 1e-4:
            reasons.append("數位絕對靜音疑似剪接點")
            w_risk = max(w_risk, 70.0)
        if len(reasons) == 2:
            w_risk = 85.0
        window_risks.append(w_risk)
        if reasons:
            anomalies.append({"start": round(s0 / sr, 2),
                              "end": round(min(len(y), s0 + win) / sr, 2),
                              "type": "AUDIO_ANOMALY",
                              "description": "; ".join(reasons)})

    # —— Top-K 聚合：前 25% 最高風險視窗平均 (長片峰值不被平均稀釋) ——
    win_topk = _topk_mean(window_risks)
    risk = round(0.8 * win_topk + 0.2 * pr["risk"], 1)

    # —— 窄頻豁免：極端高頻截斷 + 韻律自然 + 低滾降 → 疑似真實窄頻通道
    # (老電話錄音/戶外舊影片)，封頂 55；韻律機械化則不豁免 (AI 窄頻仍抓)
    channel_note = ""
    rolloff = float(hf.get("rolloff_mean_hz", 0) or 0)
    jitter_r = float(pr.get("jitter_risk", 50.0))
    if hf["risk"] >= 85 and jitter_r <= 20 and 0 < rolloff < 3000 and duration >= 3:
        if risk > 55:
            risk = 55.0
            channel_note = (f"疑似真實窄頻通道 (rolloff={rolloff:.0f}Hz 且韻律自然)，"
                            "音訊風險封頂 55；AI 窄頻合成仍可能漏判")

    # —— 頻譜圖 ——
    try:
        mel = _lb.feature.melspectrogram(y=y, sr=sr, n_mels=96)
        _to_db = getattr(_lb, "power_to_db", None) or getattr(_lb, "power_to_dB")
        logmel = _to_db(mel, ref=np.max)
        fig = _mel_spectrogram_fig(logmel, sr, 512, anomalies, duration)
        spec_b64 = fig_to_b64_png(fig)
    except Exception:
        spec_b64 = ""

    # —— 預留 DL 模型融合 ——
    dl_note = None
    if _deep_model is None and MODEL_PATH:
        load_deep_model()

    return {
        "risk": risk,
        "level": "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER"),
        "duration": duration,
        "subscores": {
            "high_freq_truncation": {"risk": hf["risk"], **{k: v for k, v in hf.items() if k != "risk"}},
            "noise_floor": {"risk": nf["risk"], **{k: v for k, v in nf.items() if k != "risk"}},
            "prosody_breath": {"risk": pr["risk"], **{k: v for k, v in pr.items() if k != "risk"}},
            "window_topk": {"risk": win_topk, "windows": len(window_risks),
                            "method": "mean of top 25% risky 2s windows"},
            "channel_profile": {"capped": bool(channel_note), "detail": channel_note},
        },
        "anomalies": anomalies,
        "spectrogram_b64": spec_b64,
        "deep_model": dl_note or ("inactive (no weights)" if _deep_model is None else "active"),
    }


def quick_scan_chunk(y: np.ndarray, sr: int = 16000) -> dict:
    """輕量版 (供 WS 即時掃描, <100ms): 只算高頻比 + RMS, 不畫圖不跑 yin."""
    if y is None or len(y) == 0:
        return {"risk": 0.0, "alerts": []}
    y = np.asarray(y, dtype=np.float32)
    # 高頻比 (FFT 近似)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1 / sr)
    cutoff = min(8000.0, (sr / 2) * 0.75)
    hi_r = float(spec[freqs >= cutoff].sum() / (spec.sum() + 1e-12))
    rms = float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))
    risk = 10.0
    alerts: list[str] = []
    if rms > 0.01 and hi_r < 0.015:
        risk = 78.0
        alerts.append("偵測到高頻音訊截斷特徵 (疑似 AI 合成)")
    elif rms > 0.01 and hi_r < 0.03:
        risk = 52.0
        alerts.append("高頻能量偏低, 建議送交深度鑑識")
    if rms < 1e-4:
        alerts.append("音訊接近靜音, 暫不評分")
        risk = min(risk, 5.0)
    return {"risk": round(risk, 1), "hi_ratio": round(hi_r, 5),
            "rms": round(rms, 5), "alerts": alerts}
