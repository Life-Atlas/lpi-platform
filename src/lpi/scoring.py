"""Goal priority scoring — SMILE-weighted composite algorithm.

Owner : Jaivardhan Singh  (Phase 2 — Task C)
QA    : Ankit Kumar Singh

CORRECTION NOTE
═══════════════════════════════════════════════════════════════
The previous version used hallucinated phases (sense=1, model=2,
intervene=3, learn=4, evolve=5). This version uses the correct
6-phase framework from data/smile-framework.json.

Phase weight changes:
  OLD (5 phases, 1–5): sense=1, model=2, ..., evolve=5
  NEW (6 phases, 1–6): reality-emulation=1, ..., perpetual-wisdom=6

Score range change:
  OLD: [0.80, 6.70]   (max = 10×0.5 + 5×0.3 + 1×0.2)
  NEW: [0.80, 7.00]   (max = 10×0.5 + 6×0.3 + 1×0.2)
═══════════════════════════════════════════════════════════════

Formula (unchanged — lead-approved):
  score = (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)

Weights sum to 1.0:  0.5 + 0.3 + 0.2 = 1.0

Why sequential integers 1–6 for phase weights:
  Each phase step adds exactly 0.30 to the score (1 × 0.3 = 0.30).
  This is linear and explainable: "each phase you advance adds 0.30."
  Phases further along (Perpetual Wisdom=6) earn the highest boost,
  reflecting the SMILE principle that near-complete knowledge must
  not be abandoned — it has the most accumulated investment.

Verified worked examples (all hand-checked):
  p=5, reality-emulation,      urgent=False → 2.80
  p=5, concurrent-engineering, urgent=False → 3.10
  p=5, collective-intelligence,urgent=False → 3.40
  p=5, contextual-intelligence,urgent=False → 3.70
  p=5, continuous-intelligence,urgent=False → 4.00
  p=5, perpetual-wisdom,        urgent=False → 4.30
  p=5, perpetual-wisdom,        urgent=True  → 4.50
  p=10,perpetual-wisdom,        urgent=True  → 7.00   ← maximum
  p=1, reality-emulation,       urgent=False → 0.80   ← minimum
"""

from lpi.models import Goal, SmilePhase

# ── Formula weights (lead-approved — change only with lead sign-off) ──────────

PRIORITY_WEIGHT: float = 0.5  # 50% — the user's explicit importance rating
PHASE_WEIGHT: float = 0.3  # 30% — SMILE phase progress (how far along)
URGENCY_WEIGHT: float = 0.2  # 20% — time-sensitive binary override

# ── Corrected 6-phase weights (from smile-framework.json phase `order`) ───────

PHASE_WEIGHTS: dict[SmilePhase, int] = {
    SmilePhase.REALITY_EMULATION: 1,  # Establishing the reality canvas
    SmilePhase.CONCURRENT_ENGINEERING: 2,  # Defining scope, validating virtually
    SmilePhase.COLLECTIVE_INTELLIGENCE: 3,  # Sensors, ontologies, KPIs connected
    SmilePhase.CONTEXTUAL_INTELLIGENCE: 4,  # Real-time decisions, connected twin
    SmilePhase.CONTINUOUS_INTELLIGENCE: 5,  # AI prognostics, simulation
    SmilePhase.PERPETUAL_WISDOM: 6,  # Sharing impact, circular strategies
}
# Each step in this dict corresponds to the JSON `order` field (1–6).
# Perpetual Wisdom = 6 (highest) because goals at this phase represent
# the greatest accumulated investment and must not be dropped.


# ── Core scoring function ──────────────────────────────────────────────────────


def score_goal(goal: Goal) -> float:
    """Compute the SMILE-weighted composite score for a single goal.

    Pure function — no HTTP, no database, no store.
    Input: a full Goal object.
    Output: float in [0.80, 7.00], rounded to 2 decimal places.
    Higher score = surface this goal earlier in sorted lists.
    """
    phase_w = PHASE_WEIGHTS[goal.smile_phase]  # integer 1–6
    urgency = int(goal.urgency_flag)  # 1 if True, 0 if False

    raw = (
        (goal.priority * PRIORITY_WEIGHT)  # e.g. 5 × 0.5 = 2.50
        + (phase_w * PHASE_WEIGHT)  # e.g. 3 × 0.3 = 0.90
        + (urgency * URGENCY_WEIGHT)  # e.g. 1 × 0.2 = 0.20
    )  # total:          3.60
    return round(raw, 2)


# ── Human-readable explanation ─────────────────────────────────────────────────


def score_explanation(goal: Goal) -> str:
    """Return a one-sentence SMILE-grounded explanation of a goal's score.

    Used by the Phase 4 recommendation engine to produce transparent reasoning.
    Example output:
      "Score 3.60: priority 5 × 0.5 = 2.50, phase 'collective-intelligence'
       weight 3 × 0.3 = 0.90, urgency True × 0.2 = 0.20.
       Phase: Connect physical sensors, meet initial KPIs..."
    """
    from lpi.smile import get_phase_description

    phase_w = PHASE_WEIGHTS[goal.smile_phase]
    urgency = int(goal.urgency_flag)
    s = score_goal(goal)

    p_contrib = round(goal.priority * PRIORITY_WEIGHT, 2)
    ph_contrib = round(phase_w * PHASE_WEIGHT, 2)
    u_contrib = round(urgency * URGENCY_WEIGHT, 2)

    return (
        f"Score {s:.2f}: "
        f"priority {goal.priority} × {PRIORITY_WEIGHT} = {p_contrib}, "
        f"phase '{goal.smile_phase}' weight {phase_w} × {PHASE_WEIGHT} = {ph_contrib}, "
        f"urgency {bool(urgency)} × {URGENCY_WEIGHT} = {u_contrib}. "
        f"Phase: {get_phase_description(goal.smile_phase)[:80]}..."
    )


# ── Sort helper ────────────────────────────────────────────────────────────────


def sort_goals_by_score(goals: list[Goal]) -> list[Goal]:
    """Return goals sorted by composite score descending.

    Tiebreaker: created_at ascending (older goals surface first when scores
    are equal, preventing arbitrary reordering between requests).

    Returns a NEW list — the input list is never mutated.
    Called from list_goals() in goals.py after all filters are applied.
    """
    return sorted(goals, key=lambda g: (-score_goal(g), g.created_at))
