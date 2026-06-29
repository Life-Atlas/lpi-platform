"""Pydantic data models for the LPI Platform.

CRITICAL CORRECTION — SMILE Methodology
═══════════════════════════════════════════════════════════════
The previous codebase used a hallucinated 5-phase SMILE acronym:
  SENSE → MODEL → INTERVENE → LEARN → EVOLVE
This does not exist in any LPI data source.

The CORRECT methodology from data/smile-framework.json is:
  S.M.I.L.E. = Sustainable Methodology for Impact Lifecycle Enablement
  Author: Nicolas Waern, WINNIIO / LifeAtlas

6 correct phases (IDs match the JSON `id` field exactly):
  1. reality-emulation
  2. concurrent-engineering
  3. collective-intelligence
  4. contextual-intelligence
  5. continuous-intelligence
  6. perpetual-wisdom

Principle: "Impact first, data last."
  Outcome → Action → Insight → Information → Data
═══════════════════════════════════════════════════════════════
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SmilePhase(StrEnum):
    """The 6 phases of S.M.I.L.E. (Sustainable Methodology for Impact Lifecycle Enablement).

    Source of truth: data/smile-framework.json in lpi-mcp-server.
    Author: Nicolas Waern, WINNIIO / LifeAtlas.

    StrEnum means the value IS the string:
        SmilePhase.REALITY_EMULATION == "reality-emulation"  →  True

    The enum attribute names use underscores (Python convention).
    The VALUES use hyphens, matching the JSON `id` field exactly.
    FastAPI serialises these to JSON as-is, so the API returns
    "reality-emulation", not "REALITY_EMULATION".

    Default phase for a new goal is REALITY_EMULATION (order 1) —
    every LPI journey begins by establishing the reality canvas.
    """

    REALITY_EMULATION = "reality-emulation"  # Phase 1
    CONCURRENT_ENGINEERING = "concurrent-engineering"  # Phase 2
    COLLECTIVE_INTELLIGENCE = "collective-intelligence"  # Phase 3
    CONTEXTUAL_INTELLIGENCE = "contextual-intelligence"  # Phase 4
    CONTINUOUS_INTELLIGENCE = "continuous-intelligence"  # Phase 5
    PERPETUAL_WISDOM = "perpetual-wisdom"  # Phase 6

class RecommendationFeedbackStatus(StrEnum):
    """Valid feedback actions for a recommendation."""

    ACCEPTED = "accepted"
    DISMISSED = "dismissed"

# ── Goal models ───────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    """Request body for POST /api/v1/goals/.

    urgency_flag is a Task C addition. It contributes 0.20 to the composite
    score when True, surfacing time-sensitive goals above same-priority peers.
    Default is False for backward compatibility with existing callers.
    """

    title: str
    description: str = ""
    priority: int = 5  # 1 (low) to 10 (high)
    smile_phase: SmilePhase = SmilePhase.REALITY_EMULATION
    urgency_flag: bool = False  # Task C: 0.20 score boost when True


class Goal(GoalCreate):
    """Full goal object — inherits all GoalCreate fields plus server-assigned ones.

    Because Goal inherits from GoalCreate, adding a field to GoalCreate
    (like urgency_flag) automatically makes it available here too.
    The **goal.model_dump() spread in create_goal() picks it up automatically.
    """

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class GoalUpdate(BaseModel):
    """Partial update schema for PATCH /api/v1/goals/{goal_id}.

    Every field is Optional (None = "caller didn't send this, leave unchanged").
    urgency_flag uses bool | None specifically so a PATCH that only changes
    the title doesn't silently reset urgency to False.
    """

    title: str | None = None
    description: str | None = None
    priority: int | None = None
    smile_phase: SmilePhase | None = None
    urgency_flag: bool | None = None  # Task C


class DeleteResponse(BaseModel):
    """Returned by DELETE /api/v1/goals/{goal_id}.
    Field is `id` (not `goal_id`) to match the OpenAPI contract.
    """

    deleted: bool = True
    id: str


# ── Signal models ─────────────────────────────────────────────────────────────


class SignalCreate(BaseModel):
    """Request body for POST /api/v1/signals/.

    FIELD DESIGN
    ─────────────
    stream     : Which business domain this signal belongs to.
                 Example values: 'lpi', 'boardy', 'datapro', 'vsab', 'altiostar'
                 This is the TOPIC of the signal, not how it arrived.

    event_type : What event happened within that stream.
                 Example values: 'pr_merged', 'commit_pushed', 'match_created'

    payload    : Raw event-specific data as a dict (stored as JSONB in Postgres).
                 Structure varies per event_type — the rec engine parses it.
                 Example: {"repo": "lpi-platform", "pr_number": 18, "title": "..."}

    source     : HOW this signal was ingested. Separate from `stream`.
                 ─────────────────────────────────────────────────────
                 WHY source IS HERE (Phase 3, not Phase 4):
                 The Phase 4 recommendation engine needs to weight signals
                 differently depending on their origin. A real GitHub commit
                 is stronger evidence of progress than a simulated test event.
                 Adding `source` now means Phase 4 has the column immediately
                 without a breaking schema migration.

                 Valid values (not enforced by DB CHECK — kept flexible):
                   'github_api'  — pulled from GitHub Events API (verified real)
                   'manual'      — sent by a human directly via the REST API
                   'simulated'   — generated by a test/seed script, not real work
                   'api'         — default: came via REST, no specific source tag

                 Default is 'api' so existing test payloads don't break —
                 callers that don't send source still work fine.

    Phase 4 note: Jaivardhan's recommendation engine can filter with
    GET /signals/?source=github_api to only read verified real signals.
    """

    stream: str
    event_type: str
    payload: dict = {}
    # `source` is optional here (defaults to 'api') so that:
    # 1. Existing test fixtures (sample_signal in conftest.py) need no changes.
    # 2. Callers who don't care about provenance don't have to send it.
    # 3. The GitHub ingestion script can explicitly set 'github_api'.
    source: str = "api"
    goal_id: str | None = None

class Signal(SignalCreate):
    """Full signal object — inherits SignalCreate fields + server-assigned ones.

    Because Signal inherits from SignalCreate, adding `source` to SignalCreate
    automatically makes it available here too. Same pattern as Goal/GoalCreate.

    Server-assigned fields (set in the router, not by the caller):
      id        : UUID generated by Python (uuid.uuid4())
      user_id   : Owner — 'default_user' in Phase 3, real JWT in Phase 4
      timestamp : When the signal was ingested (datetime.now(UTC))
    """

    id: str
    user_id: str
    timestamp: datetime


# ── Recommendation model ──────────────────────────────────────────────────────


class Recommendation(BaseModel):
    """smile_phase now references the correct 6-phase SmilePhase enum above."""

    id: str
    user_id: str
    action: str
    reasoning: str
    smile_phase: SmilePhase
    priority: float
    source_goals: list[str] = []
    source_signals: list[str] = []
    created_at: datetime

# ── Recommendation Feedback models ────────────────────────────────────────────


class RecommendationFeedbackCreate(BaseModel):
    """Request body for POST /api/v1/recommendations/.../feedback."""

    recommendation_id: str
    action: str
    smile_phase: SmilePhase
    status: RecommendationFeedbackStatus


class RecommendationFeedback(RecommendationFeedbackCreate):
    """Stored recommendation feedback."""

    id: str
    user_id: str
    created_at: datetime


# ── Team Metrics models ( Engineering Velocity & Inactivity) ──────
#
# Owner: Adil Islam. QA: Daksh Garg.
#
# These back GET /api/v1/metrics/team (routers/metrics.py). The shapes here
# intentionally mirror the spec sheet's nested structure 1:1 so the frontend
# can deserialise the JSON response directly into matching objects without
# any field-renaming glue code.


class TeamSummary(BaseModel):
    """Top-level aggregate counters — the "at a glance" numbers for the
    team dashboard's header row.

    avg_signals_per_active_user is total_signals / active_users (NOT
    total_signals / every roster member) — an inactive user contributing
    zero recent signals shouldn't drag down the "how productive is an
    engaged engineer right now" number. Rounded to 2 decimals; 0.0 when
    there are no active users (avoids a ZeroDivisionError on a quiet day).
    """

    total_signals: int
    active_users: int
    inactive_users: int
    avg_signals_per_active_user: float
    total_pr_merges: int
    total_commits: int


class UserVelocity(BaseModel):
    """Per-user breakdown of engineering activity.

    goal_advances counts only FORWARD SMILE phase transitions (see
    smile.PHASE_ORDER). A backward "re-evaluation" move is explicitly
    allowed by validate_phase_transition() and is real LPI usage, but it
    isn't "velocity" in the forward-progress sense this metric is named for.

    last_active is the max timestamp across that user's signals, goal
    updates, and phase transitions — so a user who only works through
    goals (no GitHub signals yet) still shows up as active.

    streams is the sorted set of distinct `stream` values seen in that
    user's signals (e.g. ["lpi", "boardy"]) — a quick "what are they
    touching" glance without opening the full signal list.
    """

    signal_count: int
    pr_merges: int
    commits: int
    goal_advances: int
    last_active: datetime | None
    streams: list[str]


class InactiveUserDetail(BaseModel):
    """One row of the inactive_users[] breakdown.

    days_inactive is computed as (now - last_seen).days — a whole-day
    count, not a precise duration, since "how many days has this person
    gone quiet" is the question a team lead actually asks.
    """

    user_id: str
    days_inactive: int
    last_seen: datetime | None


class GoalsSummary(BaseModel):
    """Portfolio-wide goal counts, independent of who owns each goal.

    by_phase is zero-filled for all 6 SmilePhase values up front (not just
    the phases that happen to have goals right now) so the frontend can
    render a consistent 6-bar chart without defensive `.get(key, 0)` calls.
    """

    total_goals: int
    by_phase: dict[str, int]


class TeamMetrics(BaseModel):
    """Full response body for GET /api/v1/metrics/team."""

    team_summary: TeamSummary
    per_user_velocity: dict[str, UserVelocity]
    inactive_users: list[InactiveUserDetail]
    goals_summary: GoalsSummary    
