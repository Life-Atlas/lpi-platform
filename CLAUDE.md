# LPI Platform — Claude Code Project Guide

FastAPI backend for the Life Programmable Interface: goal registry, activity
signals, LLM-assisted recommendations. SMILE methodology (6 phases). Part of
the Life Atlas / WINNIIO platform.

## Commands

```bash
pip install -e ".[dev]"          # one-time setup
ruff check src/ tests/           # lint (must be clean before every push)
mypy src/ --ignore-missing-imports   # typecheck (must be clean)
pytest tests/ -v                 # full suite — needs local Supabase (below)
uvicorn lpi.main:app --reload --port 8000   # run locally
```

## Tests need a local Supabase

`supabase start` in the repo root (Docker required), then put the values from
`supabase status` into `.env` (`SUPABASE_URL`, `SUPABASE_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`). **Without it, all
store-backed tests self-skip** — `28 passed, 167 skipped` means Supabase is
down, NOT that the suite is green. Tests marked `@pytest.mark.unit` always run.

## Architecture (read docs/ARCHITECTURE.md before claiming anything)

```
Client → FastAPI (src/lpi) → Supabase (Postgres + Auth + RLS)
                 └→ LangGraph agent → Groq LLM (recommendations)
```

- `routers/` — HTTP endpoints; `store.py` — ALL Supabase access; `middleware/`
  — JWT auth + per-IP rate limit; `langgraph_agent.py` — LLM reasoning;
  `cost_guard.py` — daily LLM spend cap.

## Gotchas (learned the hard way)

1. **Never trust migration files over the live schema** — verify with
   `supabase db query` before touching a table.
2. Ownership checks return **404, not 403** (don't leak resource existence).
3. `store.py` is the only file allowed to touch Supabase. No client creation
   in routers.
4. LLM calls must stay non-fatal: `_call_llm` returns `None` on any failure
   and the deterministic engine takes over. Never let an LLM error 500 an
   endpoint.
5. Rate limiter + cost guard are in-memory/per-process — known limitation,
   don't "fix" by adding a DB write per request without discussing.
6. Branch off `staging`, PR to `staging`. `main` is release-only.
7. Lint + typecheck locally before every push (CI minutes are budgeted).
8. Never commit tokens — even local/expired ones. `detect-secrets` runs in
   pre-commit; install it: `pre-commit install`.
