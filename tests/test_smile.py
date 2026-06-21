"""Tests for the SMILE methodology — corrected 6-phase framework.

Owner  : Yashika
QA     : All team members (SMILE is foundational)

CORRECTION NOTE
═══════════════════════════════════════════════════════════════
The previous test file validated phase transitions between the
hallucinated 5-phase system (SENSE → MODEL → INTERVENE → LEARN
→ EVOLVE). Every assertion in that file referenced non-existent
phase names and has been rewritten here for the correct phases
from data/smile-framework.json.

The transition LOGIC is unchanged (forward one step allowed,
backward any steps allowed, skip-forward forbidden, same phase
forbidden). Only the phase names and count (5 → 6) changed.
═══════════════════════════════════════════════════════════════

Run: pytest tests/test_smile.py -v
"""

from lpi.models import SmilePhase
from lpi.smile import (
    PHASE_ORDER,
    get_phase_description,
    get_phase_key_question,
    validate_phase_transition,
)


class TestPhaseOrder:
    """Verify the canonical 6-phase order matches smile-framework.json."""

    def test_phase_count_is_6(self) -> None:
        """There are exactly 6 SMILE phases — not 5 as previously hallucinated."""
        assert len(PHASE_ORDER) == 6

    def test_first_phase_is_reality_emulation(self) -> None:
        assert PHASE_ORDER[0] == SmilePhase.REALITY_EMULATION

    def test_last_phase_is_perpetual_wisdom(self) -> None:
        assert PHASE_ORDER[-1] == SmilePhase.PERPETUAL_WISDOM

    def test_full_order(self) -> None:
        """The exact sequence from smile-framework.json order fields."""
        expected = [
            SmilePhase.REALITY_EMULATION,
            SmilePhase.CONCURRENT_ENGINEERING,
            SmilePhase.COLLECTIVE_INTELLIGENCE,
            SmilePhase.CONTEXTUAL_INTELLIGENCE,
            SmilePhase.CONTINUOUS_INTELLIGENCE,
            SmilePhase.PERPETUAL_WISDOM,
        ]
        assert PHASE_ORDER == expected

    def test_enum_has_exactly_6_members(self) -> None:
        assert len(SmilePhase) == 6


class TestPhaseTransitions:
    """Transition rules are unchanged from Phase 2 — only names changed."""

    # ── Forward one step (always allowed) ───────────────────────────────────

    def test_phase1_to_phase2_allowed(self) -> None:
        """Reality Emulation → Concurrent Engineering: valid forward step."""
        assert (
            validate_phase_transition(
                SmilePhase.REALITY_EMULATION,
                SmilePhase.CONCURRENT_ENGINEERING,
            )
            is True
        )

    def test_phase2_to_phase3_allowed(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.CONCURRENT_ENGINEERING,
                SmilePhase.COLLECTIVE_INTELLIGENCE,
            )
            is True
        )

    def test_phase3_to_phase4_allowed(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.COLLECTIVE_INTELLIGENCE,
                SmilePhase.CONTEXTUAL_INTELLIGENCE,
            )
            is True
        )

    def test_phase4_to_phase5_allowed(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.CONTEXTUAL_INTELLIGENCE,
                SmilePhase.CONTINUOUS_INTELLIGENCE,
            )
            is True
        )

    def test_phase5_to_phase6_allowed(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.CONTINUOUS_INTELLIGENCE,
                SmilePhase.PERPETUAL_WISDOM,
            )
            is True
        )

    # ── Backward any steps (re-evaluation is always valid in SMILE) ─────────

    def test_backward_one_step_allowed(self) -> None:
        """A new discovery can send you back one phase."""
        assert (
            validate_phase_transition(
                SmilePhase.CONCURRENT_ENGINEERING,
                SmilePhase.REALITY_EMULATION,
            )
            is True
        )

    def test_backward_many_steps_allowed(self) -> None:
        """Perpetual Wisdom → Reality Emulation: full reset is permitted."""
        assert (
            validate_phase_transition(
                SmilePhase.PERPETUAL_WISDOM,
                SmilePhase.REALITY_EMULATION,
            )
            is True
        )

    def test_backward_partial_allowed(self) -> None:
        """Continuous Intelligence → Collective Intelligence: valid backward."""
        assert (
            validate_phase_transition(
                SmilePhase.CONTINUOUS_INTELLIGENCE,
                SmilePhase.COLLECTIVE_INTELLIGENCE,
            )
            is True
        )

    # ── Skip forward (forbidden — must step through each phase) ─────────────

    def test_skip_phase1_to_phase3_rejected(self) -> None:
        """Reality Emulation → Collective Intelligence skips Phase 2: rejected."""
        assert (
            validate_phase_transition(
                SmilePhase.REALITY_EMULATION,
                SmilePhase.COLLECTIVE_INTELLIGENCE,
            )
            is False
        )

    def test_skip_phase1_to_phase4_rejected(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.REALITY_EMULATION,
                SmilePhase.CONTEXTUAL_INTELLIGENCE,
            )
            is False
        )

    def test_skip_phase2_to_phase4_rejected(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.CONCURRENT_ENGINEERING,
                SmilePhase.CONTEXTUAL_INTELLIGENCE,
            )
            is False
        )

    def test_skip_phase1_to_phase6_rejected(self) -> None:
        """Can't jump from Phase 1 to Phase 6."""
        assert (
            validate_phase_transition(
                SmilePhase.REALITY_EMULATION,
                SmilePhase.PERPETUAL_WISDOM,
            )
            is False
        )

    # ── Same phase (no-op — always forbidden) ────────────────────────────────

    def test_same_phase_reality_emulation_rejected(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.REALITY_EMULATION,
                SmilePhase.REALITY_EMULATION,
            )
            is False
        )

    def test_same_phase_perpetual_wisdom_rejected(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.PERPETUAL_WISDOM,
                SmilePhase.PERPETUAL_WISDOM,
            )
            is False
        )

    def test_same_phase_middle_rejected(self) -> None:
        assert (
            validate_phase_transition(
                SmilePhase.COLLECTIVE_INTELLIGENCE,
                SmilePhase.COLLECTIVE_INTELLIGENCE,
            )
            is False
        )


class TestPhaseDescriptions:
    """All 6 phases must have a non-empty description sourced from the JSON."""

    def test_all_phases_have_descriptions(self) -> None:
        for phase in SmilePhase:
            desc = get_phase_description(phase)
            assert isinstance(desc, str), f"{phase}: description must be a string"
            assert len(desc) > 20, f"{phase}: description too short — likely a stub"

    def test_reality_emulation_mentions_canvas(self) -> None:
        """The JSON description for Phase 1 references the reality canvas."""
        assert "canvas" in get_phase_description(SmilePhase.REALITY_EMULATION).lower()

    def test_concurrent_engineering_mentions_mvt(self) -> None:
        """Phase 2 description mentions MVT (Minimal Viable Twin)."""
        assert (
            "mvt" in get_phase_description(SmilePhase.CONCURRENT_ENGINEERING).lower()
            or "minimal viable" in get_phase_description(SmilePhase.CONCURRENT_ENGINEERING).lower()
        )

    def test_collective_intelligence_mentions_ontology(self) -> None:
        """Phase 3 is about ontology factories — a key SMILE concept."""
        assert "ontolog" in get_phase_description(SmilePhase.COLLECTIVE_INTELLIGENCE).lower()

    def test_perpetual_wisdom_mentions_planet(self) -> None:
        """Phase 6 is about sharing impact across the planet."""
        assert "planet" in get_phase_description(SmilePhase.PERPETUAL_WISDOM).lower()

    def test_all_phases_have_key_questions(self) -> None:
        for phase in SmilePhase:
            q = get_phase_key_question(phase)
            assert isinstance(q, str)
            assert len(q) > 20
