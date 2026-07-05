"""Daily LLM cost guard — enforces settings.daily_cost_cap_usd.

WHAT: a process-local daily spend tracker consulted before every LLM call
and updated after every successful one. When the day's estimated spend
reaches the cap, further calls are refused and the recommendations flow
falls back to the deterministic engine (same graceful path as an LLM
outage — see langgraph_agent._call_llm).

WHY: DAILY_COST_CAP_USD existed in config but nothing enforced it — the
gap was flagged in recommendation_engine.py. Groq's free tier makes this
academic today; the moment a paid Anthropic key lands it is not.

HOW: costs are estimated from the provider's reported token usage when
available, otherwise from a conservative flat estimate. Pricing is a
static table — deliberately conservative rather than precise; the point
is a hard ceiling, not accounting.

LIMITATION: in-memory and per-process, same trade-off as the fixed-window
rate limiter in middleware/rate_limit.py. It resets on restart and is not
shared across replicas. Good enough for a single-instance deploy; move to
a shared store (Supabase table / Redis) before scaling out.
"""

import logging
import threading
from datetime import UTC, date, datetime

from lpi.config import settings

logger = logging.getLogger(__name__)

# Per-million-token prices (input_usd, output_usd). Conservative estimates —
# rounded UP so the guard trips early rather than late.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "groq": (0.60, 0.80),  # llama-3.3-70b-versatile tier
    "anthropic": (3.00, 15.00),  # claude sonnet tier
}
# Used when the provider response carries no usage data: assume a full
# prompt (~2000 tokens) and the max_tokens=1000 completion actually used.
_FALLBACK_TOKENS = (2000, 1000)

_lock = threading.Lock()
_day: date | None = None
_spent_usd: float = 0.0


def _today() -> date:
    return datetime.now(UTC).date()


def _roll_day_locked() -> None:
    """Reset the counter when the UTC day changes. Caller must hold _lock."""
    global _day, _spent_usd
    today = _today()
    if _day != today:
        _day = today
        _spent_usd = 0.0


def check_budget() -> bool:
    """Return True if another LLM call is allowed under the daily cap."""
    with _lock:
        _roll_day_locked()
        allowed = _spent_usd < settings.daily_cost_cap_usd
    if not allowed:
        logger.warning(
            "Daily LLM cost cap reached (%.2f/%.2f USD) — refusing LLM call, "
            "deterministic fallback will be used.",
            _spent_usd,
            settings.daily_cost_cap_usd,
        )
    return allowed


def record_usage(
    provider: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> float:
    """Record one call's estimated cost. Returns the USD amount recorded."""
    in_price, out_price = _PRICING_PER_MTOK.get(provider, _PRICING_PER_MTOK["anthropic"])
    in_tok = input_tokens if input_tokens is not None else _FALLBACK_TOKENS[0]
    out_tok = output_tokens if output_tokens is not None else _FALLBACK_TOKENS[1]
    cost = (in_tok / 1_000_000) * in_price + (out_tok / 1_000_000) * out_price
    with _lock:
        _roll_day_locked()
        global _spent_usd
        _spent_usd += cost
    return cost


def spent_today() -> float:
    """Current UTC day's estimated spend in USD."""
    with _lock:
        _roll_day_locked()
        return _spent_usd


def reset_for_tests() -> None:
    """Zero the counter. Call ONLY from test fixtures."""
    global _day, _spent_usd
    with _lock:
        _day = None
        _spent_usd = 0.0
