"""[5] Security test engine: headers, cookie flags, CORS, and harmless probes.

The scanner performs GET-only checks. It looks for missing hardening headers,
dangerous CORS combinations and cookie flags, then injects benign XSS/SQLi
markers into one query parameter and observes reflections, SQL errors, and
unexpected 5xx responses. It is a smoke test, not a replacement for an
authenticated DAST engagement.
"""

from __future__ import annotations

import html
import re
import time
from collections import Counter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from .common import cap_string, validate_http_url

SQL_ERROR_PATTERNS = [
    r"sql syntax",
    r"you have an error in your sql",
    r"unclosed quotation mark",
    r"syntax error at or near",
    r"pg_query\(\)",
    r"sqlstate",
    r"ora-\d{4,5}",
    r"sqlite3?\.(?:operational|database)error",
    r"mysql_fetch",
    r"odbc sql server driver",
    r"near \".*\": syntax error",
]

PROBES = [
    {
        "kind": "xss",
        "label": "Script tag reflection",
        "payload": "<script>alert(1)</script>",
        "severity": "high",
        "weight": 30,
    },
    {
        "kind": "xss",
        "label": "Attribute break-out reflection",
        "payload": "\"'><img src=x onerror=alert(1)>",
        "severity": "medium",
        "weight": 15,
    },
    {
        "kind": "sqli",
        "label": "Single quote error probe",
        "payload": "'",
        "severity": "high",
        "weight": 25,
    },
    {
        "kind": "sqli",
        "label": "Boolean tautology reflection",
        "payload": "' OR '1'='1",
        "severity": "medium",
        "weight": 12,
    },
]

HEADER_RULES: list[dict[str, Any]] = [
    {
        "header": "content-security-policy",
        "label": "Content-Security-Policy",
        "severity": "high",
        "weight": 15,
        "recommendation": "Define a restrictive CSP and avoid unsafe-inline/unsafe-eval.",
    },
    {
        "header": "strict-transport-security",
        "label": "Strict-Transport-Security",
        "severity": "medium",
        "weight": 10,
        "https_only": True,
        "recommendation": "Use max-age=31536000; includeSubDomains; preload.",
    },
    {
        "header": "x-content-type-options",
        "label": "X-Content-Type-Options",
        "severity": "medium",
        "weight": 8,
        "recommendation": "Set X-Content-Type-Options: nosniff.",
    },
    {
        "header": "x-frame-options",
        "label": "X-Frame-Options",
        "severity": "medium",
        "weight": 8,
        "recommendation": "Set DENY or SAMEORIGIN, or use CSP frame-ancestors.",
    },
    {
        "header": "referrer-policy",
        "label": "Referrer-Policy",
        "severity": "low",
        "weight": 5,
        "recommendation": "Use strict-origin-when-cross-origin or no-referrer.",
    },
    {
        "header": "permissions-policy",
        "label": "Permissions-Policy",
        "severity": "low",
        "weight": 5,
        "recommendation": "Disable browser features that the application does not need.",
    },
    {
        "header": "cross-origin-opener-policy",
        "label": "Cross-Origin-Opener-Policy",
        "severity": "low",
        "weight": 4,
        "recommendation": "Set Cross-Origin-Opener-Policy: same-origin.",
    },
]

SQL_ERROR_RE = re.compile("|".join(f"(?:{pattern})" for pattern in SQL_ERROR_PATTERNS), re.I)


def _finding(
    finding_id: str,
    title: str,
    severity: str,
    detail: str,
    recommendation: str,
    *,
    evidence: str | None = None,
    weight: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": finding_id,
        "title": title,
        "severity": severity,
        "detail": cap_string(detail, 2000),
        "recommendation": recommendation,
        "weight": weight,
    }
    if evidence:
        payload["evidence"] = cap_string(evidence, 800)
    return payload


def _probe_url(url: str, parameter: str, payload: str) -> str:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        pairs = [(parameter, payload)]
    else:
        replaced = False
        updated: list[tuple[str, str]] = []
        for key, value in pairs:
            if key == parameter and not replaced:
                updated.append((key, payload))
                replaced = True
            else:
                updated.append((key, value))
        if not replaced:
            updated.append((parameter, payload))
        pairs = updated
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def _reflection_evidence(body: str, payload: str) -> str | None:
    index = body.find(payload)
    if index < 0:
        return None
    start = max(0, index - 80)
    end = min(len(body), index + len(payload) + 80)
    return body[start:end].replace("\n", " ")


def _severity_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


async def scan_security(
    url: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Return a risk score, header audit, and benign reflection probe report."""
    started = time.perf_counter()
    target = validate_http_url(url, "target URL")
    timeout_seconds = max(2.0, min(float(timeout_seconds), 30.0))
    findings: list[dict[str, Any]] = []
    header_checks: list[dict[str, Any]] = []
    probe_results: list[dict[str, Any]] = []
    score = 100

    parsed = urlparse(target)
    is_https = parsed.scheme == "https"

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={
                "User-Agent": "TestPulseOmni/1.0 (security-smoke-test)",
                "Accept": "text/html,application/json,text/plain,*/*",
            },
        ) as client:
            baseline = await client.get(target)
            headers = baseline.headers

            csp = headers.get("content-security-policy", "")
            frame_ancestors = "frame-ancestors" in csp.lower()

            for rule in HEADER_RULES:
                if rule.get("https_only") and not is_https:
                    header_checks.append(
                        {
                            "header": rule["label"],
                            "present": None,
                            "value": None,
                            "status": "not-applicable",
                        }
                    )
                    continue

                value = headers.get(rule["header"])
                present = value is not None
                if rule["header"] == "x-frame-options" and frame_ancestors:
                    present = True
                    value = value or "(covered by CSP frame-ancestors)"

                header_checks.append(
                    {
                        "header": rule["label"],
                        "present": present,
                        "value": cap_string(value, 500) if value else None,
                        "status": "present" if present else "missing",
                    }
                )

                if not present:
                    score -= rule["weight"]
                    findings.append(
                        _finding(
                            f"header-{rule['header']}",
                            f"Missing {rule['label']}",
                            rule["severity"],
                            f"The response from {target} does not include "
                            f"{rule['label']}.",
                            rule["recommendation"],
                            weight=rule["weight"],
                        )
                    )

            # Weak values are still worth surfacing even when the header exists.
            xcto = headers.get("x-content-type-options", "")
            if xcto and xcto.lower().strip() != "nosniff":
                score -= 5
                findings.append(
                    _finding(
                        "header-xcto-weak",
                        "Weak X-Content-Type-Options value",
                        "low",
                        f"Expected 'nosniff', got '{xcto}'.",
                        "Set X-Content-Type-Options: nosniff.",
                        weight=5,
                    )
                )

            hsts = headers.get("strict-transport-security", "")
            if is_https and hsts:
                match = re.search(r"max-age\s*=\s*(\d+)", hsts, re.I)
                if not match or int(match.group(1)) < 15_552_000:
                    score -= 4
                    findings.append(
                        _finding(
                            "header-hsts-short",
                            "Short HSTS max-age",
                            "low",
                            f"HSTS value is '{hsts}'. A short max-age weakens protection.",
                            "Use max-age=31536000; includeSubDomains.",
                            weight=4,
                        )
                    )

            if csp and ("unsafe-inline" in csp.lower() or "unsafe-eval" in csp.lower()):
                score -= 3
                findings.append(
                    _finding(
                        "csp-unsafe",
                        "CSP allows unsafe directives",
                        "low",
                        "The CSP contains unsafe-inline or unsafe-eval.",
                        "Move inline scripts to files and remove unsafe directives.",
                        evidence=csp,
                        weight=3,
                    )
                )

            allow_origin = headers.get("access-control-allow-origin", "")
            allow_credentials = headers.get(
                "access-control-allow-credentials", ""
            ).lower()
            if allow_origin:
                if allow_origin.strip() == "*" and allow_credentials == "true":
                    score -= 20
                    findings.append(
                        _finding(
                            "cors-wildcard-credentials",
                            "CORS wildcard with credentials",
                            "high",
                            "Access-Control-Allow-Origin is '*' while credentials "
                            "are enabled.",
                            "Reflect only explicitly trusted origins when credentials "
                            "are allowed.",
                            evidence=f"ACAO={allow_origin}; ACAC={allow_credentials}",
                            weight=20,
                        )
                    )
                elif allow_origin.strip() == "*":
                    score -= 6
                    findings.append(
                        _finding(
                            "cors-wildcard",
                            "Permissive CORS wildcard",
                            "medium",
                            "Any origin can read responses from this endpoint.",
                            "Restrict CORS to known front-end origins.",
                            evidence=f"Access-Control-Allow-Origin: {allow_origin}",
                            weight=6,
                        )
                    )

            powered_by = headers.get("x-powered-by")
            if powered_by:
                score -= 5
                findings.append(
                    _finding(
                        "tech-disclosure",
                        "Technology disclosure via X-Powered-By",
                        "low",
                        f"X-Powered-By reveals '{powered_by}'.",
                        "Remove framework version/fingerprint headers.",
                        weight=5,
                    )
                )

            server = headers.get("server", "")
            if server and re.search(r"\d+\.\d+", server):
                score -= 3
                findings.append(
                    _finding(
                        "server-version",
                        "Server version disclosure",
                        "low",
                        f"Server header reveals version information: '{server}'.",
                        "Suppress the version banner at the reverse proxy.",
                        weight=3,
                    )
                )

            for cookie in headers.get_list("set-cookie"):
                cookie_name = cookie.split("=", 1)[0].strip()
                lowered = cookie.lower()
                missing = []
                if is_https and "secure" not in lowered:
                    missing.append("Secure")
                if "httponly" not in lowered:
                    missing.append("HttpOnly")
                if "samesite" not in lowered:
                    missing.append("SameSite")
                if missing:
                    weight = 8 if "HttpOnly" in missing else 5
                    score -= weight
                    findings.append(
                        _finding(
                            f"cookie-{cookie_name}",
                            f"Insecure cookie flags: {cookie_name}",
                            "medium" if "HttpOnly" in missing else "low",
                            f"Cookie '{cookie_name}' is missing: {', '.join(missing)}.",
                            "Set Secure, HttpOnly and SameSite=Lax/Strict on session cookies.",
                            weight=weight,
                        )
                    )

            # A broken baseline makes probe results meaningless.
            if baseline.status_code >= 500:
                findings.append(
                    _finding(
                        "baseline-5xx",
                        "Target returned a server error",
                        "high",
                        f"The baseline request returned HTTP {baseline.status_code}.",
                        "Fix the endpoint availability before running security probes.",
                        weight=25,
                    )
                )
                score -= 25
            else:
                parameter = parse_qsl(parsed.query, keep_blank_values=True)
                probe_parameter = parameter[0][0] if parameter else "q"
                escaped_script = html.escape("<script>alert(1)</script>")

                for probe in PROBES:
                    probe_url = _probe_url(target, probe_parameter, probe["payload"])
                    probe_started = time.perf_counter()
                    result: dict[str, Any] = {
                        "type": probe["kind"],
                        "label": probe["label"],
                        "parameter": probe_parameter,
                        "payload": probe["payload"],
                        "status": None,
                        "reflected": False,
                        "finding": False,
                        "latency_ms": None,
                    }
                    try:
                        response = await client.get(probe_url)
                        probe_body = response.text[:500_000]
                        result["status"] = response.status_code
                        result["latency_ms"] = round(
                            (time.perf_counter() - probe_started) * 1000, 2
                        )
                        result["reflected"] = probe["payload"] in probe_body

                        evidence = _reflection_evidence(
                            probe_body, probe["payload"]
                        )
                        reflected_unescaped = (
                            result["reflected"] and escaped_script not in probe_body
                            if probe["kind"] == "xss"
                            else result["reflected"]
                        )

                        if probe["kind"] == "xss" and reflected_unescaped:
                            result["finding"] = True
                            content_type = response.headers.get("content-type", "")
                            severity = (
                                "high"
                                if "html" in content_type.lower()
                                else "medium"
                            )
                            weight = probe["weight"] if severity == "high" else 10
                            score -= weight
                            findings.append(
                                _finding(
                                    f"xss-reflection-{probe['kind']}",
                                    f"Possible XSS reflection: {probe['label']}",
                                    severity,
                                    f"The payload was reflected without HTML escaping "
                                    f"in the '{probe_parameter}' parameter.",
                                    "Encode output contextually and enforce a strict CSP.",
                                    evidence=evidence,
                                    weight=weight,
                                )
                            )

                        sql_match = SQL_ERROR_RE.search(probe_body)
                        if probe["kind"] == "sqli" and sql_match:
                            result["finding"] = True
                            score -= 25
                            findings.append(
                                _finding(
                                    f"sqli-error-{probe['kind']}",
                                    "SQL error triggered by quote payload",
                                    "high",
                                    f"A database error signature appeared after sending "
                                    f"the payload in '{probe_parameter}'.",
                                    "Use parameterised queries and suppress database errors.",
                                    evidence=sql_match.group(0),
                                    weight=25,
                                )
                            )

                        if response.status_code >= 500 and baseline.status_code < 500:
                            result["finding"] = True
                            score -= 12
                            findings.append(
                                _finding(
                                    "probe-5xx",
                                    f"Payload caused HTTP {response.status_code}",
                                    "medium",
                                    f"The {probe['label']} probe caused an unexpected "
                                    "server error.",
                                    "Validate input and handle malformed data without a 5xx.",
                                    evidence=(evidence or "")[:800],
                                    weight=12,
                                )
                            )
                    except httpx.HTTPError as exc:
                        result["error"] = f"{type(exc).__name__}: {exc}"
                    probe_results.append(result)

    except httpx.HTTPError as exc:
        score = 0
        findings.append(
            _finding(
                "target-unreachable",
                "Target unreachable",
                "high",
                f"Could not fetch {target}: {type(exc).__name__}: {exc}",
                "Verify network access, DNS, TLS, and the target URL.",
                weight=100,
            )
        )
    except Exception as exc:
        score = 0
        findings.append(
            _finding(
                "scan-error",
                "Security scan error",
                "high",
                f"{type(exc).__name__}: {exc}",
                "Check the target URL and backend logs.",
                weight=100,
            )
        )

    score = max(0, min(100, score))
    severities = Counter(finding["severity"] for finding in findings)
    high_or_critical = severities.get("critical", 0) + severities.get("high", 0)
    target_reachable = not any(
        finding["id"] in {"target-unreachable", "scan-error"} for finding in findings
    )
    passed = target_reachable and score >= 70 and high_or_critical == 0

    if not target_reachable:
        summary = "Security scan could not reach the target."
    elif passed:
        summary = f"Security score {score}/100 (grade {_severity_grade(score)})."
    else:
        summary = (
            f"Security score {score}/100 (grade {_severity_grade(score)}); "
            f"{high_or_critical} high-risk finding(s)."
        )

    return {
        "passed": passed,
        "summary": summary,
        "score": score,
        "grade": _severity_grade(score),
        "url": target,
        "header_checks": header_checks,
        "probes": probe_results,
        "findings": findings,
        "severity_counts": dict(severities),
        "high_risk_count": high_or_critical,
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }
