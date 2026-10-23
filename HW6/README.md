# TestPulse Omni

全方位自動化軟體測試平台，涵蓋軟體工程的六大核心測試類型：

| # | 模組 | 引擎 | 實作重點 |
|---|------|------|----------|
| 01 | 單元測試 | pytest + Docker SDK | 無網路、無 capabilities、256MB、0.5 CPU、5 秒強制終止 |
| 02 | 整合測試 | httpx | 多步驟 API 鏈、Token 提取、`{{variable}}` 資料流插值、斷言 |
| 03 | E2E 測試 | Playwright Chromium | Title、Selector、Click、Text、URL、Console error、截圖 |
| 04 | 效能壓力 | httpx.AsyncClient | 併發上限、RPS、min/avg/max/p50/p90/p95/p99、時間軸 |
| 05 | 資安測試 | httpx | Security Headers、Cookie、CORS、XSS/SQLi 無害探測、風險評分 |
| 06 | 視覺回歸 | Playwright + Pillow | Baseline/current/diff、像素百分比、紅色差異標示圖 |

前端是單頁式深色科技儀表板：HTML5 + Tailwind CSS（CDN）+ Vanilla JS + Monaco Editor + Chart.js。後端是 FastAPI + SQLAlchemy + SQLite，所有執行結果都會寫入 `test_history` 並可從 `/api/history` 查詢。

---

## 專案結構

```text
test-pulse-omni/
├── backend/
│   ├── main.py                    # FastAPI 路由 / 執行紀錄 / 靜態檔案
│   ├── database.py                # SQLite + SQLAlchemy session
│   ├── models.py                  # TestHistory schema
│   ├── requirements.txt
│   ├── Dockerfile                 # 後端 + Chromium
│   ├── sandbox/
│   │   └── Dockerfile             # pytest-only 沙箱 image
│   ├── data/                      # runtime DB + artifacts（git 忽略）
│   └── services/
│       ├── common.py              # 共用 artifact / URL / JSON 工具
│       ├── unit_sandbox.py        # 01 Docker 隔離 pytest
│       ├── integration_chain.py   # 02 多步驟 API 鏈
│       ├── e2e_runner.py          # 03 Playwright E2E
│       ├── load_tester.py         # 04 非同步壓力測試
│       ├── sec_scanner.py         # 05 資安掃描
│       └── visual_diff.py         # 06 視覺回歸
├── frontend/
│   ├── index.html                 # 六大模組儀表板
│   └── app.js                     # Monaco / Chart.js / API 串接
├── docker-compose.yml
├── .dockerignore
├── .env.example
└── README.md
```

---

## 快速啟動（Docker，推薦）

### 必要系統套件

- **Docker Desktop**（或 Docker Engine + Compose v2）
- 不需要在主機安裝 Python / Node.js 才能使用 Docker 模式
- Docker image 內會自動安裝：
  - Chromium 與 Playwright 需要的系統函式庫
  - `fonts-noto-cjk`（讓中文網頁截圖穩定）
  - pytest sandbox image
- 後端需要掛載 Docker socket 才能建立單元測試沙箱容器

### 啟動

```bash
cd test-pulse-omni
docker compose up --build
```

開啟：

- 儀表板：<http://localhost:8000>
- API Swagger：<http://localhost:8000/docs>
- 健康檢查：<http://localhost:8000/api/health>

Compose 會先建置 `testpulse-pytest:latest`，再啟動 backend。若 image 不存在，backend 第一次執行單元測試時也會嘗試自動建置。

> 在容器內測試「主機上的服務」時，請把 target URL 從 `http://localhost:3000` 改成 `http://host.docker.internal:3000`。Compose 已加入 `host-gateway` 對應。

持久化資料存放在 named volume `testpulse-omni-data`（SQLite DB + 截圖 artifacts）。

---

## 本機開發啟動

### 1. 安裝 Python 與系統依賴

建議 **Python 3.11**。Windows / macOS / Linux 皆可。

```bash
cd test-pulse-omni
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2. 安裝 Playwright Chromium

```bash
python -m playwright install chromium
```

Linux 主機若缺少 Chromium 系統函式庫：

```bash
python -m playwright install --with-deps chromium
```

Debian / Ubuntu 等價的系統套件會由 Playwright 自動安裝。Windows 通常只需要 `install chromium`。Docker 模式已包含這些依賴。

### 3. 建置 pytest 沙箱 image

單元測試模組需要 Docker daemon：

```bash
docker build -t testpulse-pytest:latest backend/sandbox
```

請確認 Docker Desktop 正在執行，且目前使用者可以執行 `docker ps`。

### 4. 啟動 FastAPI

從 `test-pulse-omni/` 根目錄執行：

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

前端由同一個 FastAPI 程序提供：<http://localhost:8000>

本機執行時資料會放在 `backend/data/`：

```text
backend/data/
├── testpulse.db
└── artifacts/
    ├── e2e/*.png
    └── visual/<key>/{baseline,current,diff}.png
```

### 5. 可選環境變數

```bash
TESTPULSE_DATA_DIR=/absolute/path/to/data
DATABASE_URL=sqlite:////absolute/path/to/data/testpulse.db
SANDBOX_IMAGE=testpulse-pytest:latest
CORS_ORIGINS=*
LOG_LEVEL=INFO
E2E_NO_SANDBOX=1
```

`E2E_NO_SANDBOX=0` 可在非 root、已正確設定 user namespace 的主機上重新啟用 Chromium sandbox。Docker 容器預設為 `1`。

---

## 六大模組 API

所有 `POST /api/tests/*` 回應都包含：

```json
{
  "passed": true,
  "summary": "human readable result",
  "history_id": 42,
  "recorded_status": "passed",
  "duration_ms": 1234,
  "test_type": "e2e",
  "target": "https://example.com"
}
```

### 01 單元測試

`POST /api/tests/unit`

```json
{
  "code": "def add(a, b):\n    return a + b\n",
  "tests": "from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
  "timeout_seconds": 5
}
```

沙箱特性：

- image：`testpulse-pytest:latest`（`FROM python:3.11-slim`）
- **無網路**（`network_disabled=True`）
- 原始碼用 Docker API tarball 複製，不使用 host bind mount
- `user=65534:65534`、`cap_drop=ALL`、`no-new-privileges`
- 256MB RAM、64 PIDs、0.5 CPU、`/tmp` tmpfs
- Docker `wait(timeout=5)`，超時後 `kill()` 並回傳 `timed_out: true`

### 02 整合測試

`POST /api/tests/integration`

```json
{
  "stop_on_failure": true,
  "default_timeout_seconds": 15,
  "steps": [
    {
      "name": "Login",
      "method": "POST",
      "url": "https://api.example.com/login",
      "json": { "username": "demo", "password": "demo" },
      "extract": { "token": "body.token" },
      "assertions": [
        { "source": "status", "op": "eq", "value": 200 }
      ]
    },
    {
      "name": "Fetch profile",
      "method": "GET",
      "url": "https://api.example.com/me",
      "headers": { "Authorization": "Bearer {{token}}" },
      "assertions": [
        { "source": "status", "op": "eq", "value": 200 },
        { "source": "body.email", "op": "contains", "value": "@" }
      ]
    }
  ]
}
```

支援：

- 佔位符：`{{token}}`、`{{steps.0.body.user.id}}`、`{{steps.login.status}}`
- 提取路徑：`body.token`、`body.json.username`、`headers.x-request-id`
- 斷言：`eq`、`ne`、`gt`、`gte`、`lt`、`lte`、`contains`、`not_contains`、`in`、`exists`、`not_exists`、`regex`
- 未設定斷言時，預設要求 HTTP status < 400
- 失敗即停止（可關閉）；每一步都保存 masked 的提取變數與 assertion 實際值

### 03 E2E 測試

`POST /api/tests/e2e`

```json
{
  "url": "https://example.com",
  "expected_title": "Example Domain",
  "title_match": "contains",
  "selector": "h1",
  "click_selector": "a",
  "expected_text": "Example Domain",
  "text_selector": "body",
  "expected_url_contains": "example.com",
  "wait_for_selector": "h1",
  "wait_after_click_ms": 300,
  "timeout_ms": 15000,
  "viewport_width": 1280,
  "viewport_height": 720,
  "wait_until": "domcontentloaded",
  "full_page_screenshot": true,
  "capture_screenshot": true,
  "ignore_https_errors": false
}
```

每次執行會產生 `artifacts/e2e/*.png`，回應包含 `screenshot_url`、逐項 `checks`、`console_errors`、`page_errors`、`final_url` 與 `status_code`。

### 04 效能與壓力測試

`POST /api/tests/load`

```json
{
  "url": "https://httpbin.org/get",
  "method": "GET",
  "concurrency": 20,
  "total_requests": 100,
  "timeout_seconds": 10,
  "min_success_rate": 0.95,
  "headers": {},
  "json_body": null
}
```

回應包含 `rps`、`latency`（min/avg/max/p50/p90/p95/p99）、`success_rate`、`status_distribution`、每秒 `timeline`（Chart.js 會畫 RPS + 平均延遲雙軸圖）、錯誤樣本。總請求數上限 2,000，併發上限 100。

### 05 資安測試

`POST /api/tests/security`

```json
{
  "url": "https://example.com/?q=test",
  "timeout_seconds": 10
}
```

檢查：

- `Content-Security-Policy`
- `Strict-Transport-Security`（僅 HTTPS）
- `X-Content-Type-Options`
- `X-Frame-Options`（或 CSP `frame-ancestors`）
- `Referrer-Policy`、`Permissions-Policy`、`Cross-Origin-Opener-Policy`
- `Set-Cookie` 的 `Secure` / `HttpOnly` / `SameSite`
- CORS wildcard / credentials 組合
- `X-Powered-By`、`Server` 版本揭露
- 針對一個 query parameter 發送 4 個無害 XSS / SQLi 探測 payload，檢查**未轉義反射**、SQL 錯誤特徵與非預期 5xx

回應包含 `score`（0–100）、`grade`、`findings`、`header_checks`、`probes`。掃描僅使用 GET，不會修改遠端資料；仍請只對你有權測試的目標使用。

### 06 UI 視覺回歸

`POST /api/tests/visual`

```json
{
  "url": "https://example.com",
  "viewport_width": 1280,
  "viewport_height": 720,
  "full_page": true,
  "update_baseline": false,
  "diff_threshold_percent": 0.5,
  "pixel_threshold": 20,
  "wait_seconds": 0.5,
  "wait_until": "networkidle",
  "timeout_ms": 30000,
  "fail_on_size_change": true,
  "ignore_https_errors": false
}
```

流程：

1. 第一次（或勾選 `update_baseline`）：儲存 `baseline.png` 與 `current.png`，回傳 `baseline_created` / `baseline_updated`。
2. 後續：再次截圖並用 `PIL.ImageChops.difference` 比較。
3. 任一 RGB channel 的差異大於 `pixel_threshold` 才計為變更像素。
4. `diff_percent = changed_pixels / total_pixels * 100`。
5. 產生 `diff.png`：原始頁面變暗，變更像素以紅色標示，外框以黃色標記；尺寸改變時頂部顯示紅色 banner。
6. Baseline key = URL + viewport + full-page mode 的 SHA-256 前 20 碼，不同設定互不干擾。
7. 同一 baseline key 使用 async lock，避免兩個首次執行同時建立 baseline。

`diff_threshold_percent` 預設 0.5%，`fail_on_size_change` 預設 `true`。第一次執行建 baseline 時不進行比較，這是預期行為。

---

## 歷史紀錄與統計

- `GET /api/history?limit=30&offset=0&test_type=e2e`
- `GET /api/history/{id}`：完整 details
- `DELETE /api/history/{id}`
- `GET /api/stats`：總執行數、通過率、平均耗時、各模組統計
- `GET /api/health`

SQLite schema：`test_history(id, test_type, target, status, summary, score, duration_ms, details JSON, created_at)`。

---

## 安全與使用範圍

- 單元測試程式碼在獨立 Docker 容器中執行，**不掛載 host 目錄、不掛載 Docker socket、沒有網路**。
- 但 backend 本身需要 Docker socket 才能建立沙箱，因此請不要把這個平台直接暴露到不可信的公開網路。
- 壓力測試與資安掃描會主動連線目標；請只對你擁有或獲授權的系統執行。
- 視覺回歸第一次執行只會建立 baseline；若頁面本身有隨機內容，請使用穩定的測試環境或調整 `pixel_threshold` / `diff_threshold_percent`。
- 這個專案是單機 / 教學 / 內部工具等級的架構；多租戶 SaaS 需要再加上驗證、授權、資源配額、artifact 清理與 SSRF 防護。

---

## 常見問題

**單元測試回傳 Docker sandbox unavailable**

- 確認 Docker Desktop 正在執行：`docker ps`
- 建置 image：`docker build -t testpulse-pytest:latest backend/sandbox`
- Compose 模式確認 backend 有掛載 `/var/run/docker.sock`

**Playwright 啟動失敗（缺少 shared library）**

```bash
python -m playwright install --with-deps chromium
```

**在 Docker 裡打不到 localhost 的服務**

改用 `http://host.docker.internal:<port>`。macOS / Windows Docker Desktop 亦同。

**視覺比對一直失敗，但肉眼看起來一樣**

- 字體 / 圖片載入尚未完成：提高 `wait_seconds`，或等待 `networkidle`
- 動態時間、廣告、隨機推薦內容：在測試環境停用，或提高 tolerance
- 瀏覽器尺寸或 device scale factor 不同：確認使用相同 viewport

**修改 baseline**

在 Visual 模組勾選「更新 Baseline」再執行，或刪除 `backend/data/artifacts/visual/<key>/` 後重新執行。
