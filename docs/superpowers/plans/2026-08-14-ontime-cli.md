# OnTime Developer CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KeyFlow Auth OAuth 2.0 로그인(유지 포함)과 OnTime Developer 커밋 API(등록/조회)를 제공하는 `ontime` CLI를 만든다.

**Architecture:** typer 기반 CLI + httpx HTTP 클라이언트. OAuth authorization code + PKCE flow는 stdlib(`http.server`, `webbrowser`)로 직접 구현. 토큰은 `~/.config/keyflow-auth/tokens.json`(0600), 클라이언트 자격증명은 사용자가 작성하는 `~/.config/keyflow-auth/config.json`에서 읽는다.

**Tech Stack:** Python ≥3.9, typer, httpx, pytest(dev), uv(빌드/실행), hatchling(빌드 백엔드)

**Spec:** `docs/superpowers/specs/2026-08-14-ontime-cli-design.md`

## Global Constraints

- `requires-python = ">=3.9"` — 모든 코드에 `from __future__ import annotations` 사용, `X | None` 런타임 표현 금지 (`Optional` 사용)
- 의존성은 typer, httpx 두 개만. dev 의존성은 pytest만
- client_id/client_secret 실제 값을 코드·문서·커밋에 절대 포함하지 않는다
- config 경로: `~/.config/keyflow-auth/config.json`, 토큰: `~/.config/keyflow-auth/tokens.json` (권한 0600)
- redirect URI는 정확히 `http://localhost:8765/callback` (KeyFlow 서버에 이 값으로 등록됨)
- API base URL 기본값: `http://localhost:8080/api`
- 에러 메시지는 한국어, stderr 출력, exit code 1
- 커맨드 실행은 `uv run ontime ...`, 테스트는 `uv run pytest`

---

### Task 1: 프로젝트 스캐폴드

**Files:**
- Modify: `pyproject.toml`
- Delete: `main.py` (루트의 PyCharm 샘플)
- Create: `src/ontime_cli/__init__.py`
- Create: `src/ontime_cli/main.py`

**Interfaces:**
- Consumes: 없음
- Produces: `ontime_cli.main:app` (typer.Typer 인스턴스), `ontime_cli.main:run` (entry point 함수). 이후 Task들이 `main.py`에 커맨드를 추가한다.

- [ ] **Step 1: pyproject.toml 전체 교체**

```toml
[project]
name = "ontime-developer-cli"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "typer>=0.12",
    "httpx>=0.27",
]

[project.scripts]
ontime = "ontime_cli.main:run"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ontime_cli"]
```

- [ ] **Step 2: 루트 main.py 삭제, 패키지 생성**

```bash
git rm main.py
mkdir -p src/ontime_cli
touch src/ontime_cli/__init__.py
```

- [ ] **Step 3: src/ontime_cli/main.py 작성 (골격만)**

```python
from __future__ import annotations

import typer

app = typer.Typer(help="OnTime Developer CLI", no_args_is_help=True)


def run() -> None:
    app()
```

- [ ] **Step 4: 설치 및 동작 확인**

Run: `uv sync && uv run ontime --help`
Expected: exit 0, "OnTime Developer CLI" 도움말 출력 (커맨드 없음 상태)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/ontime_cli
git commit -m "feat: scaffold ontime CLI package (typer + httpx)"
```

---

### Task 2: auth 코어 로직 (config, PKCE, 토큰 파일) — TDD

**Files:**
- Create: `src/ontime_cli/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: 없음
- Produces (`ontime_cli.auth`):
  - `AuthError(Exception)`
  - `CONFIG_DIR: Path`, `CONFIG_FILE: Path`, `TOKENS_FILE: Path` (테스트에서 monkeypatch 대상)
  - `AUTH_URL`, `TOKEN_URL`, `REVOKE_URL`, `USERINFO_URL`, `REDIRECT_URI: str`
  - `load_config() -> dict` — 필수 키 `client_id`, `client_secret`, `scope`(list). 파일 없음/키 누락 시 `AuthError`
  - `generate_pkce() -> tuple` — `(verifier, challenge)` S256
  - `is_expired(tokens: dict) -> bool`
  - `save_tokens(token_response: dict) -> None` — token 엔드포인트 응답을 받아 저장
  - `load_tokens() -> Optional[dict]` — `{"access_token", "refresh_token", "expires_at"}` 또는 None

- [ ] **Step 1: 실패하는 테스트 작성 — tests/test_auth.py**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError` 또는 `AttributeError` (auth 모듈 없음)

- [ ] **Step 3: src/ontime_cli/auth.py 작성 (코어 부분)**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_auth.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/ontime_cli/auth.py tests/test_auth.py
git commit -m "feat: auth core - config load, PKCE, token file (TDD)"
```

---

### Task 3: OAuth 로그인 flow + login/logout/whoami 커맨드

**Files:**
- Modify: `src/ontime_cli/auth.py` (Task 2 코드 아래에 추가)
- Modify: `src/ontime_cli/main.py` (전체 교체)

**Interfaces:**
- Consumes: Task 2의 `auth` 코어 전부
- Produces (`ontime_cli.auth`):
  - `login() -> None` — 브라우저 OAuth flow 수행 후 토큰 저장
  - `logout() -> None` — revoke 시도(best-effort) + tokens.json 삭제
  - `refresh_tokens(config: dict, tokens: dict) -> dict` — 갱신 후 저장된 새 토큰 dict 반환, 실패 시 `AuthError`
  - `get_access_token() -> str` — 저장된 토큰 로드, 만료 시 선제 갱신, 미로그인 시 `AuthError`
- Produces (`ontime_cli.main`): `run()`이 `AuthError`/`ApiError`/`httpx.HTTPError`를 잡아 stderr + exit 1 처리. Task 4의 `ApiError`는 이 시점엔 없으므로 **Task 3에서는 AuthError와 httpx.HTTPError만** 처리하고 Task 4에서 ApiError를 추가한다.

- [ ] **Step 1: auth.py에 flow 코드 추가 (파일 끝에)**

```python
# --- OAuth flow ---------------------------------------------------------

import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx


def _await_callback(state: str) -> str:
    """localhost:8765 에서 authorization code 콜백을 기다린다."""
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in parse_qs(parsed.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>로그인 완료. 이 창을 닫고 터미널로 돌아가세요.</h2>".encode()
            )

        def log_message(self, *args):
            pass

    try:
        server = HTTPServer(("localhost", CALLBACK_PORT), Handler)
    except OSError as e:
        raise AuthError(f"콜백 포트 {CALLBACK_PORT} 를 열 수 없습니다: {e}") from e

    server.timeout = 1
    deadline = time.time() + CALLBACK_TIMEOUT
    with server:
        # 서버가 리스닝 중인 상태에서 브라우저를 연다 (호출측에서 open 후 진입해도
        # HTTPServer 는 생성 시점부터 listen 하므로 레이스 없음)
        while not result and time.time() < deadline:
            server.handle_request()

    if not result:
        raise AuthError(f"로그인 콜백 대기 시간({CALLBACK_TIMEOUT}초)을 초과했습니다.")
    if "error" in result:
        raise AuthError(f"인증 실패: {result['error']}")
    if result.get("state") != state:
        raise AuthError("state 값이 일치하지 않습니다. 다시 시도하세요.")
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
    print("브라우저에서 로그인을 진행하세요. 열리지 않으면 아래 URL을 직접 여세요:")
    print(url)
    webbrowser.open(url)
    code = _await_callback(state)
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
```

- [ ] **Step 2: main.py 전체 교체**

```python
from __future__ import annotations

import json

import httpx
import typer

from . import auth

app = typer.Typer(help="OnTime Developer CLI", no_args_is_help=True)


@app.command()
def login() -> None:
    """KeyFlow Auth 로 브라우저 로그인한다."""
    auth.login()
    typer.echo("로그인 완료. 토큰이 저장되었습니다.")


@app.command()
def logout() -> None:
    """저장된 토큰을 삭제(및 revoke)한다."""
    auth.logout()
    typer.echo("로그아웃 완료.")


@app.command()
def whoami() -> None:
    """현재 로그인한 사용자 정보를 표시한다."""
    token = auth.get_access_token()
    resp = httpx.get(auth.USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise auth.AuthError(f"userinfo 조회 실패 ({resp.status_code}): {resp.text}")
    typer.echo(json.dumps(resp.json(), ensure_ascii=False, indent=2))


def run() -> None:
    try:
        app()
    except auth.AuthError as e:
        typer.echo(str(e), err=True)
        raise SystemExit(1)
    except httpx.HTTPError as e:
        typer.echo(f"네트워크 오류: {e}", err=True)
        raise SystemExit(1)
```

- [ ] **Step 3: 기존 테스트 회귀 + 커맨드 노출 확인**

Run: `uv run pytest -v && uv run ontime --help && uv run ontime login --help`
Expected: 7 passed. `--help`에 login/logout/whoami 표시. `login --help` 정상 출력

- [ ] **Step 4: 미로그인 상태 에러 경로 확인**

Run: `HOME=$(mktemp -d) uv run ontime whoami; echo "exit=$?"`
Expected: stderr에 "로그인이 필요합니다" 메시지, exit=1

- [ ] **Step 5: Commit**

```bash
git add src/ontime_cli/auth.py src/ontime_cli/main.py
git commit -m "feat: OAuth login flow + login/logout/whoami commands"
```

---

### Task 4: 인증된 API 클라이언트 — TDD

**Files:**
- Create: `src/ontime_cli/api.py`
- Test: `tests/test_api.py`
- Modify: `src/ontime_cli/main.py` (run()에 ApiError 처리 추가)

**Interfaces:**
- Consumes: `auth.load_config`, `auth.load_tokens`, `auth.is_expired`, `auth.refresh_tokens`, `auth.AuthError`
- Produces (`ontime_cli.api`):
  - `ApiError(Exception)` — str()이 사람이 읽을 메시지
  - `format_problem(resp: httpx.Response) -> str` — RFC 9457 응답을 `"{code}: {detail}"`로, JSON 아니면 `"HTTP {status}: {본문 앞 200자}"`
  - `ApiClient()` — 생성 시 config/토큰 로드(미로그인 시 `AuthError`), 만료 시 선제 갱신
  - `ApiClient.request(method: str, path: str, **kwargs) -> dict` — Bearer 헤더로 호출, 401이면 refresh 후 1회 재시도, 4xx/5xx면 `ApiError`, 성공 시 JSON dict

- [ ] **Step 1: 실패하는 테스트 작성 — tests/test_api.py**

```python
from __future__ import annotations

import httpx
import pytest

from ontime_cli.api import format_problem


def _resp(status: int, body: str, content_type: str) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=body.encode(),
        headers={"Content-Type": content_type},
        request=httpx.Request("GET", "http://test/api"),
    )


def test_format_problem_rfc9457():
    body = (
        '{"type":"about:blank","title":"Bad Request","status":400,'
        '"detail":"Invalid request content.","instance":"/api/v1/developers/commits",'
        '"code":"BAD_REQUEST","timestamp":"2026-08-14T10:00:00","exception":"X"}'
    )
    resp = _resp(400, body, "application/problem+json")
    assert format_problem(resp) == "BAD_REQUEST: Invalid request content."


def test_format_problem_non_json():
    resp = _resp(502, "<html>bad gateway</html>", "text/html")
    assert format_problem(resp) == "HTTP 502: <html>bad gateway</html>"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ontime_cli.api'`

- [ ] **Step 3: src/ontime_cli/api.py 작성**

```python
from __future__ import annotations

import httpx

from . import auth

DEFAULT_BASE_URL = "http://localhost:8080/api"


class ApiError(Exception):
    pass


def format_problem(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return f"{body['code']}: {body['detail']}"
    except (ValueError, KeyError):
        return f"HTTP {resp.status_code}: {resp.text[:200]}"


class ApiClient:
    def __init__(self) -> None:
        self.config = auth.load_config()
        tokens = auth.load_tokens()
        if tokens is None:
            raise auth.AuthError("로그인이 필요합니다: `ontime login` 을 먼저 실행하세요.")
        if auth.is_expired(tokens):
            tokens = auth.refresh_tokens(self.config, tokens)
        self.tokens = tokens
        self.base_url = self.config.get("api_base_url", DEFAULT_BASE_URL)

    def request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._send(method, path, **kwargs)
        if resp.status_code == 401:
            self.tokens = auth.refresh_tokens(self.config, self.tokens)
            resp = self._send(method, path, **kwargs)
        if resp.status_code >= 400:
            raise ApiError(format_problem(resp))
        return resp.json()

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        return httpx.request(
            method,
            self.base_url + path,
            headers={"Authorization": f"Bearer {self.tokens['access_token']}"},
            **kwargs,
        )
```

- [ ] **Step 4: main.py의 run()에 ApiError 처리 추가**

`run()` 함수를 아래로 교체 (import에 `from .api import ApiError` 추가):

```python
from .api import ApiError


def run() -> None:
    try:
        app()
    except (auth.AuthError, ApiError) as e:
        typer.echo(str(e), err=True)
        raise SystemExit(1)
    except httpx.HTTPError as e:
        typer.echo(f"네트워크 오류: {e}", err=True)
        raise SystemExit(1)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest -v`
Expected: 9 passed (test_auth 7 + test_api 2)

- [ ] **Step 6: Commit**

```bash
git add src/ontime_cli/api.py tests/test_api.py src/ontime_cli/main.py
git commit -m "feat: authenticated API client with 401 refresh-retry"
```

---

### Task 5: commits 커맨드 (register / list) — TDD

**Files:**
- Create: `src/ontime_cli/commits.py`
- Test: `tests/test_commits.py`
- Modify: `src/ontime_cli/main.py` (commits 서브앱 등록)

**Interfaces:**
- Consumes: `api.ApiClient` (Task 4)
- Produces (`ontime_cli.commits`):
  - `commits_app: typer.Typer`
  - `format_table(items: list) -> str` — 커밋 목록 dict 리스트를 정렬된 텍스트 테이블로

- [ ] **Step 1: 실패하는 테스트 작성 — tests/test_commits.py**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_commits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ontime_cli.commits'`

- [ ] **Step 3: src/ontime_cli/commits.py 작성**

```python
from __future__ import annotations

import json
from typing import Optional

import typer

from .api import ApiClient

commits_app = typer.Typer(help="커밋 API", no_args_is_help=True)

_COLUMNS = [
    ("id", "id"),
    ("commit", "commitId"),
    ("repo", "repo"),
    ("branch", "branch"),
    ("author", "author"),
    ("message", "commitMessage"),
    ("createdDate", "createdDate"),
]


def format_table(items: list) -> str:
    if not items:
        return "(결과 없음)"
    rows = []
    for item in items:
        row = []
        for _, key in _COLUMNS:
            value = str(item.get(key, ""))
            if key == "commitId":
                value = value[:8]
            row.append(value)
        rows.append(row)
    headers = [h for h, _ in _COLUMNS]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  ".join("-" * w for w in widths),
    ]
    for r in rows:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(len(r))))
    return "\n".join(lines)


@commits_app.command("register")
def register(
    commit_id: str = typer.Option(..., "--commit-id", help="커밋 해시"),
    repo: str = typer.Option(..., "--repo", help="저장소 이름"),
    branch: str = typer.Option(..., "--branch", help="브랜치 이름"),
    author: str = typer.Option(..., "--author", help="커밋 작성자"),
    message: str = typer.Option(..., "--message", help="커밋 메시지"),
) -> None:
    """신규 커밋을 등록한다."""
    data = ApiClient().request(
        "POST",
        "/v1/developers/commits",
        json={
            "commitId": commit_id,
            "repo": repo,
            "branch": branch,
            "author": author,
            "commitMessage": message,
        },
    )
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@commits_app.command("list")
def list_(
    repo: Optional[str] = typer.Option(None, "--repo", help="저장소 이름"),
    branch: Optional[str] = typer.Option(None, "--branch", help="브랜치 이름"),
    author: Optional[str] = typer.Option(None, "--author", help="커밋 작성자"),
    message: Optional[str] = typer.Option(None, "--message", help="커밋 메시지 (부분 일치)"),
    created_from: Optional[str] = typer.Option(None, "--from", help="등록일 시작 (ISO datetime)"),
    created_to: Optional[str] = typer.Option(None, "--to", help="등록일 종료 (ISO datetime)"),
    created_by: Optional[str] = typer.Option(None, "--created-by", help="등록자"),
    page: int = typer.Option(0, "--page", help="페이지 번호 (zero-based)"),
    size: int = typer.Option(25, "--size", help="페이지당 항목 수"),
    sort: str = typer.Option("createdDate,desc", "--sort", help="정렬 ({field},{asc|desc})"),
    as_json: bool = typer.Option(False, "--json", help="raw JSON 출력"),
) -> None:
    """커밋 목록을 조회한다."""
    params = {
        "repo": repo,
        "branch": branch,
        "author": author,
        "commitMessage": message,
        "createdDateFrom": created_from,
        "createdDateTo": created_to,
        "createdBy": created_by,
        "page": page,
        "size": size,
        "sort": sort,
    }
    params = {k: v for k, v in params.items() if v is not None}
    data = ApiClient().request("GET", "/v1/developers/commits", params=params)
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    typer.echo(format_table(data.get("content", [])))
    page_info = data.get("page", {})
    typer.echo(
        f"page {page_info.get('number', 0) + 1}/{page_info.get('totalPages', 1)}"
        f" (total {page_info.get('totalElements', 0)})"
    )
```

- [ ] **Step 4: main.py에 서브앱 등록**

`app = typer.Typer(...)` 바로 아래에 추가 (import 포함):

```python
from .commits import commits_app

app.add_typer(commits_app, name="commits")
```

- [ ] **Step 5: 전체 테스트 + 커맨드 확인**

Run: `uv run pytest -v && uv run ontime commits --help && uv run ontime commits list --help`
Expected: 11 passed. `commits --help`에 register/list 표시, `list --help`에 모든 옵션 표시

- [ ] **Step 6: Commit**

```bash
git add src/ontime_cli/commits.py tests/test_commits.py src/ontime_cli/main.py
git commit -m "feat: commits register/list commands with table output"
```

---

### Task 6: E2E 수동 검증 (사용자 수행)

**Files:** 없음 (코드 변경 없음)

자동화 불가 항목 — 브라우저와 실제 서버가 필요하므로 사용자가 직접 수행한다:

- [ ] **Step 1: config 작성** — `~/.config/keyflow-auth/config.json`에 실제 client_id/client_secret/scope 작성
- [ ] **Step 2: 로그인** — `uv run ontime login` → 브라우저 로그인 → "로그인 완료" 확인, `ls -l ~/.config/keyflow-auth/tokens.json` 권한 `-rw-------` 확인
- [ ] **Step 3: whoami** — `uv run ontime whoami` → 사용자 정보 JSON 출력 확인
- [ ] **Step 4: API 호출** — 로컬 API 서버(localhost:8080) 기동 후:
  - `uv run ontime commits register --commit-id abc123 --repo test-repo --branch main --author bob --message "test"` → 등록된 커밋 JSON 확인
  - `uv run ontime commits list` → 테이블 출력 확인
  - `uv run ontime commits list --repo test-repo --json` → JSON 출력 확인
- [ ] **Step 5: 토큰 갱신 확인** — `tokens.json`의 `expires_at`을 과거 값으로 수정 후 `ontime whoami` → 자동 갱신되어 정상 동작 확인
- [ ] **Step 6: 로그아웃** — `uv run ontime logout` → tokens.json 삭제 확인, `ontime whoami` → "로그인이 필요합니다" 확인
