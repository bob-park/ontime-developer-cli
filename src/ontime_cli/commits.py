from __future__ import annotations

import json
from typing import Optional

import typer

from .api import ApiClient

commits_app = typer.Typer(help="커밋 API", no_args_is_help=True)

_COLUMNS = [
    ("id", "id"),
    ("commit", "commitId"),
    ("repo", "repo"),
    ("branch", "branch"),
    ("author", "author"),
    ("message", "commitMessage"),
    ("createdDate", "createdDate"),
]


def format_table(items: list) -> str:
    if not items:
        return "(결과 없음)"
    rows = []
    for item in items:
        row = []
        for _, key in _COLUMNS:
            value = str(item.get(key, ""))
            if key == "commitId":
                value = value[:8]
            row.append(value)
        rows.append(row)
    headers = [h for h, _ in _COLUMNS]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  ".join("-" * w for w in widths),
    ]
    for r in rows:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(len(r))))
    return "\n".join(lines)


@commits_app.command("register")
def register(
    commit_id: str = typer.Option(..., "--commit-id", help="커밋 해시"),
    repo: str = typer.Option(..., "--repo", help="저장소 이름"),
    branch: str = typer.Option(..., "--branch", help="브랜치 이름"),
    author: str = typer.Option(..., "--author", help="커밋 작성자"),
    message: str = typer.Option(..., "--message", help="커밋 메시지"),
) -> None:
    """신규 커밋을 등록한다."""
    data = ApiClient().request(
        "POST",
        "/v1/developers/commits",
        json={
            "commitId": commit_id,
            "repo": repo,
            "branch": branch,
            "author": author,
            "commitMessage": message,
        },
    )
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@commits_app.command("list")
def list_(
    repo: Optional[str] = typer.Option(None, "--repo", help="저장소 이름"),
    branch: Optional[str] = typer.Option(None, "--branch", help="브랜치 이름"),
    author: Optional[str] = typer.Option(None, "--author", help="커밋 작성자"),
    message: Optional[str] = typer.Option(None, "--message", help="커밋 메시지 (부분 일치)"),
    created_from: Optional[str] = typer.Option(None, "--from", help="등록일 시작 (ISO datetime)"),
    created_to: Optional[str] = typer.Option(None, "--to", help="등록일 종료 (ISO datetime)"),
    created_by: Optional[str] = typer.Option(None, "--created-by", help="등록자"),
    page: int = typer.Option(0, "--page", help="페이지 번호 (zero-based)"),
    size: int = typer.Option(25, "--size", help="페이지당 항목 수"),
    sort: str = typer.Option("createdDate,desc", "--sort", help="정렬 ({field},{asc|desc})"),
    as_json: bool = typer.Option(False, "--json", help="raw JSON 출력"),
) -> None:
    """커밋 목록을 조회한다."""
    params = {
        "repo": repo,
        "branch": branch,
        "author": author,
        "commitMessage": message,
        "createdDateFrom": created_from,
        "createdDateTo": created_to,
        "createdBy": created_by,
        "page": page,
        "size": size,
        "sort": sort,
    }
    params = {k: v for k, v in params.items() if v is not None}
    data = ApiClient().request("GET", "/v1/developers/commits", params=params)
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    typer.echo(format_table(data.get("content", [])))
    page_info = data.get("page", {})
    typer.echo(
        f"page {page_info.get('number', 0) + 1}/{page_info.get('totalPages', 1)}"
        f" (total {page_info.get('totalElements', 0)})"
    )
