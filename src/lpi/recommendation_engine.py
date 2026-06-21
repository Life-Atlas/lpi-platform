"""Module 3 — Recommendation Engine, Wave 2: real reasoning core.

Algorithm Owner : Jaivardhan Singh (Phase 4 — Wave 2)
This pass       : Adil Islam

WHY THIS FILE EXISTS
─────────────────────
routers/recommendations.py's own module docstring predicted this exact
path: "Jaivardhan's reasoning core (not yet built — will likely live in
a new lpi/recommendation_engine.py) owns mapping real goals + signals to
candidate actions with SMILE-grounded reasoning."

Wave 1 shipped a stable endpoint contract backed by
_build_mock_recommendations() — three hardcoded Recommendation objects,
IDENTICAL for every user_id, never touching the goals or activity_signals
tables. That unblocked Jahanvi's frontend, but it meant the "recommendation
engine" wasn't reading any of the data Module 1 (goals) and Module 3a
(activity_signals) actually store. This file fixes that: every
recommendation is now derived from the caller's real rows in Supabase.

WHAT CHANGED VS WAVE 1
────────────────────────
  - generate_recommendations(user_id) replaces the hardcoded specs list.
    It calls store.list_goals(user_id=...) and store.list_signals(user_id=...)
    and turns the ACTUAL rows into Recommendation objects.
  - Each goal produces one "advance to the next SMILE phase" recommendation.
    priority = scoring.score_goal(goal) — reusing the EXACT formula
    goals.py already uses, so a recommendation's priority badge means the
    same thing as a goal's priority badge. That's the whole reason
    Recommendation.priority lives on the [0.80, 7.00] scale in the first
    place (see the Wave 1 docstring this replaces).
  - The user's recent activity signals (not yet linked to any goal —
    Signal has no goal_id column, see models.SignalCreate) produce one
    "review your signals" recommendation, so a user who only logs
    activity and has no goals yet still gets a useful nudge.
  - source_goals / source_signals are populated with REAL ids instead of
    always being [].
  - Cold start (user has zero goals AND zero signals — true for a brand
    new account, and also true for the Wave-1 demo profiles in a freshly
    cleared test DB) falls back to build_cold_start_recommendations(),
    which is the old _build_mock_recommendations() content, relocated
    here. routers/recommendations.py re-exports the old private name so
    nothing that already imports it from there breaks.

WHAT THIS WAVE DELIBERATELY DOES NOT DO
──────────────────────────────────────────
  - No LLM call. config.py already has llm_provider / llm_model /
    daily_cost_cap_usd but nothing reads them yet — that's the LLM-bonus
    wave in the Phase 4 build plan, intentionally last, after this
    deterministic version is correct and tested.
  - No persistence / accept-dismiss storage. Still Yashika's deliverable —
    no Supabase table exists for it yet.
  - No goal<->signal FK correlation. There's no schema link saying
    "signal X helped advance goal Y" — that's a harder correlation
    problem left for a later wave. This pass treats "the user's recent
    signals" as one bucket per user, not scoped per goal.
"""

import uuid
from datetime import UTC, datetime

from lpi import store
from lpi.models import Goal, Recommendation, Signal, SmilePhase
from lpi.scoring import score_goal, sort_goals_by_score
from lpi.smile import PHASE_ORDER, get_phase_description, get_phase_key_question

# How many of the user's most recent signals to pull when building the
# signal-driven recommendation. Mirrors the "small limit" guidance already
# documented in store.list_signals() — the engine needs recent activity,
# not the user's entire history, to stay fast (TimingMiddleware's
# X-Process-Time header exists specifically to catch a slow path here).
_SIGNALS_TO_CONSIDER = 20

# Priority assigned to the signal-driven recommendation. Grounded in
# scoring.py's own worked example for a brand-new default goal —
# "p=5, reality-emulation, urgent=False -> 2.80" — instead of an arbitrary
# number, so a fresh signal-based nudge ranks roughly as important as
# creating a brand-new default-priority goal would.
_SIGNAL_RECOMMENDATION_PRIORITY = 2.80


def generate_recommendations(user_id: str) -> list[Recommendation]:
    """Build this user's candidate recommendations from real stored data.

    Returns an UNSORTED, UNTRUNCATED list — routers/recommendations.py
    owns sorting by priority descending and slicing to `limit`, exactly
    like it did for the Wave 1 mock data. Keeping that contract here is
    what lets every auth/shape/limit test in tests/test_recommendations.py
    keep passing unmodified regardless of where the data comes from.
    """
    goals = store.list_goals(user_id=user_id)
    signals = store.list_signals(user_id=user_id, limit=_SIGNALS_TO_CONSIDER)

    if not goals and not signals:
        # Cold start: brand-new account, or one of the Wave-1 demo
        # profiles against a freshly cleared test DB. Real reasoning
        # needs SOMETHING to reason about — fall back to the
        # deterministic starter set so the endpoint never returns an
        # unhelpful empty list on a user's first visit.
        return build_cold_start_recommendations(user_id)

    candidates: list[Recommendation] = []
    candidates.extend(_goal_recommendations(user_id, goals))

    signal_rec = _signal_recommendation(user_id, signals)
    if signal_rec is not None:
        candidates.append(signal_rec)

    return _diversify_by_phase(candidates)


def _phase_grounded_reasoning(phase: SmilePhase, lead_in: str) -> str:
    """Build reasoning text that ALWAYS literally names its own SMILE phase.

    WHY EXPLICIT, NOT IMPLICIT
    ────────────────────────────
    get_phase_description()'s prose doesn't always contain the phase's own
    slug as a literal word — e.g. collective-intelligence's description
    talks about sensors, KPIs, and ontologies; it never spells out the
    words "collective" or "intelligence". Naming the phase outright here,
    rather than hoping the description text happens to mention it, is
    what makes every recommendation reliably SMILE-grounded instead of
    grounded by coincidence (this is exactly the failure mode the
    test_recommendation_reasoning_names_its_smile_phase test guards
    against — it greps the reasoning string for the phase slug/words).
    """
    return (
        f"{lead_in} This action targets the {phase.value} phase. "
        f"Key question: {get_phase_key_question(phase)} "
        f"{get_phase_description(phase)[:120]}..."
    )


def _next_phase(current: SmilePhase) -> SmilePhase | None:
    """Return the phase one step forward from `current`, or None at the end.

    Mirrors the forward-step rule already enforced by
    smile.validate_phase_transition() (forward exactly one step is the
    only legal forward move) — just expressed as "what is that one step"
    instead of "is this transition legal."
    """
    idx = PHASE_ORDER.index(current)
    if idx + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[idx + 1]


def _goal_recommendations(user_id: str, goals: list[Goal]) -> list[Recommendation]:
    """One recommendation per goal: advance it to its next SMILE phase.

    Reuses sort_goals_by_score() purely so goal-derived candidates are
    built in the same priority order goals.py already shows the user —
    not required for correctness (the router re-sorts everything anyway)
    but keeps debug/log output in a familiar order.
    """
    now = datetime.now(UTC)
    recommendations: list[Recommendation] = []

    for goal in sort_goals_by_score(goals):
        target_phase = _next_phase(goal.smile_phase)
        priority = score_goal(goal)

        if target_phase is None:
            # Goal is already at Perpetual Wisdom — there is no "next"
            # phase to advance to. Recommend sustaining/sharing impact at
            # the CURRENT phase instead of crashing on a missing
            # PHASE_ORDER index (the bug a naive idx+1 lookup would hit).
            target_phase = goal.smile_phase
            action = f"Sustain and share the impact of '{goal.title}'"
            lead_in = (
                f"'{goal.title}' has already reached {goal.smile_phase.value} — "
                "the next concrete step is sustaining and sharing that impact, "
                "not advancing further."
            )
        else:
            action = f"Advance '{goal.title}' to {target_phase.value}"
            lead_in = (
                f"'{goal.title}' is currently at {goal.smile_phase.value}. "
                "Advancing it forward is the next concrete step."
            )

        recommendations.append(
            Recommendation(
                id=str(uuid.uuid4()),
                user_id=user_id,
                action=action,
                reasoning=_phase_grounded_reasoning(target_phase, lead_in),
                smile_phase=target_phase,
                priority=priority,
                source_goals=[goal.id],
                source_signals=[],
                created_at=now,
            )
        )

    return recommendations


def _signal_recommendation(user_id: str, signals: list[Signal]) -> Recommendation | None:
    """One recommendation summarising the user's recent activity signals.

    Activity signals are sensor/event data with no goal_id column (see
    models.SignalCreate) — there's no FK telling us which goal, if any, a
    given signal is "for". Rather than guess at that correlation, this
    wave treats all of the user's recent signals as one bucket and nudges
    them to fold that raw activity into a tracked goal. Smarter per-goal
    correlation is future work (see module docstring).

    Returns None when the user has no signals — callers must handle that
    (generate_recommendations() does, by skipping this candidate entirely).
    """
    if not signals:
        return None

    streams = sorted({s.stream for s in signals})

    lead_in = (
        f"You have {len(signals)} recent activity signal(s) from: "
        f"{', '.join(streams)}."
    )

    return Recommendation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=f"Review your {len(signals)} recent activity signal(s) and link them to a goal",
        reasoning=_phase_grounded_reasoning(SmilePhase.COLLECTIVE_INTELLIGENCE, lead_in),
        smile_phase=SmilePhase.COLLECTIVE_INTELLIGENCE,
        priority=_SIGNAL_RECOMMENDATION_PRIORITY,
        source_goals=[],
        source_signals=[s.id for s in signals],
        created_at=datetime.now(UTC),
    )


def _diversify_by_phase(candidates: list[Recommendation]) -> list[Recommendation]:
    """Keep at most one candidate per SMILE phase — the highest-priority one.

    WHY THIS EXISTS
    ──────────────────
    A user with three goals all sitting in reality-emulation would
    otherwise get three near-identical "advance to concurrent-engineering"
    cards. That tells the user nothing about where they stand across the
    SMILE lifecycle (the whole point per the Phase 4 gate criteria) and
    burns two of Jahanvi's three card slots on duplicate advice.

    Does NOT sort or truncate — routers/recommendations.py still owns
    that. This only drops same-phase duplicates so that sort+limit
    naturally yields a phase-diverse top N whenever enough diversity
    exists in the underlying goals/signals.
    """
    best_per_phase: dict[SmilePhase, Recommendation] = {}
    for rec in candidates:
        existing = best_per_phase.get(rec.smile_phase)
        if existing is None or rec.priority > existing.priority:
            best_per_phase[rec.smile_phase] = rec
    return list(best_per_phase.values())


def build_cold_start_recommendations(user_id: str) -> list[Recommendation]:
    """Deterministic fallback for a user with zero goals AND zero signals.

    This is the Wave 1 mock dataset's content, relocated here from
    routers/recommendations.py (_build_mock_recommendations). Two reasons
    it still exists post-Wave-2:

      1. Cold start: a brand-new account (or a freshly seeded demo profile
         / clean test DB) has nothing real to reason about yet. An empty
         list is a worse first-run experience than three generic starter
         actions.
      2. Daksh's orchestration pipeline documented a "guaranteed 3 cards"
         fallback route for when the multi-module reasoning pipeline
         doesn't finish in time — this function IS that safety net.
         routers/recommendations.py re-exports it under its old private
         name (_build_mock_recommendations) so existing callers don't break.

    Priority values intentionally land inside the existing goals scoring
    scale (0.80-7.00, see lpi/scoring.py) instead of an arbitrary 1-3, so
    the frontend can reuse the same "priority badge" component it already
    builds for goals.
    """
    now = datetime.now(UTC)

    # (action, smile_phase, priority) — priority hand-picked to land in
    # the same band a real goal at that phase/priority would score via
    # lpi/scoring.py's formula, so the fallback "looks like" real output.
    specs: list[tuple[str, SmilePhase, float]] = [
        (
            "Ingest this week's GitHub activity as a signal",
            SmilePhase.COLLECTIVE_INTELLIGENCE,
            5.60,
        ),
        (
            "Advance your active goal to Contextual Intelligence",
            SmilePhase.CONTEXTUAL_INTELLIGENCE,
            4.30,
        ),
        (
            "Re-validate your reality canvas before the next demo",
            SmilePhase.REALITY_EMULATION,
            2.90,
        ),
    ]

    lead_in = "Getting started — no goals or signals logged yet for this user."

    return [
        Recommendation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            action=action,
            reasoning=_phase_grounded_reasoning(phase, lead_in),
            smile_phase=phase,
            priority=priority,
            source_goals=[],
            source_signals=[],
            created_at=now,
        )
        for action, phase, priority in specs
    ]
