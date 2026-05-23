# Agent Instructions

This repository contains the Mello FastAPI backend.

## Repository

- GitHub: https://github.com/upstage-ambassador-2/Backend
- Follow shared PR and issue conventions from https://github.com/upstage-ambassador-2/.github/blob/main/CONTRIBUTING.md.
- Use the organization PR and issue templates from `upstage-ambassador-2/.github` unless this repository defines a local override.

## Project Rules

- Treat `docs/SPEC.md` as the product contract.
- Keep runtime database support Postgres-first. SQLite is acceptable only for isolated tests.
- Use FastAPI routers under `app/routers/` and keep external integrations under `app/services/`.
- Use LangChain and LangGraph for LLM generation code. Do not replace the generation path with direct provider HTTP calls.
- Keep Google OAuth scopes aligned with the spec: `openid`, `email`, `profile`, Gmail readonly/send, and contacts readonly.
- Manage schema changes with Alembic migrations. Do not rely on `create_all()` for production schema evolution.
- Do not commit secrets, local databases, virtual environments, caches, or `*.egg-info/`.
- `.agents/` and `.claude/` are intentionally versioned project context folders; do not add ignore rules for them.

## Validation

Run before committing backend changes:

```bash
pytest -q
```

When dependencies are missing, use Python 3.12 and install the local project with:

```bash
pip install -e ".[dev]"
```

## Notes

- Runtime schema migration is explicit through Alembic.
- OAuth tokens are encrypted before persistence.
- `/ai/generate` returns Server-Sent Events and persists a history item after generation completes.
