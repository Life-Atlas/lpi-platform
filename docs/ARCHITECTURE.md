# LPI Platform — Architecture (one page)

_Last verified against code: 2026-07-05. If this drifts from `src/`, the code
wins — update this file in the same PR._

## Data flow

```
Browser / API client
      │  Authorization: Bearer <Supabase JWT>
      ▼
FastAPI app (src/lpi/main.py)
      │
      ├─ middleware/rate_limit.py   fixed-window per client IP (in-memory)
      ├─ middleware/auth.py         JWT verify: HS256 (shared secret) or
      │                             ES256/RS256 via project JWKS
      ▼
routers/  goals · signals · recommendations · users · me · metrics ·
          github_auth · webhooks
      │  (ownership checks here: caller's user_id or admin, 404 on miss)
      ▼
store.py  — the ONLY module that talks to Supabase (service-role client,
            RLS bypassed server-side by design; every query user-scoped)
      ▼
Supabase Postgres  — tables: goals, activity_signals, recommendations,
   recommendation_feedback, goal_phase_transitions, system_logs, users,
   notifications  (RLS enabled via supabase/migrations)

Recommendations path additionally:
routers/recommendations → agent_pipeline / langgraph_agent
   → cost_guard.check_budget()          (daily USD cap, refuses when hit)
   → Groq LLM (default) — non-fatal: any failure returns None
   → fallback: deterministic recommendation_engine.py
```

## External integrations

- **GitHub OAuth + webhooks** (`routers/github_auth.py`, `routers/webhooks.py`)
  — activity signals from commits/PRs.
- **ZeroClaw** (`utils/zeroclaw_*`) — HMAC-authenticated security-scan webhook.
- **SMTP notifications** (`notifications.py`) — goal lifecycle emails.

## Deploy

Docker + Traefik (TLS) on a VM → `lpi-backend.lifeatlas.online`, port 8020.
`docker-compose.yml` in repo root. CI: `.github/workflows/ci.yml`
(ruff → mypy → full pytest against a local Supabase started in the job).

## Known limitations (intentional, don't "discover" them)

- Rate limit + LLM cost cap are per-process, in-memory — single-instance
  assumptions; move to shared store before scaling out.
- SMILE phase logic lives in `smile.py`; the 6 phases are canonical
  (reality-emulation → perpetual-wisdom). Do not reintroduce the old
  hallucinated 5-phase names.
