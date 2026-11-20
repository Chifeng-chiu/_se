"""Data structures used by :mod:`pyvision_bot`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union


@dataclass(frozen=True)
class ROI:
    """A rectangular region of interest in screen coordinates.

    Args:
        x: Left edge of the region, in pixels.
        y: Top edge of the region, in pixels.
        w: Width of the region, in pixels.
        h: Height of the region, in pixels.

    Raises:
        ValueError: If ``w`` or ``h`` is not positive.
    """

    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError("ROI width and height must be positive")

    @property
    def box(self) -> Tuple[int, int, int, int]:
        """Return the region as an ``(x, y, w, h)`` tuple."""

        return (self.x, self.y, self.w, self.h)

    def clamp(self, screen_width: int, screen_height: int) -> "ROI":
        """Clip the region to the screen bounds.

        Args:
            screen_width: Width of the screenshot in pixels.
            screen_height: Height of the screenshot in pixels.

        Returns:
            A new :class:`ROI` that is fully inside the screen.

        Raises:
            ValueError: If the screen size is invalid or the ROI does not
                overlap the screen at all.
        """

        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")

        x1 = max(0, self.x)
        y1 = max(0, self.y)
        x2 = min(screen_width, self.x + self.w)
        y2 = min(screen_height, self.y + self.h)

        if x2 <= x1 or y2 <= y1:
            raise ValueError("ROI does not overlap the screen")

        return ROI(x1, y1, x2 - x1, y2 - y1)


ROIType = Union[ROI, Tuple[int, int, int, int]]


def normalize_roi(roi: ROIType) -> ROI:
    """Convert an :class:`ROI` or ``(x, y, w, h)`` tuple into an :class:`ROI`.

    Args:
        roi: Region of interest to normalize.

    Returns:
        The normalized :class:`ROI`.

    Raises:
        TypeError: If ``roi`` is neither an :class:`ROI` nor a 4-tuple.
    """

    if isinstance(roi, ROI):
        return roi

    if isinstance(roi, tuple) and len(roi) == 4:
        x, y, w, h = roi
        return ROI(int(x), int(y), int(w), int(h))

    raise TypeError("roi must be an ROI or a (x, y, w, h) tuple")


@dataclass(frozen=True)
class MatchResult:
    """A successful template match.

    Coordinates are absolute screenshot coordinates, even when a ROI was
    used for the search.

    Args:
        x: Left edge of the match, in pixels.
        y: Top edge of the match, in pixels.
        width: Width of the matched template, in pixels.
        height: Height of the matched template, in pixels.
        confidence: Normalized match confidence in ``[0, 1]``.
    """

    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> Tuple[int, int]:
        """Return the center point of the match as ``(cx, cy)``."""

        return (self.x + self.width // 2, self.y + self.height // 2)
