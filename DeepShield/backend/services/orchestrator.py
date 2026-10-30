"""編排器: 深度鑑識 (模式 A) — 融合 4 大模組, 產出統一報告 JSON."""
from __future__ import annotations

import datetime
import hashlib
import os

try:  # uvicorn main:app (cwd=backend) → services 為頂層套件, 用絕對路徑
    from config import settings
except ImportError:  # 以套件形式被引用時的退路
    from ..config import settings  # type: ignore[no-redef]
try:
    from services.utils import extract_audio_to_wav, is_audio_file
except ImportError:
    from .utils import extract_audio_to_wav, is_audio_file  # type: ignore[no-redef]


def _weights():
    return {"audio": settings.w_audio, "visual": settings.w_visual,
            "avsync": settings.w_avsync, "semantic": settings.w_semantic}


def run_deep_analysis(media_path: str) -> dict:
    from . import audio_forensics, av_sync_analyzer, semantic_scam_analyzer, visual_forensics

    audio_only = is_audio_file(media_path)
    audio_path = media_path if audio_only else extract_audio_to_wav(media_path, sr=settings.audio_sr)
    if audio_path is None and not audio_only:
        audio_path = ""  # 降級: 無音軌仍可做 visual

    # 1) 語音
    try:
        audio_res = audio_forensics.analyze_audio_file(audio_path or media_path) \
            if (audio_path or audio_only) else \
            {"risk": 0.0, "level": "SAFE", "note": "無可用音軌, 語音維度略過",
             "subscores": {}, "anomalies": [], "spectrogram_b64": "", "duration": 0.0}
    except Exception as e:
        audio_res = {"risk": 0.0, "error": str(e)[:150], "anomalies": [],
                     "spectrogram_b64": "", "subscores": {}}

    # 2) 視覺 (純音檔則略過)
    try:
        visual_res = {"risk": 0.0, "level": "SAFE", "note": "純音檔, 視覺維度略過",
                      "anomalies": [], "heatmap_b64": "", "subscores": {}} \
            if audio_only else visual_forensics.analyze_video_file(media_path)
    except Exception as e:
        visual_res = {"risk": 0.0, "error": str(e)[:150], "anomalies": [],
                      "heatmap_b64": "", "subscores": {}}

    # 3) 唇音同步 (需影+音)
    try:
        av_res = {"risk": 0.0, "level": "SAFE", "mismatches": [],
                  "note": "純音檔, 同步維度略過"} \
            if audio_only or not audio_path else \
            av_sync_analyzer.analyze_av_sync(media_path, audio_path)
    except Exception as e:
        av_res = {"risk": 0.0, "error": str(e)[:150], "mismatches": []}

    # 4) 語意
    try:
        sem_res = semantic_scam_analyzer.analyze_audio(audio_path or media_path) \
            if (audio_path or audio_only) else \
            {"risk": 0.0, "level": "SAFE", "hits": [], "spans": [],
             "transcript": [], "full_text": "", "stt_available": False,
             "note": "無可用音軌, 語意維度略過"}
    except Exception as e:
        sem_res = {"risk": 0.0, "error": str(e)[:150], "hits": [], "spans": [],
                   "transcript": [], "full_text": ""}

    # —— 加權融合 (略過的維度權重按比例重分配) ——
    w = _weights()
    parts = {"audio": (audio_res, w["audio"]), "visual": (visual_res, w["visual"]),
             "avsync": (av_res, w["avsync"]), "semantic": (sem_res, w["semantic"])}
    skipped = {k for k, (r, _) in parts.items()
               if isinstance(r, dict) and ("略過" in str(r.get("note", "")))}
    active = {k: v for k, v in parts.items() if k not in skipped}
    if not active:  # 全略過 (理論上不會發生)
        active = parts
    # —— 語意動態權重：無明顯詐騙話術 (scam<15) 時語意只佔 5%，
    # 其餘轉移給鑑識維度，避免純深偽/AIGC 影片被 0 分語意稀釋 ——
    weights_used: dict[str, float] = {}
    if "semantic" in active and float(active["semantic"][0].get("risk", 0.0)) < 15:
        wsum_base = sum(v[1] for v in active.values()) or 1.0
        sem_share = 0.05
        scale = (1.0 - sem_share) / max(wsum_base - active["semantic"][1], 1e-9) \
            if len(active) > 1 else 0.0
        for k, (r, bw) in active.items():
            weights_used[k] = round(sem_share if k == "semantic" else bw * scale, 4)
    else:
        wsum_base = sum(v[1] for v in active.values()) or 1.0
        for k, (r, bw) in active.items():
            weights_used[k] = round(bw / wsum_base, 4)
    fake_prob = round(sum(v[0].get("risk", 0.0) * weights_used[k]
                          for k, v in active.items()), 1)

    # —— 粗估降權：av_sync 若為無關鍵點粗估 (易受晃動影響)，權重減半 ——
    coarse_av = ("avsync" in active
                 and "粗估" in str(active["avsync"][0].get("note", "")))
    if coarse_av:
        weights_used["avsync"] = round(weights_used["avsync"] * 0.5, 4)
        s = sum(weights_used.values()) or 1.0
        for k in weights_used:
            weights_used[k] = round(weights_used[k] / s, 4)
        fake_prob = round(sum(v[0].get("risk", 0.0) * weights_used[k]
                              for k, v in active.items()), 1)

    # —— 置信度分級保底 (Max-Boosting)：單維高分不該被平均吃掉 ——
    # 粗估 av_sync 只參與 WARNING 保底，不參與 DANGER 觸發
    core_risks = {k: float(active[k][0].get("risk", 0.0)) for k in active}
    precise = {k: v for k, v in core_risks.items()
               if not (coarse_av and k == "avsync")}
    boosts: list[str] = []
    sem_risk = float(core_risks.get("semantic", 0.0))
    peak_precise = max(precise.values()) if precise else 0.0
    n55_precise = sum(1 for v in precise.values() if v >= 55)
    peak_all = max(core_risks.values()) if core_risks else 0.0
    if sem_risk >= 65:
        # 高信心條件 1：明確詐騙話術
        if fake_prob < 62:
            boosts.append(f"詐騙語意 {sem_risk:.1f} (≥65)，總分保底 DANGER 區 (62)")
            fake_prob = 62.0
    a_risk = float(core_risks.get("audio", 0.0))
    v_risk = float(core_risks.get("visual", 0.0))
    if "audio" in precise and "visual" in precise and a_risk >= 62 and v_risk >= 32:
        # 高信心條件 2：語音合成特徵 + 固定比例視覺破綻 → 跨模態共鳴 +12
        boosts.append(f"跨模態共鳴 (語音 {a_risk:.1f}≥62 且視覺 {v_risk:.1f}≥32)，+12")
        fake_prob = min(97.0, max(fake_prob + 12, 60.0))
    elif peak_precise >= 75 or n55_precise >= 2:
        if fake_prob < 62:
            boosts.append(f"高置信單維峰值 {peak_precise:.1f} (≥75 或雙維≥55)，"
                          "總分保底 DANGER 區 (62)")
            fake_prob = 62.0
    elif peak_all >= 65:
        if fake_prob < 50:
            boosts.append(f"單維峰值 {peak_all:.1f} (≥65，含粗估)，總分保底 WARNING 區 (50)")
            fake_prob = 50.0
    fake_prob = min(97.0, round(fake_prob, 1))
    trust = round(100 - fake_prob, 1)
    status = "SAFE" if trust >= 60 else ("WARNING" if trust >= 40 else "DANGER")

    # —— 異常時間軸合併 ——
    timeline: list[dict] = []
    for a in audio_res.get("anomalies", []) or []:
        timeline.append(a)
    for a in visual_res.get("anomalies", []) or []:
        timeline.append(a)
    for m in av_res.get("mismatches", []) or []:
        timeline.append(m)
    for s in (sem_res.get("spans", []) or [])[:50]:
        timeline.append({"start": s["start"], "end": s["end"],
                         "type": "SCAM_KEYWORD",
                         "description": f"詐騙關鍵詞: {s.get('keyword', '')}"})
    timeline.sort(key=lambda x: x.get("start", 0))

    duration = audio_res.get("duration") or visual_res.get("duration") or 0.0

    # —— 數位指紋 + 鑑識時間 (供前端圖卡 / PDF 報告直接取用) ——
    sha256_hash = ""
    try:
        h = hashlib.sha256()
        with open(media_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        sha256_hash = h.hexdigest()
    except Exception:
        sha256_hash = ""
    analyzed_at = datetime.datetime.now(
        datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

    # 清理抽出的暫存 wav
    try:
        if audio_path and audio_path != media_path and os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception:
        pass

    return {
        "fake_probability": fake_prob,
        "trust_score": trust,
        "status": status,
        "duration": duration,
        "filename": os.path.basename(media_path),
        "sha256_hash": sha256_hash,
        "analyzed_at": analyzed_at,
        "dimensions": {"audio": audio_res, "visual": visual_res,
                       "av_sync": av_res, "semantic": sem_res},
        "timeline": timeline,
        "skipped_dimensions": sorted(skipped),
        "fusion": {"weights_used": weights_used, "boosts": boosts},
    }
