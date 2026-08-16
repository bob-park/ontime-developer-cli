from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from . import auth
from .api import ApiClient, ApiError

hooks_app = typer.Typer(help="git hooks 관리 (deprecated)", no_args_is_help=True)

DEPRECATION_WARNING = "[deprecated] git hooks 기능은 더 이상 유지되지 않으며 향후 제거될 예정입니다."

MARKER = "# ontime-developer-cli pre-push hook"
HOOK_SCRIPT = f"""#!/bin/sh
{MARKER}
ontime hooks pre-push "$@" || echo "[ontime] 커밋 등록 실패 (push는 계속 진행)" >&2
exit 0
"""


def repo_from_url(url: str) -> str:
    """remote URL 에서 org/repo 형태의 이름을 추출한다."""
    path = url.rstrip("/")
    if "://" in path:  # https://host/org/repo, ssh://git@host:port/org/repo
        path = path.split("://", 1)[1].split("/", 1)[-1]
    elif ":" in path:  # scp 형식 git@host:org/repo.git
        path = path.split(":", 1)[1]
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return "/".join(path.split("/")[-2:])


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
        user_unique_id = auth.get_user_unique_id()
    except Exception as e:
        typer.echo(f"[ontime] 커밋 등록 건너뜀: {e}", err=True)
        return
    ok = failed = 0
    for branch, local_sha, remote_sha in parse_push_lines(sys.stdin.read().splitlines()):
        try:
            shas = commits_to_push(local_sha, remote_sha, remote)
        except Exception as e:
            typer.echo(f"[ontime] {branch} 커밋 목록 조회 실패: {e}", err=True)
            continue
        for sha in shas:
            try:
                author, subject = commit_info(sha)
                client.request(
                    "POST",
                    "/v1/developers/commits",
                    json={
                        "commitId": sha,
                        "repo": repo,
                        "branch": branch,
                        "author": author,
                        "userUniqueId": user_unique_id,
                        "commitMessage": subject,
                    },
                )
                ok += 1
            except Exception as e:
                typer.echo(f"[ontime] {sha[:8]} 등록 실패: {e}", err=True)
                failed += 1
    if ok or failed:
        message = f"[ontime] {ok}개 커밋 등록 완료"
        if failed:
            message += f" ({failed}개 실패)"
        typer.echo(message)


def _hook_path() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks/pre-push"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        typer.echo("git 저장소가 아닙니다.", err=True)
        raise typer.Exit(1)
    return Path(out.stdout.strip())


@hooks_app.command(deprecated=True)
def install(
    force: bool = typer.Option(False, "--force", help="기존 pre-push 훅 덮어쓰기"),
) -> None:
    """(deprecated) 현재 repo 에 pre-push 커밋 자동 등록 훅을 설치한다."""
    typer.echo(DEPRECATION_WARNING, err=True)
    hook = _hook_path()
    if hook.exists() and MARKER not in hook.read_text() and not force:
        typer.echo(
            "다른 pre-push 훅이 이미 있습니다. --force 로 덮어쓸 수 있습니다.", err=True
        )
        raise typer.Exit(1)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK_SCRIPT)
    hook.chmod(0o755)
    typer.echo(f"pre-push 훅 설치 완료: {hook}")


@hooks_app.command(deprecated=True)
def uninstall() -> None:
    """(deprecated) 설치된 ontime pre-push 훅을 삭제한다."""
    typer.echo(DEPRECATION_WARNING, err=True)
    hook = _hook_path()
    if not hook.exists() or MARKER not in hook.read_text():
        typer.echo("설치된 ontime pre-push 훅이 없습니다.")
        return
    hook.unlink()
    typer.echo("pre-push 훅 삭제 완료.")
