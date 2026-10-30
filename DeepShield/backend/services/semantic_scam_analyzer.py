"""模組 4: 防詐語意雷達 (semantic_scam_analyzer.py)

- 即時路徑: `scan_text()` — 純關鍵字規則, <1ms, 供 WS 每 2 秒呼叫.
- 深度路徑: `analyze_audio()` — 先 STT (faster-whisper, 有裝才用) 再呼叫 scan_text,
  輸出帶時間戳逐字稿 + 螢光筆標記位置.
- 預留 LLM 接口: `LLM_ENDPOINT` 環境變數, `llm_rescore()` 目前為 stub.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# 高風險詞彙 → (權重 0-30, 類別)，一律用繁體保存；
# 比對前會先把輸入正規化為繁體 (opencc s2t)，故簡體輸入同樣命中
SCAM_PATTERNS: dict[str, tuple[int, str]] = {
    "匯款": (22, "資金轉移"),
    "轉帳": (18, "資金轉移"),
    "把錢轉進": (24, "資金轉移"),
    "保證獲利": (30, "投資詐騙"),
    "穩賺": (20, "投資詐騙"),
    "飆股": (22, "投資詐騙"),
    "外匯": (16, "投資詐騙"),
    "投資": (10, "投資詐騙"),
    "獲利": (14, "投資詐騙"),
    "賺取": (14, "投資詐騙"),
    "報酬": (14, "投資詐騙"),
    "帶單": (20, "投資詐騙"),
    "漏洞": (14, "投資詐騙"),
    "套利": (16, "投資詐騙"),
    "群組": (8, "假冒權威"),
    "內線": (16, "投資詐騙"),
    "老師": (6, "假冒權威"),
    "檢察官": (20, "假冒公檢法"),
    "警察": (10, "假冒公檢法"),
    "驗證碼": (24, "個資竊取"),
    "帳號": (8, "個資竊取"),
    "帳戶凍結": (20, "假冒公檢法"),
    "密碼": (12, "個資竊取"),
    "急用錢": (14, "親友詐騙"),
    "不能告訴別人": (18, "社交工程"),
    "不要告訴別人": (18, "社交工程"),
    "不能跟別人講": (18, "社交工程"),
    "公司機密": (16, "社交工程"),
    "內部消息": (14, "社交工程"),
    "秘密": (8, "社交工程"),
    "保密": (10, "社交工程"),
    "解除分期": (22, "購物詐騙"),
    "監管帳戶": (24, "假冒公檢法"),
    "虛擬貨幣": (12, "投資詐騙"),
    "USDT": (12, "投資詐騙"),
    "手續費": (10, "資金轉移"),
    "保證金": (16, "資金轉移"),
    "中獎": (14, "中獎詐騙"),
    "點擊連結": (16, "釣魚"),
    "下載APP": (12, "釣魚"),
    "下載app": (12, "釣魚"),
    "視訊": (6, "深偽相關"),
    "換臉": (12, "深偽相關"),
    "詐騙": (8, "警示詞"),
    "guaranteed profit": (30, "investment scam"),
    "wire transfer": (18, "money move"),
    "verification code": (24, "phishing"),
}

_COMPILED = [(re.compile(re.escape(k), re.IGNORECASE), k, w, c)
             for k, (w, c) in SCAM_PATTERNS.items()]

_s2t_fn = None


def _normalize(text: str) -> str:
    """簡繁正規化 (whisper 常吐簡體)：轉繁體後比對；opencc 缺席則原文比對。"""
    global _s2t_fn
    if _s2t_fn is None:
        try:
            from opencc import OpenCC  # type: ignore
            _s2t_fn = OpenCC("s2t").convert
        except Exception:
            _s2t_fn = lambda s: s  # noqa: E731
    try:
        return _s2t_fn(text)
    except Exception:
        return text


@dataclass
class ScamHit:
    keyword: str
    category: str
    start: float
    end: float
    weight: int


def scan_text(text: str, start: float = 0.0, end: float | None = None,
              duration: float = 0.0) -> dict:
    """掃描一段文字, 回傳風險分數 + hits + 螢光筆 spans.

    spans: [{start, end, text, keyword}] — 時間按字元比例內插, 供前端逐字稿標紅.
    """
    if not text:
        return {"risk": 0.0, "hits": [], "spans": [], "level": "SAFE"}
    norm = _normalize(text)  # 簡轉繁後比對 (opencc s2t 為逐字對應，索引與原文對齊)
    dur = float(end - start) if end is not None else float(duration or 10.0)
    dur = max(dur, 1e-3)
    n = max(len(text), 1)
    hits: list[ScamHit] = []
    spans: list[dict] = []
    total_w = 0
    for rx, kw, w, cat in _COMPILED:
        for m in rx.finditer(norm):
            s = start + (m.start() / n) * dur
            e = start + (m.end() / n) * dur
            hits.append(ScamHit(kw, cat, round(s, 2), round(e, 2), w))
            # span.text 取原文切片，前端螢光筆才能在原始逐字稿中找到
            spans.append({"start": round(s, 2), "end": round(e, 2),
                          "text": text[m.start():m.end()], "keyword": kw, "category": cat})
            total_w += w
    # 飽和曲線: 100*(1-exp(-W/45)), 單一「保證獲利」(30) ≈ 49分, 兩個高權重詞即破表
    import math
    risk = round(100 * (1 - math.exp(-total_w / 45.0)), 1)
    level = "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER")
    return {
        "risk": risk,
        "level": level,
        "hits": [{"keyword": h.keyword, "category": h.category,
                  "start": h.start, "end": h.end} for h in hits],
        "spans": spans,
        "hit_count": len(hits),
    }


def transcribe_audio(audio_path: str, model_name: str = "tiny") -> list[dict]:
    """語音轉文字 (帶時間戳). 有 faster-whisper 就用, 否則回傳佔位段落.

    回傳: [{"start": float, "end": float, "text": str}]
    """
    engine_ok = True
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        engine_ok = False
    if engine_ok:
        try:
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(audio_path, language="zh",
                                           beam_size=1, vad_filter=True)
            out = [{"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": s.text.strip()} for s in segments if s.text.strip()]
            if out:
                return out
            # 引擎正常但無語音 (純音樂/無聲) → 回空串列, 由 analyze_audio 標記
            return []
        except Exception:
            pass
    # 退路: 估計時長, 產生佔位 (讓下游串得起來, 前端會顯示 STT 未啟用提示)
    try:
        import soundfile as sf
        info = sf.info(audio_path)
        dur = float(info.duration or 0)
    except Exception:
        dur = 0.0
    return [{"start": 0.0, "end": round(dur, 2),
             "text": "[STT 未啟用: 安裝 faster-whisper 以產生逐字稿]"}]


def analyze_audio(audio_path: str, duration: float = 0.0) -> dict:
    """深度路徑: STT + 關鍵字掃描, 回傳 transcript + 風險 + 高亮 spans."""
    segments = transcribe_audio(audio_path)
    if segments and duration <= 0:
        duration = segments[-1].get("end", 0.0) or 0.0
    # STT 引擎正常但無語音 (純音樂/無聲): 誠實略過，不以 0 稀釋總分
    if not segments:
        return {"risk": 0.0, "level": "SAFE", "hits": [], "spans": [],
                "transcript": [], "full_text": "",
                "stt_available": True,
                "note": "STT 正常但未偵測到語音 (純音樂或無聲)，語意維度略過"}
    full_text = "".join(s["text"] for s in segments)
    # 若 STT 只有佔位符, 風險歸 0 但標記 stt_available=False
    stt_ok = not (len(segments) == 1 and segments[0]["text"].startswith("[STT"))
    if not stt_ok:
        return {"risk": 0.0, "level": "SAFE", "hits": [], "spans": [],
                "transcript": segments, "full_text": full_text,
                "stt_available": False,
                "note": "未安裝 faster-whisper, 語意維度略過 (風險以 0 計, 不影響其他維度)"}
    # 逐段掃描保留時間戳
    all_hits, all_spans = [], []
    import math
    total_w = 0
    for s in segments:
        r = scan_text(s["text"], start=s["start"], end=s["end"])
        all_hits.extend(r["hits"])
        all_spans.extend(r["spans"])
        total_w += sum(h.get("weight", 0) for h in [])  # 佔位, 下行重算
    total_w = sum(next((w for k2, (w, c) in SCAM_PATTERNS.items() if k2 == h["keyword"]), 0)
                  for h in all_hits)
    risk = round(100 * (1 - math.exp(-total_w / 45.0)), 1)
    level = "SAFE" if risk < 35 else ("WARNING" if risk < 65 else "DANGER")
    return {"risk": risk, "level": level, "hits": all_hits, "spans": all_spans,
            "hit_count": len(all_hits), "transcript": segments,
            "full_text": full_text, "stt_available": True}


def llm_rescore(text: str) -> dict:
    """預留 LLM 社交工程重評分接口 (目前 stub, 設 LLM_ENDPOINT 即會被 orchestrator 呼叫).

    TODO: 接 OpenAI-compatible /api/chat, prompt 判斷急迫性+權威冒充+承諾回報三構面.
    """
    endpoint = os.environ.get("LLM_ENDPOINT", "")
    if not endpoint:
        return {"enabled": False}
    return {"enabled": False, "note": f"endpoint {endpoint} 尚未實作呼叫"}
