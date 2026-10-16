# Docker 學習紀錄與微服務系統建置

本專案為 Docker 學習筆記與微服務架構實作作業。系統採用 **Docker Compose** 進行多容器編排，整合了 **Nginx**（網頁伺服器與反向代理）、**Node.js**（後端 API 微服務）與 **PostgreSQL**（關聯式資料庫），並提供互動式 Web 介面展示系統運行狀態。

---

## 一、 Docker 核心概念與學習紀錄

### 1. 為什麼需要 Docker？
在傳統開發中，常因為作業系統或套件版本差異導致「在我電腦上可以跑，部署卻失敗」的問題。Docker 透過容器化（Containerization）技術，將應用程式與執行環境打包在一起，達到環境隔離與跨平台一致性的效果。

### 2. 三大核心元件
* **Image（映像檔）**：唯讀的環境模板（如 `nginx:alpine`、`postgres:15`），用來建立容器。
* **Container（容器）**：映像檔的執行實例，彼此隔離且輕量。
* **Volume（資料卷）**：用於持久化保存容器內的資料（例如資料庫檔案），避免容器刪除後資料遺失。

### 3. 常用指令整理
```bash
# 查看目前執行中的容器
docker ps

# 依據 docker-compose.yml 建置並啟動所有服務（背景執行）
docker compose up -d --build

# 查看服務運行日誌
docker compose logs -f

# 停止並移除所有容器與網路
docker compose down
```

---

## 二、 微服務系統架構設計

本系統包含三個獨立的 Docker 容器，並透過自訂的 Bridge Network (`app-network`) 進行內部通訊：

```text
[ 使用者瀏覽器 ] 
       │ (HTTP Port 8080)
       ▼
┌─────────────────────────────┐
│  nginx (Web & Reverse Proxy)│ ── 靜態頁面 (`/` -> index.html)
└─────────────────────────────┘
       │ 反向代理 (`/api/*` -> http://backend:3000)
       ▼
┌─────────────────────────────┐
│  backend (Node.js 20 API)   │ ── 處理業務邏輯與 API 請求
└─────────────────────────────┘
       │ TCP Port 5432
       ▼
┌─────────────────────────────┐
│  db (PostgreSQL 15)         │ ── 儲存資料 (掛載 Volume 持久化)
└─────────────────────────────┘
```

---

## 三、 專案目錄結構

```text
.
├── README.md               # 學習紀錄與系統說明文件
├── docker-compose.yml      # 多容器編排設定檔
├── nginx/
│   ├── nginx.conf          # Nginx 反向代理與靜態路由設定
│   └── index.html          # 前端展示介面 (Web UI)
└── backend/
    ├── Dockerfile          # Node.js 微服務建置腳本
    ├── package.json        # Node.js 專案相依套件
    └── server.js           # Express 後端 API 與 PostgreSQL 連線邏輯
```

---

## 四、 如何啟動與展示系統

### 1. 啟動系統
在專案根目錄下開啟終端機，執行以下指令：
```bash
docker compose up -d --build
```

### 2. 瀏覽 Web 展示介面
打開瀏覽器前往：
👉 **http://localhost:8080**

在網頁介面中可以檢視：
1. **Nginx / Node.js / PostgreSQL 即時連線狀態**。
2. **資料庫互動測試**：於輸入框輸入任意文字並送出，資料將透過 Nginx 轉發給 Node.js，並寫入 PostgreSQL 資料庫中即時呈現。
