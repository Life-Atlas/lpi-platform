"""SMILE methodology implementation — Corrected 6-Phase Framework.

CRITICAL CORRECTION
═══════════════════════════════════════════════════════════════
The previous implementation used a hallucinated 5-phase system:
  SENSE → MODEL → INTERVENE → LEARN → EVOLVE
This does not exist in the LPI data source.

Correct source: data/smile-framework.json (lpi-mcp-server)
Full name: Sustainable Methodology for Impact Lifecycle Enablement
Author: Nicolas Waern, WINNIIO / LifeAtlas
Principle: "Impact first, data last."
  Outcome → Action → Insight → Information → Data
═══════════════════════════════════════════════════════════════
"""

from lpi.models import SmilePhase

# The 6 phases in their canonical order from smile-framework.json.
# The ordering matters: validate_phase_transition() uses index arithmetic
# on this list to determine whether a transition is a forward step,
# a skip, or a backward step.
PHASE_ORDER: list[SmilePhase] = [
    SmilePhase.REALITY_EMULATION,  # order 1 — establish the reality canvas
    SmilePhase.CONCURRENT_ENGINEERING,  # order 2 — define scope, validate virtually
    SmilePhase.COLLECTIVE_INTELLIGENCE,  # order 3 — sensors, ontologies, KPIs
    SmilePhase.CONTEXTUAL_INTELLIGENCE,  # order 4 — real-time decisions, connected twin
    SmilePhase.CONTINUOUS_INTELLIGENCE,  # order 5 — AI-driven prognostics, simulation
    SmilePhase.PERPETUAL_WISDOM,  # order 6 — share impact, circular strategies
]


def validate_phase_transition(current: SmilePhase, target: SmilePhase) -> bool:
    """Validate whether a SMILE phase transition is permitted.

    SMILE is not a linear lockstep process — re-evaluation is explicitly
    encouraged. The rules are:

      Allowed:
        - Forward exactly one step (e.g., Reality Emulation → Concurrent Engineering)
        - Backward any number of steps (a new discovery can return you to
          Reality Emulation even from Perpetual Wisdom)

      Not allowed:
        - Skipping forward (e.g., Reality Emulation → Collective Intelligence
          skips Concurrent Engineering, which is forbidden)
        - Staying in the same phase (no-op transition, forbidden)

    Returns True if allowed, False otherwise.
    """
    current_idx = PHASE_ORDER.index(current)
    target_idx = PHASE_ORDER.index(target)

    if target_idx == current_idx + 1:
        return True  # ✓ forward one step

    if target_idx < current_idx:
        return True  # ✓ backward — re-evaluation is always valid in SMILE

    if target_idx == current_idx:
        return False  # ✗ no-op

    return False  # ✗ skip forward (target_idx > current_idx + 1)


def get_phase_description(phase: SmilePhase) -> str:
    """Return the official description for a SMILE phase.

    Text sourced verbatim from data/smile-framework.json `description` fields.
    Used by score_explanation() in scoring.py and by the Phase 4 recommendation
    engine to provide SMILE-grounded reasoning in API responses.
    """
    descriptions: dict[SmilePhase, str] = {
        SmilePhase.REALITY_EMULATION: (
            "Create a shared reality canvas — establishing where, when, and who. "
            "The foundation is a real-world planetary foundation in 3D+, understandable "
            "by all. Everything in reality has had, has, or will occupy an area in space "
            "and time."
        ),
        SmilePhase.CONCURRENT_ENGINEERING: (
            "Define the scope (as-is to to-be), invite stakeholders to innovate together, "
            "validate hypotheses virtually before committing resources. Virtual Minimal "
            "Viable Twinning (MVT) — test ideas in simulation before reality."
        ),
        SmilePhase.COLLECTIVE_INTELLIGENCE: (
            "Connect physical sensors, meet initial KPIs, create ontologies for shared "
            "understanding. The ontology factory becomes the foundation for AI factories. "
            "Knowledge Graph ontology foundation — creating relationships between "
            "fragmented realities."
        ),
        SmilePhase.CONTEXTUAL_INTELLIGENCE: (
            "Connected everything — command & control, real-time decisions, uptime "
            "optimization, predictive analytics, root cause analysis. The digital twin "
            "becomes operationally aware of its context."
        ),
        SmilePhase.CONTINUOUS_INTELLIGENCE: (
            "Leverage accumulated knowledge — prescriptive maintenance, AI-driven "
            "prognostics, universal event pipelines. Simulate everything. Identify "
            "black swans before they strike."
        ),
        SmilePhase.PERPETUAL_WISDOM: (
            "Share impact across the planet. Up-cycle exploration, ecosystem enablement, "
            "circular strategies, open-source contribution. Knowledge becomes perpetual — "
            "transferable across generations, industries, and geographies."
        ),
    }
    return descriptions[phase]


def get_phase_key_question(phase: SmilePhase) -> str:
    """Return the key question for each SMILE phase (from smile-framework.json).

    These questions guide practitioners in knowing whether they are genuinely
    operating in a given phase. Used by the Phase 4 recommendation engine to
    generate contextually appropriate goal reasoning.
    """
    questions: dict[SmilePhase, str] = {
        SmilePhase.REALITY_EMULATION: (
            "In order to think outside the box, one has to define the box first. "
            "What is the starting point and boundary of your sociotechnological ecosystem?"
        ),
        SmilePhase.CONCURRENT_ENGINEERING: (
            "What does the Minimal Viable Twin look like, and how do we validate it "
            "virtually before investing in physical implementation?"
        ),
        SmilePhase.COLLECTIVE_INTELLIGENCE: (
            "How do we create ontology factories as the foundation for AI factories, "
            "connecting fragmented realities into a knowledge graph?"
        ),
        SmilePhase.CONTEXTUAL_INTELLIGENCE: (
            "How do we enable real-time contextual awareness across the entire ecosystem "
            "— understanding not just what is happening, but why?"
        ),
        SmilePhase.CONTINUOUS_INTELLIGENCE: (
            "How do we leverage explainable AI factories for exponential scale, scope, "
            "and learning — moving from reactive to prescriptive?"
        ),
        SmilePhase.PERPETUAL_WISDOM: (
            "How do we ensure that knowledge created today is transferable, reusable, "
            "and contributes to planetary-scale impact?"
        ),
    }
    return questions[phase]
