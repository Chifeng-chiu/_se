"""[2] Integration test engine: execute a stateful multi-step API chain.

A step can extract values from a response and later steps can interpolate
them with ``{{token}}`` or ``{{steps.0.body.user.id}}``. Assertions are
evaluated after every response, and the chain stops at the first broken link
unless ``stop_on_failure`` is disabled.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from .common import (
    json_safe,
    mask_mapping,
    validate_http_url,
)

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

_MISSING = object()


def _parse_path(path: str, context: dict[str, Any]) -> Any:
    """Resolve dotted paths against the chain context.

    Supported examples:
      token                       -> extracted variable
      steps.0.body.token          -> response of step 0
      steps.login.status          -> response of the step named login
      body.items.0.id             -> JSON body path
    """
    raw = str(path).strip()
    if not raw:
        return _MISSING
    if raw.startswith("$."):
        raw = raw[2:]

    parts = [part for part in raw.split(".") if part != ""]
    if not parts:
        return _MISSING

    current: Any
    if parts[0] == "steps":
        if len(parts) < 2 or not context.get("steps"):
            return _MISSING
        step_ref = parts[1]
        if step_ref.isdigit():
            index = int(step_ref)
            steps = context["steps"]
            if index >= len(steps):
                return _MISSING
            current = steps[index]
        else:
            found = None
            for step in context["steps"]:
                if step.get("name") == step_ref:
                    found = step
                    break
            if found is None:
                return _MISSING
            current = found
        remaining = parts[2:]
    else:
        if parts[0] == "vars":
            if "vars" not in context:
                return _MISSING
            current = context["vars"]
            remaining = parts[1:]
        elif parts[0] in context:
            current = context[parts[0]]
            remaining = parts[1:]
        elif isinstance(context.get("vars"), dict) and parts[0] in context["vars"]:
            # Extracted variables are addressable directly: {{token}}.
            current = context["vars"]
            remaining = parts
        else:
            return _MISSING

    for part in remaining:
        if isinstance(current, dict):
            if part not in current:
                # HTTP headers are case-insensitive.
                lowered = {str(k).lower(): v for k, v in current.items()}
                if part.lower() in lowered:
                    current = lowered[part.lower()]
                    continue
                return _MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


def _resolve_placeholder(expression: str, context: dict[str, Any]) -> Any:
    value = _parse_path(expression, context)
    if value is _MISSING:
        raise ValueError(f"unresolved chain variable: {{{{ {expression} }}}}")
    return value


def _interpolate(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        full = _PLACEHOLDER.fullmatch(value.strip())
        if full:
            return _resolve_placeholder(full.group(1), context)

        def replace(match: re.Match[str]) -> str:
            resolved = _resolve_placeholder(match.group(1), context)
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved, ensure_ascii=False)
            return "" if resolved is None else str(resolved)

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, dict):
        return {key: _interpolate(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, context) for item in value]
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    op = (operator or "eq").lower()
    if op == "eq":
        return actual == expected or str(actual) == str(expected)
    if op == "ne":
        return not (actual == expected or str(actual) == str(expected))
    if op == "exists":
        return actual is not None and actual is not _MISSING
    if op == "not_exists":
        return actual is None or actual is _MISSING
    if op in {"gt", "gte", "lt", "lte"}:
        try:
            left = float(actual)
            right = float(expected)
        except (TypeError, ValueError):
            return False
        return {
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[op]
    if op == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return str(expected) in str(actual)
    if op == "not_contains":
        return str(expected) not in str(actual)
    if op == "in":
        return actual in expected if isinstance(expected, (list, tuple, set)) else False
    if op in {"regex", "matches"}:
        try:
            return re.search(str(expected), str(actual)) is not None
        except re.error:
            return False
    raise ValueError(f"unsupported assertion operator: {operator}")


def _evaluate_assertion(
    assertion: dict[str, Any],
    response: httpx.Response,
    body: Any,
    elapsed_ms: float,
) -> dict[str, Any]:
    source = str(assertion.get("source", "status"))
    operator = str(assertion.get("op", "eq"))
    expected = assertion.get("value")

    actual: Any
    if source == "status":
        actual = response.status_code
    elif source == "duration_ms":
        actual = round(elapsed_ms, 2)
    elif source.startswith("headers."):
        actual = response.headers.get(source.split(".", 1)[1])
    elif source.startswith("body."):
        actual = _parse_path(source, {"body": body})
    elif source.startswith("json."):
        actual = _parse_path("body." + source.split(".", 1)[1], {"body": body})
    else:
        actual = _parse_path(source, {"body": body})

    if actual is _MISSING:
        actual = None
    passed = _compare(actual, operator, expected)
    return {
        "source": source,
        "op": operator,
        "expected": expected,
        "actual": json_safe(actual),
        "passed": passed,
    }


def _response_body(response: httpx.Response) -> tuple[Any, str]:
    text = response.text
    try:
        return response.json(), text
    except (json.JSONDecodeError, ValueError):
        return text, text


async def run_integration_chain(
    steps: list[dict[str, Any]],
    stop_on_failure: bool = True,
    default_timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Execute the API chain and return a step-by-step diagnostic report."""
    if not steps:
        raise ValueError("at least one integration step is required")
    if len(steps) > 25:
        raise ValueError("a chain may contain at most 25 steps")

    started = time.perf_counter()
    context: dict[str, Any] = {"steps": [], "vars": {}}
    records: list[dict[str, Any]] = []
    all_passed = True

    headers = {
        "User-Agent": "TestPulseOmni/1.0 (integration-chain)",
        "Accept": "application/json, text/plain, */*",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=max(1.0, min(float(default_timeout_seconds), 60.0)),
        headers=headers,
    ) as client:
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                raise ValueError(f"step {index + 1} must be a JSON object")

            step_name = str(raw_step.get("name") or f"Step {index + 1}")
            method = str(raw_step.get("method", "GET")).upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                raise ValueError(f"{step_name}: unsupported HTTP method {method}")

            step_started = time.perf_counter()
            record: dict[str, Any] = {
                "index": index,
                "name": step_name,
                "method": method,
                "status": None,
                "passed": False,
                "assertions": [],
                "extracted": {},
                "error": None,
            }

            try:
                url = validate_http_url(
                    str(_interpolate(raw_step.get("url", ""), context)),
                    f"{step_name} url",
                )
                request_headers = _interpolate(
                    raw_step.get("headers", {}) or {}, context
                )
                request_headers = {
                    str(key): str(value) for key, value in request_headers.items()
                }
                params = _interpolate(raw_step.get("params", {}) or {}, context)
                json_body = _interpolate(raw_step.get("json"), context)
                data_body = _interpolate(raw_step.get("data"), context)
                step_timeout = float(
                    raw_step.get("timeout_seconds", default_timeout_seconds)
                )
                step_timeout = max(1.0, min(step_timeout, 60.0))

                record["url"] = url
                record["request_headers"] = mask_mapping(request_headers)

                response = await client.request(
                    method,
                    url,
                    headers=request_headers,
                    params=params or None,
                    json=json_body if json_body is not None else None,
                    data=data_body if data_body is not None else None,
                    timeout=step_timeout,
                )
                elapsed_ms = round((time.perf_counter() - step_started) * 1000, 2)
                body, body_text = _response_body(response)
                record.update(
                    {
                        "status": response.status_code,
                        "duration_ms": elapsed_ms,
                        "response_headers": {
                            key: value
                            for key, value in response.headers.items()
                            if key.lower()
                            in {
                                "content-type",
                                "content-length",
                                "location",
                                "cache-control",
                                "x-request-id",
                            }
                        },
                        "body_preview": body_text[:4000],
                    }
                )

                # Persist the entire response in the context so later steps can
                # consume fields that are not shown in the UI preview.
                step_context = {
                    "name": step_name,
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body": body,
                    "text": body_text,
                    "url": str(response.url),
                }
                context["steps"].append(step_context)

                assertions = raw_step.get("assertions") or []
                if not isinstance(assertions, list):
                    raise ValueError(f"{step_name}: assertions must be an array")

                expected_status = raw_step.get("expected_status")
                if expected_status is not None:
                    assertions = [
                        {
                            "source": "status",
                            "op": "eq",
                            "value": int(expected_status),
                        },
                        *assertions,
                    ]

                # If no explicit status contract exists, a 4xx/5xx response
                # is considered a broken link in the integration chain.
                if not assertions:
                    assertions = [
                        {"source": "status", "op": "lt", "value": 400}
                    ]

                for assertion in assertions:
                    if not isinstance(assertion, dict):
                        raise ValueError(f"{step_name}: invalid assertion")
                    result = _evaluate_assertion(
                        assertion, response, body, elapsed_ms
                    )
                    record["assertions"].append(result)
                    if not result["passed"]:
                        all_passed = False

                extract_spec = raw_step.get("extract") or {}
                if not isinstance(extract_spec, dict):
                    raise ValueError(f"{step_name}: extract must be an object")
                for variable, path in extract_spec.items():
                    if isinstance(path, dict):
                        path = path.get("path", "")
                    value = _parse_path(str(path), {"body": body})
                    if value is _MISSING:
                        raise ValueError(
                            f"{step_name}: cannot extract '{variable}' from '{path}'"
                        )
                    context["vars"][str(variable)] = value
                    record["extracted"][str(variable)] = json_safe(value)
                record["passed"] = all(
                    assertion["passed"] for assertion in record["assertions"]
                )
                if not record["passed"]:
                    all_passed = False

            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - step_started) * 1000, 2)
                record["status"] = "error"
                record["duration_ms"] = elapsed_ms
                record["error"] = f"{type(exc).__name__}: {exc}"
                record["passed"] = False
                all_passed = False

            # Store only masked values in the report; the unmasked context is
            # kept in memory for interpolation by later steps.
            if record.get("extracted"):
                record["extracted"] = mask_mapping(record["extracted"])
            records.append(record)

            if not record["passed"] and stop_on_failure:
                break

    elapsed_total = round((time.perf_counter() - started) * 1000, 2)
    passed_steps = sum(1 for record in records if record["passed"])
    failed_steps = len(records) - passed_steps
    summary = (
        f"{passed_steps}/{len(steps)} chain steps passed"
        + (f"; {failed_steps} failed" if failed_steps else "")
    )

    return {
        "passed": all_passed and len(records) == len(steps),
        "summary": summary,
        "steps": records,
        "variables": mask_mapping(context["vars"]),
        "total_steps": len(steps),
        "executed_steps": len(records),
        "duration_ms": elapsed_total,
        "data_flow_verified": all_passed and len(records) == len(steps),
    }
