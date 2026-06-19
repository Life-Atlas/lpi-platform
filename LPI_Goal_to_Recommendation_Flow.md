# LPI Platform: Goal → Activity Signal → Recommendation Integration Flow

**Source repo:** `lpi-platform` (Life-Atlas org) · **Document scope:** Module 1 (Goals) → Module 2 (Activity Signals) → Module 3 (Recommendations)
**Verified against:** `src/lpi/`, `supabase/migrations/`, `scripts/ingest_github_events.py`, `tests/`

This document traces a single piece of data — a user's goal — from the moment it's typed into a form to the moment a recommendation about it comes back out the other side. Every payload, endpoint, and schema snippet below is pulled directly from the current codebase, not idealized. Where the running code diverges from the diagram or from the intended design, that's called out explicitly rather than smoothed over — those gaps are exactly what doesn't show up in an architecture diagram.

---

## 1. System Overview

### 1.1 The three modules

| Module | Router | Owner | Status in current codebase |
|---|---|---|---|
| Goals (Module 1) | `routers/goals.py` | Adil Islam (Phase 2) | Fully implemented — CRUD + SMILE phase tracking + composite scoring |
| Activity Signals (Module 2) | `routers/signals.py` | Adil Islam (Phase 3) | Fully implemented — ingest + filter + paginate, Supabase-backed |
| Recommendations (Module 3) | `routers/recommendations.py` | Jaivardhan Singh (Phase 4) | **Stub** — route is wired and returns `[]`; LangGraph reasoning not yet implemented |

This matters for reading the rest of the document: Stages 1–6 below describe code that runs today. Stage 7 (the recommendation engine) describes the *designed* contract — the shape Module 2 was deliberately built to support — not yet a working implementation. That distinction is preserved throughout.

### 1.2 Repo layout (the parts this flow touches)

```
lpi-platform/
├── src/lpi/
│   ├── models.py            ← GoalCreate/Goal, SignalCreate/Signal, Recommendation
│   ├── smile.py              ← 6-phase SMILE state machine
│   ├── scoring.py            ← composite priority score
│   ├── store.py               ← all Supabase reads/writes go through here
│   ├── middleware/auth.py    ← Supabase JWT verification → user_id
│   └── routers/
│       ├── goals.py
│       ├── signals.py
│       └── recommendations.py
├── scripts/
│   └── ingest_github_events.py   ← pulls GitHub Events API, POSTs signals
└── supabase/migrations/
    ├── 20260604000000_create_goals.sql
    ├── 20260611000000_create_activity_signals.sql
    ├── 20260607000000_create_log_tables.sql
    └── 20260615000000_signals_rls_and_log_action.sql
```

There is **no `frontend/` directory in this repo**. The README states it directly: *"Frontend — Yet to be implemented by Jahanvi."* Section 4 of this document describes the integration contract the frontend needs to honor, derived from the API as it exists — not a description of code that was found, since none exists yet.

---

## 2. Data Contracts

These three Pydantic model pairs are the backbone of the whole flow. Each follows the same pattern: a `*Create` model defines what the caller sends, and the full model adds server-assigned fields on top.

### 2.1 Goal

```python
class GoalCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 5                          # 1 (low) – 10 (high)
    smile_phase: SmilePhase = SmilePhase.REALITY_EMULATION
    urgency_flag: bool = False                  # +0.20 to composite score when True

class Goal(GoalCreate):
    id: str             # server-assigned uuid4
    user_id: str         # from JWT `sub` claim
    created_at: datetime
    updated_at: datetime
```

### 2.2 Activity Signal

```python
class SignalCreate(BaseModel):
    stream: str          # business domain: 'lpi', 'boardy', 'datapro', 'vsab'...
    event_type: str       # 'pr_merged', 'commit_pushed', 'match_created'...
    payload: dict = {}    # event-specific JSON, structure varies by event_type
    source: str = "api"   # 'github_api' | 'manual' | 'simulated' | 'api'

class Signal(SignalCreate):
    id: str
    user_id: str
    timestamp: datetime
```

**Important structural detail:** there is no `goal_id` field on `Signal`. Signals are *not* foreign-keyed to a specific goal at the database level. The only link between a goal and the signals that justify "progress" toward it is `user_id` plus whatever semantic correlation a reasoning layer performs at read time (matching `stream`, `payload.repo`, or text similarity against goal titles). This is a deliberate flexibility/strictness trade-off, covered in Section 6.

### 2.3 Recommendation (target shape — not yet produced)

```python
class Recommendation(BaseModel):
    id: str
    user_id: str
    action: str
    reasoning: str
    smile_phase: SmilePhase
    priority: float
    source_goals: list[str] = []      # goal ids the recommendation references
    source_signals: list[str] = []     # signal ids used as evidence
    created_at: datetime
```

`source_goals` and `source_signals` are exactly how the goal↔signal link described above is meant to materialize — not as a database constraint, but as an output of the recommendation engine's reasoning step.

---

## 3. End-to-End Flow

This walks the diagram top to bottom, stage by stage, showing what enters, what the backend adds or transforms, and what exits.

### Stage 1 — User creates a goal

**Frontend → Backend:**
```
POST /api/v1/goals/
Authorization: Bearer <supabase-access-token>
Content-Type: application/json

{
  "title": "Ship Phase 3 activity signals",
  "description": "Wire signal ingestion end-to-end before demo day",
  "priority": 8,
  "smile_phase": "contextual-intelligence",
  "urgency_flag": true
}
```

**What `create_goal()` does (`routers/goals.py`):**
```python
new_goal = Goal(
    id=str(uuid.uuid4()),
    user_id=user_id,                 # injected by Depends(get_current_user)
    created_at=now, updated_at=now,
    **goal.model_dump(),              # spreads title/description/priority/smile_phase/urgency_flag
)
store.insert_goal(new_goal)
log_user_activity(user_id=..., action="goal_created", resource_id=new_goal.id, metadata={...})
```

| | Enters | Backend adds | Exits |
|---|---|---|---|
| Fields | `title, description, priority, smile_phase, urgency_flag` | `id` (uuid4), `user_id` (JWT `sub`), `created_at`, `updated_at` | Full `Goal` JSON, HTTP 201 |

The `**goal.model_dump()` spread is why `urgency_flag` "just works" without any special-case code in the router — because `Goal` inherits from `GoalCreate`, any field added to the request model automatically flows through.

### Stage 2 — Supabase `goals` table

```sql
CREATE TABLE goals (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL DEFAULT 'default_user',
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    priority     INTEGER NOT NULL DEFAULT 5,
    smile_phase  TEXT NOT NULL DEFAULT 'reality-emulation'
                     CHECK (smile_phase IN ('reality-emulation', 'concurrent-engineering',
                         'collective-intelligence', 'contextual-intelligence',
                         'continuous-intelligence', 'perpetual-wisdom')),
    urgency_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
RLS (`20260612000000_goals_rls.sql`) restricts row visibility to `auth.uid()::text = user_id`. This is defense-in-depth only — the FastAPI backend writes using the **service-role key**, which bypasses RLS by design (`store.py::_get_client()`). RLS only matters if something queries Supabase directly (e.g. a future frontend using `supabase-js` against the table instead of going through the API).

### Stage 3 — Work happens on the linked GitHub repository

This is the step with no API call at all — a developer merges a PR or pushes a commit to `Life-Atlas/lpi-platform` on GitHub. GitHub itself records this as a public event, retrievable from `GET https://api.github.com/repos/{owner}/{repo}/events` (the **GitHub Events API**, not a webhook — see Section 6 for why that distinction matters).

There is no automatic trigger here. Nothing in this repo subscribes to GitHub webhooks; ingestion is **pull-based and currently manual** (Stage 4 is a script someone runs, not a listener that fires on push).

### Stage 4 — GitHub ingestion script converts events to signals

`scripts/ingest_github_events.py` is invoked manually (`python scripts/ingest_github_events.py`) and does four things:

1. **Fetch:** `GET /repos/Life-Atlas/lpi-platform/events` (last ~30 public events; 60 req/hr unauthenticated, 5000 req/hr with `GITHUB_TOKEN`).
2. **Filter + map:** only event types representing *completed* work are kept.

```python
# PullRequestEvent → only if action == "closed" and pr["merged"] is True
{
  "stream": "lpi", "event_type": "pr_merged", "source": "github_api",
  "payload": {
      "repo": repo, "pr_number": pr["number"], "title": pr["title"],
      "author": actor, "merged_at": pr["merged_at"],
      "additions": pr["additions"], "deletions": pr["deletions"],
      "changed_files": pr["changed_files"],
      "body_snippet": pr["body"][:200],
  },
}
```
Other mapped types: `PushEvent → commit_pushed`, `PullRequestReviewEvent → pr_reviewed`, `IssuesEvent → issue_closed` (closed only), `CreateEvent → branch_created` (branches only). Everything else (`WatchEvent`, `ForkEvent`, etc.) is dropped.

3. **POST each mapped event:**
```python
def post_signal(signal_payload: dict) -> bool:
    response = requests.post(f"{LPI_API_BASE}/api/v1/signals/", json=signal_payload, timeout=5)
    return response.status_code in (200, 201)
```

| | Enters (per GitHub event) | Transform | Exits (per signal) |
|---|---|---|---|
| Source | Raw GitHub event JSON (`type`, `payload`, `actor`, `repo`) | Event-type-specific field extraction | `SignalCreate`-shaped dict, `source="github_api"` |

> **Gap worth flagging:** `post_signal()` calls `requests.post()` with no `Authorization` header. Since `signals.py::ingest_signal` requires `Depends(get_current_user)`, running this script today against an auth-protected deployment returns `401 Unauthorized` for every event. The script was written before JWT auth was wired onto the signals router and hasn't been updated to attach a service token — this needs a fix before it can run against any environment with auth enabled.

### Stage 5 — Signals router persists the event

```python
new_signal = Signal(
    id=str(uuid.uuid4()),
    user_id=user_id,
    timestamp=datetime.now(UTC),
    **signal.model_dump(),     # stream, event_type, payload, source
)
store.insert_signal(new_signal)

try:
    log_user_activity(user_id=user_id, action="signal_ingested", resource_id=new_signal.id, ...)
except Exception as exc:
    print(f"[ingest_signal] WARNING: logging failed for signal {new_signal.id}: {exc}")
```

| | Enters | Backend adds | Exits |
|---|---|---|---|
| Fields | `stream, event_type, payload, source` | `id`, `user_id`, `timestamp` | Full `Signal` JSON, HTTP 201 |

The `try/except` around logging exists because of a real schema bug: `user_activity_logs` originally had a `CHECK` constraint allowing only `'goal_created' | 'goal_updated' | 'goal_deleted'`. Calling `log_user_activity(action="signal_ingested")` against that constraint raises a Postgres exception. The signal still gets stored in `activity_signals` (the insert that matters), but the activity-log write silently fails and prints a warning instead of breaking the endpoint.

The fix already exists as a migration — `20260615000000_signals_rls_and_log_action.sql` — but only takes effect once it's actually applied:
```sql
ALTER TABLE user_activity_logs DROP CONSTRAINT IF EXISTS user_activity_logs_action_check;
ALTER TABLE user_activity_logs ADD CONSTRAINT user_activity_logs_action_check
    CHECK (action IN ('goal_created', 'goal_updated', 'goal_deleted', 'signal_ingested'));
```
Until `supabase db push` runs this migration against the target environment, every signal ingestion logs a warning to stdout instead of recording a clean audit trail entry — functionally harmless (signals still land in the table), but it means `user_activity_logs` undercounts signal activity until applied.

### Stage 6 — Supabase `activity_signals` table

```sql
CREATE TABLE activity_signals (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default_user',
    stream      TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    source      TEXT NOT NULL DEFAULT 'api',
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_as_user_id    ON activity_signals (user_id);
CREATE INDEX idx_as_stream     ON activity_signals (stream);
CREATE INDEX idx_as_event_type ON activity_signals (event_type);
CREATE INDEX idx_as_source     ON activity_signals (source);
CREATE INDEX idx_as_timestamp  ON activity_signals (timestamp DESC);
```
No `CHECK` constraint on `stream` or `event_type` — intentionally. New business streams (`vsab`, `altiostar`, etc.) or new event types can be added without a migration. `source` is also unconstrained at the DB layer despite having well-known values (`github_api`, `manual`, `simulated`, `api`) — validation, if any, is application-level.

### Stage 7 — Recommendation engine reads signals + goals *(designed, not yet built)*

The intended read pattern, per the code's own docstrings (`signals.py`, `scoring.py`):
```
GET /api/v1/signals/?source=github_api&limit=20   # exclude simulated/test signals
GET /api/v1/goals/                                  # already sorted by composite score
```
`store.list_signals(source="github_api", ...)` runs a server-side `WHERE source = 'github_api'` — the rec engine never has to filter simulated data in Python. The composite goal score (Section 2.1's `priority/phase/urgency` weighting, computed in `scoring.py`) means goals are already ranked by importance before the rec engine even looks at signals.

What's *not* built: the actual reasoning step that correlates a `pr_merged` signal with `payload.repo == "lpi-platform"` to a specific goal like "Ship Phase 3 activity signals," and produces `Recommendation.reasoning` text plus `source_goals`/`source_signals` references. `recommendations.py` today:
```python
@router.get("/{user_id}", response_model=list[Recommendation])
def get_recommendations(user_id: str, limit: int = Query(default=3, ge=1, le=10)) -> list[Recommendation]:
    return []   # Phase 4 placeholder — confirms the route is wired, nothing more
```

### Stage 8 — Recommendation surfaced to the frontend

```
GET /api/v1/recommendations/{user_id}?limit=3
→ [] today, eventually:
[
  {
    "action": "Open a PR closing the activity_signals CHECK constraint gap",
    "reasoning": "3 github_api signals show signal-ingestion work in progress; this is the blocking issue before demo day.",
    "smile_phase": "contextual-intelligence",
    "priority": 6.8,
    "source_goals": ["<goal-id>"],
    "source_signals": ["<signal-id-1>", "<signal-id-2>"]
  }
]
```

---

## Scenario 1 — Production Flow (full lifecycle, all components operational)

```
┌──────────────┐  POST /api/v1/goals/      ┌─────────────────┐
│  Frontend    │ ─────────────────────────▶│ FastAPI goals   │
│  goal form   │   GoalCreate JSON          │ router          │
└──────────────┘                            └────────┬────────┘
                                                       │ insert_goal()
                                                       ▼
                                             ┌─────────────────┐
                                             │ Supabase: goals │
                                             └────────┬────────┘
                                                       │ (informational —
                                                       │  no automated trigger)
                                                       ▼
┌──────────────┐  PR merged / push          ┌─────────────────┐
│ GitHub repo  │ ─────────────────────────▶│ GitHub Events    │
│              │                            │ API (pull-based) │
└──────────────┘                            └────────┬────────┘
                                                       │ python scripts/ingest_github_events.py
                                                       ▼
                                             ┌─────────────────┐
                                             │ ingestion script│
                                             │ maps event→signal│
                                             └────────┬────────┘
                                                       │ POST /api/v1/signals/
                                                       ▼
                                             ┌─────────────────┐
                                             │ signals router  │
                                             │ ingest_signal()  │
                                             └────────┬────────┘
                                                       │ insert_signal()
                                                       ▼
                                             ┌─────────────────────┐
                                             │ Supabase:           │
                                             │ activity_signals     │
                                             └────────┬─────────────┘
                                                       │ GET ?source=github_api
                                                       ▼
                                             ┌─────────────────────┐
                  GET /api/v1/goals/ ───────▶│ Recommendation       │
                  (goals context)            │ engine (Phase 4)     │
                                             └────────┬─────────────┘
                                                       │ GET /api/v1/recommendations/{user_id}
                                                       ▼
                                             ┌─────────────────┐
                                             │ Frontend: "next  │
                                             │ step" + phase    │
                                             └─────────────────┘
```

**Concrete trace:**

1. A user creates `Goal{title: "Ship Phase 3 activity signals", priority: 8, smile_phase: "contextual-intelligence", urgency_flag: true}`. Composite score = `8×0.5 + 4×0.3 + 1×0.2 = 5.40` — this goal now sorts near the top of `GET /api/v1/goals/`.
2. Over the next few days the team merges PR #18 ("Supabase dual-sync logging") into `lpi-platform`.
3. Someone runs `python scripts/ingest_github_events.py`. It fetches GitHub events, finds the merged PR, and POSTs:
   ```json
   {"stream": "lpi", "event_type": "pr_merged", "source": "github_api",
    "payload": {"repo": "lpi-platform", "pr_number": 18, "title": "Supabase dual-sync logging", "author": "Adilislam0"}}
   ```
4. The signal lands in `activity_signals` with a server-assigned `id`, `user_id`, and `timestamp`.
5. The (future) recommendation engine queries `GET /api/v1/signals/?source=github_api&limit=20` and `GET /api/v1/goals/`, semantically matches the `pr_merged` signal's `payload.title` against the goal's title, and emits a `Recommendation` referencing both ids.
6. The frontend calls `GET /api/v1/recommendations/{user_id}` and renders: *"Recent merge confirms progress on 'Ship Phase 3 activity signals' — consider advancing to continuous-intelligence."*

---

## Scenario 2 — Demo / MVP (3–5 day timeline)

The full chain above has one component that doesn't exist yet (Stage 7's reasoning step) and one known bug blocking a clean demo (Stage 5's `CHECK` constraint, plus Stage 4's missing auth header). A 3–5 day MVP should **prove Stages 1–6 work end-to-end with real data**, and present the recommendation step as a thin, honest placeholder rather than trying to ship the LangGraph reasoning layer under time pressure.

```
Day 1                Day 2                  Day 3                 Day 4-5
──────                ──────                  ──────                 ───────
Apply pending    →    Fix ingestion      →   Build minimal     →   Rehearse +
migration             script auth +           "Activity Feed"        buffer
(supabase db          run it against          UI: list raw
push) so signal_       a real merged PR        signals chrono-
ingested logging                               ologically, no
stops warning                                  reasoning layer
```

**Day 1 — Unblock the data path**
- Run `supabase db push` to apply `20260615000000_signals_rls_and_log_action.sql`. This silences the `CHECK` constraint warning and gives `user_activity_logs` a clean record of `signal_ingested` events.
- Verify with: `SELECT * FROM user_activity_logs WHERE action = 'signal_ingested' ORDER BY logged_at DESC;`

**Day 2 — Make the ingestion script actually work against auth**
- Add a service-role (or test-user) bearer token to `post_signal()`'s request headers. Without this, every POST from the script 401s the moment auth is enforced.
- Run the script against the real repo, confirm signals land: `GET /api/v1/signals/?source=github_api`.

**Day 3 — Build the smallest honest UI**
- Skip Module 3 entirely for the demo. Instead of recommendations, build a simple "Recent Activity" panel that calls `GET /api/v1/signals/?stream=lpi&source=github_api&limit=10` and renders each row as `"{author} merged PR #{pr_number}: {title}"` or `"{author} pushed {commit_count} commit(s) to {branch}"`. This is real, verifiable data — not a simulated recommendation — which is a stronger demo artifact than a stubbed `[]` recommendations call or fabricated reasoning text.
- Pair it with the existing `GET /api/v1/goals/` list (already fully functional, already sorted by composite score) so the demo shows *goals* and *evidence of work* side by side, even without the connecting reasoning layer.

**Day 4–5 — Buffer**
- Re-run the full test suite (`pytest tests/ -v`) against a freshly migrated local Supabase instance to catch any regression from the constraint fix.
- Rehearse the narrative: "here's the goal, here's the real GitHub activity feeding it, the recommendation layer that connects them is Phase 4 — in progress."

**What this scenario deliberately excludes:** LangGraph reasoning, automatic goal-signal correlation, and webhook-based (push) ingestion. All three are real Phase 4 work, not a 3–5 day scope.

---

## 4. Frontend Integration Contract

No frontend code exists in this repo yet — this section describes the contract a frontend implementation needs to satisfy, derived from the API surface above, not a description of existing UI code.

**Authentication.** Every endpoint except `/health` requires `Authorization: Bearer <supabase-access-token>`. The README's stated pattern is `supabase-js`'s `auth.signUp` / `signInWithPassword`, with the resulting `access_token` attached to every backend call. `middleware/auth.py` accepts both HS256 (shared-secret) and ES256/RS256 (JWKS-verified) tokens depending on the Supabase project's signing configuration — the frontend doesn't need to know which; it just forwards whatever Supabase's client SDK issues.

**Displaying goals.** `GET /api/v1/goals/` already returns results sorted by composite score (`sort_goals_by_score()` runs server-side) — the frontend should *not* re-sort client-side, or it'll fight the intended urgency/phase weighting. Optional filter: `?smile_phase=reality-emulation` to scope a view to one phase. There is currently no field on `Goal` linking it to a specific GitHub repo — "linked repositories" as a UI concept would need to be inferred from `payload.repo` on associated signals (matched by `stream`), since no structural link exists yet. Flag this for whoever owns the frontend goal-detail view.

**Displaying activity signals.** `GET /api/v1/signals/?stream=lpi&source=github_api&limit=20` for a real-only, paginated activity feed. `source=github_api` specifically excludes `simulated` and `manual` test entries — useful for a "verified activity" view distinct from a raw/debug view. Pagination is `limit`/`offset`, not cursor-based; page 2 is `?offset=50` with the same `limit`.

**Displaying recommendations.** `GET /api/v1/recommendations/{user_id}?limit=3` currently always returns `[]`. The frontend should build against the `Recommendation` schema (Section 2.3) now so that when Phase 4 ships, no contract changes are needed — but should render gracefully on an empty array rather than treating it as an error state.

**Triggering ingestion.** There is no API endpoint or button-triggered action that runs `ingest_github_events.py` — it's a manually-invoked Python script today, not something the frontend can call. If a "Sync GitHub Activity" button is wanted in the UI, that script would need to be wrapped behind a new authenticated endpoint first; right now it only runs from a developer's terminal.

---

## 5. Known Gaps & Architectural Decisions Summary

| Item | Type | Detail |
|---|---|---|
| `user_activity_logs` CHECK constraint | Bug (fix exists, not yet applied) | Migration `20260615000000` adds `'signal_ingested'`; needs `supabase db push` |
| `ingest_github_events.py` missing auth header | Bug | `post_signal()` sends no `Authorization` header; will 401 against an auth-enforced deployment |
| No `goal_id` FK on `Signal` | Deliberate design | Correlation is meant to happen via reasoning (Phase 4), not a rigid foreign key — keeps signal ingestion source-agnostic |
| Recommendation engine returns `[]` | Known incomplete (Phase 4 in progress) | Route is wired so dependent code doesn't 500; reasoning logic not yet written |
| GitHub ingestion is pull/manual, not webhook-driven | Deliberate (for now) | Simpler to build and demo; no public endpoint needed for GitHub to call back to |
| RLS on `goals`/`activity_signals` | Defense-in-depth | Backend uses service-role key and bypasses RLS by design; RLS only protects against direct (non-backend) Supabase access |
