# Mello Current Feature Specification

이 문서는 현재 구현된 Mello 기능과 앞으로의 안정화 기준을 정리한다.
기능 추가는 아래 범위를 기준으로 진행하며, 디자인 시스템과 기존 화면 톤은 변경하지 않는다.

## Scope Rules

- 인증은 Google OAuth 단일 흐름을 사용한다.
- 브라우저 코드는 same-origin API contract만 호출한다.
- 외부 Google, Gmail, Contacts, Solar 호출은 백엔드 또는 mock server 뒤에 둔다.
- 현재 디자인 시스템, CSS 토큰, 레이아웃 톤은 기능 작업 범위에서 변경하지 않는다.
- 매직링크, Rate Limit, Redis/RabbitMQ, Turnstile/reCAPTCHA, quota enforcement, Slack/Notion 실제 연동은 후순위다.

## 1. Google OAuth 로그인 및 서버 세션

### 기능 명
Google OAuth 로그인 및 HttpOnly 세션 인증

### 기능 정의
사용자가 Google 계정으로 로그인하면 백엔드가 OAuth 토큰을 교환하고 서버 세션을 발급해 Mello 앱 접근을 제어한다.

### 기능 상세 동작
- 로그인 화면에서 `Google 계정으로 계속하기`를 누르면 프론트엔드가 `POST /auth/google/start`를 호출한다.
- 백엔드는 Google OAuth 동의 URL을 생성해 반환한다.
- `/auth/google/callback`은 Next.js rewrite를 통해 백엔드 `GET /auth/google/callback`으로 전달될 수 있다.
- 백엔드는 Google token과 userinfo를 저장 또는 갱신한다.
- 백엔드는 무작위 세션 토큰을 발급하고 HttpOnly cookie로 저장한다.
- 프론트엔드는 `GET /me`로 인증 상태를 확인한다.
- 로그아웃 시 `POST /auth/logout`으로 서버 세션을 삭제하고 cookie를 제거한다.

### 기능 효과
이메일/비밀번호/매직링크 없이 Gmail과 Contacts 권한, 사용자 인증을 한 번에 처리한다.

### 연계 기능
Gmail 받은편지함, Gmail 발송, Contacts import, Settings 통합 상태

## 2. 사용자 프로필 및 통합 상태

### 기능 명
사용자 프로필 및 통합 상태 조회

### 기능 정의
현재 로그인한 사용자 정보와 외부 서비스 연결 상태를 앱 shell과 Settings 화면에 제공한다.

### 기능 상세 동작
- `GET /me`는 사용자 프로필과 integration status를 반환한다.
- Gmail과 Google Contacts는 Google OAuth scope 기반 연결 상태로 표시한다.
- Slack과 Notion은 UI에 표시하지만 `지원 예정` no-op 상태로 둔다.
- Settings의 통합 버튼은 실제 연결/해제가 아니라 안내 API를 호출하고 toast를 표시한다.

### 기능 효과
사용자가 현재 계정과 사용 가능한 외부 연동 범위를 확인할 수 있다.

### 연계 기능
Google OAuth, Settings, Gmail, Contacts

## 3. People/Persona 관리

### 기능 명
페르소나 수동 CRUD

### 기능 정의
자주 메일을 보내는 사람의 이름, 이메일, 관계, 톤, 키워드, 금지 표현, 선호 표현, 메모를 저장한다.

### 기능 상세 동작
- People 화면은 `GET /personas` 결과를 목록으로 렌더링한다.
- 사람 추가 또는 수정 시 이름, 이메일, 관계, 역할, 톤, 키워드, 금지 표현, 선호 표현, 메모를 입력한다.
- 저장 시 `POST /personas` 또는 `PATCH /personas/{id}`를 호출한다.
- 삭제 시 확인 후 `DELETE /personas/{id}`를 호출한다.
- 백엔드는 사용자별 persona를 저장한다.
- 이메일이 있는 persona는 사용자별 중복 이메일을 방지한다.
- 이메일이 비어 있는 persona는 중복 생성을 허용한다.

### 기능 효과
AI 초안 생성 시 수신자의 성향, 관계, 선호 표현, 피해야 할 표현을 반영할 수 있다.

### 연계 기능
Compose, Gmail reply sender matching, History, Contacts import

## 4. Google Contacts 기반 Persona Import

### 기능 명
Contacts에서 페르소나 가져오기

### 기능 정의
Google Contacts 권한을 사용해 연락처를 persona 후보로 가져온다.

### 기능 상세 동작
- People 화면에서 `Contacts에서 가져오기` 버튼을 누른다.
- 프론트엔드는 `POST /personas/import-contacts`를 호출한다.
- 백엔드는 Google People API에서 연락처를 가져온다.
- 기존 persona 이메일과 중복되지 않는 항목만 생성한다.
- 응답은 `imported`, `skipped`, 최신 `personas` 목록을 포함한다.

### 기능 효과
사용자가 초기 수신자 목록을 빠르게 구성할 수 있다.

### 연계 기능
Google OAuth `contacts.readonly`, People, Compose

## 5. 내 메일 형식 관리

### 기능 명
사용자별 기본 메일 형식 저장

### 기능 정의
사용자의 인사말, 본문 구조, 불릿 스타일, 마무리 문장, 언어, 서명을 저장하고 AI 생성 프롬프트에 반영한다.

### 기능 상세 동작
- Format 화면은 `GET /format`으로 현재 형식을 조회한다.
- 편집 모드에서 필드를 수정하고 저장하면 `PUT /format`을 호출한다.
- 백엔드는 사용자별 1:1 MailFormat을 생성 또는 갱신한다.
- AI 생성 시 백엔드가 MailFormat을 시스템 프롬프트에 삽입한다.

### 기능 효과
AI 초안이 사용자의 평소 이메일 스타일과 서명을 따른다.

### 연계 기능
Compose, AI generation, History

## 6. AI 메일 초안 생성

### 기능 명
Solar 기반 SSE 메일 초안 생성

### 기능 정의
사용자의 brief, tone/length 옵션, persona, mail format, reply context를 조합해 Upstage Solar로 메일 초안을 생성하고 스트리밍으로 표시한다.

### 기능 상세 동작
- Compose 화면에서 brief를 입력하거나 reply context가 있는 상태에서 `Mello에게 작성 요청`을 누른다.
- 프론트엔드는 `POST /ai/generate`를 호출하고 SSE stream을 읽는다.
- 백엔드는 persona, reply context, mail format을 조회하고 Solar 프롬프트를 구성한다.
- 생성 중 `delta` event로 텍스트 청크를 보낸다.
- 완료 시 `done` event로 `subject`, `body`, `history`를 반환한다.
- 생성 완료 후 history는 `draft` 상태로 저장된다.
- `다시 생성`은 같은 입력으로 생성 API를 재호출한다.
- 생성 시작 시 현재 draft는 비워진다.
- 생성 실패 시 에러 toast를 표시하고 history는 생성하지 않는다.

### 기능 효과
사용자는 초안 생성 과정을 실시간으로 확인하고 반복 생성할 수 있다.

### 연계 기능
Persona, MailFormat, Gmail reply context, History, Gmail send

## 7. Gmail 받은편지함 및 답장 컨텍스트

### 기능 명
Gmail 받은편지함 조회 및 답장 초안 진입

### 기능 정의
Gmail에서 최근 받은 메일을 조회하고, 선택한 메일의 원문과 메타데이터를 답장 초안 생성 컨텍스트로 사용한다.

### 기능 상세 동작
- Inbox 화면은 server component에서 `GET /gmail/messages`를 호출해 메일 목록을 렌더링한다.
- 페이지 크기와 Gmail `pageToken` 기반 cursor pagination을 지원한다.
- 메일 항목 클릭 시 `/compose/{personaId}/reply/{messageId}` 또는 `/compose/reply/{messageId}`로 이동한다.
- 상세 route는 server side에서 `GET /gmail/messages/{messageId}`를 호출한다.
- 상세 응답의 raw body와 reply context를 Compose에 주입한다.
- sender email이 기존 persona와 매칭되면 해당 persona를 사용한다.
- 매칭 persona가 없고 본인 이메일이 아니면 클라이언트가 신규 persona 생성을 보조하고 생성된 persona의 reply route로 이동한다.

### 기능 효과
사용자가 Gmail 원문을 복사하지 않고 받은 메일 기반 답장 초안을 만들 수 있다.

### 연계 기능
Google OAuth `gmail.readonly`, Compose, Persona, History

## 8. Gmail API 발송

### 기능 명
Gmail API 직접 발송

### 기능 정의
생성된 초안을 Gmail API로 사용자 본인 명의로 발송한다.

### 기능 상세 동작
- Compose 결과 패널에서 `보내기`를 누르면 `POST /gmail/send`를 호출한다.
- UI의 새 메일 발송은 persona email을 수신자로 사용한다.
- API는 `to`를 직접 받을 수 있고, 없으면 history persona 또는 reply context에서 수신자를 보완한다.
- 답장인 경우 reply context의 thread metadata를 사용한다.
- 백엔드는 Gmail API send를 호출한다.
- 성공 시 history 상태를 `sent`로 갱신하고 Gmail message id와 sent_at을 저장한다.
- 실패 시 프론트엔드 toast로 에러를 표시한다.

### 기능 효과
사용자가 앱 안에서 초안 생성부터 발송까지 완료할 수 있다.

### 연계 기능
Compose, Gmail reply context, History, Google OAuth `gmail.send`

## 9. History

### 기능 명
생성/발송 히스토리 조회

### 기능 정의
AI가 생성한 초안과 Gmail 발송 상태를 사용자별로 저장하고 History 화면에서 조회한다.

### 기능 상세 동작
- `/ai/generate` 완료 시 HistoryItem을 `draft` 상태로 생성한다.
- `/gmail/send` 성공 시 연결된 HistoryItem을 `sent` 상태로 갱신한다.
- History 화면은 `GET /history` 결과를 목록으로 보여준다.
- 화면 내 client filter로 전체, persona별, reply 기록별 필터를 제공한다.
- 각 row를 펼치면 subject, body, 대상 정보를 확인할 수 있다.

### 기능 효과
사용자는 생성 및 발송 기록을 추적할 수 있다.

### 연계 기능
Compose, Gmail send, Persona, ReplyContext

## 10. Local Mock E2E 지원

### 기능 명
프론트엔드 mock API 기반 E2E 검증

### 기능 정의
실제 Google, Solar, Postgres 없이 프론트엔드 골든패스를 검증할 수 있는 Node mock server를 제공한다.

### 기능 상세 동작
- `mock-server/server.mjs`가 백엔드 계약 경로를 흉내낸다.
- `MELLO_API_URL`을 mock server로 지정하면 Next.js가 same-origin API contract를 mock으로 rewrite한다.
- Playwright CLI runbook으로 로그인, compose, inbox reply, people import, send, history, format, settings flow를 수동 검증할 수 있다.

### 기능 효과
실제 외부 API 없이 UI, SSR, API contract 회귀를 빠르게 확인할 수 있다.

### 연계 기능
Frontend routes, mock data, manual QA

## Deferred Items

다음 항목은 현재 안정화/고도화 범위에서 제외한다.

- 이메일 매직링크 인증 전체
- 로그인 폼 봇 방어 UI
- API Rate Limit
- Redis/RabbitMQ 기반 비동기 큐
- quota enforcement
- Slack/Notion 실제 연동
- 작성 세션/Message 테이블 기반 split workspace/chat editor 대규모 개편
- mailto fallback 발송
- 생성 실패 시 이전 draft 롤백
- 생성 결과 금지어/서명 무결성 검증 API 고도화
