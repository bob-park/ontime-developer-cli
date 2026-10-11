from __future__ import annotations

import datetime

from typer.testing import CliRunner

import ontime_cli.attendance as attendance
from ontime_cli.attendance import attendance_app

runner = CliRunner()

TODAY = datetime.date.today().isoformat()


class FakeClient:
    def __init__(self, records=None):
        self.calls = []
        self.records = records or []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.records if method == "GET" else {"id": 1}


def _patch(monkeypatch, records=None):
    fake = FakeClient(records)
    monkeypatch.setattr(attendance, "ApiClient", lambda: fake)
    monkeypatch.setattr(attendance.auth, "get_user_unique_id", lambda: 42)
    return fake


def test_list_defaults_to_today(monkeypatch):
    fake = _patch(monkeypatch)
    result = runner.invoke(attendance_app, ["list"])
    assert result.exit_code == 0
    assert fake.calls == [
        ("GET", "/v2/attendance/records", {"params": {
            "userUniqueId": 42, "startDate": TODAY, "endDate": TODAY,
        }})
    ]


def test_clock_in_default_office(monkeypatch):
    fake = _patch(monkeypatch)
    result = runner.invoke(attendance_app, ["in"])
    assert result.exit_code == 0
    assert fake.calls == [
        ("POST", "/v2/attendance/records/clock/in", {"json": {
            "userUniqueId": 42,
            "workType": "OFFICE",
            "latitude": 37.4827330,
            "longtitude": 126.8961727,
        }})
    ]


def test_clock_in_rejects_unknown_work_type(monkeypatch):
    _patch(monkeypatch)
    assert runner.invoke(attendance_app, ["in", "--work-type", "BEACH"]).exit_code != 0


def test_clock_out_uses_todays_record(monkeypatch):
    fake = _patch(monkeypatch, [
        {"id": 1, "workingDate": "2000-01-01"},
        {"id": 13286, "workingDate": TODAY},
    ])
    result = runner.invoke(attendance_app, ["out"])
    assert result.exit_code == 0
    assert fake.calls[-1] == ("POST", "/v2/attendance/records/clock/out", {"json": {
        "userUniqueId": 42,
        "attendanceRecordId": 13286,
        "latitude": 37.4827330,
        "longtitude": 126.8961727,
    }})


def test_clock_out_without_today_record_fails(monkeypatch):
    fake = _patch(monkeypatch, [])
    result = runner.invoke(attendance_app, ["out"])
    assert result.exit_code == 1
    assert "오늘 출근 기록이 없습니다" in result.output
    assert all(method == "GET" for method, _, _ in fake.calls)
