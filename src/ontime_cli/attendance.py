from __future__ import annotations

import datetime
import enum
import json
from typing import Optional

import typer

from . import auth
from .api import ApiClient

attendance_app = typer.Typer(help="근태 API", no_args_is_help=True)

# 기록용 좌표라 사무실 위치로 고정한다.
LATITUDE = 37.4827330
LONGITUDE = 126.8961727


class WorkType(str, enum.Enum):
    OFFICE = "OFFICE"  # 사무실
    OUTSIDE = "OUTSIDE"  # 외근
    HOME = "HOME"  # 재택


def _records(client: ApiClient, start: str, end: str) -> list:
    return client.request(
        "GET",
        "/v2/attendance/records",
        params={"userUniqueId": auth.get_user_unique_id(), "startDate": start, "endDate": end},
    )


def _echo(data) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@attendance_app.command("list")
def list_(
    start: Optional[str] = typer.Option(None, "--start", help="시작일 (YYYY-MM-DD, 기본: 오늘)"),
    end: Optional[str] = typer.Option(None, "--end", help="종료일 (YYYY-MM-DD, 기본: 오늘)"),
) -> None:
    """출근 기록을 조회한다."""
    today = datetime.date.today().isoformat()
    _echo(_records(ApiClient(), start or today, end or today))


@attendance_app.command("in")
def clock_in(
    work_type: WorkType = typer.Option(
        WorkType.OFFICE, "--work-type", help="OFFICE(사무실)|OUTSIDE(외근)|HOME(재택)"
    ),
) -> None:
    """출근한다."""
    _echo(ApiClient().request(
        "POST",
        "/v2/attendance/records/clock/in",
        json={
            "userUniqueId": auth.get_user_unique_id(),
            "workType": work_type.value,
            "latitude": LATITUDE,
            "longtitude": LONGITUDE,  # 서버 스펙 필드명 그대로
        },
    ))


@attendance_app.command("out")
def clock_out() -> None:
    """퇴근한다 (오늘 날짜 출근 기록 기준)."""
    client = ApiClient()
    today = datetime.date.today().isoformat()
    todays = [r for r in _records(client, today, today) if r.get("workingDate") == today]
    if not todays:
        typer.echo("오늘 출근 기록이 없습니다", err=True)
        raise typer.Exit(1)
    _echo(client.request(
        "POST",
        "/v2/attendance/records/clock/out",
        json={
            "userUniqueId": auth.get_user_unique_id(),
            "attendanceRecordId": todays[-1]["id"],
            "latitude": LATITUDE,
            "longtitude": LONGITUDE,  # 서버 스펙 필드명 그대로
        },
    ))
