from __future__ import annotations

import base64
import hashlib
import json
import os
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
    try:
        config = json.loads(CONFIG_FILE.read_text())
    except ValueError as e:
        raise AuthError(f"설정 파일이 올바른 JSON 형식이 아닙니다: {CONFIG_FILE}") from e
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
    fd = os.open(TOKENS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def load_tokens() -> Optional[dict]:
    if not TOKENS_FILE.exists():
        return None
    try:
        tokens = json.loads(TOKENS_FILE.read_text())
    except ValueError:
        return None
    if not isinstance(tokens, dict) or not all(
        k in tokens for k in ("access_token", "refresh_token", "expires_at")
    ):
        return None
    return tokens


# --- OAuth flow ---------------------------------------------------------

import html as _html
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

# OAuth 리다이렉트 페이지 (Spotify 스타일 다크 카드, 외부 리소스 없이 자기완결)
_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OnTime Developer CLI</title>
</head>
<body style="margin:0;background:#121212;font-family:Circular,'Helvetica Neue',Helvetica,Arial,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;">
  <div style="background:#181818;border-radius:8px;padding:28px 40px;display:flex;flex-direction:column;align-items:center;gap:12px;box-shadow:rgba(0,0,0,0.5) 0px 8px 24px;">
    <div style="width:44px;height:44px;border-radius:50%;background:{icon_bg};color:#000;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:700;">{icon}</div>
    <div style="font-size:20px;font-weight:700;color:#fff;">{title}</div>
    <div style="font-size:12px;color:#b3b3b3;text-align:center;line-height:1.5;">{desc}</div>
    <button onclick="window.close()" style="margin-top:6px;{button_style}font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;padding:10px 26px;border-radius:9999px;cursor:pointer;">창 닫기</button>
  </div>
</body>
</html>"""


def _render_callback_page(error: Optional[str]) -> str:
    if error:
        return _PAGE_TEMPLATE.format(
            icon_bg="#f3727f",
            icon="✕",
            title="로그인 실패",
            desc=(
                "인증이 완료되지 않았습니다.<br>터미널에서 "
                f'<span style="color:#f3727f;font-weight:700;">{_html.escape(error)}</span>'
                " 오류를 확인하고 다시 시도하세요."
            ),
            button_style="background:transparent;color:#fff;border:1px solid #7c7c7c;",
        )
    return _PAGE_TEMPLATE.format(
        icon_bg="#1ed760",
        icon="✓",
        title="로그인 완료",
        desc="OnTime Developer CLI 인증이 끝났습니다.<br>이 창을 닫고 터미널로 돌아가세요.",
        button_style="background:#1ed760;color:#000;border:none;",
    )


def _bind_server(result: dict) -> HTTPServer:
    """localhost:8765 에 콜백 수신 서버를 바인딩한다 (브라우저를 열기 전에 호출)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            result.update(params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_render_callback_page(params.get("error")).encode())

        def log_message(self, *args):
            pass

    try:
        server = HTTPServer(("localhost", CALLBACK_PORT), Handler)
    except OSError as e:
        raise AuthError(f"콜백 포트 {CALLBACK_PORT} 를 열 수 없습니다: {e}") from e
    server.timeout = 1
    return server


def _await_callback(server: HTTPServer, result: dict, state: str) -> str:
    """이미 바인딩된 서버에서 authorization code 콜백을 기다린다."""
    deadline = time.time() + CALLBACK_TIMEOUT
    with server:
        while not result and time.time() < deadline:
            server.handle_request()

    if not result:
        raise AuthError(f"로그인 콜백 대기 시간({CALLBACK_TIMEOUT}초)을 초과했습니다.")
    if "error" in result:
        raise AuthError(f"인증 실패: {result['error']}")
    if result.get("state") != state:
        raise AuthError("state 값이 일치하지 않습니다. 다시 시도하세요.")
    if "code" not in result:
        raise AuthError("콜백에 code 가 없습니다. 다시 시도하세요.")
    return result["code"]


def login() -> None:
    config = load_config()
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(config["scope"]),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    result: dict = {}
    server = _bind_server(result)
    print("브라우저에서 로그인을 진행하세요. 열리지 않으면 아래 URL을 직접 여세요:")
    print(url)
    webbrowser.open(url)
    code = _await_callback(server, result, state)
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        auth=(config["client_id"], config["client_secret"]),
    )
    if resp.status_code != 200:
        raise AuthError(f"토큰 교환 실패 ({resp.status_code}): {resp.text}")
    save_tokens(resp.json())


def logout() -> None:
    tokens = load_tokens()
    if tokens is None:
        raise AuthError("로그인 상태가 아닙니다.")
    try:
        config = load_config()
        httpx.post(
            REVOKE_URL,
            data={"token": tokens["refresh_token"], "token_type_hint": "refresh_token"},
            auth=(config["client_id"], config["client_secret"]),
        )
    except (AuthError, httpx.HTTPError):
        pass  # revoke 는 best-effort, 로컬 토큰 삭제가 본질
    TOKENS_FILE.unlink()


def refresh_tokens(config: dict, tokens: dict) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
        auth=(config["client_id"], config["client_secret"]),
    )
    if resp.status_code != 200:
        raise AuthError("토큰 갱신에 실패했습니다. 다시 `ontime login` 하세요.")
    data = resp.json()
    data.setdefault("refresh_token", tokens["refresh_token"])
    save_tokens(data)
    return load_tokens()


def get_access_token() -> str:
    tokens = load_tokens()
    if tokens is None:
        raise AuthError("로그인이 필요합니다: `ontime login` 을 먼저 실행하세요.")
    if is_expired(tokens):
        tokens = refresh_tokens(load_config(), tokens)
    return tokens["access_token"]


_user_unique_id = None


def get_user_unique_id():
    """userinfo 의 sub 를 userUniqueId 로 반환한다 (프로세스당 1회 조회 후 캐시)."""
    global _user_unique_id
    if _user_unique_id is None:
        token = get_access_token()
        resp = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            raise AuthError(f"userinfo 조회 실패 ({resp.status_code}): {resp.text}")
        sub = str(resp.json()["sub"])
        _user_unique_id = int(sub) if sub.isdigit() else sub  # API 스펙상 int64
    return _user_unique_id
