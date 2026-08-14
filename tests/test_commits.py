from __future__ import annotations

from ontime_cli.commits import format_table


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
