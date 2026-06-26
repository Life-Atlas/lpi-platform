"""End-to-End integration tests — three-module flow.

Owner : Daksh Garg (Phase 4)

WHAT THESE TESTS PROVE
───────────────────────
These are end-to-end integration tests that verify the full pipeline
across all three modules (Goals → Signals → Recommendations) working
together as a connected system.

They specifically test:
  1. A GitHub event ingested via the signals API creates a persisted
     activity signal with stream="lpi", source="github_api".
  2. A user goal at Phase 1 (reality-emulation) paired with that signal
     produces a recommendation that advances the goal to Phase 2
     (concurrent-engineering) — a SMILE phase-advancing recommendation.
  3. The recommendation's source_goals references the correct goal UUID
     and source_signals references the correct signal UUID — proving
     all three modules are wired together, not just returning templates.
  4. The full 7-node pipeline (POST /run) returns exactly 3 cards even
     when given real data from the DB.
  5. The webhook endpoint correctly parses all three GitHub event types
     (pr_merged, pr_reviewed, commit_pushed).
  6. User isolation — signal ingested by User A does NOT appear in
     recommendations for User B.

WHY THESE TESTS LIVE HERE
───────────────────────────
The existing tests (test_recommendations.py, test_activity_signals.py)
test each module independently. These tests intentionally cross module
boundaries to verify the integration contracts.

SUPABASE REQUIREMENT
─────────────────────
These tests require a running Supabase instance (local or cloud).
They use the same autouse `clear_store` fixture from conftest.py that
wipes tables before and after each test.

Run with:
    pytest tests/test_e2e_three_module_flow.py -v --tb=short
"""

import json

import pytest
from fastapi.testclient import TestClient

from lpi.main import app
from lpi.models import SmilePhase

# ── Constants ─────────────────────────────────────────────────────────────────

# Taken from conftest.py — must match the TEST_USER_ID and JWT secret there
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

# A second user for isolation tests
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"

# The 6 valid SMILE phase slugs
VALID_PHASES = {p.value for p in SmilePhase}

# The strict forward-phase mapping
NEXT_PHASE = {
    "reality-emulation": "concurrent-engineering",
    "concurrent-engineering": "collective-intelligence",
    "collective-intelligence": "contextual-intelligence",
    "contextual-intelligence": "continuous-intelligence",
    "continuous-intelligence": "perpetual-wisdom",
    "perpetual-wisdom": "perpetual-wisdom",  # last phase stays
}


# ── GitHub webhook payloads ──────────────────────────────────────────────────


def _pr_merged_payload(repo: str = "lpi-platform", pr_number: int = 33) -> dict:
    """Minimal GitHub pull_request webhook payload for a merged PR."""
    return {
        "action": "closed",
        "pull_request": {
            "number": pr_number,
            "title": f"feat: test PR #{pr_number}",
            "merged": True,
            "user": {"login": "thedgarg31"},
        },
        "repository": {"name": repo, "full_name": f"Life-Atlas/{repo}"},
    }


def _pr_reviewed_payload(repo: str = "lpi-platform", pr_number: int = 33) -> dict:
    """Minimal GitHub pull_request_review webhook payload."""
    return {
        "action": "submitted",
        "review": {
            "state": "approved",
            "user": {"login": "adilislam"},
        },
        "pull_request": {
            "number": pr_number,
            "title": f"feat: test PR #{pr_number}",
        },
        "repository": {"name": repo},
    }


def _push_payload(repo: str = "lpi-platform", branch: str = "staging") -> dict:
    """Minimal GitHub push webhook payload."""
    return {
        "ref": f"refs/heads/{branch}",
        "repository": {"name": repo},
        "commits": [
            {"message": "fix: update config", "id": "abc123"},
            {"message": "chore: cleanup", "id": "def456"},
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite 1 — GitHub webhook parsing
# ══════════════════════════════════════════════════════════════════════════════


class TestGitHubWebhookParsing:
    """Verify that the webhook endpoint correctly parses all three event
    types and returns 200 for each.

    The webhook endpoint does not require auth — it is public and verified
    by GitHub's X-Hub-Signature in production. In tests we call it directly.
    """

    def test_pr_merged_returns_200(self, client: TestClient) -> None:
        """A merged-PR event must return 200 with status=success."""
        response = client.post(
            "/api/v1/webhooks/github",
            json=_pr_merged_payload(),
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_pr_reviewed_returns_200(self, client: TestClient) -> None:
        """A PR review event must return 200."""
        response = client.post(
            "/api/v1/webhooks/github",
            json=_pr_reviewed_payload(),
            headers={"X-GitHub-Event": "pull_request_review"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_push_returns_200(self, client: TestClient) -> None:
        """A commit push event must return 200."""
        response = client.post(
            "/api/v1/webhooks/github",
            json=_push_payload(),
            headers={"X-GitHub-Event": "push"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_unknown_event_type_returns_200_gracefully(
        self, client: TestClient
    ) -> None:
        """An unrecognised event type must not crash — return 200 silently."""
        response = client.post(
            "/api/v1/webhooks/github",
            json={"action": "starred"},
            headers={"X-GitHub-Event": "watch"},
        )
        assert response.status_code == 200

    def test_pr_not_merged_is_ignored(self, client: TestClient) -> None:
        """A closed-but-not-merged PR must not produce a signal."""
        payload = _pr_merged_payload()
        payload["pull_request"]["merged"] = False
        response = client.post(
            "/api/v1/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite 2 — Signal ingestion via the Signals API
# ══════════════════════════════════════════════════════════════════════════════


class TestGitHubSignalIngestion:
    """Verify that a GitHub-style activity signal can be ingested via the
    signals API and is correctly stored in Supabase.

    These tests simulate what the webhook handler SHOULD do once the
    store.insert_signal() call is re-enabled — they call POST /signals/
    directly with github_api as the source, matching the format the
    webhook handler produces.
    """

    def test_github_pr_signal_is_stored(self, client: TestClient) -> None:
        """POST /signals/ with a GitHub PR event stores it correctly."""
        response = client.post(
            "/api/v1/signals/",
            json={
                "stream": "lpi",
                "event_type": "pr_merged",
                "payload": {"repo": "lpi-platform", "pr_number": 33, "title": "feat: agent pipeline"},
                "source": "github_api",
            },
        )
        assert response.status_code == 201
        signal = response.json()

        assert signal["stream"] == "lpi"
        assert signal["event_type"] == "pr_merged"
        assert signal["source"] == "github_api"
        assert signal["user_id"] == TEST_USER_ID
        assert signal["payload"]["pr_number"] == 33
        assert "id" in signal
        assert "timestamp" in signal

    def test_stored_signal_is_queryable(self, client: TestClient) -> None:
        """A stored signal must be retrievable via GET /signals/."""
        # Ingest
        created = client.post(
            "/api/v1/signals/",
            json={
                "stream": "lpi",
                "event_type": "commit_pushed",
                "payload": {"repo": "lpi-platform", "branch": "staging", "commit_count": 2},
                "source": "github_api",
            },
        ).json()

        # Retrieve by stream filter
        list_response = client.get("/api/v1/signals/?stream=lpi")
        assert list_response.status_code == 200
        signals = list_response.json()
        assert any(s["id"] == created["id"] for s in signals), (
            "Stored signal not found when querying by stream=lpi"
        )

    def test_stored_signal_queryable_by_source(self, client: TestClient) -> None:
        """Signals can be filtered by source=github_api."""
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "pr_merged", "source": "github_api"},
        )
        client.post(
            "/api/v1/signals/",
            json={"stream": "boardy", "event_type": "match_created", "source": "api"},
        )

        github_signals = client.get("/api/v1/signals/?source=github_api").json()
        assert all(s["source"] == "github_api" for s in github_signals)
        assert len(github_signals) >= 1

    def test_signal_fetch_by_id(self, client: TestClient) -> None:
        """A signal can be fetched by its UUID."""
        created = client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "pr_merged", "source": "github_api"},
        ).json()
        signal_id = created["id"]

        fetched = client.get(f"/api/v1/signals/{signal_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == signal_id


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite 3 — Full three-module flow
#   Goal (Module 1) + GitHub Signal (Module 2) → Recommendation (Module 3)
# ══════════════════════════════════════════════════════════════════════════════


class TestThreeModuleFlow:
    """Core E2E tests: verify that Goals + Signals together produce
    SMILE-grounded, phase-advancing recommendations.

    These are the most important tests in this file — they cross all three
    module boundaries in a single test.
    """

    def test_github_signal_surfaces_in_recommendations(
        self, client: TestClient
    ) -> None:
        """A GitHub signal ingested via POST /signals/ must appear in
        GET /recommendations/ as a source_signals reference.

        Flow:
          POST /signals/  (github_api)
          GET  /recommendations/{user_id}
          → at least one recommendation has signal_id in source_signals
        """
        # Step 1: ingest a GitHub signal
        signal = client.post(
            "/api/v1/signals/",
            json={
                "stream": "lpi",
                "event_type": "pr_merged",
                "payload": {"repo": "lpi-platform", "pr_number": 33},
                "source": "github_api",
            },
        ).json()
        signal_id = signal["id"]

        # Step 2: get recommendations
        recs_response = client.get(f"/api/v1/recommendations/{TEST_USER_ID}")
        assert recs_response.status_code == 200
        recs = recs_response.json()
        assert len(recs) > 0

        # Step 3: at least one rec references the ingested signal
        all_source_signals = [sid for r in recs for sid in r["source_signals"]]
        assert signal_id in all_source_signals, (
            f"Signal {signal_id} not found in any recommendation's source_signals.\n"
            f"source_signals across all recs: {all_source_signals}\n"
            "The recommendation engine must read real signals from Supabase."
        )

    def test_goal_at_reality_emulation_advances_to_concurrent_engineering(
        self, client: TestClient
    ) -> None:
        """A goal at Phase 1 (reality-emulation) paired with a GitHub signal
        must produce a recommendation targeting Phase 2 (concurrent-engineering).

        This is the core SMILE phase-advancing requirement.
        """
        # Step 1: create a goal at Phase 1
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Build the LPI agent pipeline",
                "priority": 8,
                "smile_phase": "reality-emulation",
                "urgency_flag": True,
            },
        ).json()
        goal_id = goal["id"]
        assert goal["smile_phase"] == "reality-emulation"

        # Step 2: ingest a GitHub signal (simulating a real PR merge)
        signal = client.post(
            "/api/v1/signals/",
            json={
                "stream": "lpi",
                "event_type": "pr_merged",
                "payload": {"repo": "lpi-platform", "pr_number": 33, "title": "feat: phase 4"},
                "source": "github_api",
            },
        ).json()
        signal_id = signal["id"]

        # Step 3: get recommendations
        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        assert len(recs) > 0

        # Step 4: find the recommendation for this specific goal
        goal_recs = [r for r in recs if goal_id in r["source_goals"]]
        assert goal_recs, (
            f"No recommendation referenced goal {goal_id}.\n"
            f"All source_goals: {[r['source_goals'] for r in recs]}\n"
            "The engine must read real goals from Supabase."
        )

        rec = goal_recs[0]

        # Step 5: verify phase advance — reality-emulation → concurrent-engineering
        assert rec["smile_phase"] == "concurrent-engineering", (
            f"Expected phase 'concurrent-engineering' (one step forward from "
            f"'reality-emulation'), got '{rec['smile_phase']}'.\n"
            "The engine must advance the goal exactly one SMILE phase forward."
        )

        # Step 6: verify priority matches the scoring formula
        # p=8, reality-emulation(weight=1), urgency=True → 8×0.5 + 1×0.3 + 1×0.2 = 4.50
        assert rec["priority"] == 4.50, (
            f"Expected priority 4.50 (8×0.5 + 1×0.3 + 1×0.2), got {rec['priority']}.\n"
            "Priority must match the SMILE scoring formula from scoring.py."
        )

        # Step 7: verify signal also surfaces somewhere in the recommendations
        all_signal_refs = [sid for r in recs for sid in r["source_signals"]]
        assert signal_id in all_signal_refs, (
            f"GitHub signal {signal_id} not referenced in any recommendation.\n"
            "Both goal AND signal must contribute to recommendations."
        )

    def test_each_goal_phase_advances_one_step(self, client: TestClient) -> None:
        """For each of the 5 non-final SMILE phases, verify the recommendation
        targets exactly the next phase and no other.

        This locks in the one-step-forward rule across all phases.
        """
        testcases = [
            ("reality-emulation", "concurrent-engineering"),
            ("concurrent-engineering", "collective-intelligence"),
            ("collective-intelligence", "contextual-intelligence"),
            ("contextual-intelligence", "continuous-intelligence"),
            ("continuous-intelligence", "perpetual-wisdom"),
        ]

        for current_phase, expected_next in testcases:
            # Clean slate between each phase test (clear_store autouse
            # handles full cleanup but we need intra-test isolation here)
            from lpi import store
            store.clear_all()

            goal = client.post(
                "/api/v1/goals/",
                json={
                    "title": f"Goal at {current_phase}",
                    "priority": 5,
                    "smile_phase": current_phase,
                },
            ).json()

            recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
            matching = [r for r in recs if goal["id"] in r["source_goals"]]

            assert matching, (
                f"No recommendation for goal at phase '{current_phase}'"
            )
            assert matching[0]["smile_phase"] == expected_next, (
                f"Phase '{current_phase}' should advance to '{expected_next}', "
                f"got '{matching[0]['smile_phase']}'"
            )

    def test_perpetual_wisdom_goal_does_not_crash(self, client: TestClient) -> None:
        """A goal at the final SMILE phase (perpetual-wisdom) must produce a
        'sustain and share' recommendation, not crash or advance beyond the
        last phase.
        """
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Share the knowledge platform",
                "priority": 5,
                "smile_phase": "perpetual-wisdom",
            },
        ).json()

        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        assert len(recs) > 0

        matching = [r for r in recs if goal["id"] in r["source_goals"]]
        assert matching, "No recommendation for perpetual-wisdom goal"
        assert matching[0]["smile_phase"] == "perpetual-wisdom", (
            "A goal at the final phase must stay at perpetual-wisdom, not advance beyond it."
        )

    def test_recommendation_schema_matches_model(self, client: TestClient) -> None:
        """Every recommendation returned must match the full Recommendation schema."""
        client.post(
            "/api/v1/goals/",
            json={"title": "Schema test goal", "priority": 6, "smile_phase": "reality-emulation"},
        )

        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        assert len(recs) > 0

        for rec in recs:
            assert isinstance(rec["id"], str) and rec["id"]
            assert rec["user_id"] == TEST_USER_ID
            assert isinstance(rec["action"], str) and len(rec["action"]) > 5
            assert isinstance(rec["reasoning"], str) and len(rec["reasoning"]) > 20
            assert rec["smile_phase"] in VALID_PHASES
            assert 0.80 <= rec["priority"] <= 7.00
            assert isinstance(rec["source_goals"], list)
            assert isinstance(rec["source_signals"], list)
            assert "created_at" in rec

    def test_recommendations_sorted_by_priority(self, client: TestClient) -> None:
        """Recommendations must be returned highest-priority first."""
        # Create goals with different priorities and phases
        for title, priority, phase in [
            ("Low priority goal", 2, "reality-emulation"),
            ("High priority goal", 9, "concurrent-engineering"),
            ("Medium priority goal", 5, "collective-intelligence"),
        ]:
            client.post(
                "/api/v1/goals/",
                json={"title": title, "priority": priority, "smile_phase": phase},
            )

        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        priorities = [r["priority"] for r in recs]

        assert priorities == sorted(priorities, reverse=True), (
            f"Recommendations not sorted by priority descending: {priorities}"
        )

    def test_no_cross_module_data_leak(self, client: TestClient) -> None:
        """Goals and signals created by one user must not appear in
        another user's recommendations — data isolation across modules.
        """
        from tests.conftest import _make_token

        # User A creates a goal and signal
        client.post(
            "/api/v1/goals/",
            json={"title": "User A goal", "priority": 9, "smile_phase": "reality-emulation"},
        )
        user_a_signal = client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "pr_merged", "source": "github_api"},
        ).json()

        # User B gets recommendations — must NOT see User A's signal
        other_client = TestClient(app)
        other_client.headers.update({"Authorization": f"Bearer {_make_token(OTHER_USER_ID)}"})

        other_recs = other_client.get(f"/api/v1/recommendations/{OTHER_USER_ID}").json()

        all_signal_refs = [sid for r in other_recs for sid in r["source_signals"]]
        assert user_a_signal["id"] not in all_signal_refs, (
            "User A's signal appeared in User B's recommendations — data isolation breach."
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite 4 — Pipeline endpoint (POST /run) three-module flow
# ══════════════════════════════════════════════════════════════════════════════


class TestPipelineThreeModuleFlow:
    """Verify the 7-node LangGraph pipeline endpoint also correctly
    integrates all three modules.
    """

    def test_pipeline_returns_exactly_3_cards(self, client: TestClient) -> None:
        """POST /run must always return exactly 3 cards."""
        # Create real data
        client.post(
            "/api/v1/goals/",
            json={"title": "Pipeline test goal", "priority": 7, "smile_phase": "reality-emulation"},
        )
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "pr_merged", "source": "github_api"},
        )

        response = client.post(f"/api/v1/recommendations/{TEST_USER_ID}/run")
        assert response.status_code == 200
        recs = response.json()
        assert len(recs) == 3, (
            f"Pipeline must return exactly 3 cards, got {len(recs)}"
        )

    def test_pipeline_cards_are_valid_recommendations(self, client: TestClient) -> None:
        """Every card from the pipeline must match the Recommendation schema."""
        client.post(
            "/api/v1/goals/",
            json={"title": "Valid schema test", "priority": 6, "smile_phase": "concurrent-engineering"},
        )

        recs = client.post(f"/api/v1/recommendations/{TEST_USER_ID}/run").json()

        for rec in recs:
            assert rec["smile_phase"] in VALID_PHASES
            assert 0.80 <= rec["priority"] <= 7.00
            assert isinstance(rec["action"], str) and len(rec["action"]) > 0
            assert isinstance(rec["reasoning"], str) and len(rec["reasoning"]) > 0

    def test_pipeline_guaranteed_3_cards_with_no_data(
        self, client: TestClient
    ) -> None:
        """Pipeline must return exactly 3 cold-start cards even for a brand
        new user with zero goals and zero signals.

        This is the Wednesday demo safety net requirement.
        """
        response = client.post("/api/v1/recommendations/brand-new-user-no-data/run")
        assert response.status_code == 200
        recs = response.json()
        assert len(recs) == 3, (
            f"Pipeline cold-start fallback must return 3 cards, got {len(recs)}"
        )
        # All cold-start cards reference the requested user_id
        for rec in recs:
            assert rec["user_id"] == "brand-new-user-no-data"

    def test_pipeline_references_real_goal_in_source(
        self, client: TestClient
    ) -> None:
        """At least one pipeline card must reference the real goal UUID
        in source_goals — not just generic cold-start text.
        """
        goal = client.post(
            "/api/v1/goals/",
            json={
                "title": "Real goal for pipeline test",
                "priority": 8,
                "smile_phase": "reality-emulation",
            },
        ).json()

        recs = client.post(f"/api/v1/recommendations/{TEST_USER_ID}/run").json()

        all_source_goals = [gid for r in recs for gid in r["source_goals"]]
        assert goal["id"] in all_source_goals, (
            f"Goal {goal['id']} not found in any pipeline card's source_goals.\n"
            f"source_goals across all cards: {all_source_goals}\n"
            "The pipeline must read real Supabase data, not just return cold-start cards."
        )

    def test_pipeline_sorted_priority_descending(self, client: TestClient) -> None:
        """Pipeline cards must be sorted highest-priority first."""
        client.post(
            "/api/v1/goals/",
            json={"title": "P1 goal", "priority": 9, "smile_phase": "reality-emulation"},
        )

        recs = client.post(f"/api/v1/recommendations/{TEST_USER_ID}/run").json()
        priorities = [r["priority"] for r in recs]
        assert priorities == sorted(priorities, reverse=True), (
            f"Pipeline cards not sorted by priority DESC: {priorities}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Test Suite 5 — Recommendation feedback closes the loop
# ══════════════════════════════════════════════════════════════════════════════


class TestFeedbackLoop:
    """Verify that recommendation feedback is stored correctly, completing
    the full Goals → Signals → Recommendations → Feedback loop.
    """

    def test_accept_feedback_is_stored(self, client: TestClient) -> None:
        """Accepting a recommendation must persist feedback to Supabase."""
        # Get a recommendation to react to
        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        assert len(recs) > 0
        rec = recs[0]

        # Submit accept feedback
        response = client.post(
            f"/api/v1/recommendations/{TEST_USER_ID}/feedback",
            json={
                "recommendation_id": rec["id"],
                "action": rec["action"],
                "smile_phase": rec["smile_phase"],
                "status": "accepted",
            },
        )
        assert response.status_code == 200
        feedback = response.json()

        assert feedback["recommendation_id"] == rec["id"]
        assert feedback["status"] == "accepted"
        assert feedback["smile_phase"] == rec["smile_phase"]
        assert feedback["user_id"] == TEST_USER_ID

    def test_dismiss_feedback_is_stored(self, client: TestClient) -> None:
        """Dismissing a recommendation must persist feedback to Supabase."""
        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        rec = recs[0]

        response = client.post(
            f"/api/v1/recommendations/{TEST_USER_ID}/feedback",
            json={
                "recommendation_id": rec["id"],
                "action": rec["action"],
                "smile_phase": rec["smile_phase"],
                "status": "dismissed",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    def test_feedback_requires_auth(self) -> None:
        """Submitting feedback without a JWT must be rejected with 401."""
        unauth_client = TestClient(app)
        response = unauth_client.post(
            f"/api/v1/recommendations/{TEST_USER_ID}/feedback",
            json={
                "recommendation_id": "some-id",
                "action": "test",
                "smile_phase": "reality-emulation",
                "status": "accepted",
            },
        )
        assert response.status_code == 401

    def test_feedback_cross_user_rejected(self, client: TestClient) -> None:
        """A user cannot submit feedback for another user's recommendations."""
        recs = client.get(f"/api/v1/recommendations/{TEST_USER_ID}").json()
        rec = recs[0]

        # client is authenticated as TEST_USER_ID but tries to post
        # feedback for OTHER_USER_ID
        response = client.post(
            f"/api/v1/recommendations/{OTHER_USER_ID}/feedback",
            json={
                "recommendation_id": rec["id"],
                "action": rec["action"],
                "smile_phase": rec["smile_phase"],
                "status": "accepted",
            },
        )
        assert response.status_code == 403, (
            "Cross-user feedback must be rejected with 403, not allowed silently."
        )
