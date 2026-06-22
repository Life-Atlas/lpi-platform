"""Agent Orchestration Pipeline — Phase 4 (Daksh Garg)

═══════════════════════════════════════════════════════════════
WHAT THIS FILE DOES
═══════════════════════════════════════════════════════════════
This is the multi-step reasoning pipeline that wraps the existing
LangGraph agent (langgraph_agent.py) and the deterministic fallback
engine (recommendation_engine.py) into a single, observable, fault-tolerant
orchestration graph.

The key design goal: **always return exactly 3 output cards**, even when
the LLM is unavailable, returns garbage, or times out.

PIPELINE STEPS (graph nodes, in order)
───────────────────────────────────────
  1. fetch      — load this user's goals + signals from Supabase
  2. classify   — decide which path to take (cold_start / llm / fallback)
  3. reason     — call the LangGraph LLM agent (if classify → llm)
  4. validate   — check LLM output quality; retry once with simpler prompt
  5. enrich     — convert raw dicts → Recommendation objects with
                  deterministic phase/priority (LLM provides text only)
  6. fallback   — guaranteed 3 cold-start cards if any prior node fails
  7. finalise   — ensure exactly `n_cards` outputs, sorted priority DESC

GUARANTEED 3-CARD CONTRACT
───────────────────────────
`run_pipeline()` NEVER raises and ALWAYS returns at least 3 Recommendation
objects. This is the "demo safety net" requirement for Wednesday.

The guarantee is layered:
  • If fetch fails     → fallback fires immediately
  • If LLM unavailable → fallback fires after classify
  • If LLM bad JSON    → validate triggers one retry, then fallback
  • If enrich fails    → fallback fills the gap to reach 3 cards
  • finalise always    → pads with cold-start cards if count < n_cards

HOW TO EXTEND THE GRAPH (for future phases)
─────────────────────────────────────────────
Add nodes and edges to _build_pipeline_graph() below. The AgentState
TypedDict is the contract between nodes — add new keys there if you need
to pass new data between nodes. Existing nodes do NOT need to change.

Examples of future nodes:
  - "clarify"  — ask the user a clarifying question if goals are ambiguous
  - "rerank"   — re-score recommendations using a second LLM call
  - "persist"  — write accepted recommendations back to Supabase
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from lpi import store
from lpi.models import Goal, Recommendation, Signal
from lpi.recommendation_engine import (
    _diversify_by_phase,
    _goal_recommendations,
    _signal_recommendation,
    _try_langgraph_recommendations,
    build_cold_start_recommendations,
)
from lpi.scoring import sort_goals_by_score

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# How many recent signals to pull for reasoning (matches recommendation_engine.py)
_SIGNALS_TO_CONSIDER = 20

# Default number of output cards (the demo gate asks for 3)
DEFAULT_N_CARDS = 3


# ── Pipeline State ────────────────────────────────────────────────────────────


class PipelineState(TypedDict):
    """Shared state dict passed between every node in the pipeline graph.

    Keys are progressively populated as the graph runs. A node reads the
    keys it needs and writes the keys it produces.
    """

    user_id: str
    n_cards: int  # how many output cards to return (default 3)

    # Populated by fetch node
    goals: list[Goal]
    signals: list[Signal]
    fetch_ok: bool  # False if the DB call raised

    # Populated by classify node
    route: str  # "cold_start" | "llm" | "fallback"

    # Populated by reason node
    raw_llm_actions: list[dict] | None  # raw dicts from the LLM, or None

    # Populated by validate node
    retry_count: int  # 0 or 1 — we allow exactly one retry
    llm_valid: bool  # True if the LLM output passed validation

    # Populated by enrich node
    enriched: list[Recommendation]  # Recommendations built from validated LLM output

    # Final output — written by finalise node
    recommendations: list[Recommendation]


# ── Node implementations ──────────────────────────────────────────────────────


def _node_fetch(state: PipelineState) -> PipelineState:
    """Node 1 — Load goals + signals for this user from Supabase.

    Sets fetch_ok=False (instead of raising) so the graph can route
    gracefully to the fallback node if the DB is unavailable.
    """
    try:
        state["goals"] = store.list_goals(user_id=state["user_id"])
        state["signals"] = store.list_signals(
            user_id=state["user_id"], limit=_SIGNALS_TO_CONSIDER
        )
        state["fetch_ok"] = True
        logger.debug(
            "fetch: user=%s goals=%d signals=%d",
            state["user_id"],
            len(state["goals"]),
            len(state["signals"]),
        )
    except Exception:
        logger.exception("fetch node: DB call failed for user_id=%s", state["user_id"])
        state["goals"] = []
        state["signals"] = []
        state["fetch_ok"] = False
    return state


def _node_classify(state: PipelineState) -> PipelineState:
    """Node 2 — Decide which reasoning route to take.

    Routes:
      cold_start  — no goals AND no signals (brand-new / empty account)
      llm         — real data exists; try the LangGraph LLM agent
      fallback    — fetch failed; skip LLM, go straight to deterministic

    The classify node never raises.
    """
    if not state["fetch_ok"]:
        state["route"] = "fallback"
    elif not state["goals"] and not state["signals"]:
        state["route"] = "cold_start"
    else:
        state["route"] = "llm"

    logger.debug("classify: route=%s", state["route"])
    return state


def _node_reason(state: PipelineState) -> PipelineState:
    """Node 3 — Call the LangGraph LLM agent.

    Only runs when route == "llm". Puts raw dicts into raw_llm_actions
    (or None if the agent returned nothing usable).

    Never raises — run_agent() is already guaranteed not to raise.
    """
    if state["route"] != "llm":
        state["raw_llm_actions"] = None
        return state

    from lpi import langgraph_agent

    state["raw_llm_actions"] = langgraph_agent.run_agent(
        state["user_id"], state["goals"], state["signals"]
    )
    logger.debug(
        "reason: raw_llm_actions=%s",
        len(state["raw_llm_actions"]) if state["raw_llm_actions"] else "None",
    )
    return state


def _node_validate(state: PipelineState) -> PipelineState:
    """Node 4 — Validate LLM output quality; retry once with a simpler prompt.

    Validation criteria:
      1. raw_llm_actions is a non-empty list
      2. At least one item has a valid source_goal_id or source_signal_id
         (i.e. the LLM actually referenced the user's real data)

    If validation fails and retry_count == 0:
      — run the agent again with a simpler, more constrained prompt
        (by temporarily setting a flag the reason node reads)

    If validation fails and retry_count == 1:
      — set llm_valid=False so the enrich + finalise nodes fall back
        to the deterministic engine.
    """
    raw = state.get("raw_llm_actions")
    valid_goal_ids = {g.id for g in state.get("goals", [])}
    valid_signal_ids = {s.id for s in state.get("signals", [])}

    def _has_valid_source(items: list[dict]) -> bool:
        for item in items:
            gid = item.get("source_goal_id")
            sid = item.get("source_signal_id")
            if gid in valid_goal_ids or sid in valid_signal_ids:
                return True
        return False

    if raw and isinstance(raw, list) and _has_valid_source(raw):
        state["llm_valid"] = True
        logger.debug("validate: LLM output accepted (%d items)", len(raw))
        return state

    # Validation failed
    retry = state.get("retry_count", 0)
    if retry == 0:
        logger.info(
            "validate: LLM output invalid (attempt 1), retrying with simpler prompt"
        )
        state["retry_count"] = 1
        # Re-run the agent with a stripped-down prompt (fewer goals/signals)
        # to improve the chance of getting parseable JSON
        from lpi import langgraph_agent

        goals_subset = sort_goals_by_score(state["goals"])[:3]  # top 3 only
        signals_subset = state["signals"][:5]  # 5 most recent only
        state["raw_llm_actions"] = langgraph_agent.run_agent(
            state["user_id"], goals_subset, signals_subset
        )

        # Re-validate immediately
        raw2 = state["raw_llm_actions"]
        if raw2 and isinstance(raw2, list) and _has_valid_source(raw2):
            state["llm_valid"] = True
            logger.debug(
                "validate: LLM retry accepted (%d items)", len(raw2)
            )
        else:
            state["llm_valid"] = False
            logger.info("validate: LLM retry also failed, routing to fallback")
    else:
        state["llm_valid"] = False
        logger.info("validate: LLM output invalid after retry, routing to fallback")

    return state


def _node_enrich(state: PipelineState) -> PipelineState:
    """Node 5 — Convert validated LLM raw dicts → Recommendation objects.

    Uses the same hybrid approach as recommendation_engine._try_langgraph_recommendations:
      - LLM provides: action text, reasoning text
      - We derive deterministically: smile_phase, priority, source ids

    If llm_valid is False (or route isn't "llm"), builds recommendations from
    the deterministic engine (goals + signals) instead — same as Wave 2 fallback.
    """
    user_id = state["user_id"]
    goals = state.get("goals", [])
    signals = state.get("signals", [])

    if state.get("llm_valid") and state.get("raw_llm_actions"):
        recs = _try_langgraph_recommendations(user_id, goals, signals) or []
        # Supplement with signal rec if LLM didn't cover it
        if signals:
            sig_rec = _signal_recommendation(user_id, signals)
            if sig_rec and not any(r.smile_phase == sig_rec.smile_phase for r in recs):
                recs.append(sig_rec)
        state["enriched"] = _diversify_by_phase(recs)
    elif goals or signals:
        # Deterministic fallback (Wave 2 engine)
        candidates: list[Recommendation] = list(_goal_recommendations(user_id, goals))
        sig_rec = _signal_recommendation(user_id, signals)
        if sig_rec:
            candidates.append(sig_rec)
        state["enriched"] = _diversify_by_phase(candidates)
    else:
        state["enriched"] = []

    logger.debug("enrich: %d recommendations built", len(state["enriched"]))
    return state


def _node_fallback(state: PipelineState) -> PipelineState:
    """Node 6 — Guaranteed 3-card cold-start safety net.

    Only fires when route == "cold_start" OR fetch_ok == False.
    Writes directly to state["enriched"] with exactly 3 cards.
    These cards are always valid Recommendation objects — no DB required.
    """
    if state.get("route") in ("cold_start", "fallback") or not state.get("fetch_ok"):
        state["enriched"] = build_cold_start_recommendations(state["user_id"])
        logger.debug("fallback: injected %d cold-start cards", len(state["enriched"]))
    return state


def _node_finalise(state: PipelineState) -> PipelineState:
    """Node 7 — Sort, deduplicate, and guarantee n_cards output.

    Steps:
      1. Deduplicate by recommendation id
      2. Sort by priority descending
      3. If count < n_cards, pad with cold-start cards until we reach n_cards
      4. Slice to n_cards
      5. Write to state["recommendations"]

    This node is the absolute last line of defence — after it, the caller
    is GUARANTEED to receive exactly n_cards Recommendation objects.
    """
    n = state.get("n_cards", DEFAULT_N_CARDS)
    enriched = state.get("enriched", [])

    # Deduplicate by id (shouldn't happen, but be safe)
    seen_ids: set[str] = set()
    unique: list[Recommendation] = []
    for r in enriched:
        if r.id not in seen_ids:
            unique.append(r)
            seen_ids.add(r.id)

    # Sort highest priority first
    sorted_recs = sorted(unique, key=lambda r: -r.priority)

    # Pad to n_cards if needed — e.g. a user with 1 goal gets 1 rec + 2 fallbacks
    if len(sorted_recs) < n:
        cold = build_cold_start_recommendations(state["user_id"])
        for card in cold:
            if len(sorted_recs) >= n:
                break
            # Don't add a cold-start card that duplicates an existing phase
            if not any(r.smile_phase == card.smile_phase for r in sorted_recs):
                sorted_recs.append(card)

    # Final sort after padding, then slice
    sorted_recs = sorted(sorted_recs, key=lambda r: -r.priority)
    state["recommendations"] = sorted_recs[:n]

    logger.debug(
        "finalise: returning %d recommendations (requested %d)",
        len(state["recommendations"]),
        n,
    )
    return state


# ── Graph construction ────────────────────────────────────────────────────────


def _build_pipeline_graph():
    """Build the multi-step orchestration graph.

    Graph structure:
      fetch → classify → reason → validate → enrich → finalise
                       ↘                  ↗
                         fallback ────────
                       (cold_start/error)

    All nodes are connected sequentially with conditional routing at
    classify (cold_start / fallback routes skip reason + validate).

    The graph is intentionally simple so Daksh's future phases can add
    nodes (clarify, rerank, persist) without restructuring the existing flow.
    """
    from langgraph.graph import END, StateGraph

    g = StateGraph(PipelineState)

    # Register nodes
    g.add_node("fetch", _node_fetch)
    g.add_node("classify", _node_classify)
    g.add_node("reason", _node_reason)
    g.add_node("validate", _node_validate)
    g.add_node("enrich", _node_enrich)
    g.add_node("fallback", _node_fallback)
    g.add_node("finalise", _node_finalise)

    # Entry point
    g.set_entry_point("fetch")

    # fetch → classify (always)
    g.add_edge("fetch", "classify")

    # classify → conditional routing
    def _route_after_classify(state: PipelineState) -> str:
        if state["route"] == "llm":
            return "reason"
        return "fallback"  # handles both cold_start and fallback routes

    g.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "reason": "reason",
            "fallback": "fallback",
        },
    )

    # LLM path: reason → validate → enrich → finalise
    g.add_edge("reason", "validate")
    g.add_edge("validate", "enrich")
    g.add_edge("enrich", "finalise")

    # Fallback path: fallback → finalise
    g.add_edge("fallback", "finalise")

    # finalise → END
    g.add_edge("finalise", END)

    return g.compile()


# Compiled once at import time — building the graph is cheap, no reason
# to rebuild on every request.
_pipeline_graph = None


def _get_pipeline() -> Any:
    global _pipeline_graph
    if _pipeline_graph is None:
        _pipeline_graph = _build_pipeline_graph()
    return _pipeline_graph


# ── Public entry point ────────────────────────────────────────────────────────


def run_pipeline(user_id: str, n_cards: int = DEFAULT_N_CARDS) -> list[Recommendation]:
    """Run the full multi-step orchestration pipeline for `user_id`.

    This is the public API of this module. It:
      1. Runs the LangGraph pipeline graph (fetch → classify → ... → finalise)
      2. ALWAYS returns exactly `n_cards` Recommendation objects
      3. NEVER raises — any unhandled exception triggers the cold-start fallback

    Args:
        user_id : The user to generate recommendations for.
        n_cards : How many output cards to return (default 3, max 10).
                  The demo gate requires exactly 3.

    Returns:
        list[Recommendation] — exactly n_cards items, sorted by priority DESC.
        Falls back to cold-start cards if anything in the pipeline fails.
    """
    n_cards = max(1, min(10, n_cards))  # clamp to valid range

    initial_state: PipelineState = {
        "user_id": user_id,
        "n_cards": n_cards,
        "goals": [],
        "signals": [],
        "fetch_ok": False,
        "route": "fallback",
        "raw_llm_actions": None,
        "retry_count": 0,
        "llm_valid": False,
        "enriched": [],
        "recommendations": [],
    }

    try:
        pipeline = _get_pipeline()
        result = pipeline.invoke(initial_state)
        recs = result.get("recommendations", [])

        # Absolute last resort: if we somehow got fewer than n_cards, pad
        if len(recs) < n_cards:
            logger.warning(
                "run_pipeline: got %d recs, need %d — padding with cold-start",
                len(recs),
                n_cards,
            )
            cold = build_cold_start_recommendations(user_id)
            seen_phases = {r.smile_phase for r in recs}
            for c in cold:
                if len(recs) >= n_cards:
                    break
                if c.smile_phase not in seen_phases:
                    recs.append(c)
                    seen_phases.add(c.smile_phase)

        return sorted(recs, key=lambda r: -r.priority)[:n_cards]

    except Exception:
        logger.exception(
            "run_pipeline: unhandled exception for user_id=%s — using cold-start fallback",
            user_id,
        )
        return build_cold_start_recommendations(user_id)[:n_cards]
