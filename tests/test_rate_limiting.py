"""Tests for per-endpoint rate limiting.

All tests here are marked @pytest.mark.no_store — they use endpoints that
return without touching the database (recommendations returns [], signals
returns 501), so Supabase does not need to be running.

The autouse _disable_rate_limit fixture in conftest.py keeps the limiter off
for every other test file. The rate_limit_enabled fixture here re-enables it
with a fresh storage bucket so these tests run in isolation.

Endpoints used and their limits:
  GET /api/v1/recommendations/{user_id}  →  30 / minute
  GET /api/v1/signals/                   →  60 / minute
  GET /health                            →  60 / minute
"""

import pytest
from fastapi.testclient import TestClient

from lpi.middleware.rate_limit import limiter

pytestmark = pytest.mark.no_store


@pytest.fixture
def rate_limit_enabled():
    """Re-enable the limiter with a clean bucket store for this test only.

    Uses reset() on the existing storage rather than replacing the object —
    limiter._limiter holds a reference to limiter._storage, so swapping the
    attribute has no effect on the actual counter.
    """
    limiter._storage.reset()
    limiter.enabled = True
    yield
    limiter._storage.reset()
    limiter.enabled = False


# ─────────────────────────────────────────────────────────────
# Core limit behaviour — GET /api/v1/recommendations/{user_id}
# limit: 30 / minute, no DB call (returns [])
# ─────────────────────────────────────────────────────────────

RECO_URL = "/api/v1/recommendations/test-user"


class TestRecommendationsRateLimit:
    def test_under_limit_never_429(self, client: TestClient, rate_limit_enabled) -> None:
        for _ in range(5):
            r = client.get(RECO_URL)
            assert r.status_code != 429

    def test_at_boundary_last_request_succeeds(
        self, client: TestClient, rate_limit_enabled
    ) -> None:
        """The 30th request must still return 200 (not yet exceeded)."""
        for _ in range(29):
            client.get(RECO_URL)
        r = client.get(RECO_URL)
        assert r.status_code == 200

    def test_over_limit_returns_429(self, client: TestClient, rate_limit_enabled) -> None:
        for _ in range(30):
            client.get(RECO_URL)
        r = client.get(RECO_URL)
        assert r.status_code == 429

    def test_429_response_is_json(self, client: TestClient, rate_limit_enabled) -> None:
        for _ in range(30):
            client.get(RECO_URL)
        r = client.get(RECO_URL)
        assert r.status_code == 429
        assert r.headers["content-type"].startswith("application/json")

    def test_successive_requests_after_429_also_429(
        self, client: TestClient, rate_limit_enabled
    ) -> None:
        """Once the limit is hit, every further request in the window is 429."""
        for _ in range(30):
            client.get(RECO_URL)
        for _ in range(3):
            assert client.get(RECO_URL).status_code == 429


# ─────────────────────────────────────────────────────────────
# Bucket independence — different endpoints must not share state
# ─────────────────────────────────────────────────────────────


class TestBucketsArePerEndpoint:
    def test_recommendations_exhausted_does_not_block_signals(
        self, client: TestClient, rate_limit_enabled
    ) -> None:
        """Exhaust recommendations (30/min); signals bucket must be untouched."""
        for _ in range(30):
            client.get(RECO_URL)
        assert client.get(RECO_URL).status_code == 429

        # signals list has its own 60/min bucket — must not be 429
        r = client.get("/api/v1/signals/")
        assert r.status_code != 429

    def test_signals_exhausted_does_not_block_recommendations(
        self, client: TestClient, rate_limit_enabled
    ) -> None:
        """Exhaust signals (60/min); recommendations bucket (30/min) must be untouched."""
        for _ in range(60):
            client.get("/api/v1/signals/")
        assert client.get("/api/v1/signals/").status_code == 429

        r = client.get(RECO_URL)
        assert r.status_code != 429

    def test_health_and_recommendations_are_independent(
        self, client: TestClient, rate_limit_enabled
    ) -> None:
        """Exhaust recommendations; /health must still respond."""
        for _ in range(30):
            client.get(RECO_URL)
        assert client.get(RECO_URL).status_code == 429

        r = client.get("/health")
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────
# Sanity — autouse _disable_rate_limit keeps other tests safe
# ─────────────────────────────────────────────────────────────


class TestLimiterDisabledInNormalTests:
    """Without rate_limit_enabled, many calls must never produce 429.

    If the autouse fixture in conftest.py broke, every other test file
    could start seeing spurious 429s — this catches that regression.
    """

    def test_many_recommendation_calls_never_429(self, client: TestClient) -> None:
        for _ in range(35):
            r = client.get(RECO_URL)
            assert r.status_code != 429

    def test_many_signal_calls_never_429(self, client: TestClient) -> None:
        for _ in range(65):
            r = client.get("/api/v1/signals/")
            assert r.status_code != 429
