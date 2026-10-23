"""API / system tests for the FastAPI routes and SQLite history.

The runtime data directory is redirected to a temporary folder before
``backend.main`` is imported. This keeps these tests from writing into the
application's normal ``backend/data`` directory.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="testpulse-api-"))
os.environ["TESTPULSE_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DATA_DIR / 'testpulse.db').as_posix()}"
os.environ.setdefault("E2E_NO_SANDBOX", "1")

atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)

import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint_returns_expected_json(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "TestPulse Omni"
    assert body["version"] == "1.0.0"
    assert body["engines"] == [
        "unit",
        "integration",
        "e2e",
        "load",
        "security",
        "visual",
    ]
    assert isinstance(body["docker_available"], bool)
    assert isinstance(body["docker_socket_visible"], bool)
    assert body["data_dir"] == str(_TEST_DATA_DIR.resolve())


def test_history_endpoint_starts_with_a_valid_empty_or_populated_shape(
    client: TestClient,
) -> None:
    response = client.get("/api/history", params={"limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "count", "limit", "offset"}
    assert isinstance(body["items"], list)
    assert body["count"] == len(body["items"])
    assert body["limit"] == 5
    assert body["offset"] == 0


def test_security_scan_route_persists_and_returns_sqlite_history(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_scan(url: str, timeout_seconds: float) -> dict:
        return {
            "passed": True,
            "summary": "Fake security scan passed for API testing.",
            "score": 92.5,
            "url": url,
            "findings": [],
            "checks": [{"name": "content-security-policy", "passed": True}],
            "timeout_seconds": timeout_seconds,
        }

    monkeypatch.setattr(main_module, "scan_security", fake_scan)

    response = client.post(
        "/api/tests/security",
        json={"url": "https://example.com", "timeout_seconds": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["recorded_status"] == "passed"
    assert body["test_type"] == "security"
    assert body["target"] == "https://example.com"
    assert body["score"] == 92.5
    assert isinstance(body["duration_ms"], int)
    history_id = body["history_id"]
    assert isinstance(history_id, int)
    assert history_id > 0

    detail_response = client.get(f"/api/history/{history_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == history_id
    assert detail["test_type"] == "security"
    assert detail["status"] == "passed"
    assert detail["target"] == "https://example.com"
    assert detail["score"] == 92.5
    assert detail["details"]["summary"] == "Fake security scan passed for API testing."
    assert detail["details"]["findings"] == []

    list_response = client.get(
        "/api/history",
        params={"test_type": "security", "limit": 100},
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["count"] >= 1
    assert any(item["id"] == history_id for item in listed["items"])

    stats_response = client.get("/api/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["total_runs"] >= 1
    assert stats["passed_runs"] >= 1
    assert set(stats) == {
        "total_runs",
        "passed_runs",
        "failed_or_error_runs",
        "pass_rate",
        "avg_duration_ms",
        "by_type",
        "recent",
    }

    assert (_TEST_DATA_DIR / "testpulse.db").exists()


def test_load_route_rejects_invalid_concurrency(client: TestClient) -> None:
    response = client.post(
        "/api/tests/load",
        json={
            "url": "https://example.com",
            "concurrency": 0,
            "total_requests": 1,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item["loc"][-1] == "concurrency" for item in detail)


def test_unknown_history_item_returns_404(client: TestClient) -> None:
    response = client.get("/api/history/999999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "history item not found"}
