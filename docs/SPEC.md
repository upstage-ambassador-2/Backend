# Deep Interview Spec: Mello — Backend Integration & Gmail Connectivity

## Metadata
- Interview ID: di-mello-backend-2026-05-23
- Rounds: 6
- Final Ambiguity Score: 10.0%
- Type: brownfield (Next.js UI shell exists, no backend, no real data)
- Generated: 2026-05-23
- Threshold: 0.20
- Status: PASSED (below threshold)
- Working Directory: `/Users/mason/workspace/upstage-ambassador/final_project`

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.92 | 0.35 | 0.322 |
| Constraint Clarity | 0.92 | 0.25 | 0.230 |
| Success Criteria | 0.85 | 0.25 | 0.213 |
| Context Clarity (brownfield) | 0.90 | 0.15 | 0.135 |
| **Total Clarity** | | | **0.900** |
| **Ambiguity** | | | **0.100 (10.0%)** |

## Goal
"Mello"의 UI 껍데기에 백엔드를 결합하여, **Google OAuth로 로그인한 사용자가 Upstage Solar LLM으로 메일 초안을 스트리밍 생성하고, Gmail로 직접 발송하거나 받은편지함의 메일에 답장 초안을 생성할 수 있는 풀스택 AI 메일 어시스턴트**를 약 2주 안에 Railway에 배포한다.

핵심 가치 한 줄: **"내 페르소나 + Solar LLM + 내 Gmail = 한 화면에서 끝나는 AI 메일 작성/발송"**

## Constraints
### 시간/일정
- 데모/제출 마감: **2주 내외** (구현 + Railway 배포 + 풀 데모 경로 확보)
- 배포 담당: **강민석** (Railway)

### 기술 스택 (확정)
- **Frontend**: Next.js 14.2.18 + React 18.3.1 (현 상태 유지, 클라이언트 라우팅 + 순수 CSS)
- **Backend**: FastAPI (Python)
- **DB**: Postgres
- **LLM**: Upstage Solar (Chat Completions 호환 엔드포인트, 단일 provider)
- **메일 발송**: Gmail API (사용자의 OAuth 토큰으로 본인 명의 발송) — 별도 SMTP/SES/Resend 의존성 없음
- **인증**: Google OAuth 2.0 단일 (매직링크/이메일+PW는 철회됨)
- **세션**: HttpOnly 쿠키 기반 서버 세션 (FastAPI 측에서 발행)

### 외부 API 스코프 (Google OAuth)
다음 6개 스코프 고정:
- `openid`, `email`, `profile` — 사용자 식별
- `https://www.googleapis.com/auth/gmail.readonly` — 받은편지함 조회 (답장 컨텍스트)
- `https://www.googleapis.com/auth/gmail.send` — 메일 발송
- `https://www.googleapis.com/auth/contacts.readonly` — Contacts → 페르소나 임포트

> 주의: gmail.readonly/send + contacts.readonly는 Google의 sensitive scope. 데모 단계에서는 **OAuth consent screen "Testing" 모드**로 최대 100명 테스트 유저까지 등록(검증 우회). 운영 전환 시 Verification 필요.

### 배포 토폴로지 (Railway)
- 서비스 3개 분리:
  1. `mello-web` — Next.js (Node runtime)
  2. `mello-api` — FastAPI (Python)
  3. `mello-db` — Postgres (Railway managed)
- 서비스 간 통신: Railway 내부 도메인 + 환경변수
- 도메인: web/api 각각 단일 프로젝트 안에서 관리

### 제외/연기
- **할당량 enforcement**: UI의 "Free · 30회 / 월" 표기는 **정적 라벨로 유지**. 백엔드 카운팅/429 없음.
- **Slack/Notion 통합**: Settings UI는 유지하되 토글은 비활성/no-op.
- **버전 N개 동시 생성**: UI의 "버전 선택자"는 제거. 단일 스트리밍 응답 + Regenerate 버튼.

## Non-Goals
- 매직링크/이메일+PW 인증 (OAuth로 단일화)
- 별도 SMTP/SES/Resend 등 트랜잭션 메일 인프라
- 다국어 (UI 텍스트는 한국어 기준)
- 모바일 네이티브
- 결제/플랜 업그레이드 흐름 (UI 라벨만 정적 표기)
- Slack/Notion 실제 연동
- AI 생성 결과 N개 버전 동시 비교
- Gmail 라벨/검색/스레드 분류 등 메일 클라이언트 기능
- Google OAuth verification 통과 (Testing 모드로 데모)
- 백엔드 측 사용량 quota/billing 시스템

## Acceptance Criteria
데모 시점에 다음이 전부 동작해야 한다:

### 인증
- [ ] 첫 진입 시 "Sign in with Google" 화면 노출
- [ ] Google OAuth 동의 → 콜백 → 서버 세션 발급 → 메인 화면 진입
- [ ] 로그아웃 시 세션 삭제, 로그인 화면으로 복귀
- [ ] 새로고침 시 세션 유지

### 페르소나 (People)
- [ ] 페르소나 수동 생성/수정/삭제 (이름, 관계, 톤, 메모)
- [ ] Settings 또는 People 화면에 "Contacts에서 가져오기" 버튼 → 상위 N개(예: 20) 임포트
- [ ] DB에 사용자별로 영속화

### AI 생성 (Compose) — 핵심
- [ ] brief 입력 + tone/length 슬라이더 + (옵션) 페르소나 선택 + (옵션) reply_context로 POST 요청
- [ ] **SSE 스트리밍**으로 초안(subject, body)이 실시간 표시됨
- [ ] "Regenerate" 버튼으로 동일 입력 재호출 시 새 초안 생성
- [ ] 생성 완료 후 자동으로 history에 1건 기록
- [ ] **버전 선택자 UI는 제거됨**

### 받은편지함 (신규 라우트)
- [ ] Sidebar에 "받은편지함" 항목 추가
- [ ] 최근 받은 메일 N개(예: 30) 목록 표시 (from, subject, snippet, date)
- [ ] 항목 클릭 → Compose 화면으로 이동 + reply_context 주입 (원문 + 메타) + brief는 비어있음
- [ ] Compose에서 Generate 누르면 답장 톤으로 초안 생성

### 메일 발송
- [ ] Compose 화면에서 "보내기" 버튼 → Gmail API로 사용자 본인 명의 발송
- [ ] 답장이면 In-Reply-To/References 헤더로 스레드 유지
- [ ] 발송 성공 시 토스트 + history 항목 상태가 "sent"로 업데이트
- [ ] 발송 실패 시 사용자에게 명확한 에러 메시지

### 히스토리
- [ ] 생성한 모든 초안이 사용자별로 영속화 (생성 시각, 입력 brief, 출력, persona_id, reply_context_id, status)
- [ ] History 화면에서 목록 확인 가능

### 메일 형식 (Format)
- [ ] 사용자별 시그니처/인사말 저장
- [ ] AI 생성 시 시스템 프롬프트에 주입되어 결과에 반영됨

### 통합 (Settings)
- [ ] Gmail/Contacts는 OAuth 동의 시점에 자동 "연결됨" 상태로 표시
- [ ] Slack/Notion 토글은 표시되되 클릭 시 "지원 예정" no-op

### 비기능 / 배포
- [ ] Railway에 3서비스(web/api/db) 배포 완료
- [ ] 공개 URL로 접근 가능
- [ ] 환경변수로 비밀(OAuth client secret, Solar API key, DB URL) 관리
- [ ] 기본적인 에러 핸들링 (Gmail rate limit, Solar 5xx, OAuth refresh 실패)
- [ ] README에 로컬 실행 + 데모 시나리오 명시

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 인증은 매직링크여야 한다 | OAuth로 Gmail을 어차피 받아야 한다면 매직링크는 중복 정체성 | **OAuth로 단일화** — 매직링크/메일서버 의존성 제거 |
| 메일서버(SMTP/SES/Resend) 필요 | OAuth 단일화 후엔 메일 발송도 Gmail API가 처리 | **메일서버 불필요** — 별도 인프라 제거 |
| UI의 "버전 선택자"는 유지해야 한다 | 3배 비용/지연 vs 단일 스트리밍의 명료함 — 2주 마감 가중치 | **스트리밍 단일 + Regenerate**로 단순화 |
| Gmail 받은 메일에 답장 = 어딘가에서 메일을 골라야 함 | UI에 inbox가 없음 — 어디서 고르나? | **Sidebar에 '받은편지함' 라우트 신규 추가** |
| LLM = OpenAI일 수도 | 프로젝트 경로가 'upstage-ambassador' | **Upstage Solar 단일 provider 확정** |
| "30회/월" 할당량은 실제 동작해야 한다 | 데모 가치 vs 구현 부담 | **정적 UI 라벨만 유지, 백엔드 enforcement 없음** |
| Railway는 단일 monorepo 서비스 | 배포자(강민석) 운영 부담 | **3서비스 분리** (web/api/db) — 표준적 구조 |
| 페르소나는 자동 생성된다 | 데이터 소스 미정 | **수동 CRUD 기본 + Contacts 임포트 버튼**으로 양쪽 다 |

## Technical Context (Brownfield)

### 현재 UI 구조 (탐색 결과)
- **단일 SPA**: `app/page.tsx → MelloApp.tsx`가 클라이언트 상태로 라우팅
- **내부 라우트** (state 기반): `compose`, `people`, `history`, `format`, `settings`
- **mock 데이터**: `lib/data.ts`에 정의 ("Shape preserved verbatim so a future API can return the same payload" 주석)
- **의존성**: `next@14.2.18`, `react@18.3.1`만. shadcn/Tailwind/auth lib 없음, 순수 CSS

### 백엔드 결합으로 변경되는 부분
- `lib/data.ts` → API 클라이언트(`lib/api.ts`)로 대체, 같은 shape 유지
- `MelloApp.tsx`: 라우트 enum에 `inbox` 추가, 인증 가드 추가
- `ComposerScreen.tsx`: 버전 선택자 제거, SSE 스트리밍 핸들러 추가, reply_context 주입 받음
- `Sidebar.tsx`: "받은편지함" 항목 추가
- 신규 컴포넌트: `InboxScreen.tsx`, `LoginScreen.tsx`
- `Settings → 통합`: Gmail/Contacts는 OAuth 상태와 연결, Slack/Notion은 비활성

### 백엔드 신규 (FastAPI)
- `POST /auth/google/start` → OAuth URL
- `GET  /auth/google/callback` → 토큰 교환, 세션 발급
- `POST /auth/logout`
- `GET  /me` → 현재 사용자
- `GET  /personas`, `POST /personas`, `PATCH /personas/{id}`, `DELETE /personas/{id}`
- `POST /personas/import-contacts` → top-N 임포트
- `GET  /history`, `GET /history/{id}`
- `GET  /format`, `PUT /format`
- `POST /ai/generate` (SSE) → Solar 호출, 결과 스트리밍, 완료 시 history에 저장
- `GET  /gmail/messages` → 받은편지함 목록
- `GET  /gmail/messages/{id}` → 단일 메일 (답장 컨텍스트용)
- `POST /gmail/send` → 메일 발송 (답장 시 thread_id/references 포함)

### DB 스키마 (개략)
```
users(id, google_sub, email, name, picture_url, created_at)
oauth_tokens(user_id, access_token_enc, refresh_token_enc, scope, expires_at)
personas(id, user_id, name, relation, tone, notes, source, created_at)
mail_formats(user_id, signature, greeting, updated_at)
history(id, user_id, brief, tone, length, persona_id, reply_context_id, subject, body, status, created_at)
reply_contexts(id, user_id, gmail_message_id, from_addr, subject, snippet, raw_body, thread_id, references)
```

## Ontology (Key Entities — Final Round 6)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| User | core domain | id, google_sub, email, name, picture_url | has many Persona/History/ReplyContext; has one MailFormat; has one OAuthToken |
| OAuthToken | core domain | user_id, access_token, refresh_token, scope, expires_at | belongs to User |
| Persona | core domain | id, user_id, name, relation, tone, notes, source | belongs to User |
| MailFormat | core domain | user_id, signature, greeting | belongs to User |
| AIGeneration | core domain (transient) | brief, tone, length, persona_id?, reply_context_id? → subject, body | input/output; persisted as History |
| HistoryItem | core domain | id, user_id, brief, tone, length, persona_id?, reply_context_id?, subject, body, status, created_at | belongs to User; refs Persona/ReplyContext |
| ReplyContext | core domain | id, user_id, gmail_message_id, from, subject, snippet, raw_body, thread_id, references | belongs to User |
| GmailMessage | external view | gmail_message_id, from, subject, snippet, date, thread_id | fetched from Gmail API on demand |
| Contact | external view | resource_name, name, email | fetched from People API on import |

## Ontology Convergence
| Round | Entity Count | New | Changed | Removed | Stable | Stability |
|-------|-------------|-----|---------|---------|--------|-----------|
| 0 (initial) | 8 | 8 | - | - | - | N/A |
| 1 (scope demo) | 9 | 2 (AIGeneration, MagicLinkSession) | 0 | 2 (Slack/Notion) | 6 | 75% |
| 2 (LLM=Solar) | 9 | 1 (UpstageProvider) | 0 | 0 | 8 | 88.9% |
| 3 (OAuth 단일화) | 9 | 3 (Session, GmailMessage, Contact) | 1 (GmailIntegration→User) | 1 (MagicLinkSession) | 6 | 77.8% |
| 4 (Generation contract) | 9 | 0 | 0 (AIGeneration shape refined) | 0 | 9 | **100%** |
| 5 (받은편지함 라우트) | 9 | 0 | 0 | 0 | 9 | **100%** |
| 6 (Ops defaults) | 9 | 0 | 0 | 0 | 9 | **100%** |

→ Round 4 이후 3회 연속 100% stable. 도메인 모델 완전 수렴.

## Interview Transcript
<details>
<summary>Full Q&A (6 rounds)</summary>

### Round 1 — Demo target (Success Criteria)
**Q:** 데모/제출 마감일과 그 시점에 무엇이 동작해야 "완성"인가?
**A:** 2주 내외 / 핵심 기능 풀 데모 (골든패스 + 페르소나 CRUD + 히스토리 + Gmail 받은 메일 답장. Slack/Notion은 UI만 유지)
**Ambiguity:** 38.4% (Goal 0.60, Constraints 0.55, Criteria 0.65, Context 0.70)

### Round 2 — LLM provider (Constraints)
**Q:** LLM 공급자는?
**A:** Upstage Solar (단일 provider)
**Ambiguity:** 32.4%

### Round 3 — Auth model (Constraints)
**Q:** 매직링크 인증과 Gmail OAuth는 한 사용자 안에서 어떻게 결합되는가?
**A:** OAuth로 단일화 (매직링크 결정 철회)
**Ambiguity:** 26.2%

### Round 4 — Generation contract (Goal, Contrarian mode)
**Q:** 버전 선택자가 정말 필요한가, 아니면 스트리밍 1개 명료가 더 말이 되는가?
**A:** 스트리밍 1개 명료 + 'Regenerate' 버튼
**Ambiguity:** 22.5%

### Round 5 — Reply entry point (Context, brownfield)
**Q:** 받은 메일에 답장하려면 UI 어디에서 대상 메일을 고르는가? (현재 UI에 inbox 없음)
**A:** Sidebar에 '받은편지함' 라우트 신규 추가
**Ambiguity:** 18.0% ✅ 임계치 통과

### Round 6 — Ops defaults (Constraints, Simplifier mode)
**Q:** OAuth scopes / Railway 토폴로지 / 할당량 / Persona 소스 — 추천 기본값 채택?
**A:** 추천 기본값 채택 — 단 할당량 enforcement 제거 (UI 라벨만 정적 유지)
**Ambiguity:** 10.0% ✅

</details>

## Open Decisions (이후 단계에서 결정)
다음 항목은 본 스펙의 결정과 직접 충돌하지 않으며 omc-plan/autopilot 단계에서 확정해도 무방:
- 받은편지함 페이지 사이즈(N=30 추천), 폴링/새로고침 정책
- Contacts 임포트 시 top-N 기준 (최근 연락? 알파벳? — 20개 추천)
- 토큰 암호화 알고리즘 (AES-GCM + 키는 Railway secret)
- SSE 타임아웃/하트비트 정책
- Frontend 측 API client 라이브러리 (fetch wrapper vs React Query 등 — 현재 의존성 최소 유지 권장)
- 에러 토스트의 사용자 친화적 메시지 카피
