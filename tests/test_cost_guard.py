"""Tests for the daily LLM cost guard (src/lpi/cost_guard.py).

These are pure unit tests — no Supabase, no network. They always run,
including in CI, so the cap enforcement can never silently regress the
way an integration-only test would.
"""

import pytest

from lpi import cost_guard, langgraph_agent
from lpi.config import settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_guard():
    cost_guard.reset_for_tests()
    yield
    cost_guard.reset_for_tests()


class TestBudgetCheck:
    def test_allows_under_cap(self) -> None:
        assert cost_guard.check_budget() is True

    def test_blocks_at_cap(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "daily_cost_cap_usd", 0.01)
        # One expensive anthropic-priced call blows a 1-cent cap.
        cost_guard.record_usage("anthropic", input_tokens=2_000_000, output_tokens=0)
        assert cost_guard.check_budget() is False

    def test_spend_accumulates(self) -> None:
        first = cost_guard.record_usage("groq", input_tokens=1_000_000, output_tokens=0)
        second = cost_guard.record_usage("groq", input_tokens=0, output_tokens=1_000_000)
        assert cost_guard.spent_today() == pytest.approx(first + second)

    def test_unknown_provider_uses_conservative_pricing(self) -> None:
        cost = cost_guard.record_usage("mystery-llm", input_tokens=1_000_000, output_tokens=0)
        # Falls back to the anthropic (most expensive) price row.
        assert cost == pytest.approx(3.00)

    def test_missing_usage_falls_back_to_estimate(self) -> None:
        cost = cost_guard.record_usage("groq")
        assert cost > 0

    def test_day_rollover_resets_spend(self, monkeypatch) -> None:
        import datetime

        cost_guard.record_usage("anthropic", input_tokens=2_000_000, output_tokens=0)
        assert cost_guard.spent_today() > 0
        tomorrow = datetime.datetime.now(datetime.UTC).date() + datetime.timedelta(days=1)
        monkeypatch.setattr(cost_guard, "_today", lambda: tomorrow)
        assert cost_guard.spent_today() == 0.0
        assert cost_guard.check_budget() is True


class TestCallLlmEnforcement:
    def test_call_llm_refused_when_over_cap(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "daily_cost_cap_usd", 0.01)
        monkeypatch.setattr(settings, "groq_api_key", "fake-key-should-never-be-used")
        cost_guard.record_usage("anthropic", input_tokens=2_000_000, output_tokens=0)
        # Over cap → _call_llm must bail out BEFORE touching any provider SDK.
        assert langgraph_agent._call_llm("any prompt") is None
