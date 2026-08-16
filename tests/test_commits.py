from __future__ import annotations

from typer.testing import CliRunner

import ontime_cli.commits as commits
from ontime_cli.commits import commits_app, format_table

runner = CliRunner()


SAMPLE = [
    {
        "id": "123456789",
        "commitId": "abcdef0123456789",
        "repo": "ontime-api",
        "branch": "main",
        "author": "bob",
        "commitMessage": "fix: bug",
        "createdDate": "2026-08-14T10:00:00",
        "createdBy": "bob",
    }
]


def test_format_table_columns():
    out = format_table(SAMPLE)
    lines = out.splitlines()
    assert "id" in lines[0] and "repo" in lines[0]
    assert "abcdef01" in out  # commitId 는 앞 8자만
    assert "abcdef0123456789" not in out
    assert "fix: bug" in out


def test_format_table_empty():
    assert format_table([]) == "(결과 없음)"


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"content": [], "page": {}}


def _patch(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(commits, "ApiClient", lambda: fake)
    monkeypatch.setattr(commits.auth, "get_user_unique_id", lambda: 42)
    return fake


def test_register_includes_user_unique_id(monkeypatch):
    fake = _patch(monkeypatch)
    result = runner.invoke(commits_app, [
        "register", "--commit-id", "abc", "--repo", "o/r",
        "--branch", "main", "--author", "bob", "--message", "fix",
    ])
    assert result.exit_code == 0
    assert fake.calls[0][2]["json"] == {
        "commitId": "abc",
        "repo": "o/r",
        "branch": "main",
        "author": "bob",
        "userUniqueId": 42,
        "commitMessage": "fix",
    }


def test_list_uses_new_spec_params(monkeypatch):
    fake = _patch(monkeypatch)
    result = runner.invoke(commits_app, [
        "list", "--repo", "o/r", "--user-unique-id", "42",
        "--from", "2026-08-01T00:00:00", "--to", "2026-08-14T23:59:59",
    ])
    assert result.exit_code == 0
    params = fake.calls[0][2]["params"]
    assert params["userUniqueId"] == 42
    assert params["commitDateFrom"] == "2026-08-01T00:00:00"
    assert params["commitDateTo"] == "2026-08-14T23:59:59"
    assert params["sort"] == "commitDate,desc"  # 새 기본 정렬
    assert "createdBy" not in params and "createdDateFrom" not in params


def test_list_created_by_option_removed(monkeypatch):
    _patch(monkeypatch)
    assert runner.invoke(commits_app, ["list", "--created-by", "bob"]).exit_code != 0
