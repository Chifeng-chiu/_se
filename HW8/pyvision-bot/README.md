# pyvision-bot

[![PyPI](https://img.shields.io/pypi/v/pyvision-bot.svg)](https://pypi.org/project/pyvision-bot/)
[![Python](https://img.shields.io/pypi/pyversions/pyvision-bot.svg)](https://pypi.org/project/pyvision-bot/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

以 **OpenCV 模板比對**驅動的影像自動化套件，同時支援 **Windows / macOS / Linux 桌面**與 **Android（ADB）**。用一張按鈕截圖就能等待畫面出現、點擊、拖曳，適合 GUI 測試、RPA 與手機遊戲自動化。

## 特色

* **雙模式後端**：`DesktopBackend`（`mss` 截圖 + `pyautogui` 操作）與 `ADBBackend`（`adb exec-out screencap` + `adb shell input`）
* **OpenCV 找圖**：`cv2.matchTemplate` + `TM_CCOEFF_NORMED`，支援灰階加速與 ROI 裁切
* **座標正確**：使用 ROI 時，回傳的仍是全螢幕絕對座標
* **多目標偵測**：`find_all()` 內建非極大值抑制（NMS），同一個目標不會重複回報
* **擬人化操作**：點擊／滑動支援 `jitter` 隨機偏移與隨機微延遲
* **等待流程**：`wait_for()`、`wait_and_click()` 自動輪詢直到目標出現或逾時
* **不落地截圖**：ADB 截圖直接在記憶體用 `cv2.imdecode` 解碼，不寫暫存檔
* **完整型別註記**：所有公開 API 都有 Type Hints 與 Docstrings，附 `py.typed`

## 安裝

```bash
pip install pyvision-bot
```

從原始碼安裝（含開發工具）：

```bash
git clone https://github.com/Chifeng-chiu/_se.git
cd _se/HW8/pyvision-bot
python -m pip install -e ".[dev]"
```

需求：Python 3.9 以上。

> Linux 桌面若缺少 `pyautogui` 需要的系統套件，請先安裝 `python3-xlib`、`scrot` 等相依套件；ADB 模式不需要 `pyautogui`。

## 快速上手：Desktop

```python
from pyvision_bot import ROI, VisionBot

bot = VisionBot(mode="desktop")

# 等待按鈕出現（最多 15 秒），找到後點擊中心，加入 ±3 px 隨機偏移
clicked = bot.wait_and_click("assets/login_button.png", timeout=15, jitter=3)
print("clicked:", clicked)

# 只在畫面左上角區域找圖
match = bot.find("assets/icon.png", roi=ROI(0, 0, 1280, 720))
if match:
    print("center:", match.center, "confidence:", match.confidence)
```

* `DesktopBackend` 預設擷取 **主螢幕**（`monitor=1`）。若要擷取所有螢幕的聯集，可建立 `DesktopBackend(monitor=0)` 後注入 `VisionBot(backend=...)`。
* 座標以擷取到的螢幕左上角為原點；多螢幕且非主螢幕時請自行換算全域座標。

## 快速上手：Android（ADB）

前置：安裝 Android platform-tools、開啟手機 USB 偵錯，並確認 `adb devices` 看得到裝置。

```bash
adb devices
# List of devices attached
# emulator-5554    device
```

```python
from pyvision_bot import VisionBot

bot = VisionBot(mode="adb", device_serial="emulator-5554")

# 等待遊戲開始按鈕並點擊
bot.wait_and_click("assets/start.png", timeout=20, jitter=2)

# 由下往上滑動
bot.swipe(540, 1600, 540, 400, duration=0.4, jitter=5)

# 取得目前畫面（BGR ndarray）
screen = bot.screenshot()
print(screen.shape)
```

不指定 `device_serial` 時，ADB 會使用目前唯一的裝置：

```python
bot = VisionBot(mode="adb")
```

## API 說明

### `VisionBot`

```python
VisionBot(
    mode: Literal["desktop", "adb"] = "desktop",
    device_serial: str | None = None,
    default_threshold: float = 0.85,
    *,
    backend: BaseBackend | None = None,
    matcher: TemplateMatcher | None = None,
    rng: random.Random | None = None,
)
```

| 方法 | 說明 |
| --- | --- |
| `screenshot() -> np.ndarray` | 取得目前畫面（BGR） |
| `find(template_path, threshold=None, roi=None) -> MatchResult \| None` | 找最佳匹配 |
| `find_all(template_path, threshold=None, roi=None, max_results=None) -> list[MatchResult]` | 找所有不重疊匹配（NMS） |
| `click(x, y, jitter=0)` | 點擊，支援 ±jitter 像素隨機偏移 |
| `swipe(x1, y1, x2, y2, duration=0.3, jitter=0)` | 拖曳／滑動 |
| `wait_for(template_path, timeout=10.0, interval=0.5, threshold=None, roi=None)` | 輪詢等待目標出現 |
| `wait_and_click(template_path, timeout=10.0, interval=0.5, threshold=None, roi=None, jitter=3)` | 等待目標並點擊中心 |

`backend`、`matcher`、`rng` 是進階注入點：測試時可傳入自訂 backend，或傳入固定種子的 `random.Random` 讓 jitter 可重現。

### `TemplateMatcher`

```python
from pyvision_bot import TemplateMatcher

matcher = TemplateMatcher(threshold=0.9, grayscale=True, nms_iou=0.3)
screen = bot.screenshot()

best = matcher.find(screen, "assets/target.png")
all_matches = matcher.find_all(screen, "assets/target.png", max_results=5)
```

| 參數 | 預設 | 說明 |
| --- | --- | --- |
| `threshold` | `0.85` | 相似度門檻（0～1） |
| `grayscale` | `True` | 轉灰階比對，速度較快 |
| `nms_iou` | `0.3` | `find_all()` 的 NMS IoU 門檻 |

`template_path` 可以是檔案路徑、`pathlib.Path`，或直接傳入 `numpy` 陣列。

### 資料結構

```python
from pyvision_bot import MatchResult, ROI

match = MatchResult(x=100, y=50, width=40, height=30, confidence=0.97)
print(match.center)  # (120, 65)

roi = ROI(0, 0, 1280, 720)
print(roi.box)       # (0, 0, 1280, 720)
```

* `MatchResult.center` 回傳 `(cx, cy)`。
* `ROI` 也接受 `(x, y, w, h)` tuple；超出螢幕的區域會自動裁切，完全在畫面外則拋出 `ValueError`。

### 自訂 Backend

繼承 `BaseBackend` 即可接入其他來源（例如模擬器、遠端桌面）：

```python
from pyvision_bot import BaseBackend
import numpy as np


class MyBackend(BaseBackend):
    def screenshot(self) -> np.ndarray:
        ...

    def click(self, x: int, y: int) -> None:
        ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        ...
```

## 擬人化行為

`click()` 與 `swipe()` 會：

1. 在動作前插入 20～80 ms 的隨機延遲
2. 若 `jitter > 0`，在每個座標軸加入 `±jitter` 像素的隨機偏移

```python
bot.click(500, 300, jitter=4)
bot.swipe(200, 800, 200, 200, duration=0.5, jitter=3)
```

這可以降低固定座標、固定節奏造成的機械感，但**不保證**能繞過任何特定服務的偵測機制。

## 實際跑一次（範例程式）

這個套件是 **Python 函式庫**，沒有 GUI 視窗，也不是網站。裝好之後在終端機執行 `examples/demo.py` 就能看到它在做什麼：

```bash
cd HW8/pyvision-bot

# 1. 用合成圖片測試找圖，不會控制滑鼠（最安全，建議先跑這個）
python examples/demo.py matcher

# 2. 抓一張桌面截圖存成 desktop.png
python examples/demo.py screen

# 3. 在桌面上找模板，只印座標，不點擊
python examples/demo.py find button.png

# 4. 找到模板並點擊（預設只預演，加 --yes 才會真的點）
python examples/demo.py click button.png --yes

# 5. 抓 Android 裝置截圖（需先 adb devices 看得到裝置）
python examples/demo.py adb --serial emulator-5554
```

`matcher` 的預期輸出：

```text
螢幕尺寸: (240, 320, 3)
匹配框: (150, 80, 60, 40)
中心點: (180, 100)
信心: 1.0
```

要自己寫腳本時，把上面的 `from pyvision_bot import ...` 貼進一個 `.py` 檔，用 `python your_script.py` 執行即可。

## 開發與測試

```bash
python -m pip install -e ".[dev]"
pytest
```

測試完全使用合成的 `numpy` 圖片與 Mock Backend，不需要真實螢幕、滑鼠或 ADB 裝置。

## 打包與發佈

```bash
python -m build
twine check dist/*
twine upload dist/*
```

發佈前請確認 `pyproject.toml` 的 `authors`、`project.urls` 是你要的資訊，並設定 PyPI API token：

```bash
# PowerShell
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = "pypi-..."
```

## 注意事項

* 桌面模式的座標與螢幕縮放（DPI scaling）有關；若 Windows 設定 125% / 150% 縮放，請確認截圖與 `pyautogui` 使用相同的座標系。
* `pyautogui` 預設啟用滑鼠移到左上角即中止的 failsafe，緊急時可把滑鼠移到 (0, 0)。
* ADB 模式需要裝置已授權此電腦；首次連線請在手機上按「允許 USB 偵錯」。
* 本套件只提供影像比對與輸入模擬，請僅用於你擁有或獲授權操作的裝置與服務。

## License

MIT License，詳見 [LICENSE](LICENSE)。
