# OnTime Developer CLI 설계

날짜: 2026-08-14

## 개요

KeyFlow Auth(OAuth 2.0) 로그인과 OnTime Developer REST API(커밋 등록/조회)를 제공하는 파이썬 CLI. 스택은 typer + httpx, OAuth flow는 stdlib로 직접 구현한다.

## 프로젝트 구조

```
ontime-developer-cli/
├── pyproject.toml          # typer, httpx 의존성 + [project.scripts] ontime = "ontime_cli.main:app"
├── src/ontime_cli/
│   ├── __init__.py
│   ├── main.py             # typer 앱 루트: login, logout, whoami + commits 서브앱 등록
│   ├── auth.py             # OAuth flow, 토큰 저장/로드/갱신
│   ├── api.py              # 인증된 httpx 클라이언트 (401 시 refresh 후 1회 재시도)
│   └── commits.py          # commits register / commits list 커맨드
└── tests/
    └── test_auth.py
```

기존 루트 `main.py`(PyCharm 샘플)는 삭제한다.

## 커맨드

```
ontime login                 # 브라우저 열어 OAuth 로그인, 토큰 저장
ontime logout                # 토큰 파일 삭제 + 서버 revoke 시도
ontime whoami                # userinfo 엔드포인트로 현재 로그인 사용자 표시
ontime commits register --commit-id .. --repo .. --branch .. --author .. --message ..
ontime commits list [--repo ..] [--branch ..] [--author ..] [--message ..]
                    [--from ..] [--to ..] [--created-by ..]
                    [--page 0] [--size 25] [--sort createdDate,desc] [--json]
```

- `commits list`는 기본 테이블 출력(id, commitId 앞 8자, repo, branch, author, commitMessage, createdDate), `--json` 시 raw JSON 출력. 하단에 `page N/M (total X)` 표시.
- `commits register` 성공 시 등록된 커밋 정보 출력.
- API base URL 기본값 `http://localhost:8080/api`, config의 `api_base_url`로 변경 가능.

## 인증

### KeyFlow Auth 정보 (OIDC discovery에서 확인됨)

- authorization: `https://auth.keyflow-dev.com/oauth2/authorize`
- token/refresh: `https://auth.keyflow-dev.com/oauth2/token`
- revoke: `https://auth.keyflow-dev.com/oauth2/revoke`
- userinfo: `https://auth.keyflow-dev.com/userinfo`
- grant: authorization_code(PKCE S256) + refresh_token. device flow 없음.
- 클라이언트: confidential (client_secret 필요, `client_secret_basic` 사용)
- redirect URI: `http://localhost:8765/callback` (KeyFlow 서버에 등록됨)

### 로그인 flow

1. PKCE code_verifier/challenge(S256)와 state 생성
2. stdlib `http.server`로 `localhost:8765`에 임시 콜백 서버 기동
3. `webbrowser.open`으로 authorize URL 열기 (URL을 터미널에도 출력)
4. 콜백에서 `code` 수신, `state` 검증. 브라우저에는 "로그인 완료" HTML 응답
5. token 엔드포인트에 code + code_verifier 교환 (client_secret_basic 인증)
6. 토큰 저장 후 완료 메시지 출력
7. 120초 내 콜백이 없으면 타임아웃 에러

### 로그인 유지

- API 호출 시 저장된 access_token을 Bearer로 사용
- `expires_at`이 지났으면 호출 전에 refresh_token grant로 선제 갱신
- 그래도 401이면 refresh 후 1회 재시도
- refresh 실패(refresh_token 만료 등) 시 "다시 `ontime login` 하세요" 안내 후 exit 1

## 파일 (`~/.config/keyflow-auth/`)

### config.json — 사용자가 직접 작성

```json
{
  "client_id": "...",
  "client_secret": "...",
  "scope": "openid profile users:read:summary",
  "api_base_url": "http://localhost:8080/api"
}
```

- `client_id`, `client_secret`, `scope`는 필수, `api_base_url`은 선택
- 파일이 없으면 위 예시와 경로를 출력하고 exit 1
- client secret은 git에 커밋하지 않는다 (코드/문서에 실제 값 미포함)

### tokens.json — CLI가 관리

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1765000000
}
```

- `expires_at`은 unix epoch (발급 시각 + expires_in − 30초 여유)
- 파일 권한 `0600`으로 저장

## 에러 처리

- API 에러(RFC 9457 ProblemDetail): `{code}: {detail}` 형태로 stderr 출력, exit 1
- config 없음 / 미로그인(tokens.json 없음) / 콜백 타임아웃: 각각 명확한 안내 메시지, exit 1
- 네트워크 오류: httpx 예외를 짧은 메시지로 변환

## 테스트

- `tests/test_auth.py` (pytest): PKCE 생성(길이·문자셋·challenge 계산), 토큰 만료 판정, 토큰 파일 저장/로드 라운드트립
- OAuth 브라우저 flow와 실제 API 호출은 로컬 서버 대상 수동 검증

## 범위 제외 (YAGNI)

- OpenAPI 스펙 기반 커맨드 자동 생성
- 토큰 keychain 저장 (파일 0600으로 충분)
- 멀티 프로필/계정
