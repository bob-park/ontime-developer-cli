from __future__ import annotations

import subprocess
import sys

import typer

from .api import ApiClient, ApiError

hooks_app = typer.Typer(help="git hooks 관리", no_args_is_help=True)


@hooks_app.callback()
def _hooks() -> None:
    """커맨드가 하나뿐일 때 typer 가 서브커맨드를 없애버리는 것을 막는다."""


def repo_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if ":" in name:  # scp 형식 git@host:repo.git
        name = name.split(":")[-1]
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return name


def parse_push_lines(lines: list) -> list:
    result = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, _remote_ref, remote_sha = parts
        if set(local_sha) == {"0"}:  # 브랜치 삭제 push
            continue
        if not local_ref.startswith("refs/heads/"):  # 태그 등 브랜치가 아닌 ref 제외
            continue
        branch = local_ref[len("refs/heads/"):]
        result.append((branch, local_sha, remote_sha))
    return result


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return out.stdout


def commits_to_push(local_sha: str, remote_sha: str, remote: str) -> list:
    if set(remote_sha) == {"0"}:  # 신규 브랜치: 원격에 없는 커밋 전부
        args = ["rev-list", local_sha, "--not", f"--remotes={remote}"]
    else:
        args = ["rev-list", f"{remote_sha}..{local_sha}"]
    return _git(*args).split()


def commit_info(sha: str) -> tuple:
    author, subject = _git("log", "-1", "--format=%an%x00%s", sha).rstrip("\n").split("\x00", 1)
    return author, subject


@hooks_app.command("pre-push", hidden=True)
def pre_push(remote: str = typer.Argument(...), url: str = typer.Argument(...)) -> None:
    """(내부용) git pre-push 훅 진입점. stdin 으로 push ref 줄들을 받는다."""
    repo = repo_from_url(url)
    try:
        client = ApiClient()
    except Exception as e:
        typer.echo(f"[ontime] 커밋 등록 건너뜀: {e}", err=True)
        return
    ok = failed = 0
    for branch, local_sha, remote_sha in parse_push_lines(sys.stdin.read().splitlines()):
        for sha in commits_to_push(local_sha, remote_sha, remote):
            author, subject = commit_info(sha)
            try:
                client.request(
                    "POST",
                    "/v1/developers/commits",
                    json={
                        "commitId": sha,
                        "repo": repo,
                        "branch": branch,
                        "author": author,
                        "commitMessage": subject,
                    },
                )
                ok += 1
            except Exception as e:
                typer.echo(f"[ontime] {sha[:8]} 등록 실패: {e}", err=True)
                failed += 1
    message = f"[ontime] {ok}개 커밋 등록 완료"
    if failed:
        message += f" ({failed}개 실패)"
    typer.echo(message)
