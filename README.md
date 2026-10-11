# OnTime Developer CLI

KeyFlow Auth(OAuth 2.0) 로그인과 OnTime Developer REST API(커밋 등록/조회, 휴가 신청)를 제공하는 커맨드라인 도구.

## Spec

- **인증**: KeyFlow Auth OAuth 2.0 — Authorization Code + PKCE(S256) flow
  - 로그인 시 브라우저가 열리고, `http://localhost:8765/callback` 으로 인증 코드를 수신
  - 콜백 수신 후 성공/실패 결과 페이지 표시 (Kraken 스타일 라이트 카드 디자인)
  - access token 만료 시 refresh token 으로 자동 갱신 (갱신 실패 시에만 재로그인 필요)
  - 토큰 저장: `~/.config/keyflow-auth/tokens.json` (권한 `0600`)
- **API**: OnTime Developer REST API (`/v1/developers/commits`)
  - 기본 서버: `http://localhost:8080/api` (설정으로 변경 가능)
  - 커밋 등록 시 `userUniqueId` 는 로그인 사용자(userinfo 의 `sub`)로 자동 설정
  - 에러 응답(RFC 9457 ProblemDetail)은 `CODE: 상세 메시지` 형태로 출력, exit code 1
- **휴가 API**: OnTime Document API (`/v1/documents/vacations`)
  - 기본 서버: `http://localhost:8082/api` (`document_api_base_url` 설정으로 변경 가능)
- **런타임**: Python ≥ 3.9, 의존성은 [typer](https://typer.tiangolo.com/) / [httpx](https://www.python-httpx.org/) 2개

상세 설계는 [docs/superpowers/specs/2026-08-14-ontime-cli-design.md](docs/superpowers/specs/2026-08-14-ontime-cli-design.md) 참고.

## 설치

[uv](https://docs.astral.sh/uv/) 또는 pipx 로 설치한다.

```bash
# git 저장소에서 바로 설치
uv tool install git+https://github.com/bob-park/ontime-developer-cli.git

# 또는 로컬 체크아웃에서
git clone https://github.com/bob-park/ontime-developer-cli.git
cd ontime-developer-cli
uv tool install .
```

개발 중이라면 설치 없이 저장소 안에서 `uv run ontime ...` 으로 실행해도 된다.

## 초기 설정 (최초 1회)

`~/.config/keyflow-auth/config.json` 파일을 작성한다:

```json
{
  "client_id": "<KeyFlow client id>",
  "client_secret": "<KeyFlow client secret>",
  "scope": ["openid", "profile", "users:read:summary"],
  "api_base_url": "https://auth.keyflow-dev.com/api"
}
```

- `client_id` / `client_secret` / `scope` 는 필수
- `api_base_url` 은 선택 (기본값 `http://localhost:8080/api`)
- `document_api_base_url` 은 선택 (기본값 `http://localhost:8082/api`, 휴가 API 서버)
- 파일이 없으면 CLI 가 예시 내용과 경로를 안내한다

## 사용법

### 로그인 / 로그아웃

```bash
ontime login     # 브라우저가 열림 → KeyFlow 로그인 → 토큰 저장
ontime whoami    # 현재 로그인한 사용자 정보(JSON) 출력
ontime logout    # 토큰 삭제 (서버 revoke 포함)
```

로그인은 한 번만 하면 된다. 이후 API 호출 시 토큰이 만료돼 있으면 자동 갱신된다.

로그인이 끝나면 브라우저에 결과 페이지가 표시된다. 디자인은 [docs/design/kraken-design.md](docs/design/kraken-design.md) 를 따른
라이트 카드(연회색 배경 `#f6f6f9` + 흰 카드, Kraken Purple `#7132f5`, 12px radius)이며, 외부 리소스 없이 자기완결 HTML 이다.

- **로그인 완료**: 연보라 원 안의 보라색 ✓ 아이콘 + "이제 이 탭은 닫고 터미널로 돌아가면 돼요" 안내
- **로그인 실패**: 연빨강 원 안의 ✕ 아이콘, 오류 코드를 빨간색(`#c2283b`)으로 강조 + "이 탭을 닫고 터미널에서 다시 로그인해 주세요" 안내
- 안내 문구는 연보라 박스로 강조한다.
  브라우저는 스크립트로 열지 않은 탭의 `window.close()` 를 막기 때문에 "창 닫기" 버튼은 두지 않는다.

### 커밋 등록

```bash
ontime commits register \
  --commit-id a1b2c3d \
  --repo bob-park/ontime-api \
  --branch main \
  --author bob \
  --message "fix: resolve login bug"
```

성공하면 등록된 커밋 정보가 JSON 으로 출력된다.
`userUniqueId` 는 로그인한 사용자의 `sub` 값으로 자동 설정된다.

### 커밋 목록 조회

```bash
# 전체 조회 (기본: page 0, size 25, commitDate 내림차순)
ontime commits list

# 필터링
ontime commits list --repo bob-park/ontime-api --branch main --author bob
ontime commits list --message "fix"                        # 커밋 메시지 부분 일치
ontime commits list --user-unique-id 42                    # 사용자 고유 아이디
ontime commits list --from 2026-08-01T00:00:00 --to 2026-08-14T23:59:59   # 커밋 일시 기준

# 페이징 / 정렬
ontime commits list --page 1 --size 50 --sort author,asc

# raw JSON 출력
ontime commits list --json
```

기본 출력은 테이블 형태이고, 하단에 `page 1/3 (total 62)` 형식으로 페이징 정보가 표시된다.

```
id                   commit    repo                 branch  author  message                  createdDate
-------------------  --------  -------------------  ------  ------  -----------------------  -------------------
1954732911911405568  a1b2c3d4  bob-park/ontime-api  main    bob     fix: resolve login bug   2026-08-14T10:00:00
page 1/1 (total 1)
```

### 휴가 신청

```bash
# 하루 연차
ontime vacations request --start 2025-05-07 --reason "개인사유"

# 기간 연차
ontime vacations request --start 2025-05-07 --end 2025-05-09 --reason "개인사유"

# 오전 반차 / 보상 휴가
ontime vacations request --start 2025-05-07 --sub-type AM_HALF_DAY_OFF --reason "개인사유"
ontime vacations request --start 2025-05-07 --type COMPENSATORY --reason "개인사유"
```

- `--type`: `GENERAL`(연차, 기본값) | `COMPENSATORY`(보상 휴가) | `OFFICIAL`(공가)
- `--sub-type`: `AM_HALF_DAY_OFF`(오전 반차) | `PM_HALF_DAY_OFF`(오후 반차), 생략 시 하루 단위
- `--end` 생략 시 시작일과 동일 (하루)
- 신청자(`userUniqueId`)는 로그인한 사용자의 `sub`, 상태는 `WAITING` 으로 등록된다

### 출근 / 퇴근

```bash
ontime attendance in                      # 출근 (기본 OFFICE)
ontime attendance in --work-type HOME     # 재택 출근
ontime attendance out                     # 퇴근 (오늘 출근 기록 기준)

ontime attendance list                                    # 오늘 기록 조회
ontime attendance list --start 2026-10-01 --end 2026-10-11
```

- API 서버는 `api_base_url` 을 따른다 (`/v2/attendance/records`)
- `--work-type`: `OFFICE`(사무실, 기본값) | `OUTSIDE`(외근) | `HOME`(재택)
- 위도/경도는 기록용으로 사무실 좌표로 고정되어 전송된다
- 퇴근은 오늘(`workingDate`) 기록의 `id` 로 처리하며, 오늘 기록이 없으면 exit code 1

### git 훅 (push 시 커밋 자동 등록) — **Deprecated**

> ⚠️ **이 기능은 deprecated 되었으며 향후 제거될 예정이다.** 실행 시 경고가 출력되고
> 아직 동작은 하지만, 신규 사용은 권장하지 않는다.

git repo 에서 한 번만 실행하면, 이후 `git push` 할 때 원격에 새로 올라가는
커밋들이 자동으로 등록된다.

```bash
cd <아무-git-저장소>
ontime hooks install     # .git/hooks/pre-push 설치
ontime hooks uninstall   # 제거
```

- repo 이름은 push 대상 remote URL 에서 `org/repo` 형태로 (예: `bob-park/ontime-api`), author 는 각 커밋의 git author 에서 자동 추출된다.
- 등록에 실패해도 (서버 다운, 미로그인 등) 경고만 출력하고 push 는 정상 진행된다.
- 다른 pre-push 훅이 있으면 설치를 중단한다 (`--force` 로 덮어쓰기). ontime 훅 재설치는 항상 허용된다.
- husky 를 쓰는 repo 라면 `.husky/pre-push` 에 `ontime hooks pre-push "$@"` 한 줄을 추가하면 된다.

### 도움말

```bash
ontime --help
ontime commits list --help
```

## 개발

```bash
uv sync            # 의존성 설치
uv run pytest -v   # 테스트 실행
uv run ontime --help
```
