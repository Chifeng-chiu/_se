# HW8 — pyvision-bot

第 10 週作業：將自行開發的 Python 套件發佈到公開套件庫（PyPI）。

## 套件資訊

| 項目 | 內容 |
| --- | --- |
| 套件名稱 | `pyvision-bot` |
| import 名稱 | `pyvision_bot` |
| 版本 | `0.1.0` |
| PyPI | <https://pypi.org/project/pyvision-bot/> |
| 原始碼 | [pyvision-bot/](pyvision-bot/) |

## 安裝

```bash
pip install pyvision-bot
```

## 專案簡介

以 OpenCV 模板比對驅動的影像自動化套件，支援：

- **Desktop 模式**：`mss` 截圖 + `pyautogui` 點擊／拖曳
- **ADB 模式**：`adb exec-out screencap` 截圖 + `adb shell input` 操作
- `find()`／`find_all()` 找圖、ROI 裁切、NMS 去重
- `wait_for()`／`wait_and_click()` 等待流程
- `jitter` 隨機偏移與擬人化微延遲

完整說明請見 [pyvision-bot/README.md](pyvision-bot/README.md)。
