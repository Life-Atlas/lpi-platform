# LPI Platform — Life Programmable Interface

> **Goal registry · Activity signals · AI-powered recommendations — built on the SMILE methodology** 

**Demo Branch:** `staging`  
**Live API docs:** `http://localhost:8000/docs` (Swagger UI, auto-generated)  
**Supervisors:** Danial, Nicolas — Roll-up: Christalyn

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [System Architecture — Goals × Signals × Recommendations](#2-system-architecture--goals--signals--recommendations)
3. [Prerequisites](#3-prerequisites)
4. [Quick Start — Local Dev](#4-quick-start--local-dev)
5. [Environment Variables](#5-environment-variables)
6. [SMILE Methodology](#6-smile-methodology)
7. [Phase 1 — Strategy & Architecture](#7-phase-1--strategy--architecture)
8. [Phase 2 — Goal / Intent Registry (Module 1)](#8-phase-2--goal--intent-registry-module-1)
9. [Phase 3 — Activity Signals (Module 2)](#9-phase-3--activity-signals-module-2)
10. [Phase 4 — Recommendation Engine (Module 3)](#10-phase-4--recommendation-engine-module-3)
11. [Phase 5 — QA, Integration & Polish](#11-phase-5--qa-integration--polish)
12. [API Reference — Full Endpoint List](#12-api-reference--full-endpoint-list)
13. [Database Schema](#13-database-schema)
14. [Testing](#14-testing)
15. [Project Structure](#15-project-structure)
16. [Team & Ownership](#16-team--ownership)
17. [Next Steps & Improvements](#17-next-steps--improvements)

---

## 1. What This Project Does

The LPI Platform is a backend API that helps users track and advance their personal and professional goals using the **SMILE lifecycle framework**. It has three core modules:

| Module | What It Does |
|--------|-------------|
| **Module 1 — Goals** | Create, read, update, and delete goals; track each goal through 6 SMILE phases; score goals with a composite priority formula |
| **Module 2 — Signals** | Ingest structured activity events from any source (GitHub, Boardy, manual, simulated); query a paginated, filterable timeline |
| **Module 3 — Recommendations** | Combine a user's goals and signals through an AI reasoning pipeline to surface the top 3 SMILE-grounded next actions |

---

## 2. System Architecture — Goals × Signals × Recommendations

This section documents exactly how the three core modules connect to each other end-to-end, including the latest **goal-scoped signals** feature (June 25, 2026).

---

### High-level data flow

```
User / Frontend / External Source (Boardy, GitHub)
        │
        │  HTTP requests with Supabase JWT
        ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Application                       │
│                                                              │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │   Module 1      │  │   Module 2   │  │   Module 3     │  │
│  │    Goals        │  │   Signals    │  │ Recommendations│  │
│  │ /api/v1/goals   │  │/api/v1/signals│ │/api/v1/recs    │  │
│  └────────┬────────┘  └──────┬───────┘  └──────┬─────────┘  │
│           │                  │                  │            │
│           └──────────────────┴──────────────────┘            │
│                              │                               │
│                    store.py (single DB layer)                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
                       Supabase (PostgreSQL)
    goals │ activity_signals (+ goal_id FK) │ recommendation_feedback
    goal_phase_transitions │ user_activity_logs │ system_logs
```

---

### Database relationships (June 25 update)

```
goals
  id (PK)
  user_id
  title, priority, smile_phase, urgency_flag
  created_at, updated_at
    │
    │  FK: activity_signals.goal_id → goals.id (ON DELETE SET NULL)
    │  Nullable — signals without a goal still work fine
    ▼
activity_signals
  id (PK)
  user_id
  goal_id (FK → goals.id, nullable)   ← NEW: goal-scoped signals
  stream, event_type, payload, source
  timestamp
    │
    │  source_goals / source_signals lists in Recommendation
    ▼
recommendation_feedback
  id (PK)
  user_id
  recommendation_id (NOT a FK — recs are ephemeral, not persisted)
  action, smile_phase, status (accepted | dismissed)
  created_at
```

---

### How Goals feed into Recommendations

1. User creates a goal via `POST /api/v1/goals/`
2. Goal stored in `goals` table with `smile_phase` and `priority`
3. On `GET /api/v1/recommendations/{user_id}`, `store.list_goals(user_id)` fetches all the user's goals
4. `score_goal(goal)` computes priority: `(priority × 0.5) + (phase_weight × 0.3) + (urgency × 0.2)`
5. Each goal produces one recommendation: **advance to the next SMILE phase**
6. Goal UUID appears in `source_goals` — full traceability back to the source goal

```
Goal: "Ship dashboard"  phase=concurrent-engineering  priority=8  urgency=True
          │
          ▼  score_goal() → 4.80
          │
Recommendation:
  action:       "Advance 'Ship dashboard' to collective-intelligence"
  smile_phase:  collective-intelligence  (one step forward)
  priority:     4.80
  source_goals: ["<goal-uuid>"]
```

---

### How Signals feed into Recommendations

Signals can now be either **user-scoped** (general activity) or **goal-scoped** (linked to a specific goal). They arrive via three paths:

```
GitHub Event (PR merged, commit pushed, PR reviewed)
    │  POST /api/v1/webhooks/github  (no JWT — GitHub calls this)
    │  user_id resolved from repo_db (populated at track-repo time)
    │  source = "github_webhook"
    ▼
POST /api/v1/signals/  (manual / Boardy / any external source)
    │  JWT required
    │  source = "api" | "boardy_webhook" | "github_api" | "manual"
    ▼
activity_signals table
    stream, event_type, payload, source, user_id, goal_id (optional FK)
    │
    ▼
store.list_signals(user_id, limit=20)  ← recommendation engine reads these
```

Signal (user-scoped) vs Signal (goal-scoped):

```
Signal (user-scoped)                   Signal (goal-scoped)
  stream: "lpi"                          stream: "lpi"
  event_type: "pr_merged"                event_type: "pr_merged"
  goal_id: null                          goal_id: "<goal-uuid>"  ← FK to goals
  source: "github_webhook"               source: "github_webhook"
       │                                      │
       ▼                                      ▼
General signal recommendation         Goal-specific recommendation
  phase: collective-intelligence        source_goals + source_signals both set
  source_signals: ["<signal-id>"]
```

When recommendations are generated:
- `store.list_signals(user_id, limit=20)` fetches the 20 most recent signals
- Signals with `goal_id` set are matched to their parent goal for richer reasoning
- All signals aggregate into a `collective-intelligence` recommendation

---

### Goal-scoped recommendation endpoint (NEW — June 25)

A dedicated endpoint for per-goal recommendations using only signals linked to that goal:

```
POST /api/v1/recommendations/{user_id}/by-goal/{goal_id}
        │
        ├─ Verifies caller owns goal_id (404 if not)
        ├─ store.list_signals(user_id, goal_id=goal_id)  ← only signals for THIS goal
        ├─ Runs LangGraph agent over goal + its specific signals
        └─ Returns top 3 recommendations scoped to that goal
```

This is different from the general `/run` endpoint which reasons over ALL of a user's goals and signals.

---

### Full recommendation pipeline — three endpoints compared

| Endpoint | Data scope | Engine | Always 3 cards? |
|----------|-----------|--------|-----------------|
| `GET /{user_id}` | All user goals + all signals | Deterministic + optional LLM | ✅ (cold-start fallback) |
| `POST /{user_id}/run` | All user goals + all signals | 7-node LangGraph pipeline | ✅ (guaranteed) |
| `POST /{user_id}/by-goal/{goal_id}` | Single goal + its signals only | LangGraph agent | ✅ (capped at 3) |

---

### LangGraph orchestration pipeline (POST /run)

```
POST /api/v1/recommendations/{user_id}/run
                │
                ▼
        run_pipeline(user_id, n_cards=3)
                │
    ┌───────────▼────────────┐
    │  Node 1: fetch         │  store.list_goals(user_id)
    │                        │  store.list_signals(user_id, limit=20)
    └───────────┬────────────┘
                │
    ┌───────────▼────────────┐
    │  Node 2: classify      │  no data?  → cold_start
    │                        │  has data? → llm
    │                        │  DB error? → fallback
    └─────┬──────────────────┘
          │
    ┌─────┴──────────┐
    │                │
[llm path]    [cold_start / fallback]
    │                │
┌───▼────────┐  ┌────▼─────────────────────┐
│ Node 3:    │  │ Node 6: fallback          │
│ reason     │  │ build_cold_start_recs()   │
│ LangGraph  │  │ 3 hardcoded SMILE cards   │
│ Groq/Claude│  └────┬─────────────────────┘
└───┬────────┘        │
    │                 │
┌───▼────────┐        │
│ Node 4:    │        │
│ validate   │        │
│ retry once │        │
│ on bad LLM │        │
└───┬────────┘        │
    │                 │
┌───▼────────┐        │
│ Node 5:    │        │
│ enrich     │        │
│ Goals+Sigs │        │
│ → Rec objs │        │
└───┬────────┘        │
    │                 │
    └────────┬────────┘
             │
    ┌────────▼────────────┐
    │  Node 7: finalise   │
    │  deduplicate        │
    │  sort priority DESC │
    │  pad to 3 if needed │
    │  slice to 3         │
    └────────┬────────────┘
             │
             ▼
    list[Recommendation]  ← always exactly 3
```

**Guarantee:** `run_pipeline()` never raises and always returns exactly 3 cards, regardless of LLM availability, DB state, or user data.

---

### Three-tier fallback cascade

| Tier | When it fires | Output |
|------|--------------|--------|
| **Tier 1 — LLM reasoning** | User has data AND LLM is available | Real AI-generated actions referencing specific goal/signal IDs |
| **Tier 2 — Deterministic engine** | LLM unavailable or bad JSON | Template-based but real-data-driven: advances each goal one SMILE phase, aggregates signals |
| **Tier 3 — Cold start** | No data, DB unreachable, or any unhandled error | 3 hardcoded SMILE-grounded starter cards |

---

### Recommendation feedback loop

After a user acts on a recommendation, their choice is stored:

```
User sees recommendation card
        │
        ├─ clicks Accept  → POST /api/v1/recommendations/{user_id}/feedback
        │                    { recommendation_id, action, smile_phase, status: "accepted" }
        │
        └─ clicks Dismiss → POST /api/v1/recommendations/{user_id}/feedback
                             { recommendation_id, action, smile_phase, status: "dismissed" }
                                    │
                                    ▼
                         recommendation_feedback table
                         (snapshots action + smile_phase — recs are ephemeral,
                          no FK to a recommendations table)
                                    │
                                    ▼
                         Future: engine reads dismissed recs
                         to avoid re-surfacing them
```

---

### Complete end-to-end request trace

```
1. User logs in via Supabase Auth → gets JWT

2. User connects GitHub repo:
   POST /api/v1/github/track-repo
   → registers webhook on GitHub
   → stores repo_db["owner/repo"] = user_id  ← maps repo to user

3. User creates goal:
   POST /api/v1/goals/
   → stored in goals table (user_id from JWT)
   → logged: user_activity_logs (action=goal_created)
   → logged: goal_phase_transitions (if phase changes)

4. GitHub merges PR → webhook fires automatically:
   POST /api/v1/webhooks/github  (GitHub calls this, no JWT)
   → event_type = "pull_request", action = "closed", merged = true
   → user_id resolved from repo_db["owner/repo"]
   → Signal saved to activity_signals:
       stream="lpi", event_type="pr_merged",
       source="github_webhook", user_id=<resolved>
   → logged: user_activity_logs (action=signal_ingested)
   ← returns {"status": "success"} to GitHub

5a. General recommendations:
    GET /api/v1/recommendations/{user_id}
    → loads ALL goals + signals
    → deterministic engine: one rec per goal (advance phase)
                            + one rec for signals cluster
    → returns top 3 by priority

5b. Pipeline recommendations (demo-safe):
    POST /api/v1/recommendations/{user_id}/run
    → 7-node pipeline (fetch/classify/reason/validate/enrich/fallback/finalise)
    → LLM generates natural language action + reasoning
    → deterministic engine derives phase + priority
    → always returns exactly 3 cards

5c. Goal-scoped recommendations:
    POST /api/v1/recommendations/{user_id}/by-goal/{goal_id}
    → loads ONE goal + ONLY its linked signals
    → returns up to 3 cards focused on that goal

6. Frontend renders recommendation cards

7. User clicks Accept:
   POST /api/v1/recommendations/{user_id}/feedback
   → stored: recommendation_feedback (status=accepted)
   → future engine reads dismissed recs to avoid re-surfacing
```

---

## 3. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.11 | [python.org](https://www.python.org/) |
| Docker Desktop | Latest | Required for local Supabase |
| Supabase CLI | v2+ | `npm install -g supabase` or [docs](https://supabase.com/docs/guides/cli) |
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org/) (frontend only) |
| ngrok | Latest | [ngrok.com](https://ngrok.com/) (for Boardy webhook testing only) |

---

## 4. Quick Start — Local Dev

### Step 1 — Clone & install

```bash
git clone https://github.com/Life-Atlas/lpi-platform.git
cd lpi-platform
pip install -e ".[dev]"
pre-commit install
```

### Step 2 — Start local Supabase

```bash
supabase start
```

After it starts, copy the printed output into your `.env` file:
- `SUPABASE_URL` ← the API URL (usually `http://127.0.0.1:54321`)
- `SUPABASE_KEY` ← **service_role key** (the backend bypasses RLS by design — do NOT use the anon key)
- `SUPABASE_JWT_SECRET` ← the JWT secret

> **Note:** The local default JWT secret is `super-secret-jwt-token-with-at-least-32-characters-long`

### Step 3 — Apply all database migrations

```bash
supabase db push
```

This applies all 9 migrations in `supabase/migrations/` in order. Must be run after every `supabase start` on a fresh DB.

### Step 4 — Run the API server

```bash
make run
# OR directly:
uvicorn lpi.main:app --reload --port 8000
```

API is now live at `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

### Step 5 — Run all tests

```bash
make test
# OR:
pytest tests/ -v --tb=short
```

All tests must be green before any PR is opened.

### Makefile reference

```bash
make install   # pip install + pre-commit hooks
make lint      # ruff + mypy
make test      # full pytest suite
make run       # uvicorn with --reload
make clean     # remove __pycache__ dirs
```

---

## 5. Environment Variables

Copy `.env.example` to `.env` and fill in the values.

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | ✅ | Supabase project URL (`http://127.0.0.1:54321` locally) |
| `SUPABASE_KEY` | ✅ | **Service role key** — from `supabase status` or Supabase dashboard |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Same as above; used by logging utilities |
| `SUPABASE_JWT_SECRET` | ✅ | JWT signing secret — from `supabase status` or dashboard → Project Settings → API |
| `GROQ_API_KEY` | ✅ | Groq API key for the LLM layer (free tier) — [console.groq.com](https://console.groq.com) |
| `ANTHROPIC_API_KEY` | Optional | Claude API key — alternate LLM provider |
| `LLM_PROVIDER` | Optional | `groq` (default) or `anthropic` |
| `LLM_MODEL` | Optional | Default: `llama-3.3-70b-versatile` (Groq) |
| `DAILY_COST_CAP_USD` | Optional | Max LLM spend per day — default `10.0` |
| `ADMIN_USER_IDS` | Optional | Comma-separated Supabase UUIDs with admin access |
| `GITHUB_CLIENT_ID` | Optional | GitHub OAuth App client ID (for GitHub auth integration) |
| `GITHUB_CLIENT_SECRET` | Optional | GitHub OAuth App client secret |

> ⚠️ **Security:** The `.env` file is listed in `.gitignore`. Confirm it is NOT tracked before any public push. Never commit real credentials.

---

## 6. SMILE Methodology

**Full name:** Sustainable Methodology for Impact Lifecycle Enablement  
**Author:** Nicolas Waern, WINNIIO / LifeAtlas  
**Source file:** `data/smile-framework.json`  
**Principle:** *"Impact first, data last."*

Every goal on the platform is tracked through 6 ordered phases:

| # | Phase | Slug | Key Concept |
|---|-------|------|-------------|
| 1 | Reality Emulation | `reality-emulation` | Establish the reality canvas — the foundation |
| 2 | Concurrent Engineering | `concurrent-engineering` | Virtual MVT before physical commit |
| 3 | Collective Intelligence | `collective-intelligence` | Ontology factory, sensors, KPIs connected |
| 4 | Contextual Intelligence | `contextual-intelligence` | Real-time decisions, connected digital twin |
| 5 | Continuous Intelligence | `continuous-intelligence` | AI prognostics, black swan detection |
| 6 | Perpetual Wisdom | `perpetual-wisdom` | Share impact, circular strategies |

### Phase transition rules

- ✅ Forward **exactly one step** at a time
- ✅ Backward **any number of steps** (re-evaluation always valid)
- ❌ Skipping forward → `422 Unprocessable Entity`
- ❌ Same phase → `422 Unprocessable Entity`

### Scoring formula

```
score = (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)
```

- `priority` — user-set integer 1–10
- `phase_weight` — integer 1–6 corresponding to the 6 SMILE phases
- `urgency_flag` — 1 if True, 0 if False
- **Score range:** `[0.80, 7.00]`  — higher score means surfaced earlier in lists

**Worked examples:**

| Priority | Phase | Urgent | Score |
|----------|-------|--------|-------|
| 5 | reality-emulation | False | 2.80 |
| 5 | concurrent-engineering | False | 3.10 |
| 5 | collective-intelligence | False | 3.40 |
| 5 | perpetual-wisdom | False | 4.30 |
| 5 | perpetual-wisdom | True | 4.50 |
| 10 | perpetual-wisdom | True | **7.00** ← maximum |
| 1 | reality-emulation | False | **0.80** ← minimum |

---

## 7. Phase 1 — Strategy & Architecture

**Timeline:** Week 1  
**Team deliverables:**

- **Dev Kit Challenges (all):** Completed Levels 1–8 of the LPI Dev Kit; ran the LPI MCP server locally
- **API Contract Design (Jaivardhan + Adil):** Designed OpenAPI specifications for all 3 modules before implementation began
- **Proxy Data Strategy (Aditi):** Designed the intern profile proxy data plan to unblock development while waiting for real Deri data — `docs/aditi-proxy-data-plan.md`, `data/intern_profiles.json`
- **Agent Framework Decision (Daksh):** Researched LangChain vs. LangGraph; chose LangGraph for explicit state-machine control over multi-step reasoning
- **Repository Scaffold:** `pyproject.toml`, `Makefile`, `CONTRIBUTING.md`, `.pre-commit-config.yaml`, pre-commit hooks

---

## 8. Phase 2 — Goal / Intent Registry (Module 1)

**Timeline:** Week 2  
**Owner:** Adil Islam · **QA:** Daksh Garg

### What was built

The complete CRUD API for goals, backed by Supabase, with SMILE phase tracking and composite priority scoring.

**Key files:**
- `src/lpi/main.py` — FastAPI app scaffold, router registration, lifespan hook, health endpoint
- `src/lpi/config.py` — Pydantic Settings reading all env vars
- `src/lpi/routers/goals.py` — All 5 goal endpoints (Adil)
- `src/lpi/scoring.py` — Composite score formula (Jaivardhan)
- `src/lpi/smile.py` — Phase order, transition rules, descriptions (Yashika)
- `src/lpi/store.py` — Supabase CRUD layer (Jaivardhan)
- `src/lpi/utils/logging.py` — Dual-sync audit logging, all 3 log types (Adil + Yashika spec)
- `src/lpi/middleware/auth.py` — JWT verification, HS256 + ES256/RS256 support (Aryan + Jaivardhan)
- `tests/test_goal_crud.py` — CRUD + logging integration tests (Yashika)
- `tests/test_scoring.py` — 48 scoring assertions (Yashika)
- `tests/test_smile.py` — SMILE phase logic (Yashika)

### Goal endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/goals/` | Create a goal — returns 201 with full Goal object |
| `GET` | `/api/v1/goals/` | List caller's goals, sorted by composite SMILE score |
| `GET` | `/api/v1/goals/{goal_id}` | Fetch one goal by UUID |
| `PATCH` | `/api/v1/goals/{goal_id}` | Partial update; validates SMILE transitions |
| `DELETE` | `/api/v1/goals/{goal_id}` | Delete a goal |

### Goal schema

```json
{
  "title": "Wire the ontology layer",
  "description": "Connect all data sources to the knowledge graph",
  "priority": 7,
  "smile_phase": "concurrent-engineering",
  "urgency_flag": false
}
```

Server assigns: `id` (UUID), `user_id` (from JWT), `created_at`, `updated_at`, `score`.

### Dual-sync logging

Every write operation logs to **two places simultaneously** — in-memory (tests) and Supabase (production). A Supabase failure is caught and logged; it never breaks the API call.

```
POST /goals/
  └── log_user_activity(action="goal_created")  → user_activity_logs table

PATCH /goals/{id}  (phase change)
  └── log_transition(from_phase, to_phase)       → goal_phase_transitions table
  └── log_user_activity(action="goal_updated")  → user_activity_logs table

DELETE /goals/{id}
  └── log_user_activity(action="goal_deleted")  → user_activity_logs table
```

### PR history

| PR | Description | Status |
|----|-------------|--------|
| #17 | SMILE 5-phase → 6-phase correction across all files | ✅ Merged |
| #18 | Supabase persistence + dual-sync logging | ✅ Merged |

---

## 8. Phase 3 — Activity Signals (Module 2)

**Timeline:** Week 2–3  
**Owner:** Adil Islam · **QA:** Daksh Garg / Jaivardhan Singh

### What was built

The event ingestion and query layer — the input pipeline for the recommendation engine. Accepts structured events from any stream and exposes a filterable, paginated timeline.

**Key files:**
- `src/lpi/routers/signals.py` — Signal ingest + query endpoints (Adil)
- `src/lpi/routers/webhooks.py` — GitHub webhook receiver; routes push/PR/review events (Aditi)
- `src/lpi/routers/github_auth.py` — GitHub OAuth token exchange + repo tracking (Aryan + Jaivardhan)
- `src/lpi/middleware/rate_limit.py` — Rate limiting across all endpoints (Aryan + Jaivardhan)
- `supabase/migrations/20260611000000_create_activity_signals.sql` — activity_signals table + all indexes (Adil + Aditi + Aryan)
- `supabase/migrations/20260615000000_signals_rls_and_log_action.sql` — RLS policies + extended CHECK constraint for `signal_ingested` (Adil)
- `tests/test_activity_signals.py` — Signal endpoint test suite (Adil + Yashika)
- `tests/test_rate_limit.py` — Rate limit tests (Yashika)
- `tests/test_webhooks.py` — Webhook tests (Yashika)

### Signal endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/signals/` | Ingest a new activity signal — returns 201 |
| `GET` | `/api/v1/signals/` | List signals with filters + pagination |
| `GET` | `/api/v1/signals/{signal_id}` | Fetch a single signal by UUID |

### Signal schema

```json
{
  "stream": "lpi",
  "event_type": "pr_merged",
  "payload": { "repo": "lpi-platform", "pr_number": 18 },
  "source": "github_api"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `stream` | string | Business domain: `lpi`, `boardy`, `datapro`, `vsab`, `altiostar` |
| `event_type` | string | What happened: `pr_merged`, `match_created`, `deal_closed`, etc. |
| `payload` | object | Raw JSONB event data — structure varies by event_type |
| `source` | string | Ingestion source: `github_api`, `manual`, `simulated`, `api` (default) |

Server assigns: `id` (UUID), `user_id` (from JWT), `timestamp` (UTC).

### Server-side filtering & pagination

All filters translate directly to Postgres `WHERE` clauses — no client-side filtering.

```bash
# Filter by stream
GET /api/v1/signals/?stream=boardy

# Filter by stream + event type
GET /api/v1/signals/?stream=lpi&event_type=pr_merged

# Only verified real signals (excludes simulated data — used by Phase 4)
GET /api/v1/signals/?source=github_api

# Time window
GET /api/v1/signals/?start=2026-06-13T00:00:00Z&end=2026-06-20T00:00:00Z

# Pagination (default limit=50, max=200)
GET /api/v1/signals/?stream=boardy&limit=50&offset=50
```

### Live Boardy webhook integration

The platform is wired to receive real Boardy events via ngrok tunnel:

- **Tunnel:** `shimmer-overview-coat.ngrok-free.dev` → `localhost:8000`
- **Webhook endpoint:** `POST /api/v1/signals/`
- **Service account:** `boardy-integration@winniio.com`
- **Auth:** Supabase JWT in `Authorization: Bearer <token>` header
- **Confirmed:** 201 HTTP response + row verified in `activity_signals` table

---

## 9. Phase 4 — Recommendation Engine (Module 3)

**Timeline:** Week 3–4  
**Endpoint owner:** Adil Islam · **Algorithm owner:** Jaivardhan Singh · **Orchestration:** Daksh Garg

### What was built

A multi-layered recommendation engine that reads a user's real goals and activity signals and surfaces the top 3 SMILE-grounded next actions. Three fallback layers guarantee a response even when the LLM is unavailable.

**Key files:**
- `src/lpi/routers/recommendations.py` — HTTP endpoint layer (Adil)
- `src/lpi/recommendation_engine.py` — Deterministic Wave 2 engine + LangGraph integration (Jaivardhan + Adil)
- `src/lpi/langgraph_agent.py` — LangGraph 7-node agent pipeline (Jaivardhan + Daksh)
- `src/lpi/agent_pipeline.py` — Full orchestration pipeline with retry logic (Daksh)
- `tests/test_recommendations.py` — 25+ test cases across 4 test classes (Adil + Yashika)

### Recommendation endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/recommendations/{user_id}` | Top 3 SMILE-grounded recommendations, sorted by priority |
| `POST` | `/api/v1/recommendations/{user_id}/feedback` | Record user accept/dismiss on a recommendation |
| `POST` | `/api/v1/recommendations/{user_id}/run` | Run the full LangGraph agent pipeline (7-node, demo-safe) |

### How the engine works

```
generate_recommendations(user_id)
  │
  ├─ 1. Fetch: store.list_goals(user_id) + store.list_signals(user_id, limit=20)
  │
  ├─ 2. Cold start (no goals, no signals)
  │      └─ build_cold_start_recommendations() → 3 deterministic starter cards
  │
  ├─ 3. LangGraph LLM path (Wave 3)
  │      └─ run_agent(user_id, goals, signals) → Groq/Anthropic LLM
  │            ↓ validates source IDs against real data (no hallucinated IDs)
  │            ↓ derives phase + priority deterministically, not from LLM
  │
  └─ 4. Deterministic fallback (Wave 2, if LLM fails)
         ├─ _goal_recommendations() — one rec per goal, advancing to next SMILE phase
         ├─ _signal_recommendation() — one rec from recent activity signals
         └─ _diversify_by_phase() — one rec per SMILE phase, highest priority wins
```

### LangGraph pipeline nodes (POST /run)

```
fetch → classify → reason → validate → enrich → fallback → finalise
```

Always returns exactly 3 recommendations regardless of LLM availability, DB state, or user data (demo guarantee).

### Recommendation schema

```json
{
  "id": "uuid",
  "user_id": "intern-a-demo-profile",
  "action": "Advance 'Wire the ontology layer' to collective-intelligence",
  "reasoning": "This goal is at concurrent-engineering. Advancing forward is the next concrete step. Key question: ...",
  "smile_phase": "collective-intelligence",
  "priority": 4.30,
  "source_goals": ["<goal-uuid>"],
  "source_signals": [],
  "created_at": "2026-06-24T..."
}
```

> **Note on user_id:** `user_id` is a path parameter (not derived from the JWT) by design. This allows one authenticated demo session to view any seeded intern profile without re-logging in.

---

## 10. Phase 5 — QA, Integration & Polish

**Timeline:** Week 4  

### What was done

- **E2E Smoke Testing (Aditi + Adil):** Cross-module end-to-end verification — signal ingested via `POST /signals/` appears via `GET /signals/` and surfaces in `GET /recommendations/` for the same user
- **Live Boardy Integration (Adil):** End-to-end webhook validated with real Boardy events — 201 response confirmed, row verified in Supabase
- **UI/UX Polish (Jahanvi + Adil + Aditi + Jaivardhan):** Responsive design, styling cleanup, React component refinements
- **Documentation:** Final README, API docs, architecture diagrams

### Test results summary

| Test file | Coverage |
|-----------|----------|
| `test_goal_crud.py` | Goal CRUD, logging, ownership scoping |
| `test_scoring.py` | 48 scoring assertions covering all phase/priority/urgency combos |
| `test_smile.py` | 6-phase enum, transition rules, forward/backward validation |
| `test_activity_signals.py` | Ingest, query, all 4 filters, pagination, auth, logging contract |
| `test_recommendations.py` | Auth, schema, limit, cold-start, real data correctness, SMILE reasoning |
| `test_rate_limit.py` | Rate limiting across endpoints |
| `test_webhooks.py` | GitHub webhook event routing |
| `test_smoke.py` | Fast boot + platform invariants |

---

## 11. API Reference — Full Endpoint List

All endpoints require `Authorization: Bearer <supabase-jwt>` except `/health`.

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness probe — returns `{"status": "ok", "version": "0.1.0", "timestamp": "..."}` |

### Goals — `/api/v1/goals`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/goals/` | ✅ JWT | Create a goal |
| `GET` | `/api/v1/goals/` | ✅ JWT | List goals (sorted by SMILE score); optional `?smile_phase=` filter |
| `GET` | `/api/v1/goals/{goal_id}` | ✅ JWT | Fetch one goal |
| `PATCH` | `/api/v1/goals/{goal_id}` | ✅ JWT | Partial update (validates SMILE transitions) |
| `DELETE` | `/api/v1/goals/{goal_id}` | ✅ JWT | Delete a goal |

### Signals — `/api/v1/signals`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/signals/` | ✅ JWT | Ingest a signal |
| `GET` | `/api/v1/signals/` | ✅ JWT | List signals — `?stream=&event_type=&source=&start=&end=&limit=&offset=` |
| `GET` | `/api/v1/signals/{signal_id}` | ✅ JWT | Fetch one signal |

### Recommendations — `/api/v1/recommendations`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/recommendations/{user_id}` | ✅ JWT | Top `limit` recommendations (default 3, max 10) |
| `POST` | `/api/v1/recommendations/{user_id}/feedback` | ✅ JWT | Submit accept/dismiss feedback |
| `POST` | `/api/v1/recommendations/{user_id}/run` | ✅ JWT | Run full LangGraph pipeline — always returns 3 cards |
| `POST` | `/api/v1/recommendations/{user_id}/by-goal/{goal_id}` | ✅ JWT | Run pipeline scoped to one goal + its linked signals |

### Webhooks — `/api/v1/webhooks`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/webhooks/github` | None (shared secret) | GitHub webhook receiver — parses push/PR/review events, **persists to `activity_signals` table** with user_id resolved from repo ownership |

### GitHub Auth — `/api/v1/github`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/github/exchange-token` | None | Trade GitHub OAuth code for access token |
| `GET` | `/api/v1/github/user-repositories/{user_id}` | None | List user's GitHub repos |
| `POST` | `/api/v1/github/track-repo` | None | Register webhook on repo + store `repo_db["owner/repo"] = user_id` |
| `POST` | `/api/v1/github/disconnect-repo` | None | Remove webhook + clear repo mapping from `repo_db` |
| `POST` | `/api/v1/github/disconnect-account/{user_id}` | None | Remove stored token for a user |

> **How `repo_db` connects GitHub to Signals:** When a user registers a repo via `track-repo`, their `user_id` is stored against `"owner/repo"` in memory. When GitHub fires a webhook, the receiver looks up `repo_db["owner/repo"]` to resolve the `user_id` and save the signal under the correct user — replacing the old `default_user` stub.

---

## 12. Database Schema

All migrations live in `supabase/migrations/`. Run `supabase db push` to apply them all in order.

| Migration | Table(s) Created | Owner |
|-----------|-----------------|-------|
| `20260604000000_create_goals.sql` | `goals` (6-phase CHECK constraints) | Aditi + Aryan |
| `20260605000000_create_goal_phase_transitions.sql` | `goal_phase_transitions` | Team |
| `20260607000000_create_log_tables.sql` | `user_activity_logs`, `system_logs` | Adil |
| `20260608000000_create_request_logs.sql` | `request_logs` | Team |
| `20260611000000_create_activity_signals.sql` | `activity_signals` + all indexes | Adil + Aditi + Aryan |
| `20260612000000_goals_rls.sql` | RLS policies on `goals` | Aditi + Aryan |
| `20260613000000_logs_rls.sql` | RLS policies on log tables | Team |
| `20260615000000_signals_rls_and_log_action.sql` | RLS on `activity_signals` + CHECK fix | Adil |
| `20260621000000_create_recommendation_feedback.sql` | `recommendation_feedback` | Aryan |
| `20260625000000_activity_signals_goal_fk.sql` | `goal_id` FK on `activity_signals` + strict goal-scoped RLS | Jaivardhan |

### Table overview

| Table | Purpose |
|-------|---------|
| `goals` | All goal data with SMILE phase and composite score |
| `goal_phase_transitions` | Immutable audit trail of every phase change |
| `user_activity_logs` | CRUD event log (`goal_created`, `goal_updated`, `goal_deleted`, `signal_ingested`) |
| `system_logs` | Platform-level events (`info`, `warning`, `error`) |
| `activity_signals` | All ingested activity events from all streams |
| `recommendation_feedback` | User accept/dismiss decisions on recommendation cards |

### Useful SQL queries

```sql
-- Recent goal mutations
SELECT * FROM user_activity_logs ORDER BY logged_at DESC LIMIT 50;

-- SMILE phase transition history for a goal
SELECT * FROM goal_phase_transitions WHERE goal_id = '<uuid>' ORDER BY transitioned_at ASC;

-- All recent signals
SELECT * FROM activity_signals ORDER BY timestamp DESC LIMIT 50;

-- System errors
SELECT * FROM system_logs WHERE level = 'error' ORDER BY logged_at DESC;
```

> **Important:** The **Logs & Analytics** tab in Supabase Studio shows infrastructure logs only. Your custom tables are under **Table Editor**.

---

## 13. Testing

### Run tests

```bash
# Full suite
pytest tests/ -v --tb=short

# Individual modules
pytest tests/test_goal_crud.py -v          # Goal CRUD + logging
pytest tests/test_scoring.py -v            # 48 scoring assertions
pytest tests/test_smile.py -v              # SMILE phase logic
pytest tests/test_activity_signals.py -v   # Signal endpoints (all filters)
pytest tests/test_recommendations.py -v    # Recommendation engine + endpoint
pytest tests/test_rate_limit.py -v         # Rate limiting
pytest tests/test_webhooks.py -v           # GitHub webhook routing
pytest tests/test_smoke.py -v              # Boot + invariant checks
```

### Test architecture

Tests are **integration tests** — they hit real FastAPI endpoints and read/write the local Supabase instance. The `conftest.py` autouse fixture clears all tables before and after every test to prevent state bleed.

Requirements:
- `supabase start` must be running
- `.env` must point to local Supabase (`SUPABASE_URL=http://127.0.0.1:54321`)
- All migrations applied (`supabase db push`)

---

## 14. Project Structure

```
lpi-platform/
├── src/lpi/
│   ├── main.py                      # FastAPI app, router registration, health endpoint
│   ├── config.py                    # Pydantic Settings — reads all .env vars
│   ├── models.py                    # Pydantic schemas (Goal, Signal, Recommendation, SmilePhase)
│   ├── smile.py                     # Phase order, transition rules, descriptions
│   ├── scoring.py                   # Composite score formula: priority×0.5 + phase×0.3 + urgency×0.2
│   ├── store.py                     # All Supabase CRUD — single persistence entry point
│   ├── recommendation_engine.py     # Wave 2 deterministic engine + LangGraph integration
│   ├── langgraph_agent.py           # LangGraph multi-step reasoning agent
│   ├── agent_pipeline.py            # Full orchestration pipeline with retry + fallback
│   ├── middleware/
│   │   ├── auth.py                  # JWT verification (HS256 + ES256/RS256)
│   │   └── rate_limit.py            # Rate limiting middleware
│   ├── routers/
│   │   ├── goals.py                 # POST/GET/PATCH/DELETE /api/v1/goals
│   │   ├── signals.py               # POST/GET /api/v1/signals
│   │   ├── recommendations.py       # GET/POST /api/v1/recommendations
│   │   ├── webhooks.py              # POST /api/v1/webhooks/github
│   │   ├── github_auth.py           # GitHub OAuth + repo tracking
│   │   ├── me.py                    # Caller profile endpoint
│   │   └── users.py                 # User management
│   └── utils/
│       └── logging.py               # Dual-sync audit logger (3 log types)
│
├── tests/
│   ├── conftest.py                  # Fixtures, test client, DB clear helpers
│   ├── test_goal_crud.py            # Goal CRUD + logging integration
│   ├── test_scoring.py              # 48 scoring assertions
│   ├── test_smile.py                # SMILE phase logic
│   ├── test_activity_signals.py     # Signal endpoints + all filters
│   ├── test_recommendations.py      # Recommendation engine + endpoint contract
│   ├── test_rate_limit.py           # Rate limiting
│   ├── test_webhooks.py             # GitHub webhook routing
│   └── test_smoke.py                # Boot + platform invariants
│
├── supabase/
│   └── migrations/                  # 9 SQL migration files — apply with: supabase db push
│
├── data/
│   ├── smile-framework.json         # Canonical SMILE phase definitions
│   └── intern_profiles.json         # Proxy seed data (Aditi)
│
├── docs/
│   ├── aditi-proxy-data-plan.md     # Proxy data strategy
│   └── qa/                          # QA matrices and checklists
│
├── frontend-js/                     # React + Vite frontend (Jahanvi)
├── scripts/                         # Simulation and test data scripts (Aditi)
├── reports/                         # Daily progress reports
├── pyproject.toml                   # Python project config + all dependencies
├── Makefile                         # install / lint / test / run / clean
├── CONTRIBUTING.md                  # Onboarding and contribution protocol
├── .env.example                     # Template for .env
└── .pre-commit-config.yaml          # pre-commit hooks (ruff, detect-secrets)
```

---

## 15. Team & Ownership

| Name | Role | Primary Ownership |
|------|------|-------------------|
| **Jaivardhan Singh** | Phase 1 Lead + Scoring / Auth / DB | `store.py`, `scoring.py`, `langgraph_agent.py`, auth middleware |
| **Adil Islam** | Backend Dev + Team Lead (Phase 2→3) | `main.py`, `goals.py`, `signals.py`, `recommendations.py`, `utils/logging.py` |
| **Daksh Garg** | Phase 3 Lead + QA | `agent_pipeline.py`, QA matrices, `docs/qa/` |
| **Aditi Mehta** | Seed Data + Webhooks | `data/intern_profiles.json`, `routers/webhooks.py`, simulation scripts |
| **Aryan** | QA + Security | `middleware/rate_limit.py`, `github_auth.py`, DB schemas |
| **Yashika Verma** | SMILE Logging / Floater | `smile.py`, `test_smile.py`, `test_scoring.py`, logging spec |
| **Jahanvi Gupta** | Frontend | `frontend-js/` — Goals UI, Signals timeline, Recommendation cards |

**Supervisors:** Danial, Nicolas — Roll-up: Christalyn

---

## 16. Next Steps & Improvements

### Immediate (pre-handoff)

- [ ] Seed real Deri profile data from the LPI Backend staging API (`la-backend-staging.lifeatlas.online`) into the team's Supabase instance
- [X] Confirm all team branches merged into `staging` before Demo Day (June 27)
- [X] Record the 2-minute demo video of the running system

### Short-term improvements

- [ ] **Multi-tenancy hardening:** Add `user_id` ownership check to `GET /recommendations/{user_id}` before any production rollout (currently any authenticated caller can fetch any user's recommendations — intentional for demo, should be revisited)
- [ ] **LangGraph cost cap:** Wire `settings.daily_cost_cap_usd` into the LLM call path to prevent runaway API spend
- [ ] **GitHub webhook persistence:** Re-enable `store.insert_signal()` call in `routers/webhooks.py` (currently commented out for linting reasons)
- [ ] **Log transition logger:** Migrate `log_transition()` from `print()` to `logger.exception()` for Supabase failure reporting (same fix already applied to `log_user_activity()`)
- [ ] **Frontend completion:** Wire recommendation feedback (accept/dismiss) UI through to `POST /recommendations/{user_id}/feedback`

### Longer-term

- [ ] Replace ngrok tunnel with a stable webhook URL for production Boardy integration
- [ ] Add GitHub Actions CI pipeline (lint + test on every push to `Staging`)
- [ ] Add `total_count` to paginated list responses for frontend pagination UI
- [ ] Implement notification/re-engagement system for inactive goals (inactivity detection architecture already designed — see internship docs)
- [ ] Expand RLS policies to cover the `recommendation_feedback` table
- [ ] Add real-time signal streaming via Supabase Realtime for the frontend timeline

---
**Updated by TEAM LPI**

*LPI Platform — Winniio Amity 2026 Internship · Demo Day: June 26, 2026*
