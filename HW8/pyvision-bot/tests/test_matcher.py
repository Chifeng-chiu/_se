"""Tests for OpenCV template matching (no real screen required)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from pyvision_bot.matcher import TemplateMatcher
from pyvision_bot.models import ROI, MatchResult


def make_image(seed: int, height: int = 240, width: int = 320) -> np.ndarray:
    """Create a reproducible, textured BGR image."""

    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def paste(
    screen: np.ndarray,
    patch: np.ndarray,
    x: int,
    y: int,
) -> None:
    """Paste ``patch`` into ``screen`` at ``(x, y)`` in place."""

    height, width = patch.shape[:2]
    screen[y : y + height, x : x + width] = patch


def save_template(tmp_path: Path, template: np.ndarray) -> Path:
    """Write a template image and return its path."""

    path = tmp_path / "template.png"
    assert cv2.imwrite(str(path), template)
    return path


def test_find_returns_absolute_coordinates(tmp_path: Path) -> None:
    screen = make_image(seed=1)
    template = screen[40:80, 90:150].copy()
    path = save_template(tmp_path, template)

    result = TemplateMatcher(threshold=0.9).find(screen, path)

    assert result is not None
    assert (result.x, result.y, result.width, result.height) == (90, 40, 60, 40)
    assert result.confidence > 0.999
    assert result.center == (120, 60)


def test_find_accepts_an_in_memory_template() -> None:
    screen = make_image(seed=2)
    template = screen[10:50, 20:70].copy()

    result = TemplateMatcher(threshold=0.9).find(screen, template)

    assert result is not None
    assert (result.x, result.y) == (20, 10)


def test_find_works_without_grayscale() -> None:
    screen = make_image(seed=3)
    template = screen[60:100, 140:200].copy()

    result = TemplateMatcher(threshold=0.9, grayscale=False).find(screen, template)

    assert result is not None
    assert (result.x, result.y) == (140, 60)


def test_roi_is_applied_and_coordinates_are_absolute() -> None:
    screen = make_image(seed=4)
    template = screen[100:130, 150:190].copy()

    result = TemplateMatcher(threshold=0.9).find(
        screen,
        template,
        roi=ROI(130, 80, 90, 80),
    )

    assert result is not None
    assert (result.x, result.y) == (150, 100)


def test_roi_accepts_a_tuple() -> None:
    screen = make_image(seed=5)
    template = screen[70:100, 120:160].copy()

    result = TemplateMatcher(threshold=0.9).find(
        screen,
        template,
        roi=(100, 50, 100, 80),
    )

    assert result is not None
    assert (result.x, result.y) == (120, 70)


def test_threshold_rejects_an_unrelated_template() -> None:
    screen = make_image(seed=6)
    unrelated = make_image(seed=7, height=30, width=30)

    result = TemplateMatcher(threshold=0.99).find(screen, unrelated)

    assert result is None


def test_find_all_uses_nms_and_returns_each_target_once() -> None:
    screen = make_image(seed=8, height=300, width=360)
    template = make_image(seed=9, height=36, width=44)
    positions = [(20, 20), (150, 110), (280, 220)]
    for x, y in positions:
        paste(screen, template, x, y)

    matches = TemplateMatcher(threshold=0.95).find_all(screen, template)

    assert len(matches) == 3
    assert {(match.x, match.y) for match in matches} == set(positions)
    assert all(match.confidence > 0.99 for match in matches)


def test_find_all_respects_max_results() -> None:
    screen = make_image(seed=10, height=300, width=360)
    template = make_image(seed=11, height=30, width=30)
    for x, y in [(20, 20), (150, 110), (280, 220)]:
        paste(screen, template, x, y)

    matches = TemplateMatcher(threshold=0.95).find_all(
        screen,
        template,
        max_results=2,
    )

    assert len(matches) == 2


def test_template_larger_than_search_area_returns_no_match() -> None:
    screen = make_image(seed=12, height=50, width=50)
    template = make_image(seed=13, height=100, width=100)
    matcher = TemplateMatcher(threshold=0.9)

    assert matcher.find(screen, template) is None
    assert matcher.find_all(screen, template) == []


def test_roi_outside_screen_raises() -> None:
    screen = make_image(seed=14)
    template = screen[10:40, 10:40].copy()

    with pytest.raises(ValueError):
        TemplateMatcher().find(screen, template, roi=(1000, 1000, 10, 10))


def test_constant_template_falls_back_to_sqdiff() -> None:
    screen = make_image(seed=15)
    screen[70:90, 110:130] = (0, 0, 255)
    template = np.full((20, 20, 3), (0, 0, 255), dtype=np.uint8)

    result = TemplateMatcher(threshold=0.99).find(screen, template)

    assert result is not None
    assert (result.x, result.y) == (110, 70)


def test_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(ValueError):
        TemplateMatcher(threshold=1.5)

    screen = make_image(seed=16)
    template = screen[10:40, 10:40].copy()
    with pytest.raises(ValueError):
        TemplateMatcher().find(screen, template, threshold=-0.1)


def test_match_result_center_and_roi_validation() -> None:
    match = MatchResult(x=10, y=20, width=40, height=30, confidence=0.9)

    assert match.center == (30, 35)
    assert ROI(1, 2, 3, 4).box == (1, 2, 3, 4)

    with pytest.raises(ValueError):
        ROI(0, 0, 0, 10)
