from __future__ import annotations

import subprocess

from typer.testing import CliRunner

import ontime_cli.hooks as hooks
from ontime_cli.hooks import (
    commit_info,
    commits_to_push,
    hooks_app,
    parse_push_lines,
    repo_from_url,
)

ZERO = "0" * 40

runner = CliRunner()


def test_repo_from_url():
    assert repo_from_url("git@github.com:bob-park/ontime-api.git") == "ontime-api"
    assert repo_from_url("https://github.com/bob-park/ontime-api.git") == "ontime-api"
    assert repo_from_url("https://github.com/bob-park/ontime-api") == "ontime-api"
    assert repo_from_url("git@github.com:ontime-api.git") == "ontime-api"


def test_parse_push_lines_normal():
    lines = [f"refs/heads/main aaa111 refs/heads/main bbb222"]
    assert parse_push_lines(lines) == [("main", "aaa111", "bbb222")]


def test_parse_push_lines_skips_delete_and_junk():
    lines = [
        f"refs/heads/old {ZERO} refs/heads/old bbb222",  # 삭제 push
        "",  # 빈 줄
    ]
    assert parse_push_lines(lines) == []


def test_parse_push_lines_skips_non_branch_refs():
    lines = ["refs/tags/v1.0 aaa111 refs/tags/v1.0 bbb222"]
    assert parse_push_lines(lines) == []


def test_parse_push_lines_new_branch():
    lines = [f"refs/heads/feat aaa111 refs/heads/feat {ZERO}"]
    assert parse_push_lines(lines) == [("feat", "aaa111", ZERO)]


def make_repo(tmp_path, monkeypatch):
    """임시 git repo를 만들고 커밋 2개의 sha를 (첫번째, 두번째) 로 반환."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "bob@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "bob"], check=True)
    shas = []
    for i, msg in enumerate(["first commit", "fix: second\n\nbody line"]):
        (tmp_path / "f.txt").write_text(str(i))
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-qm", msg], check=True)
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        shas.append(out.stdout.strip())
    return shas


def test_commits_to_push_range(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    assert commits_to_push(second, first, "origin") == [second]


def test_commits_to_push_new_branch(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    # 원격에 아무 ref도 없으면 전체 커밋이 대상 (최신순)
    assert commits_to_push(second, "0" * 40, "origin") == [second, first]


def test_commits_to_push_new_branch_excludes_remote_commits(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", first], check=True)
    assert commits_to_push(second, "0" * 40, "origin") == [second]


def test_commit_info(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    assert commit_info(first) == ("bob", "first commit")
    assert commit_info(second) == ("bob", "fix: second")  # 제목 줄만


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        return {}


def test_pre_push_registers_commits(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(hooks, "ApiClient", lambda: fake)
    stdin = f"refs/heads/main {second} refs/heads/main {first}\n"
    result = runner.invoke(
        hooks_app, ["pre-push", "origin", "git@github.com:bob-park/demo.git"], input=stdin
    )
    assert result.exit_code == 0
    assert fake.calls == [
        ("POST", "/v1/developers/commits", {
            "commitId": second,
            "repo": "demo",
            "branch": "main",
            "author": "bob",
            "commitMessage": "fix: second",
        })
    ]
    assert "1개 커밋 등록 완료" in result.output


def test_pre_push_survives_client_init_failure(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)
    def boom():
        raise RuntimeError("로그인이 필요합니다")
    monkeypatch.setattr(hooks, "ApiClient", boom)
    stdin = f"refs/heads/main {second} refs/heads/main {first}\n"
    result = runner.invoke(
        hooks_app, ["pre-push", "origin", "https://github.com/bob-park/demo.git"], input=stdin
    )
    assert result.exit_code == 0
    assert "건너뜀" in result.output


def test_pre_push_survives_git_failure(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(hooks, "ApiClient", lambda: fake)
    stdin = f"refs/heads/main {'a' * 40} refs/heads/main {'0' * 40}\n"
    result = runner.invoke(
        hooks_app, ["pre-push", "origin", "https://github.com/bob-park/demo.git"], input=stdin
    )
    assert result.exit_code == 0
    assert "[ontime]" in result.output
    assert fake.calls == []


def test_pre_push_partial_failure(tmp_path, monkeypatch):
    first, second = make_repo(tmp_path, monkeypatch)

    class FailingClient(FakeClient):
        def request(self, method, path, **kwargs):
            super().request(method, path, **kwargs)
            if kwargs["json"]["commitId"] == second:
                raise hooks.ApiError("DUPLICATE: 이미 등록됨")
            return {}

    fake = FailingClient()
    monkeypatch.setattr(hooks, "ApiClient", lambda: fake)
    stdin = f"refs/heads/main {second} refs/heads/main {'0' * 40}\n"
    result = runner.invoke(
        hooks_app, ["pre-push", "origin", "https://github.com/bob-park/demo.git"], input=stdin
    )
    assert result.exit_code == 0
    assert len(fake.calls) == 2  # 실패해도 나머지 계속 진행
    assert "1개 커밋 등록 완료" in result.output
    assert "1개 실패" in result.output


def hook_path(tmp_path):
    return tmp_path / ".git" / "hooks" / "pre-push"


def test_install_and_uninstall(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch)
    result = runner.invoke(hooks_app, ["install"])
    assert result.exit_code == 0
    hook = hook_path(tmp_path)
    assert hook.exists()
    assert hook.read_text() == hooks.HOOK_SCRIPT
    assert hook.stat().st_mode & 0o111  # 실행 권한
    # 우리 훅은 재설치(업데이트) 허용
    assert runner.invoke(hooks_app, ["install"]).exit_code == 0
    assert runner.invoke(hooks_app, ["uninstall"]).exit_code == 0
    assert not hook.exists()


def test_install_refuses_foreign_hook(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch)
    hook = hook_path(tmp_path)
    hook.write_text("#!/bin/sh\necho other hook\n")
    assert runner.invoke(hooks_app, ["install"]).exit_code == 1
    assert "other hook" in hook.read_text()  # 보존됨
    assert runner.invoke(hooks_app, ["install", "--force"]).exit_code == 0
    assert hooks.MARKER in hook.read_text()


def test_install_outside_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(hooks_app, ["install"]).exit_code == 1


def test_uninstall_when_not_installed(tmp_path, monkeypatch):
    make_repo(tmp_path, monkeypatch)
    result = runner.invoke(hooks_app, ["uninstall"])
    assert result.exit_code == 0
    assert "없습니다" in result.output
