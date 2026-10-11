from __future__ import annotations

import json

import httpx
import typer

from . import auth
from .api import ApiError
from .attendance import attendance_app
from .commits import commits_app
from .hooks import hooks_app
from .vacations import vacations_app

app = typer.Typer(help="OnTime Developer CLI", no_args_is_help=True)

app.add_typer(commits_app, name="commits")
app.add_typer(hooks_app, name="hooks")
app.add_typer(vacations_app, name="vacations")
app.add_typer(attendance_app, name="attendance")


@app.command()
def login() -> None:
    """KeyFlow Auth 로 브라우저 로그인한다."""
    auth.login()
    typer.echo("로그인 완료. 토큰이 저장되었습니다.")


@app.command()
def logout() -> None:
    """저장된 토큰을 삭제(및 revoke)한다."""
    auth.logout()
    typer.echo("로그아웃 완료.")


@app.command()
def whoami() -> None:
    """현재 로그인한 사용자 정보를 표시한다."""
    token = auth.get_access_token()
    resp = httpx.get(auth.USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise auth.AuthError(f"userinfo 조회 실패 ({resp.status_code}): {resp.text}")
    typer.echo(json.dumps(resp.json(), ensure_ascii=False, indent=2))


def run() -> None:
    try:
        app()
    except (auth.AuthError, ApiError) as e:
        typer.echo(str(e), err=True)
        raise SystemExit(1)
    except httpx.HTTPError as e:
        typer.echo(f"네트워크 오류: {e}", err=True)
        raise SystemExit(1)
