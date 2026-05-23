# Claude Instructions

Use this repository as the backend service for Mello.

## Context

- The authoritative backend requirements are in `docs/SPEC.md`.
- The service is FastAPI with SQLAlchemy models and Postgres runtime configuration.
- DB schema changes must be represented as Alembic migrations.
- LLM generation must use LangChain and LangGraph. The current implementation calls Upstage Solar through OpenAI-compatible `ChatOpenAI`.
- Google OAuth, Gmail, and Contacts integrations live in `app/services/google.py`.
- API routes live in `app/routers/`.

## Guardrails

- Do not commit `.env`, local DB files, `.venv`, cache folders, or `*.egg-info/`.
- Do not ignore `.claude/` or `.agents/`; they are intended to remain in Git.
- Keep secrets in environment variables.
- Keep response shapes compatible with the existing frontend mock shapes where possible.

## Common Commands

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
pytest -q
uvicorn app.main:app --reload
```
