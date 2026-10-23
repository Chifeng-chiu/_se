"""Shared helpers for TestPulse Omni service modules."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# TESTPULSE_DATA_DIR makes the data location configurable inside Docker.
DATA_DIR = Path(
    os.getenv("TESTPULSE_DATA_DIR", str(BACKEND_DIR / "data"))
).resolve()
ARTIFACTS_DIR = DATA_DIR / "artifacts"

MAX_ARTIFACT_NAME = 80


def ensure_data_dirs() -> None:
    """Create the runtime data directories if they do not exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat()


def validate_http_url(value: str, field_name: str = "url") -> str:
    """Validate and normalise a user supplied HTTP(S) target URL."""
    candidate = (value or "").strip()
    if not candidate:
        raise ValueError(f"{field_name} is required")
    if len(candidate) > 4096:
        raise ValueError(f"{field_name} is too long")
    if any(ch.isspace() for ch in candidate):
        raise ValueError(f"{field_name} must not contain whitespace")

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{field_name} must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError(f"{field_name} must include a host")
    return candidate


def artifact_dir(name: str) -> Path:
    ensure_data_dirs()
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-")[:MAX_ARTIFACT_NAME]
    target = ARTIFACTS_DIR / (safe_name or "misc")
    target.mkdir(parents=True, exist_ok=True)
    return target


def artifact_url(path: Path) -> str:
    """Return a browser-accessible URL for a file inside ARTIFACTS_DIR."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ARTIFACTS_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Artifact path is outside the artifacts directory") from exc
    return "/artifacts/" + relative.as_posix()


def stable_key(*parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def cap_string(value: str, limit: int = 20_000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n... [truncated {len(value) - limit} characters]"


def json_safe(value: Any, depth: int = 0) -> Any:
    """Make arbitrary service output safe for SQLite JSON serialization."""
    if depth > 12:
        return "[max depth reached]"
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, str):
        return cap_string(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item, depth + 1) for item in list(value)[:10_000]]
    return cap_string(str(value))


def percentile(values: list[float], ratio: float) -> float:
    """Linear-interpolated percentile (ratio between 0.0 and 1.0)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * max(0.0, min(1.0, ratio))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def mask_secret(value: Any) -> Any:
    """Mask a token-like value while keeping enough context to debug it."""
    if value is None:
        return None
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def mask_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    secret_words = (
        "token",
        "secret",
        "password",
        "passwd",
        "authorization",
        "cookie",
        "api_key",
        "apikey",
        "session",
    )
    masked: dict[str, Any] = {}
    for key, value in mapping.items():
        lowered = str(key).lower()
        if any(word in lowered for word in secret_words):
            masked[str(key)] = mask_secret(value)
        elif isinstance(value, dict):
            masked[str(key)] = mask_mapping(value)
        else:
            masked[str(key)] = value
    return masked


def seconds_since(start: float) -> float:
    return round(time.perf_counter() - start, 4)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
