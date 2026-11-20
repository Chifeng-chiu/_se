"""High-level image automation API."""

from __future__ import annotations

import random
import time
from typing import List, Literal, Optional, Tuple

import numpy as np

from .backends import ADBBackend, BaseBackend, DesktopBackend
from .matcher import ImageSource, TemplateMatcher
from .models import MatchResult, ROIType

Mode = Literal["desktop", "adb"]


class VisionBot:
    """Image-driven automation for a desktop screen or an Android device.

    Args:
        mode: ``"desktop"`` for ``mss`` + ``pyautogui``, or ``"adb"`` for an
            Android device.
        device_serial: Optional ADB device serial, for example
            ``"emulator-5554"``. Ignored in desktop mode.
        default_threshold: Default template matching confidence in ``[0, 1]``.
        backend: Optional pre-built backend. Useful for tests or custom
            transports. When omitted, a backend is created from ``mode``.
        matcher: Optional :class:`TemplateMatcher` instance.
        rng: Optional random source used for jitter and human-like delays.

    Raises:
        ValueError: If ``mode`` is unknown or the threshold is invalid.
    """

    #: Minimum and maximum delay inserted before a click or swipe.
    MIN_ACTION_DELAY = 0.02
    MAX_ACTION_DELAY = 0.08

    def __init__(
        self,
        mode: Mode = "desktop",
        device_serial: Optional[str] = None,
        default_threshold: float = 0.85,
        *,
        backend: Optional[BaseBackend] = None,
        matcher: Optional[TemplateMatcher] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        if mode not in ("desktop", "adb"):
            raise ValueError("mode must be 'desktop' or 'adb'")
        if not 0.0 <= default_threshold <= 1.0:
            raise ValueError("default_threshold must be between 0 and 1")

        self.mode: Mode = mode
        self.device_serial = device_serial
        self.default_threshold = float(default_threshold)
        self._rng = rng or random.Random()

        if backend is not None:
            self._backend = backend
        elif mode == "desktop":
            self._backend = DesktopBackend()
        else:
            self._backend = ADBBackend(device_serial=device_serial)

        self._matcher = matcher or TemplateMatcher(threshold=self.default_threshold)

    @property
    def backend(self) -> BaseBackend:
        """Return the active backend."""

        return self._backend

    @property
    def matcher(self) -> TemplateMatcher:
        """Return the active template matcher."""

        return self._matcher

    def screenshot(self) -> np.ndarray:
        """Capture the current screen as a BGR ``numpy`` array."""

        image = self._backend.screenshot()
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise RuntimeError("backend returned an empty screenshot")
        return image

    def find(
        self,
        template_path: ImageSource,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
    ) -> Optional[MatchResult]:
        """Take a screenshot and return the best template match.

        Args:
            template_path: Path to the template image, or an in-memory image.
            threshold: Optional confidence override.
            roi: Optional search region in absolute screen coordinates.

        Returns:
            The best :class:`MatchResult`, or ``None`` when not found.
        """

        threshold_value = self._resolve_threshold(threshold)
        return self._matcher.find(
            self.screenshot(),
            template_path,
            threshold=threshold_value,
            roi=roi,
        )

    def find_all(
        self,
        template_path: ImageSource,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
        max_results: Optional[int] = None,
    ) -> List[MatchResult]:
        """Take a screenshot and return all non-overlapping matches."""

        threshold_value = self._resolve_threshold(threshold)
        return self._matcher.find_all(
            self.screenshot(),
            template_path,
            threshold=threshold_value,
            roi=roi,
            max_results=max_results,
        )

    def click(self, x: int, y: int, jitter: int = 0) -> None:
        """Click at ``(x, y)`` with optional random pixel jitter.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            jitter: Maximum random offset in each axis, in pixels.

        Raises:
            ValueError: If ``jitter`` is negative.
        """

        if jitter < 0:
            raise ValueError("jitter must be zero or positive")

        self._human_pause()
        click_x, click_y = self._apply_jitter(int(x), int(y), int(jitter))
        self._backend.click(click_x, click_y)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.3,
        jitter: int = 0,
    ) -> None:
        """Drag between two points with optional jitter.

        Args:
            x1: Start x coordinate.
            y1: Start y coordinate.
            x2: End x coordinate.
            y2: End y coordinate.
            duration: Gesture duration in seconds.
            jitter: Maximum random offset in each axis, in pixels.

        Raises:
            ValueError: If ``duration`` or ``jitter`` is negative.
        """

        if duration < 0:
            raise ValueError("duration must be zero or positive")
        if jitter < 0:
            raise ValueError("jitter must be zero or positive")

        self._human_pause()
        start_x, start_y = self._apply_jitter(int(x1), int(y1), int(jitter))
        end_x, end_y = self._apply_jitter(int(x2), int(y2), int(jitter))
        self._backend.swipe(
            start_x,
            start_y,
            end_x,
            end_y,
            float(duration),
        )

    def wait_for(
        self,
        template_path: ImageSource,
        timeout: float = 10.0,
        interval: float = 0.5,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
    ) -> Optional[MatchResult]:
        """Poll the screen until a template appears or the timeout expires.

        Args:
            template_path: Path to the template image, or an in-memory image.
            timeout: Maximum wait time in seconds.
            interval: Delay between screenshots in seconds.
            threshold: Optional confidence override.
            roi: Optional search region in absolute screen coordinates.

        Returns:
            The first matching :class:`MatchResult`, or ``None`` on timeout.

        Raises:
            ValueError: If ``timeout`` is negative or ``interval`` is not
                positive.
        """

        if timeout < 0:
            raise ValueError("timeout must be zero or positive")
        if interval <= 0:
            raise ValueError("interval must be positive")

        deadline = time.monotonic() + float(timeout)

        while True:
            match = self.find(template_path, threshold=threshold, roi=roi)
            if match is not None:
                return match

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            time.sleep(min(float(interval), remaining))

    def wait_and_click(
        self,
        template_path: ImageSource,
        timeout: float = 10.0,
        interval: float = 0.5,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
        jitter: int = 3,
    ) -> bool:
        """Wait for a template, then click its center.

        Args:
            template_path: Path to the template image, or an in-memory image.
            timeout: Maximum wait time in seconds.
            interval: Delay between screenshots in seconds.
            threshold: Optional confidence override.
            roi: Optional search region in absolute screen coordinates.
            jitter: Maximum random click offset in each axis, in pixels.

        Returns:
            ``True`` when the template was found and clicked, otherwise
            ``False``.
        """

        match = self.wait_for(
            template_path,
            timeout=timeout,
            interval=interval,
            threshold=threshold,
            roi=roi,
        )
        if match is None:
            return False

        center_x, center_y = match.center
        self.click(center_x, center_y, jitter=jitter)
        return True

    def _resolve_threshold(self, threshold: Optional[float]) -> float:
        value = self.default_threshold if threshold is None else float(threshold)
        if not 0.0 <= value <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        return value

    def _apply_jitter(self, x: int, y: int, jitter: int) -> Tuple[int, int]:
        if jitter <= 0:
            return x, y
        return (
            x + self._rng.randint(-jitter, jitter),
            y + self._rng.randint(-jitter, jitter),
        )

    def _human_pause(self) -> None:
        time.sleep(
            self._rng.uniform(self.MIN_ACTION_DELAY, self.MAX_ACTION_DELAY)
        )
