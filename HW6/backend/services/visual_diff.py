"""[6] Visual regression engine: Playwright screenshots + Pillow pixel diff.

The first run creates ``baseline.png``. Later runs save ``current.png`` and
produce ``diff.png`` where changed pixels are highlighted in red. The baseline
key is derived from URL, viewport, and full-page mode, so each configuration
keeps its own history. A per-key async lock prevents two concurrent first runs
from racing to create the baseline.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    async_playwright,
)

from .common import (
    artifact_dir,
    artifact_url,
    stable_key,
    validate_http_url,
    write_json,
)

ALLOWED_WAIT_UNTIL = {"commit", "domcontentloaded", "load", "networkidle"}
_locks: dict[str, asyncio.Lock] = {}


def _launch_args() -> list[str]:
    args = [
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
    ]
    if os.getenv("E2E_NO_SANDBOX", "1") == "1":
        args.append("--no-sandbox")
    return args


def _key_for(url: str, width: int, height: int, full_page: bool) -> str:
    # v2 lets us intentionally invalidate all old screenshots after changing
    # the stabilisation CSS below.
    return stable_key("visual-v2", url, f"{width}x{height}", str(full_page).lower())


def _visual_dir(key: str) -> Path:
    target = artifact_dir("visual") / key
    target.mkdir(parents=True, exist_ok=True)
    return target


async def _capture(
    url: str,
    width: int,
    height: int,
    full_page: bool,
    wait_seconds: float,
    wait_until: str,
    timeout_ms: int,
    ignore_https_errors: bool,
) -> bytes:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=_launch_args(),
        )
        try:
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                ignore_https_errors=ignore_https_errors,
                user_agent="TestPulseOmni/1.0 (visual-regression) Chromium",
            )
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

            # Disable animation and caret blink so two screenshots of the same
            # page are comparable. This style is applied after navigation so it
            # cannot modify how the page initially renders.
            await page.add_style_tag(
                content="""
                    *, *::before, *::after {
                        animation-delay: 0s !important;
                        animation-duration: 0s !important;
                        animation-iteration-count: 1 !important;
                        transition-duration: 0s !important;
                        transition-delay: 0s !important;
                        caret-color: transparent !important;
                        scroll-behavior: auto !important;
                    }
                """
            )
            try:
                await page.evaluate(
                    "() => document.fonts ? document.fonts.ready.then(() => true) : true"
                )
            except PlaywrightError:
                pass

            if wait_seconds > 0:
                await page.wait_for_timeout(int(wait_seconds * 1000))

            png = await page.screenshot(
                type="png",
                full_page=full_page,
                animations="disabled",
                caret="hide",
                timeout=timeout_ms,
            )
            await context.close()
            return png
        finally:
            await browser.close()


def _compare_images(
    baseline_path: Path,
    current_path: Path,
    diff_path: Path,
    pixel_threshold: int,
) -> dict[str, Any]:
    with Image.open(baseline_path) as baseline_image, Image.open(
        current_path
    ) as current_image:
        baseline = baseline_image.convert("RGB")
        current = current_image.convert("RGB")

        size_changed = baseline.size != current.size
        width = max(baseline.width, current.width)
        height = max(baseline.height, current.height)

        # Pad the smaller image with white so the diff report remains
        # inspectable instead of crashing on a viewport/content height change.
        base_canvas = Image.new("RGB", (width, height), (255, 255, 255))
        current_canvas = Image.new("RGB", (width, height), (255, 255, 255))
        base_canvas.paste(baseline, (0, 0))
        current_canvas.paste(current, (0, 0))

        difference = ImageChops.difference(base_canvas, current_canvas)
        red, green, blue = difference.split()
        # Any changed channel above the per-pixel tolerance counts. This is
        # stricter than converting the RGB difference to luminance, which can
        # hide small but saturated colour changes.
        max_channel_diff = ImageChops.lighter(
            ImageChops.lighter(red, green), blue
        )
        mask = max_channel_diff.point(
            lambda value: 255 if value > pixel_threshold else 0
        )

        histogram = mask.histogram()
        changed_pixels = int(histogram[255]) if len(histogram) > 255 else 0
        total_pixels = width * height
        diff_percent = (changed_pixels / total_pixels * 100.0) if total_pixels else 0.0

        # Visual output: dimmed current page, with changed pixels painted red.
        dimmed = current_canvas.point(lambda value: int(value * 0.35))
        red_layer = Image.new("RGB", (width, height), (255, 32, 32))
        diff_image = Image.composite(red_layer, dimmed, mask)

        bbox = mask.getbbox()
        draw = ImageDraw.Draw(diff_image)
        if bbox:
            draw.rectangle(
                (max(0, bbox[0] - 2), max(0, bbox[1] - 2), bbox[2] + 2, bbox[3] + 2),
                outline=(255, 210, 0),
                width=3,
            )
        if size_changed:
            banner = (
                f"SIZE CHANGED: {baseline.width}x{baseline.height} -> "
                f"{current.width}x{current.height}"
            )
            draw.rectangle((0, 0, width, 26), fill=(120, 0, 0))
            draw.text((8, 7), banner, fill=(255, 255, 255))

        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_image.save(diff_path, format="PNG", optimize=True)

        return {
            "diff_percent": diff_percent,
            "changed_pixels": changed_pixels,
            "total_pixels": total_pixels,
            "size_changed": size_changed,
            "baseline_dimensions": {
                "width": baseline.width,
                "height": baseline.height,
            },
            "current_dimensions": {
                "width": current.width,
                "height": current.height,
            },
            "diff_dimensions": {"width": width, "height": height},
            "change_bbox": list(bbox) if bbox else None,
        }


async def run_visual_diff(config: dict[str, Any]) -> dict[str, Any]:
    """Capture a page, compare it with the baseline, and persist artifacts."""
    started = time.perf_counter()
    url = validate_http_url(str(config.get("url", "")), "target URL")
    width = max(320, min(int(config.get("viewport_width", 1280)), 3840))
    height = max(240, min(int(config.get("viewport_height", 720)), 2160))
    full_page = bool(config.get("full_page", True))
    update_baseline = bool(config.get("update_baseline", False))
    diff_threshold = max(
        0.0, min(float(config.get("diff_threshold_percent", 0.5)), 100.0)
    )
    pixel_threshold = max(
        0, min(int(config.get("pixel_threshold", 20)), 255)
    )
    wait_seconds = max(0.0, min(float(config.get("wait_seconds", 0.5)), 10.0))
    wait_until = str(config.get("wait_until", "networkidle")).lower()
    if wait_until not in ALLOWED_WAIT_UNTIL:
        wait_until = "networkidle"
    timeout_ms = max(5000, min(int(config.get("timeout_ms", 30_000)), 90_000))
    fail_on_size_change = bool(config.get("fail_on_size_change", True))
    ignore_https_errors = bool(config.get("ignore_https_errors", False))

    key = _key_for(url, width, height, full_page)
    target_dir = _visual_dir(key)
    baseline_path = target_dir / "baseline.png"
    current_path = target_dir / "current.png"
    diff_path = target_dir / "diff.png"
    metadata_path = target_dir / "metadata.json"

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        png = await _capture(
            url,
            width,
            height,
            full_page,
            wait_seconds,
            wait_until,
            timeout_ms,
            ignore_https_errors,
        )
        current_path.write_bytes(png)

        first_run = not baseline_path.exists()
        baseline_created = first_run
        baseline_updated = False

        if first_run or update_baseline:
            baseline_path.write_bytes(png)
            baseline_created = first_run
            baseline_updated = update_baseline
            if diff_path.exists():
                diff_path.unlink(missing_ok=True)
            with Image.open(io.BytesIO(png)) as captured:
                captured_size = captured.size
            write_json(
                metadata_path,
                {
                    "url": url,
                    "key": key,
                    "viewport": {"width": width, "height": height},
                    "full_page": full_page,
                    "created_at": time.time(),
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "bytes": len(png),
                    "image_dimensions": {
                        "width": captured_size[0],
                        "height": captured_size[1],
                    },
                },
            )
            action = "created" if first_run else "updated"
            return {
                "passed": True,
                "summary": (
                    f"Baseline {action}. Run the same configuration again to "
                    "compare against it."
                ),
                "url": url,
                "key": key,
                "baseline_created": baseline_created,
                "baseline_updated": baseline_updated,
                "first_run": first_run,
                "diff_percent": 0.0,
                "changed_pixels": 0,
                "total_pixels": captured_size[0] * captured_size[1],
                "threshold_percent": diff_threshold,
                "pixel_threshold": pixel_threshold,
                "size_changed": False,
                "baseline_url": artifact_url(baseline_path),
                "current_url": artifact_url(current_path),
                "diff_url": None,
                "dimensions": {
                    "width": captured_size[0],
                    "height": captured_size[1],
                },
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }

        try:
            comparison = _compare_images(
                baseline_path, current_path, diff_path, pixel_threshold
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not compare screenshots: {type(exc).__name__}: {exc}"
            ) from exc

        diff_percent = round(comparison["diff_percent"], 4)
        size_pass = not (fail_on_size_change and comparison["size_changed"])
        passed = diff_percent <= diff_threshold and size_pass

        metadata = {
            "url": url,
            "key": key,
            "viewport": {"width": width, "height": height},
            "full_page": full_page,
            "last_compared_at": time.time(),
            "diff_percent": diff_percent,
            "threshold_percent": diff_threshold,
            "current_sha256": hashlib.sha256(png).hexdigest(),
            "baseline_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
            "last_result": "passed" if passed else "failed",
        }
        write_json(metadata_path, metadata)

        if passed:
            summary = (
                f"Visual match: {diff_percent:.3f}% pixels differ "
                f"(threshold {diff_threshold:.3f}%)."
            )
        elif comparison["size_changed"] and fail_on_size_change:
            summary = (
                f"Visual regression: page dimensions changed "
                f"{comparison['baseline_dimensions']['width']}x"
                f"{comparison['baseline_dimensions']['height']} -> "
                f"{comparison['current_dimensions']['width']}x"
                f"{comparison['current_dimensions']['height']}; "
                f"{diff_percent:.3f}% pixels differ."
            )
        else:
            summary = (
                f"Visual regression: {diff_percent:.3f}% pixels differ "
                f"(threshold {diff_threshold:.3f}%)."
            )

        return {
            "passed": passed,
            "summary": summary,
            "url": url,
            "key": key,
            "baseline_created": False,
            "baseline_updated": False,
            "first_run": False,
            "diff_percent": diff_percent,
            "changed_pixels": comparison["changed_pixels"],
            "total_pixels": comparison["total_pixels"],
            "threshold_percent": diff_threshold,
            "pixel_threshold": pixel_threshold,
            "size_changed": comparison["size_changed"],
            "change_bbox": comparison["change_bbox"],
            "dimensions": comparison["current_dimensions"],
            "baseline_dimensions": comparison["baseline_dimensions"],
            "current_dimensions": comparison["current_dimensions"],
            "baseline_url": artifact_url(baseline_path),
            "current_url": artifact_url(current_path),
            "diff_url": artifact_url(diff_path),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
