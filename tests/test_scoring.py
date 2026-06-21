"""Tests for the SMILE-weighted goal priority scoring module — corrected 6-phase framework.

Owner : Jaivardhan Singh
QA    : Daksh Garg

CORRECTION NOTE
═══════════════════════════════════════════════════════════════
The previous test file used hallucinated phase names (SENSE, MODEL,
INTERVENE, LEARN, EVOLVE) and their associated weights (1–5).
Every known-value assertion produced wrong expected numbers under
the correct 6-phase framework. This file replaces it entirely.

Changes:
  - Phase names updated to the 6 correct SMILE phases
  - Phase weights now 1–6 (was 1–5), PERPETUAL_WISDOM = 6
  - Score range now [0.80, 7.00] (was [0.80, 6.70])
  - _goal() helper updated: urgent= param kept, phase default changed
  - TestPhaseWeightsConstant: 12 tests → 13 tests (6th phase added)
  - TestScoreGoalKnownValues: all expected values recomputed
═══════════════════════════════════════════════════════════════

Formula (unchanged):
  score = (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)

Run: pytest tests/test_scoring.py -v   ← no server needed, ~50ms
"""

import time
from datetime import UTC, datetime

import pytest

from lpi.models import Goal, SmilePhase
from lpi.scoring import (
    PHASE_WEIGHT,
    PHASE_WEIGHTS,
    PRIORITY_WEIGHT,
    URGENCY_WEIGHT,
    score_explanation,
    score_goal,
    sort_goals_by_score,
)

# ── Test helper ───────────────────────────────────────────────────────────────


def _goal(
    priority: int,
    phase: SmilePhase,
    urgent: bool = False,
    title: str = "Test",
) -> Goal:
    """Build a minimal Goal for scoring tests — no HTTP, no store, no fixtures.

    Default phase is REALITY_EMULATION (Phase 1, the correct first phase).
    urgent defaults to False so legacy call-sites that don't pass it still work.
    """
    now = datetime.now(UTC)
    return Goal(
        id="test-id",
        user_id="default_user",
        title=title,
        description="",
        priority=priority,
        smile_phase=phase,
        urgency_flag=urgent,
        created_at=now,
        updated_at=now,
    )


# ── Phase weights constant tests ──────────────────────────────────────────────


class TestPhaseWeightsConstant:
    """Verify every weight constant in PHASE_WEIGHTS matches smile-framework.json.

    These 13 tests are the contract for the formula. If anyone changes a
    constant, these fail immediately and visibly before any deployment.
    """

    def test_reality_emulation_weight_is_1(self) -> None:
        assert PHASE_WEIGHTS[SmilePhase.REALITY_EMULATION] == 1

    def test_concurrent_engineering_weight_is_2(self) -> None:
        assert PHASE_WEIGHTS[SmilePhase.CONCURRENT_ENGINEERING] == 2

    def test_collective_intelligence_weight_is_3(self) -> None:
        assert PHASE_WEIGHTS[SmilePhase.COLLECTIVE_INTELLIGENCE] == 3

    def test_contextual_intelligence_weight_is_4(self) -> None:
        assert PHASE_WEIGHTS[SmilePhase.CONTEXTUAL_INTELLIGENCE] == 4

    def test_continuous_intelligence_weight_is_5(self) -> None:
        assert PHASE_WEIGHTS[SmilePhase.CONTINUOUS_INTELLIGENCE] == 5

    def test_perpetual_wisdom_weight_is_6(self) -> None:
        """Phase 6 — the most evolved, highest weight."""
        assert PHASE_WEIGHTS[SmilePhase.PERPETUAL_WISDOM] == 6

    def test_all_6_phases_have_weights(self) -> None:
        assert len(PHASE_WEIGHTS) == 6
        for phase in SmilePhase:
            assert phase in PHASE_WEIGHTS, f"Missing weight for {phase}"

    def test_perpetual_wisdom_is_highest_weight(self) -> None:
        assert max(PHASE_WEIGHTS.values()) == PHASE_WEIGHTS[SmilePhase.PERPETUAL_WISDOM]

    def test_reality_emulation_is_lowest_weight(self) -> None:
        assert min(PHASE_WEIGHTS.values()) == PHASE_WEIGHTS[SmilePhase.REALITY_EMULATION]

    def test_formula_weights_sum_to_1(self) -> None:
        """0.5 + 0.3 + 0.2 must equal exactly 1.0 — design invariant."""
        assert PRIORITY_WEIGHT + PHASE_WEIGHT + URGENCY_WEIGHT == pytest.approx(1.0)

    def test_urgency_weight_is_0_2(self) -> None:
        assert URGENCY_WEIGHT == pytest.approx(0.2)

    def test_priority_weight_is_0_5(self) -> None:
        assert PRIORITY_WEIGHT == pytest.approx(0.5)

    def test_phase_weight_is_0_3(self) -> None:
        assert PHASE_WEIGHT == pytest.approx(0.3)


# ── Known-value tests (all hand-verified) ────────────────────────────────────


class TestScoreGoalKnownValues:
    """Every assertion is hand-computed and verified. These are the ground truth.

    Formula: score = (priority × 0.5) + (phase_weight × 0.3) + (urgency × 0.2)
    """

    def test_p5_reality_emulation_nonurgent(self) -> None:
        """(5×0.5) + (1×0.3) + (0×0.2) = 2.50 + 0.30 + 0.00 = 2.80"""
        assert score_goal(_goal(5, SmilePhase.REALITY_EMULATION, False)) == 2.80

    def test_p5_concurrent_engineering_nonurgent(self) -> None:
        """(5×0.5) + (2×0.3) + (0×0.2) = 2.50 + 0.60 + 0.00 = 3.10"""
        assert score_goal(_goal(5, SmilePhase.CONCURRENT_ENGINEERING, False)) == 3.10

    def test_p5_collective_intelligence_nonurgent(self) -> None:
        """(5×0.5) + (3×0.3) + (0×0.2) = 2.50 + 0.90 + 0.00 = 3.40"""
        assert score_goal(_goal(5, SmilePhase.COLLECTIVE_INTELLIGENCE, False)) == 3.40

    def test_p5_contextual_intelligence_nonurgent(self) -> None:
        """(5×0.5) + (4×0.3) + (0×0.2) = 2.50 + 1.20 + 0.00 = 3.70"""
        assert score_goal(_goal(5, SmilePhase.CONTEXTUAL_INTELLIGENCE, False)) == 3.70

    def test_p5_continuous_intelligence_nonurgent(self) -> None:
        """(5×0.5) + (5×0.3) + (0×0.2) = 2.50 + 1.50 + 0.00 = 4.00"""
        assert score_goal(_goal(5, SmilePhase.CONTINUOUS_INTELLIGENCE, False)) == 4.00

    def test_p5_perpetual_wisdom_nonurgent(self) -> None:
        """(5×0.5) + (6×0.3) + (0×0.2) = 2.50 + 1.80 + 0.00 = 4.30"""
        assert score_goal(_goal(5, SmilePhase.PERPETUAL_WISDOM, False)) == 4.30

    def test_p5_perpetual_wisdom_urgent(self) -> None:
        """(5×0.5) + (6×0.3) + (1×0.2) = 2.50 + 1.80 + 0.20 = 4.50"""
        assert score_goal(_goal(5, SmilePhase.PERPETUAL_WISDOM, True)) == 4.50

    def test_p10_perpetual_wisdom_urgent_is_maximum(self) -> None:
        """(10×0.5) + (6×0.3) + (1×0.2) = 5.00 + 1.80 + 0.20 = 7.00  ← max"""
        assert score_goal(_goal(10, SmilePhase.PERPETUAL_WISDOM, True)) == 7.00

    def test_p1_reality_emulation_nonurgent_is_minimum(self) -> None:
        """(1×0.5) + (1×0.3) + (0×0.2) = 0.50 + 0.30 + 0.00 = 0.80   ← min"""
        assert score_goal(_goal(1, SmilePhase.REALITY_EMULATION, False)) == 0.80

    def test_p7_reality_emulation_nonurgent(self) -> None:
        """(7×0.5) + (1×0.3) + (0×0.2) = 3.50 + 0.30 + 0.00 = 3.80"""
        assert score_goal(_goal(7, SmilePhase.REALITY_EMULATION, False)) == 3.80

    def test_p7_reality_emulation_urgent(self) -> None:
        """(7×0.5) + (1×0.3) + (1×0.2) = 3.50 + 0.30 + 0.20 = 4.00"""
        assert score_goal(_goal(7, SmilePhase.REALITY_EMULATION, True)) == 4.00

    def test_p8_collective_intelligence_nonurgent(self) -> None:
        """(8×0.5) + (3×0.3) + (0×0.2) = 4.00 + 0.90 + 0.00 = 4.90"""
        assert score_goal(_goal(8, SmilePhase.COLLECTIVE_INTELLIGENCE, False)) == 4.90


# ── Urgency flag behaviour ────────────────────────────────────────────────────


class TestScoreGoalWithUrgency:
    """Tests that isolate the urgency_flag contribution across all 6 phases."""

    def test_urgency_adds_exactly_0_2_on_every_phase(self) -> None:
        """Flipping urgency_flag True must add exactly 0.20 on any goal."""
        for phase in SmilePhase:
            for p in (1, 5, 10):
                without = score_goal(_goal(p, phase, False))
                with_u = score_goal(_goal(p, phase, True))
                diff = round(with_u - without, 2)
                assert diff == 0.20, f"p={p}, {phase}: expected urgency diff=0.20, got {diff}"

    def test_urgent_goal_always_scores_higher_than_nonurgent(self) -> None:
        for phase in SmilePhase:
            for p in range(1, 11):
                assert score_goal(_goal(p, phase, True)) > score_goal(_goal(p, phase, False))

    def test_urgency_can_narrow_gap_between_adjacent_phases(self) -> None:
        """Phase 1 urgent vs Phase 2 non-urgent — Phase 2 still wins, but gap shrinks.

        reality-emulation urgent=True:   2.80 + 0.20 = 3.00
        concurrent-engineering urgent=False:   3.10
        Phase 2 wins (3.10 > 3.00), but gap is now 0.10 instead of 0.30.
        """
        re_urgent = score_goal(_goal(5, SmilePhase.REALITY_EMULATION, True))  # 3.00
        ce_normal = score_goal(_goal(5, SmilePhase.CONCURRENT_ENGINEERING, False))  # 3.10
        assert ce_normal > re_urgent
        assert round(ce_normal - re_urgent, 2) == pytest.approx(0.10)

    def test_urgency_flag_defaults_to_false(self) -> None:
        g = _goal(5, SmilePhase.REALITY_EMULATION)  # no urgent= arg
        assert g.urgency_flag is False
        assert score_goal(g) == 2.80


# ── General properties ────────────────────────────────────────────────────────


class TestScoreGoalProperties:
    def test_returns_float(self) -> None:
        assert isinstance(score_goal(_goal(5, SmilePhase.REALITY_EMULATION)), float)

    def test_all_phases_produce_valid_scores(self) -> None:
        for phase in SmilePhase:
            for urgent in (True, False):
                s = score_goal(_goal(5, phase, urgent))
                assert isinstance(s, float)

    def test_higher_priority_always_gives_higher_score(self) -> None:
        for phase in SmilePhase:
            for urgent in (True, False):
                assert score_goal(_goal(10, phase, urgent)) > score_goal(_goal(1, phase, urgent))

    def test_phases_strictly_ascending_by_score(self) -> None:
        """Each subsequent phase must score higher at equal priority."""
        scores = [
            score_goal(_goal(5, ph, False))
            for ph in [
                SmilePhase.REALITY_EMULATION,
                SmilePhase.CONCURRENT_ENGINEERING,
                SmilePhase.COLLECTIVE_INTELLIGENCE,
                SmilePhase.CONTEXTUAL_INTELLIGENCE,
                SmilePhase.CONTINUOUS_INTELLIGENCE,
                SmilePhase.PERPETUAL_WISDOM,
            ]
        ]
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1], (
                f"Phase {i} score {scores[i]} should be < {scores[i + 1]}"
            )

    def test_deterministic(self) -> None:
        g = _goal(7, SmilePhase.COLLECTIVE_INTELLIGENCE, True)
        assert score_goal(g) == score_goal(g)

    def test_result_rounded_to_2dp(self) -> None:
        s = score_goal(_goal(3, SmilePhase.CONCURRENT_ENGINEERING, True))
        assert s == round(s, 2)


# ── Sort behaviour ────────────────────────────────────────────────────────────


class TestSortGoalsByScore:
    def test_empty_returns_empty(self) -> None:
        assert sort_goals_by_score([]) == []

    def test_single_item_unchanged(self) -> None:
        g = _goal(5, SmilePhase.REALITY_EMULATION)
        assert sort_goals_by_score([g]) == [g]

    def test_sorted_descending_by_score(self) -> None:
        goals = [
            _goal(1, SmilePhase.REALITY_EMULATION, False, "Low"),
            _goal(10, SmilePhase.PERPETUAL_WISDOM, True, "High"),
            _goal(5, SmilePhase.COLLECTIVE_INTELLIGENCE, False, "Mid"),
        ]
        result = sort_goals_by_score(goals)
        scores = [score_goal(g) for g in result]
        assert scores == sorted(scores, reverse=True)

    def test_urgent_goal_surfaces_above_nonurgent_peer(self) -> None:
        g_urgent = _goal(5, SmilePhase.COLLECTIVE_INTELLIGENCE, True, "Urgent")
        g_normal = _goal(5, SmilePhase.COLLECTIVE_INTELLIGENCE, False, "Normal")
        result = sort_goals_by_score([g_normal, g_urgent])
        assert result[0].title == "Urgent"

    def test_highest_score_is_first(self) -> None:
        goals = [
            _goal(1, SmilePhase.REALITY_EMULATION, False, "Worst"),
            _goal(10, SmilePhase.PERPETUAL_WISDOM, True, "Best"),
        ]
        assert sort_goals_by_score(goals)[0].title == "Best"

    def test_lowest_score_is_last(self) -> None:
        goals = [
            _goal(10, SmilePhase.PERPETUAL_WISDOM, True, "Best"),
            _goal(1, SmilePhase.REALITY_EMULATION, False, "Worst"),
        ]
        assert sort_goals_by_score(goals)[-1].title == "Worst"

    def test_tiebreak_older_goal_surfaces_first(self) -> None:
        g_old = _goal(5, SmilePhase.REALITY_EMULATION, False, "Older")
        time.sleep(0.02)
        g_new = _goal(5, SmilePhase.REALITY_EMULATION, False, "Newer")
        assert sort_goals_by_score([g_new, g_old])[0].title == "Older"

    def test_does_not_mutate_input(self) -> None:
        goals = [
            _goal(9, SmilePhase.PERPETUAL_WISDOM, True, "A"),
            _goal(1, SmilePhase.REALITY_EMULATION, False, "B"),
        ]
        first_before = goals[0].title
        sort_goals_by_score(goals)
        assert goals[0].title == first_before


# ── Score explanation ─────────────────────────────────────────────────────────


class TestScoreExplanation:
    def test_returns_non_empty_string(self) -> None:
        assert len(score_explanation(_goal(5, SmilePhase.REALITY_EMULATION))) > 30

    def test_contains_score_value(self) -> None:
        g = _goal(5, SmilePhase.REALITY_EMULATION, False)
        assert str(score_goal(g)) in score_explanation(g)

    def test_contains_phase_name(self) -> None:
        for phase in SmilePhase:
            assert str(phase) in score_explanation(_goal(5, phase))

    def test_contains_priority_value(self) -> None:
        assert "7" in score_explanation(_goal(7, SmilePhase.CONCURRENT_ENGINEERING))

    def test_contains_urgency_info(self) -> None:
        explanation = score_explanation(_goal(5, SmilePhase.REALITY_EMULATION, True))
        assert "True" in explanation or "urgency" in explanation.lower()
