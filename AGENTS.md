# Agent Instructions

This repository contains the Mello FastAPI backend.

## Project Rules

- Treat `docs/SPEC.md` as the product contract.
- Keep runtime database support Postgres-first. SQLite is acceptable only for isolated tests.
- Use FastAPI routers under `app/routers/` and keep external integrations under `app/services/`.
- Use LangChain and LangGraph for LLM generation code. Do not replace the generation path with direct provider HTTP calls.
- Keep Google OAuth scopes aligned with the spec: `openid`, `email`, `profile`, Gmail readonly/send, and contacts readonly.
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

- Tables are created on startup for the demo-oriented implementation.
- OAuth tokens are encrypted before persistence.
- `/ai/generate` returns Server-Sent Events and persists a history item after generation completes.
