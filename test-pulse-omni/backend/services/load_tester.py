"""[4] Performance/load engine: asynchronous concurrent HTTP requests.

Requests are scheduled with a semaphore so the configured concurrency is a
hard upper bound. The report includes RPS, min/avg/max latency, p50/p95/p99,
status-code distribution, per-second timeline data for Chart.js, and sampled
errors.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Any

import httpx

from .common import percentile, validate_http_url

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


async def run_load_test(
    url: str,
    concurrency: int = 20,
    total_requests: int = 100,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    timeout_seconds: float = 10.0,
    min_success_rate: float = 0.95,
) -> dict[str, Any]:
    target = validate_http_url(url, "target URL")
    concurrency = max(1, min(int(concurrency), 100))
    total_requests = max(1, min(int(total_requests), 2000))
    method = str(method or "GET").upper()
    if method not in ALLOWED_METHODS:
        raise ValueError(f"unsupported HTTP method: {method}")
    timeout_seconds = max(1.0, min(float(timeout_seconds), 60.0))
    min_success_rate = max(0.0, min(float(min_success_rate), 1.0))

    request_headers = {
        "User-Agent": "TestPulseOmni/1.0 (load-test)",
        "Accept": "*/*",
    }
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items()})

    semaphore = asyncio.Semaphore(concurrency)
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    timeout = httpx.Timeout(timeout_seconds)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
        headers=request_headers,
    ) as client:

        async def one_request(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                record: dict[str, Any] = {
                    "index": index,
                    "ok": False,
                    "status": None,
                    "latency_ms": timeout_seconds * 1000.0,
                    "error": None,
                    "offset_s": 0.0,
                }
                try:
                    response = await client.request(
                        method,
                        target,
                        json=json_body if json_body is not None else None,
                    )
                    # Read the body so latency includes the complete response.
                    await response.aread()
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    record.update(
                        {
                            "ok": 200 <= response.status_code < 400,
                            "status": response.status_code,
                            "latency_ms": latency_ms,
                        }
                    )
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    record["latency_ms"] = latency_ms
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    if len(errors) < 20:
                        errors.append(record["error"])
                finally:
                    record["offset_s"] = time.perf_counter() - run_started
                    records.append(record)

        run_started = time.perf_counter()
        await asyncio.gather(
            *(one_request(index) for index in range(total_requests))
        )
        wall_seconds = time.perf_counter() - run_started

    latencies = [float(record["latency_ms"]) for record in records]
    successes = sum(1 for record in records if record["ok"])
    completed = len(records)
    success_rate = (successes / completed) if completed else 0.0
    rps = completed / wall_seconds if wall_seconds > 0 else 0.0

    status_counts = Counter(
        str(record["status"])
        for record in records
        if record["status"] is not None
    )
    error_types = Counter()
    for record in records:
        if record["error"]:
            error_types[record["error"].split(":", 1)[0]] += 1

    # One bucket per elapsed second. This is intentionally cheap to render in
    # Chart.js and reveals stalls even when the overall average looks fine.
    buckets: dict[int, dict[str, float]] = {}
    for record in records:
        second = int(record["offset_s"])
        bucket = buckets.setdefault(
            second, {"requests": 0, "latency_sum": 0.0, "errors": 0}
        )
        bucket["requests"] += 1
        bucket["latency_sum"] += float(record["latency_ms"])
        if not record["ok"]:
            bucket["errors"] += 1

    timeline = []
    for second in sorted(buckets):
        bucket = buckets[second]
        timeline.append(
            {
                "second": second,
                "requests": int(bucket["requests"]),
                "rps": round(bucket["requests"], 2),
                "avg_latency_ms": round(
                    bucket["latency_sum"] / max(1, bucket["requests"]), 2
                ),
                "errors": int(bucket["errors"]),
            }
        )

    passed = completed == total_requests and success_rate >= min_success_rate
    summary = (
        f"{completed}/{total_requests} requests | {rps:.1f} RPS | "
        f"success {success_rate * 100:.1f}% | "
        f"p95 {percentile(latencies, 0.95):.1f} ms"
    )

    return {
        "passed": passed,
        "summary": summary,
        "url": target,
        "method": method,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "completed_requests": completed,
        "successful_requests": successes,
        "failed_requests": completed - successes,
        "success_rate": round(success_rate, 4),
        "min_success_rate": min_success_rate,
        "rps": round(rps, 2),
        "elapsed_seconds": round(wall_seconds, 3),
        "latency": {
            "min_ms": round(min(latencies), 2) if latencies else 0.0,
            "avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "max_ms": round(max(latencies), 2) if latencies else 0.0,
            "p50_ms": round(percentile(latencies, 0.50), 2),
            "p90_ms": round(percentile(latencies, 0.90), 2),
            "p95_ms": round(percentile(latencies, 0.95), 2),
            "p99_ms": round(percentile(latencies, 0.99), 2),
        },
        "status_distribution": dict(sorted(status_counts.items())),
        "timeline": timeline,
        "errors_sample": errors[:20],
        "error_types": dict(error_types),
    }
