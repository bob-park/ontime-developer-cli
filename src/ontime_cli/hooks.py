from __future__ import annotations

import typer

hooks_app = typer.Typer(help="git hooks 관리", no_args_is_help=True)


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
