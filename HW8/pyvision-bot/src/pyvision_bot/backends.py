"""Screenshot and input backends for desktop and Android (ADB)."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from typing import List, Optional

import cv2
import numpy as np


class BaseBackend(ABC):
    """Abstract screenshot and input backend.

    Implementations must return screenshots as OpenCV-style BGR arrays.
    """

    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """Capture the current screen and return a BGR ``numpy`` array."""

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """Click at ``(x, y)`` in screen coordinates."""

    @abstractmethod
    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float,
    ) -> None:
        """Drag from ``(x1, y1)`` to ``(x2, y2)`` over ``duration`` seconds."""


class DesktopBackend(BaseBackend):
    """Desktop backend powered by ``mss`` and ``pyautogui``.

    Args:
        monitor: Monitor index understood by ``mss``. ``1`` is the primary
            monitor; ``0`` means the union of all monitors.

    Raises:
        ValueError: If ``monitor`` is negative.
    """

    def __init__(self, monitor: int = 1) -> None:
        if monitor < 0:
            raise ValueError("monitor must be zero or a positive index")
        self.monitor = monitor

    def screenshot(self) -> np.ndarray:
        """Capture one monitor and convert BGRA to OpenCV BGR."""

        try:
            import mss
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "DesktopBackend requires the 'mss' package. "
                "Install it with: pip install mss"
            ) from exc

        with mss.mss() as capture:
            try:
                monitor = capture.monitors[self.monitor]
            except IndexError as exc:
                raise ValueError(
                    f"monitor {self.monitor} is not available; "
                    f"found {len(capture.monitors)} monitor entries"
                ) from exc

            frame = np.asarray(capture.grab(monitor))

        if frame.ndim == 3 and frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        return frame

    def click(self, x: int, y: int) -> None:
        """Click with the left mouse button."""

        pyautogui = self._load_pyautogui()
        pyautogui.click(x=int(x), y=int(y))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float,
    ) -> None:
        """Drag with the left mouse button held down."""

        pyautogui = self._load_pyautogui()
        pyautogui.moveTo(int(x1), int(y1))
        pyautogui.dragTo(
            int(x2),
            int(y2),
            duration=max(0.0, float(duration)),
            button="left",
        )

    @staticmethod
    def _load_pyautogui():
        try:
            import pyautogui
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "DesktopBackend requires the 'pyautogui' package. "
                "Install it with: pip install pyautogui"
            ) from exc
        return pyautogui


class ADBBackend(BaseBackend):
    """Android backend that shells out to the ``adb`` executable.

    Screenshots are decoded directly from the bytes returned by
    ``adb exec-out screencap -p``; no temporary file is written.

    Args:
        device_serial: Optional device serial passed as ``adb -s``.
        adb_path: Path or command name of the ADB executable.
    """

    def __init__(
        self,
        device_serial: Optional[str] = None,
        adb_path: str = "adb",
    ) -> None:
        self.device_serial = device_serial
        self.adb_path = adb_path

    def screenshot(self) -> np.ndarray:
        """Capture the device screen and decode the PNG in memory."""

        data = self._run_bytes("exec-out", "screencap", "-p")

        # Some ADB/Windows combinations translate LF to CRLF in the PNG
        # stream. Only repair the data when the PNG signature is not intact.
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            data = data.replace(b"\r\n", b"\n")

        buffer = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("adb screencap did not return a valid PNG image")

        return image

    def click(self, x: int, y: int) -> None:
        """Send ``adb shell input tap``."""

        self._run_text("shell", "input", "tap", str(int(x)), str(int(y)))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float,
    ) -> None:
        """Send ``adb shell input swipe`` with a millisecond duration."""

        duration_ms = max(0, int(round(float(duration) * 1000)))
        self._run_text(
            "shell",
            "input",
            "swipe",
            str(int(x1)),
            str(int(y1)),
            str(int(x2)),
            str(int(y2)),
            str(duration_ms),
        )

    def _base_command(self) -> List[str]:
        command = [self.adb_path]
        if self.device_serial:
            command.extend(["-s", self.device_serial])
        return command

    def _run_text(self, *arguments: str) -> str:
        command = self._base_command() + list(arguments)
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"adb executable not found: {self.adb_path}. "
                "Install Android platform-tools and add adb to PATH."
            ) from exc

        if process.returncode != 0:
            raise RuntimeError(
                f"adb command failed ({process.returncode}): "
                f"{' '.join(command)}\n{process.stderr.strip()}"
            )

        return process.stdout

    def _run_bytes(self, *arguments: str) -> bytes:
        command = self._base_command() + list(arguments)
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"adb executable not found: {self.adb_path}. "
                "Install Android platform-tools and add adb to PATH."
            ) from exc

        if process.returncode != 0:
            stderr = process.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"adb command failed ({process.returncode}): "
                f"{' '.join(command)}\n{stderr.strip()}"
            )

        return process.stdout
