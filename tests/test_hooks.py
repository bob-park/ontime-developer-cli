from __future__ import annotations

import subprocess

from ontime_cli.hooks import commit_info, commits_to_push, parse_push_lines, repo_from_url

ZERO = "0" * 40


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
