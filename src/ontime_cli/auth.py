from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".config" / "keyflow-auth"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOKENS_FILE = CONFIG_DIR / "tokens.json"

AUTH_URL = "https://auth.keyflow-dev.com/oauth2/authorize"
TOKEN_URL = "https://auth.keyflow-dev.com/oauth2/token"
REVOKE_URL = "https://auth.keyflow-dev.com/oauth2/revoke"
USERINFO_URL = "https://auth.keyflow-dev.com/userinfo"
REDIRECT_URI = "http://localhost:8765/callback"
CALLBACK_PORT = 8765
CALLBACK_TIMEOUT = 120

CONFIG_EXAMPLE = """\
{
  "client_id": "<KeyFlow client id>",
  "client_secret": "<KeyFlow client secret>",
  "scope": ["openid", "profile", "users:read:summary"],
  "api_base_url": "http://localhost:8080/api"
}"""


class AuthError(Exception):
    pass


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise AuthError(
            f"설정 파일이 없습니다: {CONFIG_FILE}\n아래 내용으로 작성하세요:\n{CONFIG_EXAMPLE}"
        )
    config = json.loads(CONFIG_FILE.read_text())
    for key in ("client_id", "client_secret", "scope"):
        if not config.get(key):
            raise AuthError(f"설정 파일에 '{key}' 값이 없습니다: {CONFIG_FILE}")
    return config


def generate_pkce() -> tuple:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def is_expired(tokens: dict) -> bool:
    return time.time() >= tokens["expires_at"]


def save_tokens(token_response: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(token_response.get("expires_in", 300)) - 30,
    }
    TOKENS_FILE.write_text(json.dumps(data))
    TOKENS_FILE.chmod(0o600)


def load_tokens() -> Optional[dict]:
    if not TOKENS_FILE.exists():
        return None
    return json.loads(TOKENS_FILE.read_text())
