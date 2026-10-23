"""TestPulse Omni — FastAPI entry point and REST API."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import TestHistory
from .services import common
from .services.e2e_runner import run_e2e
from .services.integration_chain import run_integration_chain
from .services.load_tester import run_load_test
from .services.sec_scanner import scan_security
from .services.unit_sandbox import run_unit_tests
from .services.visual_diff import run_visual_diff

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("testpulse")

FRONTEND_DIR = Path(
    os.getenv("TESTPULSE_FRONTEND_DIR", str(common.PROJECT_DIR / "frontend"))
).resolve()

common.ensure_data_dirs()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    common.ensure_data_dirs()
    logger.info("TestPulse Omni ready; data directory: %s", common.DATA_DIR)
    yield


app = FastAPI(
    title="TestPulse Omni API",
    version="1.0.0",
    description=(
        "All-in-one automated software testing platform covering unit, "
        "integration, E2E, load, security, and visual regression testing."
    ),
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (common.ARTIFACTS_DIR).exists():
    app.mount(
        "/artifacts",
        StaticFiles(directory=str(common.ARTIFACTS_DIR)),
        name="artifacts",
    )
if FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )


# ---------------------------------------------------------------------------
# Request contracts
# ---------------------------------------------------------------------------


class UnitTestRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100_000)
    tests: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: int = Field(default=5, ge=1, le=10)


class IntegrationTestRequest(BaseModel):
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=25)
    stop_on_failure: bool = True
    default_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)


class E2ETestRequest(BaseModel):
    url: str
    expected_title: str | None = None
    title_match: Literal["contains", "exact", "regex"] = "contains"
    selector: str | None = None
    click_selector: str | None = None
    expected_text: str | None = None
    text_selector: str | None = None
    wait_for_selector: str | None = None
    expected_url_contains: str | None = None
    wait_after_click_ms: int = Field(default=300, ge=0, le=10_000)
    timeout_ms: int = Field(default=15_000, ge=1_000, le=60_000)
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
        "domcontentloaded"
    )
    full_page_screenshot: bool = True
    capture_screenshot: bool = True
    ignore_https_errors: bool = False


class LoadTestRequest(BaseModel):
    url: str
    concurrency: int = Field(default=20, ge=1, le=100)
    total_requests: int = Field(default=100, ge=1, le=2000)
    method: Literal[
        "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
    ] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: Any = None
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    min_success_rate: float = Field(default=0.95, ge=0.0, le=1.0)


class SecurityTestRequest(BaseModel):
    url: str
    timeout_seconds: float = Field(default=10.0, ge=2.0, le=30.0)


class VisualTestRequest(BaseModel):
    url: str
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)
    full_page: bool = True
    update_baseline: bool = False
    diff_threshold_percent: float = Field(default=0.5, ge=0.0, le=100.0)
    pixel_threshold: int = Field(default=20, ge=0, le=255)
    wait_seconds: float = Field(default=0.5, ge=0.0, le=10.0)
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
        "networkidle"
    )
    timeout_ms: int = Field(default=30_000, ge=5_000, le=90_000)
    fail_on_size_change: bool = True
    ignore_https_errors: bool = False


# ---------------------------------------------------------------------------
# Execution + persistence helper
# ---------------------------------------------------------------------------


async def execute_and_record(
    test_type: str,
    target: str,
    runner: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run one engine, persist the result, and attach history metadata."""
    started = time.perf_counter()
    try:
        result = await runner()
        if not isinstance(result, dict):
            raise TypeError("test engine returned an invalid result")
        status = "passed" if result.get("passed") else "failed"
    except Exception as exc:
        logger.exception("Test engine %s failed", test_type)
        result = {
            "passed": False,
            "summary": f"{type(exc).__name__}: {exc}",
            "error": str(exc),
            "checks": [],
        }
        status = "error"

    duration_ms = round((time.perf_counter() - started) * 1000)
    score = result.get("score")
    if not isinstance(score, (int, float)):
        score = None
    else:
        score = float(score)

    details = common.json_safe(result)
    history_id: int | None = None
    try:
        with common_session() as db:
            row = TestHistory(
                test_type=test_type,
                target=common.cap_string(str(target or ""), 4000),
                status=status,
                summary=common.cap_string(str(result.get("summary", "")), 4000),
                score=score,
                duration_ms=duration_ms,
                details=details,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            history_id = row.id
    except Exception:
        logger.exception("Could not persist %s test history", test_type)

    response = dict(result)
    response.update(
        {
            "history_id": history_id,
            "recorded_status": status,
            "duration_ms": duration_ms,
            "test_type": test_type,
            "target": target,
        }
    )
    return response


def common_session() -> Session:
    # Local import avoids a circular import at module import time.
    from .database import SessionLocal

    return SessionLocal()


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    docker_socket = Path("/var/run/docker.sock")

    def _docker_available() -> bool:
        try:
            import docker

            client = docker.from_env(timeout=2)
            try:
                return bool(client.ping())
            finally:
                client.close()
        except Exception:
            return False

    docker_available = await asyncio.to_thread(_docker_available)
    return {
        "status": "ok",
        "service": "TestPulse Omni",
        "version": "1.0.0",
        "time": common.now_iso(),
        "data_dir": str(common.DATA_DIR),
        "docker_socket_visible": docker_socket.exists(),
        "docker_available": docker_available,
        "engines": [
            "unit",
            "integration",
            "e2e",
            "load",
            "security",
            "visual",
        ],
    }


@app.post("/api/tests/unit")
async def api_unit_test(payload: UnitTestRequest) -> dict[str, Any]:
    return await execute_and_record(
        "unit",
        "docker://pytest-sandbox",
        lambda: run_unit_tests(
            payload.code,
            payload.tests,
            payload.timeout_seconds,
        ),
    )


@app.post("/api/tests/integration")
async def api_integration_test(payload: IntegrationTestRequest) -> dict[str, Any]:
    first_url = payload.steps[0].get("url") if payload.steps else "api-chain"
    return await execute_and_record(
        "integration",
        str(first_url or "api-chain"),
        lambda: run_integration_chain(
            payload.steps,
            stop_on_failure=payload.stop_on_failure,
            default_timeout_seconds=payload.default_timeout_seconds,
        ),
    )


@app.post("/api/tests/e2e")
async def api_e2e_test(payload: E2ETestRequest) -> dict[str, Any]:
    return await execute_and_record(
        "e2e",
        payload.url,
        lambda: run_e2e(payload.model_dump()),
    )


@app.post("/api/tests/load")
async def api_load_test(payload: LoadTestRequest) -> dict[str, Any]:
    return await execute_and_record(
        "load",
        payload.url,
        lambda: run_load_test(
            url=payload.url,
            concurrency=payload.concurrency,
            total_requests=payload.total_requests,
            method=payload.method,
            headers=payload.headers,
            json_body=payload.json_body,
            timeout_seconds=payload.timeout_seconds,
            min_success_rate=payload.min_success_rate,
        ),
    )


@app.post("/api/tests/security")
async def api_security_test(payload: SecurityTestRequest) -> dict[str, Any]:
    return await execute_and_record(
        "security",
        payload.url,
        lambda: scan_security(payload.url, payload.timeout_seconds),
    )


@app.post("/api/tests/visual")
async def api_visual_test(payload: VisualTestRequest) -> dict[str, Any]:
    return await execute_and_record(
        "visual",
        payload.url,
        lambda: run_visual_diff(payload.model_dump()),
    )


@app.get("/api/history")
def api_history(
    test_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    query = select(TestHistory)
    if test_type:
        query = query.where(TestHistory.test_type == test_type)
    query = (
        query.order_by(TestHistory.created_at.desc(), TestHistory.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(query).scalars().all()
    return {
        "items": [row.to_dict(include_details=False) for row in rows],
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/history/{history_id}")
def api_history_item(
    history_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(TestHistory, history_id)
    if row is None:
        raise HTTPException(status_code=404, detail="history item not found")
    return row.to_dict(include_details=True)


@app.delete("/api/history/{history_id}")
def api_delete_history(
    history_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.get(TestHistory, history_id)
    if row is None:
        raise HTTPException(status_code=404, detail="history item not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": history_id}


@app.get("/api/stats")
def api_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.scalar(select(func.count(TestHistory.id))) or 0
    passed = (
        db.scalar(
            select(func.count(TestHistory.id)).where(
                TestHistory.status == "passed"
            )
        )
        or 0
    )
    average_duration = db.scalar(select(func.avg(TestHistory.duration_ms))) or 0

    rows = db.execute(
        select(
            TestHistory.test_type,
            func.count(TestHistory.id),
            func.sum(case((TestHistory.status == "passed", 1), else_=0)),
            func.avg(TestHistory.duration_ms),
        ).group_by(TestHistory.test_type)
    ).all()

    by_type = [
        {
            "test_type": row[0],
            "count": int(row[1] or 0),
            "passed": int(row[2] or 0),
            "pass_rate": round((row[2] or 0) / row[1] * 100, 1) if row[1] else 0.0,
            "avg_duration_ms": round(float(row[3] or 0), 1),
        }
        for row in rows
    ]

    recent = db.execute(
        select(TestHistory)
        .order_by(TestHistory.created_at.desc(), TestHistory.id.desc())
        .limit(6)
    ).scalars().all()

    return {
        "total_runs": int(total),
        "passed_runs": int(passed),
        "failed_or_error_runs": int(total - passed),
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "avg_duration_ms": round(float(average_duration), 1),
        "by_type": by_type,
        "recent": [row.to_dict(include_details=False) for row in recent],
    }


@app.get("/", include_in_schema=False)
async def index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        status_code=503,
        content={
            "error": "Frontend not found",
            "expected": str(index_file),
            "docs": "/docs",
        },
    )
