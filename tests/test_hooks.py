from __future__ import annotations

from ontime_cli.hooks import parse_push_lines, repo_from_url

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
