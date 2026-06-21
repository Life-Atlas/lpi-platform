"""LangGraph reasoning agent for SMILE recommendations.

Owner : Jaivardhan Singh (Phase 4 — Core Algorithm)

═══════════════════════════════════════════════════════════════
WHAT THIS FILE DOES
═══════════════════════════════════════════════════════════════
This is the "real AI reasoning" layer the leader asked for. Before this
file, lpi/recommendation_engine.py only produced TEMPLATED sentences —
e.g. "Advance '<goal title>' to <next phase>" — built from an f-string,
not from any actual reasoning about the user's combination of goals +
signals together. That is what the leader meant by "not generic
templates."

This module adds a tiny LangGraph graph (currently one node) that:
  1. Receives the user's REAL goals + activity signals — already fetched
     from Supabase by recommendation_engine.py. This file does NOT touch
     the database itself; it only reasons over data handed to it.
  2. Builds a SMILE-grounded prompt naming every goal/signal explicitly
     (by id, title, phase, priority) so the LLM can't give generic advice
     disconnected from the user's real data.
  3. Sends that prompt to the configured LLM (Groq free tier by default;
     Anthropic Claude code kept here but commented out — see _call_llm).
  4. Parses the LLM's JSON reply into plain Python dicts.

═══════════════════════════════════════════════════════════════
WHY A GRAPH AND NOT JUST A FUNCTION CALL
═══════════════════════════════════════════════════════════════
The leader's instructions specifically ask for "LangGraph agent reasoning
logic," because Daksh's next task (Phase 1 orchestration / multi-step
pipeline) is meant to extend this graph later — e.g. adding a "retry on
bad JSON" node or a "clarify ambiguous goal" node — without touching the
reasoning prompt itself. Today there's exactly ONE node because the brief
only asks for WORKING code, not an over-engineered pipeline. Daksh adds
the multi-step orchestration on top of this.

═══════════════════════════════════════════════════════════════
WHY IT CANNOT BREAK ANYTHING (SAFETY CONTRACT)
═══════════════════════════════════════════════════════════════
run_agent() NEVER raises. If the API key is missing, the network call
fails, or the LLM returns malformed JSON, it returns None. The caller
(recommendation_engine.py) is REQUIRED to treat None as "fall back to the
deterministic Phase 1 engine" — that deterministic engine already exists
(it was the old "Wave 2" code) and now serves as the safety net both for
this agent AND for Daksh's orchestration pipeline.

This also means: existing tests that run with no ANTHROPIC_API_KEY set
(the normal test environment) automatically skip the LLM call and fall
straight through to the deterministic engine — so nothing that already
passes can break.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from lpi.config import settings
from lpi.models import Goal, Signal

logger = logging.getLogger(__name__)


# ── LangGraph state ───────────────────────────────────────────────────────────
# WHAT: the dict-like object passed between graph nodes.
# WHY a TypedDict: LangGraph requires a typed state schema; this keeps the
# data flowing through the graph self-documenting.
class AgentState(TypedDict):
    user_id: str
    goals: list[Goal]
    signals: list[Signal]
    raw_actions: list[dict] | None  # filled in by the "reason" node, or left None on failure


_VALID_PHASES = (
    "reality-emulation",
    "concurrent-engineering",
    "collective-intelligence",
    "contextual-intelligence",
    "continuous-intelligence",
    "perpetual-wisdom",
)


# ── Prompt construction ───────────────────────────────────────────────────────


def _build_prompt(goals: list[Goal], signals: list[Signal]) -> str:
    """Build the SMILE-grounded reasoning prompt sent to the LLM.

    WHAT: lists every goal (id, title, phase, priority, urgency) and every
    signal (id, stream, event_type) in plain text, then demands a STRICT
    JSON array back.

    WHY: naming each goal/signal explicitly — instead of just describing
    "the user's goals" abstractly — is what forces the LLM to reason about
    THIS user's real data instead of returning boilerplate advice.
    """
    goal_lines = (
        "\n".join(
            f"- id={g.id} title='{g.title}' phase={g.smile_phase.value} "
            f"priority={g.priority} urgent={g.urgency_flag}"
            for g in goals
        )
        or "(no goals yet)"
    )

    signal_lines = (
        "\n".join(
            f"- id={s.id} stream={s.stream} event_type={s.event_type} source={s.source}"
            for s in signals
        )
        or "(no signals yet)"
    )

    return f"""You are the SMILE (Sustainable Methodology for Impact Lifecycle
Enablement) recommendation reasoner for the LPI Platform.

The 6 SMILE phases, in strict forward order, are:
reality-emulation -> concurrent-engineering -> collective-intelligence ->
contextual-intelligence -> continuous-intelligence -> perpetual-wisdom

User's current goals:
{goal_lines}

User's recent activity signals:
{signal_lines}

Task: Recommend up to 5 concrete next actions for this user. Every action
MUST be grounded in a SPECIFIC goal or signal listed above (reference its
id) — do not give generic advice. When recommending a goal move forward,
only suggest the single next SMILE phase (never skip a phase).

Respond with ONLY a JSON array, no markdown fences, no commentary.
Each array item must look exactly like this:
{{
  "action": "short imperative sentence",
  "reasoning": "1-2 sentences explaining WHY, naming the SMILE phase",
  "smile_phase": "one of the 6 phase slugs above",
  "priority": 0.0,
  "source_goal_id": "an id from the goals list above, or null",
  "source_signal_id": "an id from the signals list above, or null"
}}
priority must be a number between 0.80 and 7.00.
"""


# ── LLM call ───────────────────────────────────────────────────────────────────


def _call_llm(prompt: str) -> str | None:
    """Call the configured LLM provider. Returns raw text, or None on failure.

    WHAT: a single, non-streaming chat completion call.
    WHY None on failure (never raises): this function is on the hot path
    of every recommendations request — a flaky LLM call must never 500
    the endpoint. The caller falls back to the deterministic engine.
    HOW: selects provider from settings.llm_provider. Defaults to "groq"
    (free tier) — switch to "anthropic" once we have a paid Claude API key.

    Provider selection (settings.llm_provider):
      • "groq"      → uses settings.groq_api_key + settings.llm_model
                      (default model: llama-3.3-70b-versatile)
      • "anthropic" → uses settings.anthropic_api_key + settings.llm_model
                      (Claude — kept below, commented out for now)
    """
    provider = (settings.llm_provider or "groq").lower().strip()

    if provider == "anthropic":
        # ════════════════════════════════════════════════════════════════════
        # ANTHROPIC (Claude) — KEPT HERE, COMMENTED OUT.
        # WILL BE USED ONCE WE HAVE A CLAUDE / ANTHROPIC API KEY.
        # Until then we use the Groq free-tier key (default).
        # Uncomment this block + set LLM_PROVIDER=anthropic in .env to switch.
        # ════════════════════════════════════════════════════════════════════
        # if not settings.anthropic_api_key:
        #     logger.info("ANTHROPIC_API_KEY not set — skipping LangGraph LLM reasoning.")
        #     return None
        #
        # try:
        #     import anthropic  # lazy import
        #     client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        #     response = client.messages.create(
        #         model=settings.llm_model,
        #         max_tokens=1000,
        #         messages=[{"role": "user", "content": prompt}],
        #     )
        #     return response.content[0].text
        # except Exception:
        #     logger.exception("Anthropic LangGraph LLM reasoning call failed.")
        #     return None
        logger.info(
            "LLM_PROVIDER=anthropic requested but the Anthropic code path is "
            "currently commented out — falling back to Groq."
        )
        # fall through to the Groq path

    # ── GROQ (free tier) — ACTIVE DEFAULT ────────────────────────────────────
    if not settings.groq_api_key:
        logger.info("GROQ_API_KEY not set — skipping LangGraph LLM reasoning.")
        return None

    try:
        from groq import Groq  # lazy import: keeps this module importable

        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception:
        logger.exception("Groq LangGraph LLM reasoning call failed.")
        return None


# ── Graph node ─────────────────────────────────────────────────────────────────


def _reason_node(state: AgentState) -> AgentState:
    """The graph's only node: build the prompt, call the LLM, parse JSON.

    Always returns a state (LangGraph node contract) — never raises.
    On any failure, raw_actions stays None so run_agent() reports failure.
    """
    prompt = _build_prompt(state["goals"], state["signals"])
    raw_text = _call_llm(prompt)

    if raw_text is None:
        state["raw_actions"] = None
        return state

    try:
        # Defensive cleanup in case the model wraps output in ```json fences
        # despite being told not to.
        cleaned = (
            raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        )
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            raise ValueError("LLM response was not a JSON array")
        state["raw_actions"] = parsed
    except Exception:
        logger.exception("Failed to parse LLM JSON output for recommendations.")
        state["raw_actions"] = None

    return state


# ── Graph construction ─────────────────────────────────────────────────────────


def _build_graph():
    """Build the (currently one-node) LangGraph graph.

    Kept as its own function so Daksh's orchestration pipeline can later
    import and extend this graph (add nodes/edges) without touching the
    reasoning prompt or LLM call logic above.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("reason", _reason_node)
    graph.set_entry_point("reason")
    graph.add_edge("reason", END)
    return graph.compile()


# Compiled once, reused across requests — building the graph is cheap but
# there's no reason to rebuild it on every call.
_compiled_graph = None


def run_agent(user_id: str, goals: list[Goal], signals: list[Signal]) -> list[dict] | None:
    """Public entry point. Run the LangGraph agent over this user's data.

    Returns:
        list[dict] — one dict per recommended action (schema documented in
                      _build_prompt above), when the agent succeeded.
        None        — whenever the LLM is unavailable or its output could
                      not be parsed. Callers MUST fall back to the
                      deterministic engine in lpi/recommendation_engine.py
                      in that case — see this module's docstring.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()

    initial_state: AgentState = {
        "user_id": user_id,
        "goals": goals,
        "signals": signals,
        "raw_actions": None,
    }

    try:
        result = _compiled_graph.invoke(initial_state)
        return result.get("raw_actions")
    except Exception:
        logger.exception("LangGraph agent invocation failed for user_id=%s", user_id)
        return None
