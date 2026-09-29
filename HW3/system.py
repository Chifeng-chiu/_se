"""Windows 通知與開機自動啟動。"""

import ctypes
import subprocess
import sys
from pathlib import Path

import settings


def _app_id() -> str:
    return "NBA_Tracker_App"


def toast(title: str, message: str) -> bool:
    """用 PowerShell + WinRT 發 Windows 通知，成功回 True。"""
    script = f"""
$ErrorActionPreference='Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$n=$t.GetElementsByTagName('text')
$n.Item(0).AppendChild($t.CreateTextNode({_ps(title)})) | Out-Null
$n.Item(1).AppendChild($t.CreateTextNode({_ps(message)})) | Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('NBA Tracker').Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20, creationflags=flags, check=False,
        )
        return True
    except Exception:
        return False


def _ps(text: str) -> str:
    """把字串安全地包成 PowerShell 單引號字面值。"""
    return "'" + str(text).replace("'", "''") + "'"


def flash_taskbar(hwnd: int, times: int = 6):
    """讓工作列按鈕閃爍，視窗在背景時也能注意到。"""
    if not hwnd or sys.platform != "win32":
        return
    try:
        class FLASHINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                        ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                        ("dwFlashTime", ctypes.c_uint)]

        FLASHWINFO = FLASHINFO()
        FLASHWINFO.cbSize = ctypes.sizeof(FLASHINFO)
        FLASHWINFO.hwnd = hwnd
        FLASHWINFO.dwFlags = 0x00000003  # FLASH | TIMER
        FLASHWINFO.uCount = times
        FLASHWINFO.dwFlashTime = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(FLASHWINFO))
    except Exception:
        pass


# ---------- 開機自動啟動（用登錄檔，不需要管理員權限） ----------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "NBA_Tracker"


def _entry_command() -> str:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    script = settings.app_dir() / "main.py"
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{exe}" "{script}"'


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE)
        return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """回傳 True 代表設定成功。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE, 0, winreg.REG_SZ, _entry_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
