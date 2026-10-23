"""[3] E2E test engine: drive a real Chromium browser with Playwright.

The runner supports navigation, title assertions, selector visibility/click
assertions, post-click URL/text assertions, console error collection, and a
full-page screenshot that is served as an artifact for the dashboard.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright.async_api import (
    async_playwright,
)

from .common import artifact_dir, artifact_url, cap_string, validate_http_url

ALLOWED_WAIT_UNTIL = {"commit", "domcontentloaded", "load", "networkidle"}


def _check(
    name: str,
    passed: bool,
    *,
    expected: Any = None,
    actual: Any = None,
    kind: str = "assertion",
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "passed": bool(passed),
        "expected": expected,
        "actual": cap_string(str(actual), 1000) if actual is not None else None,
    }
    if error:
        payload["error"] = cap_string(error, 2000)
    return payload


def _matches(actual: str, expected: str, mode: str) -> bool:
    if mode == "exact":
        return actual == expected
    if mode == "regex":
        return re.search(expected, actual) is not None
    return expected in actual


def _launch_args() -> list[str]:
    args = ["--disable-dev-shm-usage", "--disable-gpu"]
    # Docker's default seccomp profile and root user cannot use Chromium's
    # namespace sandbox. It can be re-enabled with E2E_NO_SANDBOX=0 on hosts
    # where the browser is run as an unprivileged user.
    if os.getenv("E2E_NO_SANDBOX", "1") == "1":
        args.append("--no-sandbox")
    return args


async def run_e2e(config: dict[str, Any]) -> dict[str, Any]:
    """Run a headless Chromium scenario and expose a screenshot artifact."""
    started = time.perf_counter()
    url = validate_http_url(str(config.get("url", "")), "target URL")

    timeout_ms = max(1000, min(int(config.get("timeout_ms", 15_000)), 60_000))
    wait_until = str(config.get("wait_until", "domcontentloaded")).lower()
    if wait_until not in ALLOWED_WAIT_UNTIL:
        wait_until = "domcontentloaded"

    width = max(320, min(int(config.get("viewport_width", 1280)), 3840))
    height = max(240, min(int(config.get("viewport_height", 720)), 2160))
    capture_screenshot = bool(config.get("capture_screenshot", True))
    full_page = bool(config.get("full_page_screenshot", True))

    checks: list[dict[str, Any]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    error_message: str | None = None
    screenshot_url: str | None = None
    screenshot_path = None

    status_code: int | None = None
    final_url = url
    title = ""
    body_text = ""

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=_launch_args(),
            )
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                ignore_https_errors=bool(config.get("ignore_https_errors", False)),
                user_agent=(
                    "TestPulseOmni/1.0 (E2E; +https://localhost/testpulse) "
                    "Chromium"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)

            page.on(
                "console",
                lambda message: (
                    console_errors.append(cap_string(message.text, 500))
                    if message.type == "error" and len(console_errors) < 20
                    else None
                ),
            )
            page.on(
                "pageerror",
                lambda exception: (
                    page_errors.append(cap_string(str(exception), 800))
                    if len(page_errors) < 20
                    else None
                ),
            )

            try:
                response = await page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=timeout_ms,
                )
                status_code = response.status if response is not None else None
                final_url = page.url
                title = await page.title()

                navigated_ok = status_code is not None and status_code < 400
                checks.append(
                    _check(
                        "Page navigation",
                        navigated_ok,
                        expected="HTTP status < 400",
                        actual=f"HTTP {status_code}" if status_code else "no response",
                        kind="navigation",
                    )
                )

                wait_selector = (config.get("wait_for_selector") or "").strip()
                if wait_selector:
                    try:
                        await page.wait_for_selector(
                            wait_selector,
                            state="visible",
                            timeout=timeout_ms,
                        )
                        checks.append(
                            _check(
                                "Wait for selector",
                                True,
                                expected=wait_selector,
                                actual="visible before timeout",
                            )
                        )
                    except PlaywrightTimeoutError:
                        checks.append(
                            _check(
                                "Wait for selector",
                                False,
                                expected=wait_selector,
                                actual="not visible before timeout",
                            )
                        )

                expected_title = (config.get("expected_title") or "").strip()
                if expected_title:
                    title_mode = str(config.get("title_match", "contains")).lower()
                    try:
                        title_ok = _matches(title, expected_title, title_mode)
                        title_error = None
                    except re.error as exc:
                        title_ok = False
                        title_error = f"invalid title regex: {exc}"
                    checks.append(
                        _check(
                            "Page title",
                            title_ok,
                            expected=f"{title_mode}: {expected_title}",
                            actual=title,
                            error=title_error,
                        )
                    )

                selector = (config.get("selector") or "").strip()
                if selector:
                    try:
                        locator = page.locator(selector)
                        count = await locator.count()
                        visible = count > 0 and await locator.first.is_visible()
                        checks.append(
                            _check(
                                "Selector exists and is visible",
                                visible,
                                expected=selector,
                                actual=f"{count} element(s), visible={visible}",
                            )
                        )
                        if count > 0:
                            enabled = await locator.first.is_enabled()
                            checks.append(
                                _check(
                                    "Selector is enabled",
                                    enabled,
                                    expected=f"{selector} enabled",
                                    actual=str(enabled),
                                )
                            )
                    except PlaywrightError as exc:
                        checks.append(
                            _check(
                                "Selector exists and is visible",
                                False,
                                expected=selector,
                                actual="invalid selector or browser error",
                                error=str(exc),
                            )
                        )

                click_selector = (config.get("click_selector") or "").strip()
                if click_selector:
                    try:
                        click_locator = page.locator(click_selector)
                        click_count = await click_locator.count()
                        if click_count == 0:
                            checks.append(
                                _check(
                                    "Click element",
                                    False,
                                    expected=click_selector,
                                    actual="selector not found",
                                )
                            )
                        else:
                            await click_locator.first.scroll_into_view_if_needed(
                                timeout=timeout_ms
                            )
                            await click_locator.first.click(timeout=timeout_ms)
                            checks.append(
                                _check(
                                    "Click element",
                                    True,
                                    expected=click_selector,
                                    actual="click completed",
                                )
                            )
                    except PlaywrightError as exc:
                        checks.append(
                            _check(
                                "Click element",
                                False,
                                expected=click_selector,
                                actual="click failed",
                                error=str(exc),
                            )
                        )

                    wait_after = max(
                        0, min(int(config.get("wait_after_click_ms", 300)), 10_000)
                    )
                    try:
                        await page.wait_for_load_state(
                            "domcontentloaded", timeout=min(timeout_ms, 5_000)
                        )
                    except PlaywrightTimeoutError:
                        # A click does not always trigger navigation; this is a
                        # best-effort wait, not a failed assertion.
                        pass
                    if wait_after:
                        await page.wait_for_timeout(wait_after)
                    final_url = page.url

                expected_url_part = (config.get("expected_url_contains") or "").strip()
                if expected_url_part:
                    final_url = page.url
                    checks.append(
                        _check(
                            "URL after interaction",
                            expected_url_part in final_url,
                            expected=f"contains {expected_url_part}",
                            actual=final_url,
                        )
                    )

                expected_text = (config.get("expected_text") or "").strip()
                if expected_text:
                    text_selector = (config.get("text_selector") or "").strip()
                    try:
                        if text_selector:
                            text_locator = page.locator(text_selector)
                            if await text_locator.count() == 0:
                                body_text = ""
                                text_found = False
                                text_error = "text selector not found"
                            else:
                                body_text = await text_locator.first.inner_text(
                                    timeout=timeout_ms
                                )
                                text_found = expected_text in body_text
                                text_error = None
                        else:
                            body_text = await page.locator("body").inner_text(
                                timeout=timeout_ms
                            )
                            text_found = expected_text in body_text
                            text_error = None
                    except PlaywrightError as exc:
                        text_found = False
                        text_error = str(exc)
                    checks.append(
                        _check(
                            "Expected text",
                            text_found,
                            expected=f"contains {expected_text}",
                            actual=cap_string(body_text, 1000) if body_text else "(empty)",
                            error=text_error,
                        )
                    )

                title = await page.title()
                final_url = page.url

            except PlaywrightTimeoutError as exc:
                error_message = f"Browser timeout: {exc}"
            except PlaywrightError as exc:
                error_message = f"Playwright error: {exc}"
            finally:
                if capture_screenshot:
                    try:
                        out_dir = artifact_dir("e2e")
                        screenshot_path = out_dir / (
                            f"{time.strftime('%Y%m%d-%H%M%S')}-"
                            f"{uuid.uuid4().hex[:8]}.png"
                        )
                        await page.screenshot(
                            path=str(screenshot_path),
                            full_page=full_page,
                            animations="disabled",
                            caret="hide",
                            timeout=timeout_ms,
                        )
                        screenshot_url = artifact_url(screenshot_path)
                        checks.append(
                            _check(
                                "Screenshot captured",
                                True,
                                expected="PNG artifact",
                                actual=screenshot_url,
                                kind="artifact",
                            )
                        )
                    except Exception as exc:  # page may already be closed
                        console_errors.append(
                            f"Screenshot failed: {type(exc).__name__}: {exc}"
                        )
                        checks.append(
                            _check(
                                "Screenshot captured",
                                False,
                                expected="PNG artifact",
                                actual="capture failed",
                                kind="artifact",
                                error=str(exc),
                            )
                        )

                await context.close()
                await browser.close()

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

    passed_checks = sum(1 for check in checks if check["passed"])
    all_checks_passed = bool(checks) and passed_checks == len(checks)
    overall_passed = all_checks_passed and error_message is None

    if error_message:
        summary = f"E2E failed: {error_message}"
    elif overall_passed:
        summary = f"E2E passed: {passed_checks}/{len(checks)} checks"
    else:
        failed_names = ", ".join(
            check["name"] for check in checks if not check["passed"]
        )
        summary = f"E2E failed: {failed_names or 'no checks executed'}"

    return {
        "passed": overall_passed,
        "summary": summary,
        "url": url,
        "final_url": final_url,
        "status_code": status_code,
        "title": title,
        "checks": checks,
        "checks_passed": passed_checks,
        "checks_total": len(checks),
        "console_errors": console_errors[:20],
        "page_errors": page_errors[:20],
        "screenshot_url": screenshot_url,
        "viewport": {"width": width, "height": height},
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "error": error_message,
    }
