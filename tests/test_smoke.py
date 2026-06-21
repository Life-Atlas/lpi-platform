"""Smoke tests — fast sanity checks that the app boots and core invariants hold.

SMILE correction: phase order assertions updated from 5-phase hallucination
to the correct 6-phase framework from data/smile-framework.json.
"""


def test_imports() -> None:
    from lpi import main

    assert main.app is not None


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_smile_phase_order() -> None:
    """Verify PHASE_ORDER matches the 6-phase smile-framework.json exactly.

    CORRECTED from previous version which asserted:
      PHASE_ORDER[0] == SmilePhase.SENSE      ← hallucinated
      PHASE_ORDER[-1] == SmilePhase.EVOLVE    ← hallucinated
      len(PHASE_ORDER) == 5                   ← wrong count
    """
    from lpi.smile import PHASE_ORDER, SmilePhase  # noqa: PLC0415

    # First phase: Reality Emulation (the reality canvas foundation)
    assert PHASE_ORDER[0] == SmilePhase.REALITY_EMULATION

    # Last phase: Perpetual Wisdom (perpetual knowledge sharing)
    assert PHASE_ORDER[-1] == SmilePhase.PERPETUAL_WISDOM

    # There are exactly 6 phases — not 5
    assert len(PHASE_ORDER) == 6
