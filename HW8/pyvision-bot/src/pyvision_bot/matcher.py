"""OpenCV template matching with ROI support and non-maximum suppression."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np

from .models import MatchResult, ROIType, normalize_roi

ImageSource = Union[str, Path, np.ndarray]
PreparedMatch = Tuple[np.ndarray, Tuple[int, int], Tuple[int, int]]


class TemplateMatcher:
    """Find template images inside a screenshot.

    The matcher uses ``cv2.matchTemplate`` with ``cv2.TM_CCOEFF_NORMED``.
    A constant (single-color) template has no correlation variance, so the
    matcher automatically falls back to ``cv2.TM_SQDIFF_NORMED`` for that
    case and converts the score to the same "higher is better" scale.

    Args:
        threshold: Default confidence threshold in ``[0, 1]``.
        grayscale: Convert both images to grayscale before matching. This is
            faster and usually accurate enough for UI automation.
        nms_iou: Intersection-over-union above which :meth:`find_all`
            suppresses a lower-confidence box.

    Raises:
        ValueError: If a threshold or NMS value is outside ``[0, 1]``.
    """

    def __init__(
        self,
        threshold: float = 0.85,
        grayscale: bool = True,
        nms_iou: float = 0.3,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if not 0.0 <= nms_iou <= 1.0:
            raise ValueError("nms_iou must be between 0 and 1")

        self.threshold = float(threshold)
        self.grayscale = bool(grayscale)
        self.nms_iou = float(nms_iou)

    def find(
        self,
        screen: np.ndarray,
        template_path: ImageSource,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
    ) -> Optional[MatchResult]:
        """Return the best match, or ``None`` when nothing reaches the threshold.

        Args:
            screen: Screenshot as a BGR (or grayscale) ``numpy`` array.
            template_path: Path to the template image, or an in-memory image.
            threshold: Override the matcher's default threshold.
            roi: Optional search region. Returned coordinates are always
                absolute screen coordinates.

        Returns:
            The best :class:`MatchResult`, or ``None``.

        Raises:
            ValueError: If the screenshot is empty, the ROI is invalid, or the
                threshold is outside ``[0, 1]``.
            FileNotFoundError: If the template path cannot be read.
        """

        threshold_value = self._resolve_threshold(threshold)
        prepared = self._prepare(screen, template_path, roi)
        if prepared is None:
            return None

        scores, offset, (template_width, template_height) = prepared
        _, max_value, _, max_location = cv2.minMaxLoc(scores)
        if max_value < threshold_value:
            return None

        return MatchResult(
            x=int(max_location[0]) + offset[0],
            y=int(max_location[1]) + offset[1],
            width=template_width,
            height=template_height,
            confidence=float(max_value),
        )

    def find_all(
        self,
        screen: np.ndarray,
        template_path: ImageSource,
        threshold: Optional[float] = None,
        roi: Optional[ROIType] = None,
        max_results: Optional[int] = None,
    ) -> List[MatchResult]:
        """Return all non-overlapping matches above the threshold.

        Candidate locations are sorted by confidence and filtered with
        non-maximum suppression (NMS), so adjacent peaks belonging to the same
        target do not produce duplicate results.

        Args:
            screen: Screenshot as a BGR (or grayscale) ``numpy`` array.
            template_path: Path to the template image, or an in-memory image.
            threshold: Override the matcher's default threshold.
            roi: Optional search region. Returned coordinates are always
                absolute screen coordinates.
            max_results: Optional cap on the number of returned matches.

        Returns:
            Matches sorted by descending confidence. Empty when nothing is
            found or the template is larger than the search area.

        Raises:
            ValueError: If ``max_results`` is not positive, the screenshot is
                empty, the ROI is invalid, or the threshold is invalid.
            FileNotFoundError: If the template path cannot be read.
        """

        if max_results is not None and max_results <= 0:
            raise ValueError("max_results must be positive")

        threshold_value = self._resolve_threshold(threshold)
        prepared = self._prepare(screen, template_path, roi)
        if prepared is None:
            return []

        scores, offset, (template_width, template_height) = prepared
        ys, xs = np.where(scores >= threshold_value)

        candidates = [
            MatchResult(
                x=int(x) + offset[0],
                y=int(y) + offset[1],
                width=template_width,
                height=template_height,
                confidence=float(scores[y, x]),
            )
            for y, x in zip(ys, xs)
        ]
        candidates.sort(key=lambda item: item.confidence, reverse=True)

        kept: List[MatchResult] = []
        for candidate in candidates:
            if any(self._iou(candidate, existing) > self.nms_iou for existing in kept):
                continue
            kept.append(candidate)
            if max_results is not None and len(kept) >= max_results:
                break

        return kept

    def _resolve_threshold(self, threshold: Optional[float]) -> float:
        value = self.threshold if threshold is None else float(threshold)
        if not 0.0 <= value <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        return value

    def _prepare(
        self,
        screen: np.ndarray,
        template_path: ImageSource,
        roi: Optional[ROIType],
    ) -> Optional[PreparedMatch]:
        if not isinstance(screen, np.ndarray) or screen.size == 0:
            raise ValueError("screen must be a non-empty numpy array")

        template = self._load_template(template_path)
        screen_image = self._prepare_image(screen, self.grayscale)
        template_image = self._prepare_image(template, self.grayscale)

        offset = (0, 0)
        search = screen_image

        if roi is not None:
            region = normalize_roi(roi).clamp(
                screen_image.shape[1], screen_image.shape[0]
            )
            x, y, w, h = region.box
            search = screen_image[y : y + h, x : x + w]
            offset = (x, y)

        template_height, template_width = template_image.shape[:2]
        search_height, search_width = search.shape[:2]

        # A template larger than the search area can never match.
        if template_height > search_height or template_width > search_width:
            return None

        if float(template_image.std()) < 1e-6:
            # TM_CCOEFF_NORMED is undefined for a constant template.
            raw = cv2.matchTemplate(search, template_image, cv2.TM_SQDIFF_NORMED)
            scores = 1.0 - np.clip(raw, 0.0, 1.0)
        else:
            raw = cv2.matchTemplate(search, template_image, cv2.TM_CCOEFF_NORMED)
            scores = np.clip(raw, -1.0, 1.0)

        scores = np.nan_to_num(
            scores, nan=-1.0, posinf=1.0, neginf=-1.0
        ).astype(np.float32)

        return scores, offset, (template_width, template_height)

    @staticmethod
    def _load_template(template_path: ImageSource) -> np.ndarray:
        if isinstance(template_path, np.ndarray):
            template = template_path
        else:
            path = Path(template_path)
            template = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if template is None:
                raise FileNotFoundError(f"could not read template image: {path}")

        if not isinstance(template, np.ndarray) or template.size == 0:
            raise ValueError("template must be a non-empty numpy array")

        return template

    @staticmethod
    def _prepare_image(image: np.ndarray, grayscale: bool) -> np.ndarray:
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)

        if image.ndim == 2:
            if grayscale:
                return np.ascontiguousarray(image)
            return np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_GRAY2BGR))

        if image.ndim != 3:
            raise ValueError("image must be 2D grayscale or 3D color")

        channels = image.shape[2]
        if channels == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        elif channels != 3:
            raise ValueError("image must have 1, 3, or 4 channels")

        if grayscale:
            return np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))

        return np.ascontiguousarray(image)

    @staticmethod
    def _iou(first: MatchResult, second: MatchResult) -> float:
        first_x2 = first.x + first.width
        first_y2 = first.y + first.height
        second_x2 = second.x + second.width
        second_y2 = second.y + second.height

        intersection_width = max(
            0, min(first_x2, second_x2) - max(first.x, second.x)
        )
        intersection_height = max(
            0, min(first_y2, second_y2) - max(first.y, second.y)
        )
        intersection = intersection_width * intersection_height

        if intersection == 0:
            return 0.0

        union = (
            first.width * first.height
            + second.width * second.height
            - intersection
        )
        return intersection / union if union else 0.0
