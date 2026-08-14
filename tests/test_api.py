from __future__ import annotations

import httpx
import pytest

from ontime_cli.api import format_problem


def _resp(status: int, body: str, content_type: str) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=body.encode(),
        headers={"Content-Type": content_type},
        request=httpx.Request("GET", "http://test/api"),
    )


def test_format_problem_rfc9457():
    body = (
        '{"type":"about:blank","title":"Bad Request","status":400,'
        '"detail":"Invalid request content.","instance":"/api/v1/developers/commits",'
        '"code":"BAD_REQUEST","timestamp":"2026-08-14T10:00:00","exception":"X"}'
    )
    resp = _resp(400, body, "application/problem+json")
    assert format_problem(resp) == "BAD_REQUEST: Invalid request content."


def test_format_problem_non_json():
    resp = _resp(502, "<html>bad gateway</html>", "text/html")
    assert format_problem(resp) == "HTTP 502: <html>bad gateway</html>"
