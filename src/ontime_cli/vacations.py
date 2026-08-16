from __future__ import annotations

import enum
import json
from typing import Optional

import httpx
import typer

from . import auth
from .api import ApiError, format_problem

vacations_app = typer.Typer(help="휴가 API", no_args_is_help=True)

DEFAULT_DOCUMENT_BASE_URL = "http://localhost:8082/api"


class VacationType(str, enum.Enum):
    GENERAL = "GENERAL"  # 연차
    COMPENSATORY = "COMPENSATORY"  # 보상 휴가
    OFFICIAL = "OFFICIAL"  # 공가


class VacationSubType(str, enum.Enum):
    AM_HALF_DAY_OFF = "AM_HALF_DAY_OFF"  # 오전 반차
    PM_HALF_DAY_OFF = "PM_HALF_DAY_OFF"  # 오후 반차


@vacations_app.callback()
def _callback() -> None:
    """명령이 하나여도 `vacations request` 서브커맨드 형태를 유지한다."""


@vacations_app.command("request")
def request_(
    start: str = typer.Option(..., "--start", help="시작일 (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", help="종료일 (생략 시 시작일과 동일)"),
    vacation_type: VacationType = typer.Option(
        VacationType.GENERAL, "--type", help="GENERAL(연차)|COMPENSATORY(보상 휴가)|OFFICIAL(공가)"
    ),
    sub_type: Optional[VacationSubType] = typer.Option(
        None, "--sub-type", help="AM_HALF_DAY_OFF(오전 반차)|PM_HALF_DAY_OFF(오후 반차), 생략 시 하루"
    ),
    reason: str = typer.Option(..., "--reason", help="사유"),
) -> None:
    """휴가를 신청한다."""
    base_url = auth.load_config().get("document_api_base_url", DEFAULT_DOCUMENT_BASE_URL)
    resp = httpx.post(
        base_url + "/v1/documents/vacations",
        json={
            "userUniqueId": auth.get_user_unique_id(),
            "vacationType": vacation_type.value,
            "vacationSubType": sub_type.value if sub_type else None,
            "startDate": start,
            "endDate": end or start,
            "reason": reason,
            "status": "WAITING",
        },
    )
    if resp.status_code >= 400:
        raise ApiError(format_problem(resp))
    typer.echo(json.dumps(resp.json(), ensure_ascii=False, indent=2))
