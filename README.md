# Mello API Backend

FastAPI backend for Mello, the Google OAuth + Gmail + Upstage Solar mail assistant described in `docs/SPEC.md`.

## Stack

- FastAPI + SQLAlchemy
- Postgres with `psycopg`
- Google OAuth 2.0, Gmail API, Google People API
- Upstage Solar through LangChain `ChatOpenAI` compatibility
- LangGraph for the LLM generation workflow
- HttpOnly cookie server sessions

## Local Run

1. Create a Postgres database.
2. Copy `.env.example` to `.env`.
3. Fill `DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and `SOLAR_API_KEY`.
4. Install and run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Schema changes are managed by Alembic migrations. Runtime configuration is Postgres-first because the product spec and Railway deployment use Postgres. SQLite is used only inside the test suite through an explicit test override.

For local OAuth testing with the frontend on port `3004`, keep these values aligned in `.env` and in the Google Cloud Web OAuth client:

```env
FRONTEND_URL=http://localhost:3004
CORS_ORIGINS=http://localhost:3004
GOOGLE_REDIRECT_URI=http://localhost:3004/auth/google/callback
SESSION_COOKIE_SECURE=false
```

## Checks

```bash
pytest -q
```

## Database Migrations

Apply migrations:

```bash
alembic upgrade head
```

Create a new migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe change"
```

`AUTO_CREATE_TABLES` is disabled by default. It exists only as a local/demo escape hatch; production and Railway should run Alembic explicitly.

## Configuration

See `.env.example` for the full variable list.

Required for the full demo path:

- `DATABASE_URL`
- `SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `SOLAR_API_KEY`

For Railway with separate web/API domains, set `SESSION_COOKIE_SECURE=true`, `SESSION_COOKIE_SAMESITE=none`, and configure `CORS_ORIGINS` to the public frontend URL.

## Demo Scenario

1. Frontend calls `POST /auth/google/start` and redirects the browser to the returned `url`.
2. Google redirects to `GET /auth/google/callback`; the API stores OAuth tokens, creates an HttpOnly session cookie, and redirects to `FRONTEND_URL`.
3. Frontend calls `GET /me`, `GET /personas`, `GET /format`, and `GET /history` with credentials included.
4. User creates or imports personas through `POST /personas` or `POST /personas/import-contacts`.
5. User opens `GET /gmail/messages?limit=30`, follows `nextPageToken` when present, selects one message, then `GET /gmail/messages/{id}` returns a persisted `reply_context`.
6. Compose calls `POST /ai/generate` and consumes SSE events:
   - `event: delta` with streamed text
   - `event: done` with final `subject`, `body`, and persisted `history`
   - `event: error` on external failures
7. Compose calls `POST /gmail/send`; Gmail sends from the authenticated user and matching history becomes `sent`.

## Key Endpoints

- `POST /auth/google/start`
- `GET /auth/google/callback`
- `POST /auth/logout`
- `GET /me`
- `GET/POST/PATCH/DELETE /personas`
- `POST /personas/import-contacts`
- `GET /history`, `GET /history/{id}`
- `GET /format`, `PUT /format`
- `POST /ai/generate`
- `GET /gmail/messages?limit=30&pageToken=<opaque-token>`, `GET /gmail/messages/{id}`
- `POST /gmail/send`
- `GET /integrations`, `POST /integrations/{provider}/toggle`
- `GET /health` for process liveness, `GET /health/ready` for DB readiness

`POST /ai/generate` accepts `tone` and `length` as 1-5 scale integers. During the frontend transition, legacy 0-100 slider values are normalized to the same 5-step scale. Persona `tone` accepts one of `매우 격식`, `격식`, `중립`, `친근`, `매우 친근`.

`GET /gmail/messages` returns a cursor-paginated envelope:

```json
{
  "messages": [],
  "nextPageToken": null,
  "resultSizeEstimate": 0,
  "limit": 30,
  "hasMore": false
}
```

`pageToken` is the opaque Gmail cursor from the previous response. `limit` is bounded from 1 to 100.

## Railway

Use three services in one Railway project:

- `mello-web`: Next.js frontend
- `mello-api`: this FastAPI service
- `mello-db`: Railway Postgres

The Dockerfile runs `alembic upgrade head` before starting Uvicorn and binds to Railway's `PORT` environment variable. Railway's default `postgresql://...` URL is normalized to SQLAlchemy's `postgresql+psycopg://...` driver URL in app config.

Set secrets in Railway variables, not in source control. Minimum API variables:

- `DATABASE_URL`
- `SECRET_KEY`
- `TOKEN_ENCRYPTION_KEY` recommended for stable token encryption
- `FRONTEND_URL`
- `CORS_ORIGINS`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `SOLAR_API_KEY`
- `SESSION_COOKIE_SECURE=true`
- `SESSION_COOKIE_SAMESITE=none`

## Branch and Railway Environments

- `main` deploys to Railway `production`.
- `dev` deploys to Railway `dev`.
- Feature work should merge `feature/* -> dev`, then verified `dev -> main`.
- Auth behavior must stay environment-driven. Do not hardcode dev/prod callback URLs in code.

Dev Railway uses the same backend code with a separate Postgres service instance and separate variables:

- `APP_ENV=dev`
- `DATABASE_URL=${{Postgres.DATABASE_URL}}` in the Railway `dev` environment
- `FRONTEND_URL=<dev frontend public URL>`
- `CORS_ORIGINS=<dev frontend public URL>`
- `GOOGLE_REDIRECT_URI=<dev frontend public URL>/auth/google/callback`
- `SESSION_COOKIE_SECURE=true`
- `SESSION_COOKIE_SAMESITE=lax`
