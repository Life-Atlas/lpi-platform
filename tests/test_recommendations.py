"""Tests for GET /api/v1/recommendations/{user_id}.

Owner: Adil Islam (Phase 4 — Backend Endpoints & QA)

SCOPE
──────
Two layers of coverage, kept in one file (test_recommendations_endpoint.py
was merged into this file — see git history):

  1. TestGetRecommendations{Auth,Shape,Limit} — the ENDPOINT CONTRACT:
     auth, validation, response shape, the `limit` param. These run
     against DEMO_USER_ID, a path-param string with no real goals/signals
     in a freshly cleared test DB, so they always exercise the
     deterministic cold-start fallback
     (recommendation_engine.build_cold_start_recommendations). They are
     unchanged by which reasoning core sits behind the endpoint, by
     design — see lpi/recommendation_engine.py's module docstring.

  2. TestRecommendations{ColdStart,FromGoals,FromSignals,Diversity,Reasoning}
     — Wave 2 CORRECTNESS: the reasoning core must actually read the
     caller's real goals + activity signals and reason over them instead
     of returning hardcoded mock data. These create real goals/signals
     via the authenticated `client` fixture (TEST_USER_ID, from
     conftest.py) and query recommendations for that SAME user_id — fixing
     an earlier version of this file that POSTed goals/signals as the real
     authenticated user but then queried recommendations for an unrelated
     literal "test-user" string that owned nothing, so the Wave 2
     assertions could never actually pass.

Run with:
  pytest tests/test_recommendations.py -v
"""

from datetime import datetime

from fastapi.testclient import TestClient

from lpi.main import app
from lpi.models import SmilePhase

# Used by the contract tests below. No real goals/signals exist for this
# string in a freshly cleared test DB, so these always hit the
# deterministic cold-start fallback (3 items) — that's intentional, not
# an oversight; see the module docstring.
DEMO_USER_ID = "intern-a-demo-profile"

# Matches conftest.py's TEST_USER_ID exactly — the JWT subject the
# `client` fixture authenticates as. Used by the Wave 2 correctness tests
# below so that goals/signals POSTed via `client` and the recommendations
# GET both refer to the SAME user_id.
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


class TestGetRecommendationsAuth:
    """No Depends(get_current_user) existed before this pass — these tests
    guard against that regression (the endpoint silently accepting
    unauthenticated requests again).
    """

    def test_requires_authentication(self) -> None:
        """No Authorization header at all -> 401, not 200 with an empty list."""
        unauthenticated_client = TestClient(app)
        response = unauthenticated_client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        assert response.status_code == 401

    def test_rejects_garbage_token(self) -> None:
        unauthenticated_client = TestClient(app)
        unauthenticated_client.headers.update({"Authorization": "Bearer not-a-real-jwt"})
        response = unauthenticated_client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        assert response.status_code == 401


class TestGetRecommendationsShape:
    """Response shape must match the Recommendation model exactly, since
    Jahanvi's frontend cards are built directly against this contract.
    """

    def test_returns_200_and_a_list(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_default_limit_is_3(self, client) -> None:
        """§4.1 gate: 'output 3 recommended next actions'."""
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_every_recommendation_matches_schema(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        assert response.status_code == 200
        recs = response.json()
        assert len(recs) > 0

        valid_phases = {phase.value for phase in SmilePhase}

        for rec in recs:
            assert isinstance(rec["id"], str) and rec["id"]
            assert rec["user_id"] == DEMO_USER_ID
            assert isinstance(rec["action"], str) and rec["action"]
            assert isinstance(rec["reasoning"], str) and rec["reasoning"]
            assert rec["smile_phase"] in valid_phases, (
                f"'{rec['smile_phase']}' is not one of the 6 correct SMILE "
                "phases — check for the hallucinated 5-phase regression."
            )
            assert isinstance(rec["priority"], (int, float))
            assert 0.80 <= rec["priority"] <= 7.00, (
                f"priority {rec['priority']} is outside the goals scoring "
                "scale [0.80, 7.00] from lpi/scoring.py — recommendations "
                "and goals should share one priority scale."
            )
            assert isinstance(rec["source_goals"], list)
            assert isinstance(rec["source_signals"], list)
            # created_at must be a parseable ISO-8601 timestamp
            datetime.fromisoformat(rec["created_at"])

    def test_recommendations_sorted_by_priority_descending(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}")
        priorities = [r["priority"] for r in response.json()]
        assert priorities == sorted(priorities, reverse=True), (
            "Recommendations must be ordered highest-priority first so "
            "Jahanvi's stacked cards show the most important action on top."
        )

    def test_user_id_is_echoed_for_a_different_profile(self, client) -> None:
        """user_id is a path param (not derived from the JWT) BY DESIGN —
        see the module docstring in routers/recommendations.py. This test
        locks in that contract: a second demo profile must work from the
        SAME authenticated session, which is what the demo flow needs.
        """
        response = client.get("/api/v1/recommendations/intern-b-demo-profile")
        assert response.status_code == 200
        recs = response.json()
        assert len(recs) > 0
        for rec in recs:
            assert rec["user_id"] == "intern-b-demo-profile"


class TestGetRecommendationsLimit:
    """`limit` query param: ge=1, le=10, default=3."""

    def test_limit_1_returns_1(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=1")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_limit_2_returns_2(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_limit_above_mock_count_returns_all_available(self, client) -> None:
        """limit=10 is valid per the route's le=10 bound, but the cold-start
        fallback only has 3 items — must return 3, not error and not pad
        the response with junk to hit 10.
        """
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=10")
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_limit_zero_is_rejected(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=0")
        assert response.status_code == 422

    def test_limit_above_max_is_rejected(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=11")
        assert response.status_code == 422

    def test_negative_limit_is_rejected(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=-1")
        assert response.status_code == 422

    def test_non_integer_limit_is_rejected(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=not-a-number")
        assert response.status_code == 422

    def test_limit_1_returns_highest_priority_item(self, client) -> None:
        """limit=1 must return the single HIGHEST-priority recommendation —
        i.e. limit is applied AFTER sorting, not before.
        """
        full = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}").json()
        top = client.get(f"/api/v1/recommendations/{DEMO_USER_ID}?limit=1").json()
        assert len(top) == 1
        assert top[0]["priority"] == max(r["priority"] for r in full)


class TestRecommendationsColdStart:
    """A user with zero goals and zero signals still gets useful starter
    recommendations instead of an empty list. This is the safety net
    Daksh's orchestration pipeline also relies on — see
    recommendation_engine.build_cold_start_recommendations.
    """

    def test_cold_start_returns_suggestions(self, client) -> None:
        """GET on a clean store should return suggestions, not an empty list."""
        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_cold_start_respects_limit(self, client) -> None:
        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}?limit=3")
        assert response.status_code == 200
        assert len(response.json()) <= 3


class TestRecommendationsFromGoals:
    """Wave 2 correctness: recommendations must reason over the caller's
    REAL goals, not hardcoded mock data.
    """

    def test_recommendation_advances_goal_to_next_phase(self, client) -> None:
        """A goal at concurrent-engineering must produce a recommendation
        targeting collective-intelligence — the next SMILE phase, per the
        forward-one-step rule in smile.validate_phase_transition().
        """
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Wire the ontology layer",
                "priority": 6,
                "smile_phase": "concurrent-engineering",
            },
        ).json()

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        matching = [r for r in recs if goal["id"] in r["source_goals"]]
        assert matching, (
            f"No recommendation referenced goal {goal['id']}. "
            "The engine must read the caller's real goals from Supabase."
        )
        assert matching[0]["smile_phase"] == "collective-intelligence"

    def test_recommendation_priority_matches_goal_score(self, client) -> None:
        """A goal-derived recommendation's priority must equal
        scoring.score_goal() for that same goal — recommendations and
        goals share one priority scale by design.
        """
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Ship the dashboard",
                "priority": 8,
                "smile_phase": "reality-emulation",
                "urgency_flag": True,
            },
        ).json()
        # p=8, reality-emulation(1), urgent=True -> 8*0.5 + 1*0.3 + 1*0.2 = 4.50
        expected_priority = 4.50

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        recs = response.json()
        matching = [r for r in recs if goal["id"] in r["source_goals"]]
        assert matching
        assert matching[0]["priority"] == expected_priority

    def test_goal_at_perpetual_wisdom_does_not_crash(self, client) -> None:
        """A goal already at the final SMILE phase has no 'next' phase to
        advance to. The engine must handle this gracefully (sustain/share
        framing) instead of raising on a missing PHASE_ORDER index.
        """
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Open-source the toolkit",
                "priority": 5,
                "smile_phase": "perpetual-wisdom",
            },
        ).json()

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        matching = [r for r in recs if goal["id"] in r["source_goals"]]
        assert matching
        assert matching[0]["smile_phase"] == "perpetual-wisdom"


class TestRecommendationsFromSignals:
    """Wave 2 correctness: recent activity signals must also surface as a
    recommendation, not just goals — a user who only logs activity (no
    goals yet) should still get a useful nudge.
    """

    def test_recommendation_sourced_from_signal(self, client, sample_signal) -> None:
        signal = client.post("/api/v1/signals/", json=sample_signal).json()

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        matching = [r for r in recs if signal["id"] in r["source_signals"]]
        assert matching, (
            "No recommendation referenced the ingested signal. "
            "The engine must read the caller's real signals from Supabase."
        )
        assert matching[0]["smile_phase"] == "collective-intelligence"

    def test_recommendations_sourced_from_user_goals_and_signals(
        self, client, sample_goal, sample_signal
    ) -> None:
        """A user with BOTH a goal and a signal should get recommendations
        crediting each one, not just whichever the engine processes first.
        """
        goal_id = client.post("/api/v1/goals/", json=sample_goal).json()["id"]
        signal_id = client.post("/api/v1/signals/", json=sample_signal).json()["id"]

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        all_source_goals = [g for r in recs for g in r["source_goals"]]
        all_source_signals = [s for r in recs for s in r["source_signals"]]

        assert goal_id in all_source_goals, (
            "No recommendation referenced the user's goal. "
            "The engine must read real store data and populate source_goals."
        )
        assert signal_id in all_source_signals, (
            "No recommendation referenced the user's signal. "
            "The engine must read real store data and populate source_signals."
        )


class TestRecommendationsDiversity:
    """Wave 2 correctness: spread recommendations across distinct SMILE
    phases, and never repeat a recommendation id.
    """

    def test_no_duplicate_recommendation_ids(self, client) -> None:
        """Each recommendation returned must have a unique id — duplicate
        cards in Jahanvi's frontend would confuse the user.
        """
        client.post(
            "/api/v1/goals/",
            json={"title": "Goal A", "priority": 5, "smile_phase": "reality-emulation"},
        )
        client.post(
            "/api/v1/goals/",
            json={"title": "Goal B", "priority": 5, "smile_phase": "concurrent-engineering"},
        )

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        ids = [r["id"] for r in recs]
        assert len(ids) == len(set(ids)), (
            f"Duplicate recommendation ids found: {ids}. Each recommendation must have a unique id."
        )

    def test_each_recommendation_covers_a_different_smile_phase(self, client) -> None:
        """Default 3 recommendations should span 3 distinct SMILE phases
        when the caller's goals are spread across distinct phases.

        WHY THIS MATTERS
        ─────────────────
        Returning three recommendations all in the same phase would give
        the user no sense of where they stand across the full SMILE
        journey. The engine must spread its output across different
        phases to be useful as a lifecycle guide.
        """
        for title, phase in [
            ("Goal A", "reality-emulation"),
            ("Goal B", "concurrent-engineering"),
            ("Goal C", "collective-intelligence"),
        ]:
            client.post(
                "/api/v1/goals/",
                json={"title": title, "priority": 5, "smile_phase": phase},
            )

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert response.status_code == 200

        recs = response.json()
        phases = [r["smile_phase"] for r in recs]

        valid_phases = {phase.value for phase in SmilePhase}
        for phase in phases:
            assert phase in valid_phases, (
                f"'{phase}' is not a valid SMILE phase. "
                "Check for the hallucinated 5-phase regression "
                "(sense/model/intervene/learn/evolve)."
            )

        assert len(set(phases)) == len(recs), (
            f"Recommendations share SMILE phases: {phases}. "
            "Each recommendation must target a different phase so the "
            "user gets a spread across the SMILE lifecycle."
        )


class TestRecommendationsReasoning:
    """Wave 2 correctness: reasoning text must be real and SMILE-grounded,
    not a generic placeholder.
    """

    def test_recommendations_have_real_reasoning(self, client, sample_goal) -> None:
        """Each recommendation must include non-trivial SMILE-based
        reasoning — and, with real goal data on the store, must NOT be
        the cold-start placeholder text.
        """
        client.post("/api/v1/goals/", json=sample_goal)

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        recs = response.json()
        assert len(recs) > 0

        for rec in recs:
            assert isinstance(rec["reasoning"], str)
            assert len(rec["reasoning"]) > 20
            assert "Getting started" not in rec["reasoning"], (
                "Got the cold-start fallback even though real goal data "
                "exists — the engine is not reading the caller's stored goals."
            )

    def test_recommendation_reasoning_names_its_smile_phase(self, client, sample_goal) -> None:
        """Each recommendation's reasoning must literally name the SMILE
        phase it targets — generic advice with no phase reference is not
        SMILE-grounded.

        Example PASSING reasoning: mentions 'concurrent-engineering' or
        the words 'concurrent'/'engineering'.
        Example FAILING reasoning: 'Consider advancing your goals' with no
        phase named at all.
        """
        client.post("/api/v1/goals/", json=sample_goal)

        response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        recs = response.json()
        assert len(recs) > 0

        for rec in recs:
            phase_slug = rec["smile_phase"]
            reasoning = rec["reasoning"].lower()

            phase_slug_in_reasoning = phase_slug.lower() in reasoning
            phase_words = set(phase_slug.replace("-", " ").split())
            phase_words_in_reasoning = any(w in reasoning for w in phase_words)

            assert phase_slug_in_reasoning or phase_words_in_reasoning, (
                f"Recommendation reasoning does not mention its SMILE phase.\n"
                f"  smile_phase : {phase_slug}\n"
                f"  reasoning   : {rec['reasoning'][:120]}...\n"
                "The reasoning must reference the phase it targets so the "
                "user understands WHY this action is recommended at this "
                "point in the SMILE lifecycle."
            )
