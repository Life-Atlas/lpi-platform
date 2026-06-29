"""Tests for GET /api/v1/metrics/team — Priority 1 Engineering Velocity & Inactivity.

Owner : Adil Islam
QA    : Daksh Garg

HOW THESE TESTS WORK
─────────────────────
Same integration-test pattern as test_activity_signals.py / test_goal_crud.py:
real FastAPI endpoints, real local Supabase, autouse `clear_store` fixture
(conftest.py) wipes goals + activity_signals before and after every test.

ADMIN GATING
─────────────
/metrics/team is admin-only (mirrors GET /api/v1/users/map). The `client`
fixture's TEST_USER_ID is NOT an admin by default, so most tests use the
`admin_client` fixture (conftest.py) instead, which monkeypatches
settings.admin_user_ids for the duration of the test.

WHY TEST_USER_ID IS RE-DECLARED HERE INSTEAD OF IMPORTED
────────────────────────────────────────────────────────────
tests/ has no __init__.py, so `from tests.conftest import TEST_USER_ID`
is fragile depending on how pytest's rootdir import-mode resolves things.
Re-declaring the literal here (it must match conftest.py's TEST_USER_ID —
both authenticate via the same fixtures) is simpler and more robust than
relying on a cross-module import. settings.supabase_jwt_secret, by
contrast, IS safe to read live: conftest's autouse `_jwt_secret` fixture
patches it before every test runs, so _token_for() below always signs
with the same secret get_current_user() verifies against.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from lpi import store
from lpi.config import settings
from lpi.models import Signal
from lpi.routers import metrics as metrics_module

# Must match conftest.py's TEST_USER_ID — the `client`/`admin_client`
# fixtures always authenticate as this UUID.
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def _token_for(user_id: str) -> str:
    """Sign a test JWT for an arbitrary user_id, reusing the secret
    conftest's autouse _jwt_secret fixture already patched into
    settings.supabase_jwt_secret. Lets a test simulate a second team
    member without needing a real Supabase Auth user record.
    """
    payload = {"sub": user_id, "aud": "authenticated", "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.supabase_jwt_secret, algorithm="HS256")


class TestAuthGating:
    """/metrics/team must reject non-admins and unauthenticated callers."""

    def test_requires_auth(self, unauthenticated_client) -> None:
        response = unauthenticated_client.get("/api/v1/metrics/team")
        assert response.status_code == 401

    def test_rejects_non_admin(self, client) -> None:
        """TEST_USER_ID is a regular (non-admin) caller by default."""
        response = client.get("/api/v1/metrics/team")
        assert response.status_code == 403

    def test_allows_admin(self, admin_client) -> None:
        response = admin_client.get("/api/v1/metrics/team")
        assert response.status_code == 200


class TestEmptyState:
    """On a freshly wiped store, every count should be zero, not missing."""

    def test_empty_team_summary(self, admin_client) -> None:
        response = admin_client.get("/api/v1/metrics/team")
        assert response.status_code == 200
        data = response.json()

        assert data["team_summary"] == {
            "total_signals": 0,
            "active_users": 0,
            "inactive_users": 0,
            "avg_signals_per_active_user": 0.0,
            "total_pr_merges": 0,
            "total_commits": 0,
        }
        assert data["per_user_velocity"] == {}
        assert data["inactive_users"] == []

    def test_goals_summary_zero_fills_all_six_phases(self, admin_client) -> None:
        """by_phase must list all 6 SMILE phases at 0, not omit empty ones —
        the frontend renders a fixed 6-bar chart and shouldn't need
        defensive .get(key, 0) calls.
        """
        response = admin_client.get("/api/v1/metrics/team")
        by_phase = response.json()["goals_summary"]["by_phase"]

        assert set(by_phase.keys()) == {
            "reality-emulation",
            "concurrent-engineering",
            "collective-intelligence",
            "contextual-intelligence",
            "continuous-intelligence",
            "perpetual-wisdom",
        }
        assert all(count == 0 for count in by_phase.values())
        assert response.json()["goals_summary"]["total_goals"] == 0


class TestSignalAggregation:
    """Core counting logic: pr_merges/commits/signal_count/streams."""

    def test_counts_pr_merged_and_commit_pushed(self, client, admin_client) -> None:
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "pr_merged", "payload": {}},
        )
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "commit_pushed", "payload": {}},
        )
        # A non-engineering signal should count toward signal_count/streams
        # but NOT toward pr_merges/commits.
        client.post(
            "/api/v1/signals/",
            json={"stream": "boardy", "event_type": "match_created", "payload": {}},
        )

        data = admin_client.get("/api/v1/metrics/team").json()

        assert data["team_summary"]["total_signals"] == 3
        assert data["team_summary"]["total_pr_merges"] == 1
        assert data["team_summary"]["total_commits"] == 1

        user_row = data["per_user_velocity"][TEST_USER_ID]
        assert user_row["signal_count"] == 3
        assert user_row["pr_merges"] == 1
        assert user_row["commits"] == 1
        assert sorted(user_row["streams"]) == ["boardy", "lpi"]

    def test_unmerged_pr_event_type_not_counted_as_merge(self, client, admin_client) -> None:
        """Raw GitHub event types from the dynamic per-goal sync endpoint
        (PullRequestEvent/PushEvent) aren't filtered for merged status —
        see routers/metrics.py module docstring. Must count toward
        signal_count but NOT pr_merges, since an unmerged 'PullRequestEvent'
        would otherwise inflate the merge count.
        """
        client.post(
            "/api/v1/signals/",
            json={"stream": "github", "event_type": "PullRequestEvent", "payload": {}},
        )

        data = admin_client.get("/api/v1/metrics/team").json()
        assert data["team_summary"]["total_signals"] == 1
        assert data["team_summary"]["total_pr_merges"] == 0

    def test_aggregates_across_multiple_users(self, client, admin_client) -> None:
        other_user_id = str(uuid.uuid4())
        other_headers = {"Authorization": f"Bearer {_token_for(other_user_id)}"}

        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "commit_pushed", "payload": {}},
        )
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "commit_pushed", "payload": {}},
            headers=other_headers,
        )

        data = admin_client.get("/api/v1/metrics/team").json()

        assert data["team_summary"]["total_signals"] == 2
        assert TEST_USER_ID in data["per_user_velocity"]
        assert other_user_id in data["per_user_velocity"]
        assert data["per_user_velocity"][other_user_id]["commits"] == 1


class TestActiveInactiveClassification:
    """A user freshly active right now must count as active; a user whose
    last signal is 10 days old must show up in inactive_users with a
    matching days_inactive/last_seen.
    """

    def test_fresh_signal_counts_as_active(self, client, admin_client) -> None:
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "commit_pushed", "payload": {}},
        )

        data = admin_client.get("/api/v1/metrics/team").json()
        assert data["team_summary"]["active_users"] == 1
        assert data["team_summary"]["inactive_users"] == 0
        assert data["inactive_users"] == []

    def test_zero_day_threshold_makes_everyone_inactive(self, client, admin_client) -> None:
        """Boundary check on the strict `<` comparison: with
        inactive_threshold_days=0, even a signal from this instant doesn't
        satisfy days_inactive < 0, so the user is classified inactive.
        """
        client.post(
            "/api/v1/signals/",
            json={"stream": "lpi", "event_type": "commit_pushed", "payload": {}},
        )

        data = admin_client.get("/api/v1/metrics/team?inactive_threshold_days=0").json()

        assert data["team_summary"]["active_users"] == 0
        assert data["team_summary"]["inactive_users"] == 1
        assert data["inactive_users"][0]["user_id"] == TEST_USER_ID

    def test_old_signal_flagged_inactive_with_default_threshold(self, admin_client) -> None:
        """Seed a 10-day-old signal directly through store.insert_signal()
        (bypassing the API, which always stamps `now`) to simulate a team
        member who's gone quiet — then verify the default 3-day threshold
        correctly flags them.
        """
        old_timestamp = datetime.now(UTC) - timedelta(days=10)
        store.insert_signal(
            Signal(
                id=str(uuid.uuid4()),
                user_id=TEST_USER_ID,
                stream="lpi",
                event_type="commit_pushed",
                payload={},
                source="api",
                timestamp=old_timestamp,
            )
        )

        data = admin_client.get("/api/v1/metrics/team").json()

        assert data["team_summary"]["active_users"] == 0
        assert data["team_summary"]["inactive_users"] == 1

        detail = data["inactive_users"][0]
        assert detail["user_id"] == TEST_USER_ID
        assert detail["days_inactive"] >= 10


class TestGoalAdvances:
    """goal_advances must count only FORWARD SMILE phase transitions —
    a backward re-evaluation move is valid LPI usage but isn't 'velocity'.
    """

    def test_forward_transition_counts_backward_does_not(self, client, admin_client) -> None:
        goal_id = client.post(
            "/api/v1/goals/",
            json={
                "title": "Ship Phase 4",
                "priority": 8,
                "smile_phase": "reality-emulation",
            },
        ).json()["id"]

        # Forward: reality-emulation -> concurrent-engineering (counts)
        client.patch(
            f"/api/v1/goals/{goal_id}",
            json={"smile_phase": "concurrent-engineering"},
        )
        # Backward: concurrent-engineering -> reality-emulation (re-evaluation,
        # explicitly allowed by SMILE — must NOT count as an "advance")
        client.patch(
            f"/api/v1/goals/{goal_id}",
            json={"smile_phase": "reality-emulation"},
        )

        data = admin_client.get("/api/v1/metrics/team").json()
        assert data["per_user_velocity"][TEST_USER_ID]["goal_advances"] == 1


class TestPaginationBoundary:
    """_fetch_all_signals() must page past a single batch instead of
    silently truncating at the per-call limit. Rather than inserting
    hundreds of real rows, shrink the page size to 3 and insert 7 signals —
    proves the offset-increment loop actually crosses a page boundary.
    """

    def test_pages_past_a_single_batch(self, client, admin_client, monkeypatch) -> None:
        monkeypatch.setattr(metrics_module, "_SIGNALS_PAGE_SIZE", 3)

        for i in range(7):
            client.post(
                "/api/v1/signals/",
                json={"stream": "lpi", "event_type": f"event_{i}", "payload": {}},
            )

        data = admin_client.get("/api/v1/metrics/team").json()
        assert data["team_summary"]["total_signals"] == 7

class TestParseUtcTimestamp:
    """Direct unit tests for metrics.py::_parse_utc_timestamp() — added in
    response to PR review point 3 (Daksh).

    NOTE: a real Supabase round-trip can't actually produce a naive string
    here — transitioned_at is TIMESTAMPTZ and PostgREST always serialises
    timestamptz columns with an explicit offset on read (verified against
    supabase/migrations/20260605000000_create_goal_phase_transitions.sql).
    That's why this is a direct unit test of the helper, not an
    integration test through the API — an integration test would pass
    even without the fix and wouldn't prove anything.
    """

    def test_returns_none_for_empty_input(self) -> None:
        assert metrics_module._parse_utc_timestamp(None) is None
        assert metrics_module._parse_utc_timestamp("") is None

    def test_passes_through_an_already_aware_string(self) -> None:
        result = metrics_module._parse_utc_timestamp("2026-06-20T10:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_coerces_a_naive_string_to_utc_instead_of_crashing(self) -> None:
        """The exact scenario Daksh's review flagged: a transitioned_at
        string with no offset must not raise when later compared against
        a timezone-aware datetime (e.g. a Signal.timestamp) elsewhere in
        the aggregation pass.
        """
        result = metrics_module._parse_utc_timestamp("2026-06-20T10:00:00")
        assert result is not None
        assert result.tzinfo is not None  # would be None pre-fix — that's the bug

        # Confirm the comparison that would TypeError pre-fix now works
        aware_now = datetime.now(UTC)
        assert result < aware_now