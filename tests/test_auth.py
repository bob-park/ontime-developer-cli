from __future__ import annotations

import base64
import hashlib
import time

import pytest

from ontime_cli import auth


def test_generate_pkce():
    verifier, challenge = auth.generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected


def test_is_expired():
    assert auth.is_expired({"expires_at": time.time() - 1})
    assert not auth.is_expired({"expires_at": time.time() + 100})


def test_tokens_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(auth, "TOKENS_FILE", tmp_path / "tokens.json")
    auth.save_tokens(
        {"access_token": "a", "refresh_token": "r", "expires_in": 300}
    )
    tokens = auth.load_tokens()
    assert tokens["access_token"] == "a"
    assert tokens["refresh_token"] == "r"
    assert tokens["expires_at"] > time.time()
    assert (tmp_path / "tokens.json").stat().st_mode & 0o777 == 0o600


def test_load_tokens_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKENS_FILE", tmp_path / "tokens.json")
    assert auth.load_tokens() is None


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "CONFIG_FILE", tmp_path / "config.json")
    with pytest.raises(auth.AuthError):
        auth.load_config()


def test_load_config_missing_key(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"client_id": "x"}')
    monkeypatch.setattr(auth, "CONFIG_FILE", cfg)
    with pytest.raises(auth.AuthError):
        auth.load_config()


def test_load_config_malformed_json(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"client_id": ')
    monkeypatch.setattr(auth, "CONFIG_FILE", cfg)
    with pytest.raises(auth.AuthError):
        auth.load_config()


def test_load_tokens_malformed_json(tmp_path, monkeypatch):
    tok = tmp_path / "tokens.json"
    tok.write_text("not json")
    monkeypatch.setattr(auth, "TOKENS_FILE", tok)
    assert auth.load_tokens() is None
    tok.write_text('{"access_token": "a"}')
    assert auth.load_tokens() is None


def _patch_userinfo(monkeypatch, sub, calls):
    import httpx

    monkeypatch.setattr(auth, "get_access_token", lambda: "tok")
    monkeypatch.setattr(auth, "_user_unique_id", None)

    def fake_get(url, **kwargs):
        calls.append(url)
        return httpx.Response(
            200, json={"sub": sub}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(auth.httpx, "get", fake_get)


def test_get_user_unique_id_numeric_sub(monkeypatch):
    calls = []
    _patch_userinfo(monkeypatch, "12345", calls)
    assert auth.get_user_unique_id() == 12345


def test_get_user_unique_id_non_numeric_sub(monkeypatch):
    calls = []
    _patch_userinfo(monkeypatch, "abc-uuid", calls)
    assert auth.get_user_unique_id() == "abc-uuid"


def test_get_user_unique_id_cached(monkeypatch):
    calls = []
    _patch_userinfo(monkeypatch, "12345", calls)
    auth.get_user_unique_id()
    auth.get_user_unique_id()
    assert len(calls) == 1  # userinfo 는 프로세스당 1회만 호출


def _request_callback(path):
    import threading

    import httpx

    result = {}
    server = auth._bind_server(result)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        resp = httpx.get(f"http://localhost:{auth.CALLBACK_PORT}{path}")
    finally:
        thread.join()
        server.server_close()
    return resp, result


def test_callback_success_page():
    resp, result = _request_callback("/callback?code=abc&state=s")
    assert result == {"code": "abc", "state": "s"}
    assert "로그인 완료" in resp.text
    assert "#7132f5" in resp.text  # 보라 아이콘 + 안내 문구 (Kraken 라이트 카드)
    assert "#f6f6f9" in resp.text  # 라이트 페이지 배경
    assert "이제 이 탭은 닫고 터미널로 돌아가면 돼요" in resp.text
    assert "<button" not in resp.text  # window.close() 는 브라우저가 막으므로 버튼 없음


def test_callback_error_page():
    resp, result = _request_callback("/callback?error=access_denied")
    assert result["error"] == "access_denied"
    assert "로그인 실패" in resp.text
    assert "access_denied" in resp.text
    assert "#c2283b" in resp.text  # 실패 red


def test_callback_error_code_escaped():
    resp, _ = _request_callback("/callback?error=%3Cscript%3E")
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_load_config_ok(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        '{"client_id": "x", "client_secret": "y", "scope": ["openid", "profile"]}'
    )
    monkeypatch.setattr(auth, "CONFIG_FILE", cfg)
    loaded = auth.load_config()
    assert loaded["scope"] == ["openid", "profile"]
