from __future__ import annotations

import httpx
from typer.testing import CliRunner

import ontime_cli.vacations as vacations
from ontime_cli.vacations import vacations_app

runner = CliRunner()


def _patch(monkeypatch, config, calls, status=200, body=None):
    monkeypatch.setattr(vacations.auth, "get_user_unique_id", lambda: 42)
    monkeypatch.setattr(vacations.auth, "load_config", lambda: config)

    def fake_post(url, **kwargs):
        calls.append((url, kwargs.get("json")))
        return httpx.Response(
            status, json=body or {"id": "1"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(vacations.httpx, "post", fake_post)


def test_request_posts_full_payload(monkeypatch):
    calls = []
    _patch(monkeypatch, {"document_api_base_url": "http://doc:1234/api"}, calls)
    result = runner.invoke(
        vacations_app,
        ["request", "--start", "2025-05-07", "--reason", "개인사유"],
    )
    assert result.exit_code == 0
    assert calls == [
        ("http://doc:1234/api/v1/documents/vacations", {
            "userUniqueId": 42,
            "vacationType": "GENERAL",
            "vacationSubType": None,
            "startDate": "2025-05-07",
            "endDate": "2025-05-07",  # --end 생략 시 시작일과 동일
            "reason": "개인사유",
            "status": "WAITING",
        })
    ]


def test_request_with_type_subtype_and_end(monkeypatch):
    calls = []
    _patch(monkeypatch, {}, calls)
    result = runner.invoke(
        vacations_app,
        [
            "request",
            "--start", "2025-05-07",
            "--end", "2025-05-09",
            "--type", "COMPENSATORY",
            "--sub-type", "AM_HALF_DAY_OFF",
            "--reason", "개인사유",
        ],
    )
    assert result.exit_code == 0
    url, body = calls[0]
    assert url == "http://localhost:8082/api/v1/documents/vacations"  # 기본 base URL
    assert body["vacationType"] == "COMPENSATORY"
    assert body["vacationSubType"] == "AM_HALF_DAY_OFF"
    assert body["endDate"] == "2025-05-09"


def test_request_rejects_unknown_type(monkeypatch):
    calls = []
    _patch(monkeypatch, {}, calls)
    result = runner.invoke(
        vacations_app,
        ["request", "--start", "2025-05-07", "--reason", "x", "--type", "NOPE"],
    )
    assert result.exit_code != 0
    assert calls == []


def test_request_error_response(monkeypatch):
    calls = []
    _patch(monkeypatch, {}, calls, status=400,
           body={"code": "BAD_REQUEST", "detail": "invalid"})
    result = runner.invoke(
        vacations_app, ["request", "--start", "2025-05-07", "--reason", "x"]
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, vacations.ApiError)
