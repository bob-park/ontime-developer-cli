from __future__ import annotations

import httpx
import pytest

from ontime_cli import api
from ontime_cli.api import ApiClient, format_problem


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


def test_format_problem_json_not_object():
    resp = _resp(400, "[1,2]", "application/json")
    assert format_problem(resp) == "HTTP 400: [1,2]"


def _patch_auth(monkeypatch, refresh_calls):
    far_future = 4102444800  # 2100-01-01
    monkeypatch.setattr(
        api.auth, "load_config",
        lambda: {"client_id": "c", "client_secret": "s", "scope": ["openid"]},
    )
    monkeypatch.setattr(
        api.auth, "load_tokens",
        lambda: {"access_token": "old", "refresh_token": "r", "expires_at": far_future},
    )
    monkeypatch.setattr(api.auth, "is_expired", lambda tokens: False)

    def fake_refresh(config, tokens):
        refresh_calls.append(tokens)
        return {"access_token": "new", "refresh_token": "r", "expires_at": far_future}

    monkeypatch.setattr(api.auth, "refresh_tokens", fake_refresh)


def test_request_retries_once_after_401(monkeypatch):
    refresh_calls = []
    _patch_auth(monkeypatch, refresh_calls)

    sent = []
    responses = [
        _resp(401, '{"code":"UNAUTHORIZED","detail":"expired"}', "application/problem+json"),
        _resp(200, '{"ok":true}', "application/json"),
    ]

    def fake_request(method, url, **kwargs):
        sent.append(kwargs["headers"]["Authorization"])
        return responses[len(sent) - 1]

    monkeypatch.setattr(api.httpx, "request", fake_request)

    assert ApiClient().request("GET", "/x") == {"ok": True}
    assert len(refresh_calls) == 1
    assert sent == ["Bearer old", "Bearer new"]


def test_request_2xx_non_json_body(monkeypatch):
    _patch_auth(monkeypatch, [])
    monkeypatch.setattr(
        api.httpx, "request",
        lambda method, url, **kwargs: _resp(200, "not json", "text/plain"),
    )
    with pytest.raises(api.ApiError, match="응답이 JSON 형식이 아닙니다"):
        ApiClient().request("GET", "/x")
