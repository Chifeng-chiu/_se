"""Tests for VisionBot and backends using mocks (no screen or ADB device)."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import pytest

import pyvision_bot.bot as bot_module
from pyvision_bot.backends import ADBBackend, BaseBackend
from pyvision_bot.bot import VisionBot


def make_image(seed: int, height: int = 200, width: int = 260) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


class MockBackend(BaseBackend):
    """In-memory backend that returns a scripted list of screenshots."""

    def __init__(self, frames: List[np.ndarray]) -> None:
        if not frames:
            raise ValueError("MockBackend needs at least one frame")
        self.frames = list(frames)
        self.screenshot_count = 0
        self.clicks: List[Tuple[int, int]] = []
        self.swipes: List[Tuple[int, int, int, int, float]] = []

    def screenshot(self) -> np.ndarray:
        index = min(self.screenshot_count, len(self.frames) - 1)
        self.screenshot_count += 1
        return self.frames[index]

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float,
    ) -> None:
        self.swipes.append((x1, y1, x2, y2, duration))


class FakeClock:
    """Deterministic clock used instead of ``time`` inside ``bot``."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def screen_and_template(tmp_path: Path) -> Tuple[np.ndarray, np.ndarray, Path]:
    screen = make_image(seed=21)
    template = screen[30:60, 70:110].copy()
    path = tmp_path / "target.png"
    assert cv2.imwrite(str(path), template)
    return screen, template, path


def test_find_delegates_to_backend(
    screen_and_template: Tuple[np.ndarray, np.ndarray, Path],
) -> None:
    screen, _, path = screen_and_template
    backend = MockBackend([screen])
    bot = VisionBot(backend=backend, rng=random.Random(0))

    result = bot.find(path, threshold=0.9)

    assert result is not None
    assert (result.x, result.y) == (70, 30)
    assert backend.screenshot_count == 1


def test_find_roi_returns_absolute_coordinates() -> None:
    screen = make_image(seed=22)
    template = screen[100:130, 150:190].copy()
    backend = MockBackend([screen])
    bot = VisionBot(backend=backend)

    result = bot.find(template, roi=(130, 80, 90, 80))

    assert result is not None
    assert (result.x, result.y) == (150, 100)


def test_click_without_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MockBackend([np.zeros((10, 10, 3), dtype=np.uint8)])
    bot = VisionBot(backend=backend, rng=random.Random(0))
    clock = FakeClock()
    monkeypatch.setattr(bot_module, "time", clock)

    bot.click(100, 200)

    assert backend.clicks == [(100, 200)]
    assert clock.now > 0


def test_click_jitter_stays_within_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MockBackend([np.zeros((10, 10, 3), dtype=np.uint8)])
    bot = VisionBot(backend=backend, rng=random.Random(0))
    monkeypatch.setattr(bot_module, "time", FakeClock())

    bot.click(100, 200, jitter=4)

    click_x, click_y = backend.clicks[0]
    assert 96 <= click_x <= 104
    assert 196 <= click_y <= 204


def test_swipe_records_duration_and_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MockBackend([np.zeros((10, 10, 3), dtype=np.uint8)])
    bot = VisionBot(backend=backend, rng=random.Random(0))
    monkeypatch.setattr(bot_module, "time", FakeClock())

    bot.swipe(10, 20, 30, 40, duration=0.5, jitter=2)

    start_x, start_y, end_x, end_y, duration = backend.swipes[0]
    assert duration == 0.5
    assert 8 <= start_x <= 12
    assert 18 <= start_y <= 22
    assert 28 <= end_x <= 32
    assert 38 <= end_y <= 42


def test_negative_jitter_and_duration_are_rejected() -> None:
    backend = MockBackend([np.zeros((10, 10, 3), dtype=np.uint8)])
    bot = VisionBot(backend=backend)

    with pytest.raises(ValueError):
        bot.click(1, 2, jitter=-1)
    with pytest.raises(ValueError):
        bot.swipe(1, 2, 3, 4, duration=-0.1)
    with pytest.raises(ValueError):
        bot.swipe(1, 2, 3, 4, jitter=-1)


def test_wait_for_returns_match_after_polling(
    screen_and_template: Tuple[np.ndarray, np.ndarray, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen, _, path = screen_and_template
    blank = np.zeros_like(screen)
    backend = MockBackend([blank, blank, screen])
    bot = VisionBot(backend=backend, rng=random.Random(0))
    clock = FakeClock()
    monkeypatch.setattr(bot_module, "time", clock)

    result = bot.wait_for(path, timeout=5.0, interval=0.5, threshold=0.9)

    assert result is not None
    assert backend.screenshot_count == 3
    assert clock.now == pytest.approx(1.0)


def test_wait_for_returns_none_on_timeout(
    screen_and_template: Tuple[np.ndarray, np.ndarray, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen, _, path = screen_and_template
    blank = np.zeros_like(screen)
    backend = MockBackend([blank])
    bot = VisionBot(backend=backend)
    clock = FakeClock()
    monkeypatch.setattr(bot_module, "time", clock)

    result = bot.wait_for(path, timeout=1.0, interval=0.5, threshold=0.9)

    assert result is None
    assert backend.screenshot_count == 3
    assert clock.now == pytest.approx(1.0)


def test_wait_and_click_clicks_the_center(
    screen_and_template: Tuple[np.ndarray, np.ndarray, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen, template, path = screen_and_template
    blank = np.zeros_like(screen)
    backend = MockBackend([blank, screen])
    bot = VisionBot(backend=backend, rng=random.Random(0))
    monkeypatch.setattr(bot_module, "time", FakeClock())

    clicked = bot.wait_and_click(path, timeout=2.0, interval=0.5, jitter=0)

    assert clicked is True
    assert backend.clicks == [
        (70 + template.shape[1] // 2, 30 + template.shape[0] // 2)
    ]


def test_wait_and_click_returns_false_on_timeout(
    screen_and_template: Tuple[np.ndarray, np.ndarray, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen, _, path = screen_and_template
    backend = MockBackend([np.zeros_like(screen)])
    bot = VisionBot(backend=backend)
    monkeypatch.setattr(bot_module, "time", FakeClock())

    clicked = bot.wait_and_click(path, timeout=0.0, interval=0.5)

    assert clicked is False
    assert backend.clicks == []


def test_invalid_mode_and_threshold_are_rejected() -> None:
    with pytest.raises(ValueError):
        VisionBot(mode="browser")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        VisionBot(default_threshold=1.5)

    backend = MockBackend([np.zeros((10, 10, 3), dtype=np.uint8)])
    bot = VisionBot(backend=backend)
    with pytest.raises(ValueError):
        bot.find("missing.png", threshold=-0.1)
    with pytest.raises(ValueError):
        bot.wait_for("missing.png", interval=0)


def test_adb_backend_uses_serial_and_decodes_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Tuple[List[str], dict]] = []
    image = np.zeros((32, 48, 3), dtype=np.uint8)
    image[:, :, 2] = 255
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    png = encoded.tobytes()

    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((command, kwargs))
        if command[-3:] == ["exec-out", "screencap", "-p"]:
            return subprocess.CompletedProcess(command, 0, stdout=png, stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = ADBBackend(device_serial="emulator-5554")

    screenshot = backend.screenshot()

    assert screenshot.shape == (32, 48, 3)
    assert calls[0][0] == [
        "adb",
        "-s",
        "emulator-5554",
        "exec-out",
        "screencap",
        "-p",
    ]


def test_adb_backend_click_and_swipe_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[List[str]] = []

    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = ADBBackend(device_serial="emulator-5554")

    backend.click(12, 34)
    backend.swipe(1, 2, 3, 4, duration=0.5)

    assert calls[0] == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "input",
        "tap",
        "12",
        "34",
    ]
    assert calls[1] == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "input",
        "swipe",
        "1",
        "2",
        "3",
        "4",
        "500",
    ]


def test_adb_backend_without_serial_omits_dash_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[List[str]] = []

    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ADBBackend().click(1, 2)

    assert calls[0] == ["adb", "shell", "input", "tap", "1", "2"]


def test_adb_backend_reports_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"device offline",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="device offline"):
        ADBBackend().screenshot()


def test_adb_backend_rejects_invalid_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"not a png",
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="valid PNG"):
        ADBBackend().screenshot()


def test_adb_backend_reports_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: List[str], **kwargs: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError("adb")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="adb executable not found"):
        ADBBackend().click(1, 2)
