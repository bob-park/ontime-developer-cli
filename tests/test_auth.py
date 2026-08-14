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


def test_load_config_ok(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        '{"client_id": "x", "client_secret": "y", "scope": ["openid", "profile"]}'
    )
    monkeypatch.setattr(auth, "CONFIG_FILE", cfg)
    loaded = auth.load_config()
    assert loaded["scope"] == ["openid", "profile"]
