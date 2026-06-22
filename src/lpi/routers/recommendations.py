"""Module 3 — Recommendation Engine: HTTP endpoint.

Algorithm Owner : Jaivardhan Singh  (Phase 4 — Wave 2)
Endpoint Owner  : Adil Islam        (Phase 4 — Wave 1, also QA)

═══════════════════════════════════════════════════════════
WAVE 2 (this pass) — real data wired in
═══════════════════════════════════════════════════════════
Wave 1 shipped this endpoint backed by deterministic mock data
(_build_mock_recommendations) so Jahanvi's frontend wasn't blocked on the
real reasoning core. That mock data NEVER read the goals or
activity_signals tables — every user_id got the same 3 hardcoded cards.

Wave 2 fixes exactly that: the data source is now
lpi.recommendation_engine.generate_recommendations(user_id), which reads
the caller's REAL goals + activity_signals from Supabase and reasons over
them (see lpi/recommendation_engine.py for the full algorithm writeup).

This file is now a thin HTTP layer:
  - auth (Depends(get_current_user))
  - validation (the `limit` Query bounds)
  - the stable response contract (always <= limit Recommendation objects,
    sorted by priority descending)
  - delegating the actual "what should this user do next" decision to
    lpi/recommendation_engine.py

WHAT STAYS THE SAME AS WAVE 1 (unchanged on purpose)
───────────────────────────────────────────────────────
  - Real auth, same as goals.py / signals.py.
  - Same response contract: Recommendation objects on the SAME 0.80-7.00
    priority scale goals use, sorted highest-priority first.
  - user_id is still a path param, NOT derived from the JWT. This is
    still BY DESIGN, not an oversight: it's what lets one authenticated
    demo session pull up Aryan's seeded "Intern A/B/C" profiles, and it's
    also what lets the recommendation engine read ANY user_id's goals/
    signals rather than only the caller's own. If this becomes a
    production multi-tenant endpoint, add the same 404-on-mismatch
    ownership check used in goals.py / signals.py
    (`if resource.user_id != caller_id: raise 404`).
  - No persistence. Accept/dismiss storage is still Yashika's deliverable.

HOW THE SWAP WORKS (for anyone touching this file next)
───────────────────────────────────────────────────────────
generate_recommendations(user_id) -> list[Recommendation] is the same
shape _build_mock_recommendations(user_id) always had, so improving the
reasoning core (smarter signal correlation, an LLM-backed bonus pass,
etc.) means editing lpi/recommendation_engine.py — this router shouldn't
need to change again for that.

Daksh: your orchestration pipeline's "guaranteed 3 cards" fallback can
still call `_build_mock_recommendations()` (re-exported below from
lpi.recommendation_engine.build_cold_start_recommendations under its old
name) directly as the safety-net route if the multi-module reasoning
hasn't finished in time.
"""

from fastapi import APIRouter, Depends, Query

from lpi.agent_pipeline import run_pipeline
from lpi.middleware.auth import get_current_user
from lpi.models import Recommendation
from lpi.recommendation_engine import build_cold_start_recommendations, generate_recommendations

router = APIRouter()

# Backward-compatible alias. Wave 1's mock builder lived here under this
# private name; Wave 2 relocated its implementation to
# lpi/recommendation_engine.py (as build_cold_start_recommendations) so
# the real engine can call it directly for the cold-start case without a
# circular import between this router and the engine module. Anything
# that already imports `_build_mock_recommendations` from this module
# (e.g. Daksh's orchestration safety net) keeps working unchanged.
_build_mock_recommendations = build_cold_start_recommendations


@router.get(
    "/{user_id}",
    response_model=list[Recommendation],
    summary="Get recommended next actions for a user",
    description=(
        "Returns up to `limit` SMILE-grounded next-action recommendations, "
        "highest priority first. Wave 2: derived from the user's real "
        "goals + activity signals, with a deterministic 3-item fallback "
        "for users with no goals or signals yet."
    ),
)
def get_recommendations(
    user_id: str,
    limit: int = Query(
        default=3,
        ge=1,
        le=10,
        description="Max recommendations to return (1-10). Demo gate asks for 3.",
    ),
    _caller_id: str = Depends(get_current_user),
) -> list[Recommendation]:
    """Return up to `limit` recommended next actions for `user_id`.

    Auth: requires a valid Supabase JWT (any authenticated caller — see
    module docstring for why user_id is NOT restricted to the caller's
    own id). `_caller_id` is intentionally unused beyond the Depends()
    call itself: its only job here is to reject unauthenticated requests
    with 401 before this function body ever runs.

    Sorted by priority descending (highest-priority action first), then
    truncated to `limit`. With a cold-start user (no goals/signals yet),
    `limit` only has a visible effect for limit < 3, since the fallback
    set always has exactly 3 items. With real goal/signal data, the
    candidate count varies with how much the user has actually logged.
    """
    recommendations = sorted(
        generate_recommendations(user_id),
        key=lambda r: -r.priority,
    )
    return recommendations[:limit]


@router.post(
    "/{user_id}/run",
    response_model=list[Recommendation],
    summary="Run the full agent orchestration pipeline for a user",
    description=(
        "Executes the multi-step LangGraph orchestration pipeline: "
        "fetch → classify → reason (LLM) → validate → enrich → finalise. "
        "Always returns the **top 3 recommendations** sorted by priority — "
        "even if the LLM is unavailable, returns bad JSON, or the DB is unreachable. "
        "The pipeline retries failed LLM output once with a simplified prompt before "
        "falling back to the deterministic Wave 2 engine, and finally to cold-start "
        "cards. This is the Phase 4 demo-safe endpoint."
    ),
)
def run_recommendation_pipeline(
    user_id: str,
    _caller_id: str = Depends(get_current_user),
) -> list[Recommendation]:
    """Run the full multi-step agent orchestration pipeline.

    Always returns exactly the top 3 recommendations for the user,
    sorted by priority descending. No limit parameter — 3 cards is
    the fixed contract for this endpoint.

    The pipeline runs through 7 nodes:
      1. fetch    — loads user's goals + signals from Supabase
      2. classify — routes to LLM path or cold-start/fallback
      3. reason   — runs the LangGraph LLM agent (Groq/Anthropic)
      4. validate — checks LLM output quality; retries once if invalid
      5. enrich   — converts validated LLM output → Recommendation objects
                    (falls back to deterministic engine if LLM invalid)
      6. fallback — guaranteed cold-start 3 cards if route != llm
      7. finalise — deduplicates, sorts by priority DESC, pads to 3

    DEMO GUARANTEE: always returns exactly 3 Recommendation objects
    regardless of LLM availability, DB state, or user data.
    """
    return run_pipeline(user_id, n_cards=3)
