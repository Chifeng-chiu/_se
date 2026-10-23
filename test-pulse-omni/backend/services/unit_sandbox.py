"""[1] Unit test engine: run user supplied pytest code inside Docker.

The container has no network, no Linux capabilities, a read-only user, memory
and PID limits, and is killed after the configured deadline. Source files are
copied through the Docker API (tarball) rather than a host bind mount, so the
same implementation also works when the backend itself runs in Docker.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import tarfile
import threading
import time
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "testpulse-pytest:latest")
SANDBOX_DIR = Path(__file__).resolve().parent.parent / "sandbox"

_client_lock = threading.Lock()
_client: docker.DockerClient | None = None
_image_lock = threading.Lock()


def _docker_client() -> docker.DockerClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = docker.from_env()
        return _client


def _ensure_image(client: docker.DockerClient) -> None:
    """Build the tiny pytest image on first use if compose has not built it."""
    try:
        client.images.get(SANDBOX_IMAGE)
        return
    except ImageNotFound:
        pass

    with _image_lock:
        try:
            client.images.get(SANDBOX_IMAGE)
            return
        except ImageNotFound:
            pass

        if not (SANDBOX_DIR / "Dockerfile").exists():
            raise RuntimeError(
                f"Docker image '{SANDBOX_IMAGE}' is missing and its Dockerfile "
                f"was not found at {SANDBOX_DIR}."
            )

        client.images.build(
            path=str(SANDBOX_DIR),
            tag=SANDBOX_IMAGE,
            rm=True,
            forcerm=True,
        )


def _make_tar(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in files.items():
            raw = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(raw)
            info.mode = 0o644
            info.mtime = now
            archive.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


def _parse_pytest_output(output: str, exit_code: int | None, timed_out: bool) -> dict:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "warnings": 0,
    }
    labels = {
        "passed": "passed",
        "failed": "failed",
        "error": "errors",
        "errors": "errors",
        "skipped": "skipped",
        "warning": "warnings",
        "warnings": "warnings",
    }
    for amount, label in re.findall(
        r"(\d+)\s+(passed|failed|error|errors|skipped|warning|warnings)\b",
        output,
        flags=re.IGNORECASE,
    ):
        key = labels[label.lower()]
        counts[key] = max(counts[key], int(amount))

    # pytest's final "1 failed, 2 passed in 0.31s" line is the most reliable
    # short summary, but the individual counters above still work when -q is
    # combined with a traceback that contains other numbers.
    final_line = ""
    for line in reversed(output.splitlines()):
        if re.search(r"\b(passed|failed|error|errors|skipped)\b", line):
            final_line = line.strip()
            break

    passed = bool(
        exit_code == 0
        and not timed_out
        and counts["failed"] == 0
        and counts["errors"] == 0
    )
    return {
        "counts": counts,
        "final_line": final_line,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "passed": passed,
    }


def _execute_sync(
    code: str,
    tests: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    client = _docker_client()
    _ensure_image(client)

    container = client.containers.create(
        image=SANDBOX_IMAGE,
        command=[
            "python",
            "-m",
            "pytest",
            "test_solution.py",
            "-q",
            "--tb=short",
            "--disable-warnings",
            "--color=no",
            "-p",
            "no:cacheprovider",
        ],
        working_dir="/workspace",
        environment={
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": "/workspace",
            "HOME": "/tmp",
        },
        network_disabled=True,
        user="65534:65534",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        mem_limit="256m",
        memswap_limit="256m",
        pids_limit=64,
        nano_cpus=500_000_000,
        tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
        labels={"testpulse.role": "pytest-sandbox"},
    )

    timed_out = False
    exit_code: int | None = None
    output = ""
    started = time.perf_counter()

    try:
        container.put_archive(
            "/workspace",
            _make_tar(
                {
                    "solution.py": code,
                    "test_solution.py": tests,
                }
            ),
        )
        container.start()

        # Do not rely on the Docker wait endpoint's optional timeout query:
        # implementations differ across engines. A daemon thread + event gives
        # us a hard wall-clock deadline regardless of the daemon version.
        wait_done = threading.Event()
        wait_result: dict[str, Any] = {}
        wait_errors: list[Exception] = []

        def _wait_for_exit() -> None:
            try:
                wait_result.update(container.wait())
            except Exception as exc:  # surfaced below if the container did not time out
                wait_errors.append(exc)
            finally:
                wait_done.set()

        wait_thread = threading.Thread(
            target=_wait_for_exit,
            name="testpulse-container-wait",
            daemon=True,
        )
        wait_thread.start()
        finished = wait_done.wait(timeout_seconds)

        if not finished:
            timed_out = True
            try:
                container.kill()
            except DockerException:
                pass
            wait_done.wait(2.0)
            exit_code = 124
        elif wait_errors:
            raise DockerException(f"container wait failed: {wait_errors[0]}")
        else:
            exit_code = int(wait_result.get("StatusCode", -1))

        try:
            output = container.logs(stdout=True, stderr=True).decode(
                "utf-8", errors="replace"
            )
        except DockerException:
            output = ""

        # The log stream can lag a fraction of a second behind container exit.
        if not output.strip():
            time.sleep(0.05)
            try:
                output = container.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                )
            except DockerException:
                output = ""
    finally:
        try:
            container.remove(force=True)
        except DockerException:
            pass

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    parsed = _parse_pytest_output(output, exit_code, timed_out)

    if timed_out:
        summary = f"Sandbox timed out after {timeout_seconds}s; container killed."
    elif parsed["passed"]:
        summary = parsed["final_line"] or "pytest passed"
    else:
        failed = parsed["counts"]["failed"] + parsed["counts"]["errors"]
        summary = f"pytest failed ({failed} failing/error tests). {parsed['final_line']}".strip()

    return {
        "passed": parsed["passed"],
        "summary": summary,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "duration_ms": elapsed_ms,
        "counts": parsed["counts"],
        "output": output[-20_000:],
        "image": SANDBOX_IMAGE,
        "network": "disabled",
        "limits": {
            "memory": "256 MB",
            "cpus": 0.5,
            "pids": 64,
            "timeout_seconds": timeout_seconds,
        },
    }


async def run_unit_tests(
    code: str,
    tests: str,
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """Run pytest in an isolated Docker container without blocking asyncio."""
    if not code.strip():
        raise ValueError("solution code must not be empty")
    if not tests.strip():
        raise ValueError("pytest test code must not be empty")
    if len(code) > 100_000 or len(tests) > 100_000:
        raise ValueError("code and tests are limited to 100 KB each")

    timeout_seconds = max(1, min(int(timeout_seconds), 10))
    try:
        return await asyncio.to_thread(_execute_sync, code, tests, timeout_seconds)
    except DockerException as exc:
        return {
            "passed": False,
            "summary": f"Docker sandbox unavailable: {exc}",
            "error": str(exc),
            "counts": {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "warnings": 0,
            },
            "output": "",
        }
    except Exception as exc:  # image build errors, daemon permission errors, etc.
        return {
            "passed": False,
            "summary": f"Sandbox execution error: {type(exc).__name__}: {exc}",
            "error": str(exc),
            "counts": {
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "warnings": 0,
            },
            "output": "",
        }
