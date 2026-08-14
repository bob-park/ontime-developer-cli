# git hooks (pre-push 커밋 자동 등록) 설계

2026-08-14

## 목적

push 할 때 원격에 새로 올라가는 커밋들을 자동으로 `POST /v1/developers/commits` 에 등록한다.
어떤 git 저장소에서든 `ontime hooks install` 한 번으로 사용할 수 있어야 한다.

## 배경 결정 사항

- git 에는 post-push 훅이 없으므로 **pre-push** 훅을 사용한다. pre-push 는 stdin 으로
  push 되는 ref 와 커밋 범위를 정확히 받을 수 있다.
- husky 는 Node/npm 프로젝트에서만 동작하므로 사용하지 않는다. 순수 git 훅을 CLI 가 설치한다.
  (husky 를 이미 쓰는 repo 는 `.husky/pre-push` 에 `ontime hooks pre-push "$@"` 한 줄로 연동 가능)
- 등록 실패(서버 다운, 미로그인 등)는 경고만 출력하고 **push 는 항상 진행**한다.
- `--repo` 값은 push 대상 remote URL 의 마지막 경로에서 추출한다
  (`git@github.com:bob-park/ontime-api.git` → `ontime-api`).
- `--author` 값은 각 커밋의 git author 이름(`%an`)을 사용한다.

## 구조

새 모듈 `src/ontime_cli/hooks.py` 에 typer 서브앱 `hooks_app` 을 만들고 `main.py` 에
`app.add_typer(hooks_app, name="hooks")` 로 등록한다. 로직은 전부 Python 에 두고,
설치되는 훅 스크립트는 CLI 를 호출하는 껍데기로 유지한다.

### 명령

| 명령 | 동작 |
|------|------|
| `ontime hooks install` | 현재 repo 의 `.git/hooks/pre-push` 에 훅 스크립트 설치 (실행 권한 포함) |
| `ontime hooks uninstall` | 우리가 설치한 훅이면 삭제 |
| `ontime hooks pre-push <remote> <url>` | (hidden) 훅이 내부적으로 호출. stdin 파싱 → 커밋 등록 |

install 규칙:

- git repo 가 아니면 에러 (exit 1).
- 기존 `pre-push` 훅이 있을 때: 마커 주석(`# ontime-developer-cli pre-push hook`)이 있으면
  우리 훅이므로 덮어쓰기(업데이트), 다른 훅이면 중단하고 안내. `--force` 로 덮어쓰기 가능.

### 훅 스크립트

```sh
#!/bin/sh
# ontime-developer-cli pre-push hook
ontime hooks pre-push "$@" || echo "[ontime] 커밋 등록 실패 (push는 계속 진행)" >&2
exit 0
```

`exit 0` 고정이므로 `ontime` 이 PATH 에 없거나 실패해도 push 를 막지 않는다.

## pre-push 처리 로직

git pre-push 훅 규약: 인자로 remote 이름·URL, stdin 으로
`<local_ref> <local_sha> <remote_ref> <remote_sha>` 줄들이 들어온다.

각 줄에 대해:

1. **삭제 push** (local_sha 가 모두 0) → 건너뜀.
2. **branch**: `local_ref` 에서 `refs/heads/` 접두어 제거.
3. **커밋 범위**:
   - 신규 브랜치 (remote_sha 가 모두 0): `git rev-list <local_sha> --not --remotes=<remote>`
   - 그 외: `git rev-list <remote_sha>..<local_sha>`
4. 각 커밋에 대해 `git log -1 --format` 으로 author 이름(`%an`)과 메시지 제목 줄(`%s`)을 얻어
   기존 `ApiClient` 로 `POST /v1/developers/commits` 호출 (register 와 동일 페이로드, 커밋당 1건).

출력: `[ontime] N개 커밋 등록 완료` (실패 건수 있으면 함께 표시). 개별 커밋 등록 실패
(중복 등록 등)는 경고만 하고 나머지는 계속 진행. 전체 실패(미로그인, 서버 다운)도 경고 후
정상 종료 — 어떤 경우에도 push 를 막지 않는다.

## 테스트

`tests/test_hooks.py` (기존 테스트 패턴대로 API 는 mock):

- remote URL → repo 이름 추출 (ssh/https, `.git` 유무)
- stdin 파싱: 일반 push, 삭제 push 건너뜀, 신규 브랜치
- install/uninstall: 임시 git repo 에서 설치·실행권한·마커 감지·`--force`·미설치 uninstall
- API 실패 시에도 exit 0

## 문서

README 에 `ontime hooks install` 사용법과 husky repo 연동 한 줄 안내 추가.
