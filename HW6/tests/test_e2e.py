"""End-to-end browser tests for the TestPulse Omni dashboard.

These tests start a real Uvicorn server on a free localhost port, open the
dashboard in headless Chromium, switch modules through the sidebar, and submit
a small load test through the rendered form.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Uvicorn exited before becoming ready (code {process.returncode})."
            )
        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.2)
    raise RuntimeError(f"Uvicorn did not become ready within {timeout:.0f}s.")


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    temp_dir = tempfile.TemporaryDirectory(prefix="testpulse-e2e-")
    log_path = Path(temp_dir.name) / "uvicorn.log"

    env = os.environ.copy()
    env["TESTPULSE_DATA_DIR"] = temp_dir.name
    env["DATABASE_URL"] = (
        f"sqlite:///{(Path(temp_dir.name) / 'testpulse.db').as_posix()}"
    )
    env.setdefault("E2E_NO_SANDBOX", "1")

    log_file = log_path.open("w", encoding="utf-8")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )

    try:
        try:
            _wait_until_ready(base_url, process, timeout=45)
        except Exception:
            log_file.flush()
            log_file.close()
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"Uvicorn failed to start:\n{log_text}") from None
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if not log_file.closed:
            log_file.close()
        temp_dir.cleanup()


def _open_dashboard(page: Page, base_url: str) -> None:
    # The dashboard loads fonts and charts from CDNs, but its navigation and
    # API form do not need them. Blocking HTTPS keeps this test deterministic
    # and offline-friendly.
    page.route(re.compile(r"^https://"), lambda route: route.abort())
    page.goto(f"{base_url}/", wait_until="domcontentloaded", timeout=30_000)
    expect(page).to_have_title(re.compile("TestPulse Omni"))
    expect(page.locator("#api-status")).to_have_text("Online", timeout=20_000)


def test_dashboard_navigation_form_and_rendered_load_result(live_server: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})

            _open_dashboard(page, live_server)

            expect(page.locator("#module-title")).to_have_text("單元測試沙箱")

            page.locator('.nav-item[data-module="integration"]').click()
            expect(page.locator('[data-panel="integration"]')).to_be_visible()
            expect(page.locator("#module-title")).to_have_text("整合測試鏈")

            page.locator('.nav-item[data-module="load"]').click()
            expect(page.locator('[data-panel="load"]')).to_be_visible()
            expect(page.locator("#module-title")).to_have_text("效能與壓力測試")

            target = f"{live_server}/api/health"
            page.locator("#load-url").fill(target)
            page.locator("#load-concurrency").fill("2")
            page.locator("#load-total").fill("5")
            expect(page.locator("#load-url")).to_have_value(target)

            page.locator("#load-run").click()

            result = page.locator("#load-result")
            banner = result.locator(".result-banner")
            expect(banner).to_be_visible(timeout=30_000)
            expect(banner).to_contain_text("PASS")
            expect(result).to_contain_text("RPS")
            expect(result).to_contain_text("Success rate")
            expect(result).to_contain_text("Completed")
        finally:
            browser.close()
