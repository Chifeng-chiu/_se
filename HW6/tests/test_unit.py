"""Unit tests for pure backend helpers.

These tests do not touch the network, Docker, SQLite, or the browser. They
import service-layer functions directly and verify deterministic inputs and
outputs.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from backend.services.common import percentile, stable_key, validate_http_url
from backend.services.integration_chain import _interpolate, _parse_path
from backend.services.sec_scanner import _probe_url
from backend.services.visual_diff import _compare_images


def test_validate_http_url_accepts_http_and_https() -> None:
    assert validate_http_url(" https://example.com/path?q=1 ") == (
        "https://example.com/path?q=1"
    )
    assert validate_http_url("http://127.0.0.1:8000/api/health") == (
        "http://127.0.0.1:8000/api/health"
    )

    with pytest.raises(ValueError, match="http"):
        validate_http_url("ftp://example.com/file")
    with pytest.raises(ValueError):
        validate_http_url("not-a-url")
    with pytest.raises(ValueError):
        validate_http_url("https://")


def test_percentile_handles_empty_single_and_interpolated_values() -> None:
    assert percentile([], 0.95) == 0.0
    assert percentile([42.0], 0.50) == 42.0
    assert percentile([10.0, 20.0, 30.0], 0.50) == 20.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.50) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 1.0) == 4.0


def test_stable_key_is_deterministic_and_bounded() -> None:
    first = stable_key("visual", "https://example.com", "1280x720")
    second = stable_key("visual", "https://example.com", "1280x720")
    other = stable_key("visual", "https://example.com", "1440x900")

    assert first == second
    assert first != other
    assert len(first) == 20


def test_integration_chain_resolves_extracted_data_flow() -> None:
    context = {
        "vars": {"token": "abc123", "user_id": 7},
        "steps": [
            {
                "name": "login",
                "status": 200,
                "body": {"user": {"id": 7, "role": "admin"}},
            }
        ],
    }

    assert _parse_path("steps.0.body.user.id", context) == 7
    assert _parse_path("steps.login.status", context) == 200
    assert _parse_path("user_id", context) == 7
    assert _interpolate(
        {
            "headers": {"Authorization": "Bearer {{token}}"},
            "params": {"uid": "{{steps.login.body.user.id}}"},
        },
        context,
    ) == {
        "headers": {"Authorization": "Bearer abc123"},
        "params": {"uid": 7},
    }


def test_security_probe_replaces_the_target_query_parameter() -> None:
    payload = "<script>alert(1)</script>"
    probe = _probe_url(
        "https://example.com/search?q=original&page=2",
        "q",
        payload,
    )
    query = parse_qs(urlparse(probe).query)

    assert query["q"] == [payload]
    assert query["page"] == ["2"]


def test_visual_diff_counts_changed_pixels_and_writes_diff(tmp_path) -> None:
    baseline_path = tmp_path / "baseline.png"
    current_path = tmp_path / "current.png"
    diff_path = tmp_path / "diff.png"

    baseline = Image.new("RGB", (100, 100), (255, 255, 255))
    current = baseline.copy()
    current.paste((0, 0, 0), (0, 0, 10, 10))
    baseline.save(baseline_path)
    current.save(current_path)

    result = _compare_images(
        baseline_path=baseline_path,
        current_path=current_path,
        diff_path=diff_path,
        pixel_threshold=10,
    )

    assert result["changed_pixels"] == 100
    assert result["total_pixels"] == 10_000
    assert result["diff_percent"] == 1.0
    assert result["size_changed"] is False
    assert result["change_bbox"] == [0, 0, 10, 10]
    assert diff_path.exists()
    assert diff_path.stat().st_size > 0
