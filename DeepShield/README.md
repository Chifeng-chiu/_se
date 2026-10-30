# DeepShield — AI 語音與深偽影片雙層防禦系統
> 模式 B（即時防護盾 Chrome Extension） + 模式 A（事後鑑定所 Web Dashboard + FastAPI 鑑識引擎）

## Monorepo 結構

```
DeepShield/
├── backend/               # FastAPI 暨鑑識引擎 (模式 A/B 共用)
│   ├── main.py            # API 入口: POST /api/v1/analyze/deep, WS /api/v1/ws/realtime-scan
│   ├── config.py
│   ├── requirements.txt
│   ├── api/
│   └── services/          # 四大分析器
│       ├── audio_forensics.py
│       ├── visual_forensics.py
│       ├── av_sync_analyzer.py
│       ├── semantic_scam_analyzer.py
│       ├── orchestrator.py
│       ├── realtime_scanner.py
│       └── utils.py
├── frontend-web/          # 模式 A: React + Vite + TS + Tailwind 深度鑑識儀表板
└── extension-realtime/    # 模式 B: Chrome Extension MV3 即時防護盾
```

## 快速開始 (Backend, Step 1+2)

```powershell
cd DeepShield\backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# 健康檢查: http://localhost:8000/api/v1/health
# API 文件:   http://localhost:8000/docs
```

> 注意: 本機若無系統 `ffmpeg`，後端會自動改用 `imageio-ffmpeg` 內附的二進位檔；
> 若兩者皆無，影片的聲音軌分析會自動降級（visual 照常運作，不會崩潰）。

## API 一覽

| 端點 | 用途 |
|---|---|
| `GET /api/v1/health` | 健康檢查 |
| `POST /api/v1/analyze/deep` | 模式 A: 上傳 `file` (.mp4/.mp3/.wav)，回傳總體偽造機率 + 4 維度分數 + 異常時間軸 + Base64 圖表 |
| `WS /api/v1/ws/realtime-scan` | 模式 B: 每 2 秒送一次 JSON `{audio_b64, frames_b64[], transcript_snippet}`，回傳 `{timestamp, trust_score, status, alerts, transcript_snippet}` |

### WS 訊息範例 (client → server)

```json
{"audio_b64": "<wav/webm chunk base64>", "frames_b64": ["<jpeg base64>"], "transcript_snippet": "現在加入老師的群組保證獲利"}
```

### WS 回傳範例

```json
{
  "timestamp": 12.5,
  "trust_score": 28,
  "status": "DANGER",
  "alerts": ["偵測到高頻音訊截斷特徵", "觸發高風險詐騙詞彙：保證獲利"],
  "transcript_snippet": "現在加入老師的群組保證獲利..."
}
```

## 檢測模組權重 (深度鑑識)

- 語音鑑識 30% + 視覺深偽 30% + 唇音同步 15% + 防詐語意 25% = 總體偽造機率
- `trust_score = 100 - fake_probability`

## 免責聲明

本系統的啟發式物理特徵演算法為 Baseline，可直接運作；
`services/*` 內皆預留 `*_MODEL_PATH` / `load_deep_model()` 接口，
可隨時掛載 Xception / EfficientNet / Wav2Vec2 / Whisper 等預訓練權重升級精度。
鑑識結果僅供風險參考，不構成法律證據。
