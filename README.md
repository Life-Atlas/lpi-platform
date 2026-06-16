# LPI Platform — Life Programmable Interface

Goal registry, activity signals, and recommendation engine — powered by the
**SMILE methodology** (Sustainable Methodology for Impact Lifecycle Enablement).

---

## Quick Start

```bash
pip install -e ".[dev]"
supabase start                  # start local Supabase (Docker required)
supabase db push                # apply all migrations
make test                       # full test suite — must be green before any PR
make run                        # FastAPI on http://localhost:8000
# Swagger UI → http://localhost:8000/docs
```

After `supabase start`, copy the printed values into `.env`:
- `SUPABASE_KEY` ← **service_role key** (the backend bypasses RLS by design)
- `SUPABASE_JWT_SECRET` ← **JWT secret**

### Frontend

Yet to be implemented by Jahanvi

---

## Architecture
Module 1: Goals           →  CRUD, SMILE phase tracking, composite scoring
Module 2: Signals         →  Activity events from Boardy, DataPro+, VSAB, etc.
Module 3: Recommendations →  Goals + Signals → Top 3 SMILE-grounded actions

### Layer map
src/lpi/
├── models.py               Pydantic schemas — SmilePhase enum (source of truth)
├── smile.py                Phase order, transition rules, descriptions, key questions
├── scoring.py              Composite score: priority×0.5 + phase×0.3 + urgency×0.2
├── store.py                Supabase CRUD — all persistence goes through here
├── config.py               Settings from .env (supabase_url, supabase_key)
├── main.py                 FastAPI app, lifespan hook, router registration
├── middleware/             CORS + TimingMiddleware (X-Process-Time, X-Request-ID)
├── routers/
│   ├── goals.py            POST / GET / PATCH / DELETE /api/v1/goals
│   ├── signals.py          Signal ingestion endpoints
│   └── recommendations.py  Recommendation engine stub
└── utils/
└── logging.py          Dual-sync logging — in-memory (tests) + Supabase (production)

---

## Authentication

Email/password only (Supabase Auth — no OAuth providers).

- The frontend (`frontend/`) signs users up / in via `supabase-js`
  (`supabase.auth.signUp` / `signInWithPassword`).
- Every request to `/api/v1/goals/*` must include
  `Authorization: Bearer <supabase-access-token>`.
- `middleware/auth.py::get_current_user` verifies the JWT against
  `SUPABASE_JWT_SECRET` and returns the user's Supabase UUID — this becomes
  `Goal.user_id` on create, and every read/update/delete is scoped to it
  (cross-user access returns `404`).
- `supabase/migrations/20260612000000_goals_rls.sql` enables Postgres RLS on
  `goals` as defense-in-depth for any direct (non-backend) access.

---

## SMILE Methodology — 6 Phases

Source: `data/smile-framework.json` — Author: Nicolas Waern, WINNIIO / LifeAtlas  
Full name: **Sustainable Methodology for Impact Lifecycle Enablement**  
Principle: *"Impact first, data last."*

| # | Phase | Slug | Key concept |
|---|---|---|---|
| 1 | Reality Emulation | `reality-emulation` | Establish the reality canvas — the foundation |
| 2 | Concurrent Engineering | `concurrent-engineering` | Virtual MVT before physical commit |
| 3 | Collective Intelligence | `collective-intelligence` | Ontology factory, sensors, KPIs connected |
| 4 | Contextual Intelligence | `contextual-intelligence` | Real-time decisions, connected twin |
| 5 | Continuous Intelligence | `continuous-intelligence` | AI prognostics, black swan detection |
| 6 | Perpetual Wisdom | `perpetual-wisdom` | Share impact, circular strategies |

**Transition rules:**
- ✅ Forward exactly one step
- ✅ Backward any number of steps (re-evaluation always valid)
- ❌ Skipping forward → `422 Unprocessable Entity`
- ❌ Same phase → `422 Unprocessable Entity`

**Scoring formula:**
score = (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)
Score range: `[0.80, 7.00]`. Higher score = surfaced earlier in `GET /api/v1/goals/`.

---

## Supabase Schema

| Table | Purpose | Written by |
|---|---|---|
| `goals` | All goal data | `store.py` |
| `goal_phase_transitions` | SMILE phase change audit trail | `utils/logging.py` → `log_transition()` |
| `user_activity_logs` | Create / update / delete events | `utils/logging.py` → `log_user_activity()` |
| `system_logs` | Platform-level events | `utils/logging.py` → `log_system_event()` |

> **Important:** The **Logs & Analytics** tab in Supabase Studio shows infrastructure
> logs (PostgREST, Edge Functions, Auth). Your custom tables are in **Table Editor** only.

### View your logs

```sql
-- Recent goal mutations
SELECT * FROM user_activity_logs ORDER BY logged_at DESC LIMIT 50;

-- SMILE phase transition history for a specific goal
SELECT * FROM goal_phase_transitions WHERE goal_id = '<uuid>' ORDER BY transitioned_at ASC;

-- All transitions
SELECT * FROM goal_phase_transitions ORDER BY transitioned_at DESC LIMIT 50;

-- System events
SELECT * FROM system_logs WHERE level = 'error' ORDER BY logged_at DESC;
```

### Migrations — apply in order
supabase/migrations/
├── 20260604000000_create_goals.sql              Goals table (6-phase CHECKs)
├── 20260605000000_create_goal_phase_transitions.sql  Transitions table (6-phase CHECKs)
└── 20260607000000_create_log_tables.sql         user_activity_logs + system_logs

Run: `supabase db push`

---

## Dual-Sync Logging Pattern

Every log function writes to two destinations simultaneously:
API call
│
├── log_user_activity()   → user_activity_logs[]  (memory)
│                         → user_activity_logs    (Supabase)
│
├── log_transition()      → phase_transition_logs[] (memory)   ← phase change only
│                         → goal_phase_transitions  (Supabase)
│
└── log_system_event()    → system_logs[]          (memory)
→ system_logs             (Supabase)

Memory lists are cleared between tests by `conftest.py` autouse fixture.  
If Supabase fails, the error is caught, printed to stdout, and the request continues normally.

---

## PR History

| PR | Title | Status | Owner |
|---|---|---|---|
| #17 | SMILE methodology migration — 5-phase → 6-phase correction | ✅ Merged | Team |
| #18 | Supabase persistence + dual-sync logging — Phase 2 | PR up for staging | Adil Islam |

### PR #17 — SMILE Migration (merged)
- Corrected `SmilePhase` enum from hallucinated 5-phase to correct 6-phase framework
- Updated `smile.py`, `scoring.py`, all test files, QA matrix, proxy data plan
- 11 files changed · test count 46 → 48 · max score 6.70 → 7.00

### PR #18 — Supabase Persistence + Dual-Sync Logging (merged)
- `store.py` — Supabase-backed CRUD replacing in-memory dict
- `utils/logging.py` — 3 dual-sync log types (transition, user activity, system)
- `routers/goals.py` — activity logging wired on create, update, delete
- `migrations/20260604` + `20260605` — corrected 6-phase CHECK constraints
- `migrations/20260607` — new `user_activity_logs` + `system_logs` tables
- `README.md` — schema docs, PR history, logging architecture diagram

---

## Activity Signals 


> **Phase 3** · Owner: Adil Islam · QA: Daksh Garg

The Activity Signals module is the input layer for the LPI recommendation engine. It ingests structured events from any stream (LPI, Boardy, DataPro+, VSAB, etc.) and exposes a queryable, paginated timeline scoped to the authenticated user.
- `src/lpi/routers/signals.py` — added auth via `Depends(get_current_user)` to POST/GET signal endpoints, matching the goals auth pattern and ensuring requests are scoped to the authenticated user.
- `src/lpi/store.py` — updated `list_signals()` to accept `user_id` and apply `.eq("user_id", user_id)`, preventing cross-user visibility of signals.
- `tests/test_activity_signals.py` — expanded `test_list_signals()` to assert every returned signal belongs to the authenticated test user.
- `supabase/migrations/20260615000000_signals_rls_and_log_action.sql` — new migration adding RLS policies for `activity_signals` and extending `user_activity_logs` CHECK constraint to allow `'signal_ingested'`.
- Note: The backend still uses service_role for Supabase writes; RLS is defense-in-depth for any direct client-side access.

---
### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/signals/` | Ingest a new activity signal |
| `GET` | `/api/v1/signals/` | List signals with optional filters + pagination |
| `GET` | `/api/v1/signals/{signal_id}` | Fetch a single signal by UUID |

### Signal Schema

```json
{
  "stream": "lpi",
  "event_type": "pr_merged",
  "payload": { "repo": "lpi-platform", "pr_number": 18 },
  "source": "github_api"
}
```

**Field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `stream` | `string` | Business domain the signal belongs to (`lpi`, `boardy`, `datapro`, `vsab`, `altiostar`) |
| `event_type` | `string` | What happened within that stream (`pr_merged`, `match_created`, `deal_closed`, etc.) |
| `payload` | `object` | Raw event data (JSONB). Structure varies per `event_type`. |
| `source` | `string` | How the signal was ingested. Values: `github_api`, `manual`, `simulated`, `api` (default). Used by Phase 4 rec engine to weight signals. |

Server assigns: `id` (UUID), `user_id`, `timestamp` (UTC).

### Filtering & Pagination

All filters are **server-side** — only matching rows are fetched from Supabase.

```bash
# All signals for the authenticated user
GET /api/v1/signals/

# Filter by stream
GET /api/v1/signals/?stream=boardy

# Filter by stream + event type
GET /api/v1/signals/?stream=lpi&event_type=pr_merged

# Only real GitHub signals (exclude simulated — used by Phase 4 rec engine)
GET /api/v1/signals/?source=github_api

# Pagination: page 2 of boardy signals
GET /api/v1/signals/?stream=boardy&limit=50&offset=50
```

`limit` defaults to 50, maximum 200. `offset` defaults to 0.

### Database

Table: `activity_signals`  
Migration: `supabase/migrations/..._create_activity_signals.sql`  
Indexes: `idx_as_stream`, `idx_as_event_type`, `idx_as_source`, `idx_as_timestamp DESC`


### Notes

- Auth required on all endpoints (`Authorization: Bearer <jwt>`).
- In Phase 3, `user_id` resolves to `default_user`. Real JWT scoping activates with the auth PR.
- `source` field is the bridge to Phase 4: the recommendation engine calls `?source=github_api` to read only verified real signals, ignoring seeded/simulated test data.
- Logging to `user_activity_logs` (`action: signal_ingested`) is guarded by `try/except` — a missing CHECK constraint entry never breaks ingestion.
```
```

---

## Testing

```bash
# Full suite
pytest tests/ -v --tb=short

# Individual modules
pytest tests/test_goal_crud.py -v     # CRUD + logging integration
pytest tests/test_smile.py -v         # SMILE phase logic (6-phase)
pytest tests/test_scoring.py -v       # composite score assertions (48 tests)
pytest tests/test_smoke.py -v         # fast boot + invariant checks
pytest tests/test_activity_signals.py -v       # activity signa endpoints

```


---

## Team

| Name | Role | Owns |
|---|---|---|
| **Jaivardhan** | Lead, scoring / auth / DB | `test_recommendations.py`, scoring domain |
| Adil | API endpoints, Supabase logging | `goals.py`, `store.py`, `utils/logging.py` |
| Daksh | QA | `docs/qa/goal_endpoints_qa_matrix.md` |
| Aditi | Seed / proxy data | `docs/aditi-proxy-data-plan.md` |
| Jahanvi | Frontend | UI components |
| Yashika | Logging spec / design | `utils/logging.py` spec, `test_smile.py` |
| Aryan | Support | — |

**Supervisors:** Danial, Nicolas — Roll-up: Christalyn