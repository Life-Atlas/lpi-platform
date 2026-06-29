"""Priority 1 — Engineering Velocity & Inactivity Metrics.

Owner : Adil Islam 
QA    : Daksh Garg

WHY THIS ENDPOINT EXISTS
──────────────────────────
Nicolas wants immediate value from existing data — zero 30-day warmup
required. This reads what's already in activity_signals/goals/
goal_phase_transitions today and turns it into a team-wide velocity +
inactivity view. No new tables, no new ingestion path.

NEW ENDPOINT
─────────────
  GET /api/v1/metrics/team

DATA SOURCES (all already exist)
───────────────────────────────────
  store.list_signals()                → signal_count, pr_merges, commits,
                                         streams[], last_active (signal side)
  store.list_goals()                  → goals_summary, last_active (goal side)
  store.list_goal_phase_transitions() → goal_advances, last_active (phase side)

ADMIN GATING
─────────────
Mirrors GET /api/v1/users/map exactly — this is a cross-user aggregate, so
only admins (settings.admin_user_ids) can read it. Same 403 message, for
consistency with the one other admin-gated endpoint in this codebase.

ROSTER DEFINITION — read this before changing anything below
─────────────────────────────────────────────────────────────────
"Team" here is NOT pulled from Supabase Auth's user list. Two reasons:
  1. Test JWTs (conftest.py) are self-signed UUIDs that never exist as
     real Supabase Auth users — calling client.auth.admin.list_users()
     would make active_users always 0 in tests.
  2. Semantically, the inactive_users[] contract requires a `last_seen` —
     a registered user who has NEVER done anything doesn't have a
     last_seen and isn't "inactive" in the velocity sense, they're just
     absent from the data entirely.
So: the roster is the union of every user_id seen in signals, goals, and
goal_phase_transitions. You can only be "inactive" if you were active once.

PR_MERGED / COMMIT_PUSHED COUNTING — a deliberate gap, not an oversight
──────────────────────────────────────────────────────────────────────────
scripts/ingest_github_events.py filters to ACTUALLY merged PRs before
tagging a signal "pr_merged" (see map_github_event() there: only emits it
when action=="closed" and pr.merged is True). That's the only data source
in this codebase that's provably "merged."

signals.py::sync_github_events (Aditi's dynamic per-goal sync) ingests RAW
GitHub event types ("PullRequestEvent", "PushEvent") with NO merged-status
filter — an opened-but-not-merged PR counts as a signal there. Counting
those toward total_pr_merges would inflate the number with non-merged PRs.
So this file only counts the canonical, pre-filtered event_type strings.
Raw GitHub event types still count toward signal_count/streams (they ARE
real signals) — just not toward pr_merges/commits. Flag for Aditi: align
sync_github_events' filtering/tagging with the static script if you want
its data to count here too.

KNOWN UPSTREAM BUG THAT AFFECTS WHAT THIS ENDPOINT WILL SHOW
─────────────────────────────────────────────────────────────────
scripts/ingest_github_events.py's post_signal() sends no Authorization
header (the P0 from the June 28 audit). With auth now enforced on
POST /api/v1/signals/, every run of that script 401s silently. Until that
bearer-token fix lands, total_pr_merges/total_commits from REAL GitHub
activity will read near-zero in the demo — not a bug in this endpoint,
a starvation of its primary upstream data source. Worth a one-line
mention in the demo so nobody reads it as this endpoint being broken.

PAGINATION TRADE-OFF
──────────────────────
store.list_signals() hard-caps at 200 rows/call. _fetch_all_signals()
below pages through it with offset increments. Fine at current team
scale; capped at _MAX_SIGNAL_PAGES as a safety valve with a system_logs
warning if hit, so nobody's silently missing data once this table grows
past ~10k rows. The real long-term fix is a SQL aggregate (a Postgres
RPC / count() query) instead of pulling every row into Python — out of
scope for a Saturday deadline, noted here for whoever picks it up next.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from lpi import store
from lpi.middleware.auth import UserContext, get_current_user_context
from lpi.models import (
    GoalsSummary,
    InactiveUserDetail,
    Signal,
    SmilePhase,
    TeamMetrics,
    TeamSummary,
    UserVelocity,
)
from lpi.smile import PHASE_ORDER
from lpi.utils.logging import log_system_event

router = APIRouter()

# ── Pagination constants (see module docstring) ───────────────────────────────
_SIGNALS_PAGE_SIZE = 200  # store.list_signals()'s hard max per call
_MAX_SIGNAL_PAGES = 50  # safety valve — 10,000 signals before we warn

# ── Event-type sets for pr_merges / commits (see module docstring) ────────────
# Deliberately narrow: only scripts/ingest_github_events.py emits these, and
# only AFTER filtering to genuinely merged PRs / non-empty pushes.
PR_MERGE_EVENT_TYPES = frozenset({"pr_merged"})
COMMIT_EVENT_TYPES = frozenset({"commit_pushed"})


@dataclass
class _UserAccumulator:
    """Mutable scratch space for one user while we walk signals/goals/
    transitions. Never leaves this module — gets converted into the public
    UserVelocity model only after all three passes finish.
    """

    signal_count: int = 0
    pr_merges: int = 0
    commits: int = 0
    goal_advances: int = 0
    last_active: datetime | None = None
    streams: set[str] = field(default_factory=set)

    def bump_last_active(self, ts: datetime | None) -> None:
        """Keep the latest of (current last_active, ts). No-op if ts is None
        (defensive — e.g. a malformed phase_transition row missing
        transitioned_at shouldn't crash the whole endpoint).
        """
        if ts is None:
            return
        if self.last_active is None or ts > self.last_active:
            self.last_active = ts


def _fetch_all_signals() -> list[Signal]:
    """Page through store.list_signals() until every signal (any user) is
    fetched. user_id=None → no user scoping, same fetch_all pattern goals.py
    and signals.py already use for admin views.

    See module docstring for the pagination trade-off this represents.
    """
    all_signals: list[Signal] = []
    offset = 0

    for _ in range(_MAX_SIGNAL_PAGES):
        page = store.list_signals(user_id=None, limit=_SIGNALS_PAGE_SIZE, offset=offset)
        all_signals.extend(page)
        if len(page) < _SIGNALS_PAGE_SIZE:
            break  # last page was partial — we've got everything
        offset += _SIGNALS_PAGE_SIZE
    else:
        # for/else: only runs if we never hit the `break` above, i.e. every
        # single page came back full, all the way up to the cap. That means
        # there's likely MORE data we didn't fetch — surface it loudly
        # rather than silently undercounting totals.
        log_system_event(
            event="metrics_team_signal_pagination_capped",
            level="warning",
            detail=(
                f"Hit the {_MAX_SIGNAL_PAGES}-page cap "
                f"({_MAX_SIGNAL_PAGES * _SIGNALS_PAGE_SIZE} rows) while fetching "
                "all signals for /metrics/team. Totals may be undercounted — "
                "replace this with a real SQL aggregate instead of paging "
                "through every row in Python."
            ),
        )

    return all_signals


def _is_forward_transition(from_phase: str | None, to_phase: str | None) -> bool:
    """True only if to_phase is strictly later than from_phase in
    smile.PHASE_ORDER. Mirrors the forward-step check inside
    smile.validate_phase_transition(), but here we don't care whether it
    was a *valid* (exactly-one-step) forward move — any forward movement
    counts as an "advance". Invalid/unrecognised phase strings return
    False rather than raising, since this is a read-only aggregation pass
    over an audit log, not request validation.
    """
    if from_phase is None or to_phase is None:
        return False
    try:
        from_idx = PHASE_ORDER.index(SmilePhase(from_phase))
        to_idx = PHASE_ORDER.index(SmilePhase(to_phase))
    except ValueError:
        return False
    return to_idx > from_idx


@router.get(
    "/team",
    response_model=TeamMetrics,
    summary="Team-wide engineering velocity and inactivity metrics",
    description=(
        "Admin-only. Aggregates activity_signals, goals, and "
        "goal_phase_transitions into a team velocity dashboard: total/"
        "per-user signal counts, PR merges, commits, goal advances, and "
        "which team members have gone quiet."
    ),
)
def _parse_utc_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO8601 timestamp string from a raw Supabase row into a
    timezone-AWARE datetime — never naive.

    WHY THIS EXISTS (PR review — Daksh)
    ─────────────────────────────────────
    utils/logging.py::log_transition() always writes transitioned_at via
    datetime.now(UTC).isoformat(), and the column is TIMESTAMPTZ (see
    supabase/migrations/20260605000000_create_goal_phase_transitions.sql) —
    PostgREST always serialises timestamptz columns back out with an
    explicit UTC offset, so in practice this string is never naive today.

    Still, Pass 3 below is the one place in this file doing our own
    fromisoformat() on a raw string (signals/goals arrive as already-
    validated Signal/Goal Pydantic objects — this table has no model layer
    in between). Relying on an unenforced assumption about a third-party
    library's serialisation format is fragile: if it were ever violated,
    mixing a naive datetime into the same `>` comparison as the timezone-
    aware signal/goal timestamps in bump_last_active() raises
    `TypeError: can't compare offset-naive and offset-aware datetimes` and
    500s this endpoint. This makes the "treat as UTC" assumption explicit
    and crash-proof instead of implicit and silent.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # No offset in the string — the only convention this codebase
        # writes timestamps in is UTC (datetime.now(UTC) everywhere), so
        # that's the safe assumption rather than guessing local time.
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
def get_team_metrics(
    inactive_threshold_days: int = Query(
        default=3,
        ge=0,
        le=90,
        description=(
            "A user counts as inactive once this many days have passed "
            "since their last signal/goal update/phase transition. "
            "Default 3 — matches the team's daily-log cadence; 3 quiet "
            "days is a meaningful gap on a sprint this fast. Tune per "
            "demo/sprint as needed."
        ),
    ),
    user_context: UserContext = Depends(get_current_user_context),
) -> TeamMetrics:
    """Build the full team metrics snapshot. See module docstring for the
    roster definition, pr_merges/commits counting rule, and pagination
    trade-off — those decisions live there, not duplicated here.
    """
    if not user_context.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    # ── Pull every row from all three sources, admin-wide (user_id=None) ──
    signals = _fetch_all_signals()
    goals = store.list_goals(user_id=None)
    transitions = store.list_goal_phase_transitions(user_id=None)

    now = datetime.now(UTC)

    # defaultdict(_UserAccumulator): each missing key gets a FRESH
    # _UserAccumulator() (fresh set/None, not a shared mutable default —
    # the factory is called once per missing key, not once total).
    user_stats: dict[str, _UserAccumulator] = defaultdict(_UserAccumulator)

    # ── Pass 1: signals → signal_count, pr_merges, commits, streams ───────
    for sig in signals:
        stats = user_stats[sig.user_id]
        stats.signal_count += 1
        stats.streams.add(sig.stream)
        if sig.event_type in PR_MERGE_EVENT_TYPES:
            stats.pr_merges += 1
        if sig.event_type in COMMIT_EVENT_TYPES:
            stats.commits += 1
        stats.bump_last_active(sig.timestamp)

    # ── Pass 2: goals → roster membership + last_active (no signal yet) ───
    for g in goals:
        stats = user_stats[g.user_id]  # registers the key even at 0 signals
        stats.bump_last_active(g.updated_at)

    # ── Pass 3: phase transitions → goal_advances (forward-only) ──────────
    for t in transitions:
        uid = t.get("user_id")
        if not uid:
            continue  # defensive — shouldn't happen, log_transition always sets it
        stats = user_stats[uid]
        if _is_forward_transition(t.get("from_phase"), t.get("to_phase")):
            stats.goal_advances += 1
            stats.bump_last_active(_parse_utc_timestamp(t.get("transitioned_at")))


    # ── Classify active/inactive + build the public response models ──────
    per_user_velocity: dict[str, UserVelocity] = {}
    inactive_details: list[InactiveUserDetail] = []
    active_count = 0

    for uid, stats in user_stats.items():
        last_active = stats.last_active
        # days_inactive=-1 is an "unknown" sentinel (last_active somehow
        # missing) — shouldn't be reachable given the roster construction
        # above, but kept defensive rather than crashing on bad data.
        days_inactive = (now - last_active).days if last_active is not None else -1
        is_active = last_active is not None and days_inactive < inactive_threshold_days

        per_user_velocity[uid] = UserVelocity(
            signal_count=stats.signal_count,
            pr_merges=stats.pr_merges,
            commits=stats.commits,
            goal_advances=stats.goal_advances,
            last_active=last_active,
            streams=sorted(stats.streams),
        )

        if is_active:
            active_count += 1
        else:
            inactive_details.append(
                InactiveUserDetail(
                    user_id=uid,
                    days_inactive=days_inactive,
                    last_seen=last_active,
                )
            )

    # Most-inactive-first — the dashboard should lead with who to nudge.
    inactive_details.sort(key=lambda d: d.days_inactive, reverse=True)

    total_signals = len(signals)
    total_pr_merges = sum(s.pr_merges for s in user_stats.values())
    total_commits = sum(s.commits for s in user_stats.values())
    avg_signals_per_active_user = (
        round(total_signals / active_count, 2) if active_count else 0.0
    )

    team_summary = TeamSummary(
        total_signals=total_signals,
        active_users=active_count,
        inactive_users=len(inactive_details),
        avg_signals_per_active_user=avg_signals_per_active_user,
        total_pr_merges=total_pr_merges,
        total_commits=total_commits,
    )

    # ── goals_summary: zero-fill all 6 phases, then count real goals ──────
    by_phase: dict[str, int] = {phase.value: 0 for phase in SmilePhase}
    for g in goals:
        by_phase[g.smile_phase.value] += 1

    goals_summary = GoalsSummary(total_goals=len(goals), by_phase=by_phase)

    return TeamMetrics(
        team_summary=team_summary,
        per_user_velocity=per_user_velocity,
        inactive_users=inactive_details,
        goals_summary=goals_summary,
    )
