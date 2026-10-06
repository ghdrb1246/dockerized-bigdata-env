# 협업 규칙 (Conventions)

여러 대의 PC에서, Claude Code와 손코딩이 섞여서 작업합니다.
**서로 꼬이지 않게 하는 것이 이 문서의 목적**입니다. 작업 시작 전에 한 번 읽고 시작해 주세요.

> 📌 **Git이 익숙하지 않다면 [GIT-GUIDE.md](GIT-GUIDE.md) 를 먼저 보세요.**
> 이 문서는 "무엇을 지킬지"(규칙), GIT-GUIDE는 "어떻게 하는지"(명령어)를 다룹니다.

---

## 1. 작업 시작 전 3줄 체크리스트

1. `develop`에서 `git pull` 먼저.
2. 이슈·PR·팀 채널에서 다른 사람이 같은 파일을 작업 중인지 확인.
3. 브랜치 새로 파고 시작. `develop`과 `main`에 직접 커밋하지 않습니다.

> 명령어가 기억 안 나면 [GIT-GUIDE.md](GIT-GUIDE.md) 3장(매일 하는 작업 흐름)을 그대로 복사해서 쓰세요.

## 2. 브랜치 전략

- `main` — 배포 기준 브랜치. 직접 push 금지.
- `develop` — 작업 통합 브랜치. 작업 브랜치는 여기에서 만들고 PR도 여기로 병합.
- 작업 브랜치: `<타입>/<범위>-<내용>`

```
feat/fe-station-list
feat/fe-kakao-map
fix/fe-marker-duplicate
docs/docs-guide-update
```

타입: `feat` / `fix` / `refactor` / `docs` / `chore`
범위: `fe`(프론트) / `be`(백엔드) / `db` / `deploy` / `docs`

> 프론트 2명(우진, 황지성)이 동시에 작업하므로, **한 브랜치에 두 사람이 같이 커밋하지 않습니다.**
> 기능 단위로 브랜치를 나누고 PR로 합칩니다.

## 3. 커밋 메시지

```
<타입>: <한 줄 요약>

(필요하면) 왜 이렇게 했는지
```

예시:

```
feat: 역 목록 컴포넌트 추가
fix: 역 변경 시 이전 마커가 남는 문제 수정
docs: MVP 범위에서 다크모드 제외 명시
```

- 한글로 써도 됩니다. 팀 내 소통이 우선입니다.
- 커밋은 **작게, 자주**. "하루치 몰아서 1커밋" 금지.

## 4. PR 규칙

- PR 제목 = 커밋 제목과 동일한 형식
- PR 본문에 아래 3가지는 꼭 적기:
  1. **무엇을** 했는지
  2. **어떻게 확인**했는지 (브라우저에서 확인한 화면 / 스크린샷)
  3. 관련 현재 문서나 이슈 링크
- 리뷰어 1명 이상 승인 후 병합. (급하면 Discord에서 확인받고 사유를 PR에 남기기)
- 병합은 **Squash and merge** 권장 — 히스토리가 깔끔해집니다.

## 5. 파일 담당 구역 (충돌 방지)

> **현재 상태: 담당자 고정 없음.** MVP는 Claude Code로 개발하므로 사람별 구역을 나누지 않습니다.
>
> **브랜치를 나눠 쓰면 같은 시간에 동시 작업해도 됩니다.** 서로의 작업이 덮어써지지 않습니다.
> 다만 **같은 파일을 동시에 고치면 나중에 합칠 때 충돌**이 나므로, 아래 표의 공용 파일만 주의하세요.
> (충돌은 사고가 아니라 정상입니다. 해결법은 [GIT-GUIDE.md](GIT-GUIDE.md) 5장)
>
> 작업 시작 전 이슈·PR·팀 채널에서 **어떤 파일을 만질지** 공유하면 충돌을 미리 피할 수 있습니다.

> 2026-08-10 이후 프론트는 Next.js App Router 구조입니다.

| 영역 | 파일/폴더 | 주의사항 |
|---|---|---|
| 화면·라우트 | `frontend/app/*` | Next.js 페이지와 페이지 전용 컴포넌트 |
| 공용 UI | `frontend/src/components/*` | 여러 화면에서 재사용하는 컴포넌트 |
| API·세션 | `frontend/src/lib/*` | API 클라이언트, FastAPI 호환 변환, 인증 세션 |
| API 타입 | `frontend/src/contracts/*` | **단독 수정 금지**, UI와 어댑터가 함께 참조 |
| 전역 스타일 | `frontend/app/styles.css`, `frontend/src/styles/tokens.css` | 디자인 토큰 변경 시 모든 화면 확인 |

> `frontend/src/contracts/*`와 `frontend/src/styles/tokens.css`는 여러 화면이 참조합니다. 바꾸기 전에 반드시 알리세요.

### 프론트엔드 구조 원칙

- `frontend/app/`은 App Router 페이지와 페이지 전용 클라이언트 컴포넌트를 둡니다.
- `frontend/src/components/`에는 실제로 여러 화면에서 재사용하는 UI만 둡니다.
- 공용 API 호출과 계약 변환은 `frontend/src/lib/api.ts`, `legacyApiAdapter.ts`를 우선 사용합니다.
- 서버 컴포넌트의 직접 호출은 `legacyMappers.ts` 변환을 재사용하고, 관리자·시간표처럼 독립된 계약은 해당 `src/lib` 모듈에서 관리합니다.
- 고정 폭·색상·간격은 `frontend/src/styles/tokens.css`의 토큰으로 관리합니다.
- 새 백엔드 계약이 Codex UI 계약과 일치하면 호환 변환을 제거하고 직접 연결합니다.
## 6. 문서화 규칙

- 프로젝트 공통 문서는 `docs/`에 두고, 실행·구조 안내는 해당 디렉터리의 `README.md`에 둡니다.
- **기능을 바꾸면 문서도 같은 PR에서 바꿉니다.** (코드만 바뀌고 문서가 남는 게 제일 위험)
- 범위가 바뀌면 현재 기준 문서인 루트 `README.md`와 관련 파트 문서를 함께 수정합니다.

### 문서 목록

| 문서 | 용도 |
|---|---|
| [GIT-GUIDE.md](GIT-GUIDE.md) | Git/GitHub 사용법 (명령어, 충돌 해결, 사고 복구) |
| [CLAUDE-CODE-WORKFLOW.md](CLAUDE-CODE-WORKFLOW.md) | Claude Code 작업 흐름, 프롬프트 모음 |
| [`CLAUDE.md`](../CLAUDE.md) | Claude Code가 자동으로 읽는 팀 공통 규칙 |
| [`README.md`](../README.md) | 현재 기능·실행·배포 개요 |
| [FRONTEND-API-INTEGRATION.md](FRONTEND-API-INTEGRATION.md) | 현재 프론트엔드 API 연동 상태 |
| [CONVENTIONS.md](CONVENTIONS.md) | 이 문서 (협업 규칙) |
| [SPEC.md](SPEC.md), [REQUIREMENTS.md](REQUIREMENTS.md) | 초기 MVP 범위·단계 계획 역사 자료 |
| [HANDOFF.md](HANDOFF.md), [BACKEND-HANDOFF.md](BACKEND-HANDOFF.md) | 완료 전 인수인계 역사 자료 |
| [PRESENTATION.md](PRESENTATION.md), [WORKLOG.md](WORKLOG.md) | 발표 구성·날짜별 작업 역사 자료 |

## 7. Claude Code를 쓸 때

> 상세한 작업 흐름과 프롬프트 예시는 [CLAUDE-CODE-WORKFLOW.md](CLAUDE-CODE-WORKFLOW.md) 참고.
> 저장소 루트의 [`CLAUDE.md`](../CLAUDE.md)는 **Claude Code가 자동으로 읽는 팀 공통 규칙**입니다.

여러 PC에서 각자 Claude Code를 돌리면 **같은 파일을 서로 다르게 고쳐놓는 일**이 생깁니다.

- 작업 전 `git pull`, 작업 후 바로 push. 로컬에 오래 들고 있지 않기.
- Claude에게 시킬 때 변경할 기능과 파일 범위를 구체적으로 명시하기.
- 현재 문서에 없는 기능을 제안하면 작업 범위에 포함할지 먼저 확인하기.
- 생성된 코드는 **브라우저에서 직접 동작 확인 후** 커밋. 확인 없이 커밋 금지.
- 라이브러리를 새로 설치했으면 PR 본문에 **왜 필요한지** 적기.

## 8. 환경변수

- `frontend/.env.local`은 **절대 커밋하지 않습니다.** (`.gitignore`에 포함되어 있음)
- 새 프런트엔드 환경변수를 추가하면 `frontend/.env.example`에 **키 이름만** 추가하고 Discord에 공유.
- 카카오 키가 커밋된 걸 발견하면 즉시 Discord에 알리고 **키를 재발급**합니다.
