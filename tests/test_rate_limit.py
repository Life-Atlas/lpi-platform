"""Tests for RateLimitMiddleware — fixed-window per-IP limiter.

Supabase-free. The local `clear_store` fixture overrides conftest's autouse
one so Supabase availability is never checked in this module.

Strategy: rather than making 60+ real HTTP calls per test, we pre-fill
the in-memory counter via _fill() to simulate being at the limit, then make
one final request and assert the 429 response. This keeps the suite fast.
"""

import time

import pytest
from fastapi.testclient import TestClient

from lpi.main import app
from lpi.middleware import rate_limit as rl

_TEST_IP = "testclient"  # IP Starlette assigns to TestClient requests


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_store():
    """Override conftest's autouse clear_store — no Supabase needed here."""
    rl._store.clear()
    yield
    rl._store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _fill(ip: str, limit_type: str, count: int) -> None:
    """Pre-fill the rate limit counter to simulate `count` prior requests."""
    bucket = int(time.time() // rl._WINDOW_SECONDS)
    rl._store[(ip, f"{limit_type}:{bucket}")] = count


# ── Happy path — requests below the limit pass through ────────────────────────


class TestRateLimitPassThrough:
    def test_health_passes_below_limit(self, client) -> None:
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT - 1)
        assert client.get("/health").status_code != 429

    def test_read_passes_below_limit(self, client) -> None:
        # recommendations GET has no auth — clean proxy for the read bucket
        _fill(_TEST_IP, "read", rl._READ_LIMIT - 1)
        assert client.get("/api/v1/recommendations/test-user").status_code != 429

    def test_write_passes_below_limit(self, client) -> None:
        # POST will hit auth (401) after rate limit passes — assert not 429
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT - 1)
        assert client.post("/api/v1/goals/", json={}).status_code != 429


# ── Limit enforced — requests at or over the limit return 429 ─────────────────


class TestRateLimitEnforced:
    def test_health_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT)
        assert client.get("/health").status_code == 429

    def test_read_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "read", rl._READ_LIMIT)
        assert client.get("/api/v1/recommendations/test-user").status_code == 429

    def test_goals_get_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "read", rl._READ_LIMIT)
        assert client.get("/api/v1/goals/").status_code == 429

    def test_goals_post_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.post("/api/v1/goals/", json={}).status_code == 429

    def test_goals_patch_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.patch("/api/v1/goals/some-id", json={}).status_code == 429

    def test_goals_delete_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.delete("/api/v1/goals/some-id").status_code == 429

    def test_signals_post_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.post("/api/v1/signals/", json={}).status_code == 429

    def test_signals_get_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "read", rl._READ_LIMIT)
        assert client.get("/api/v1/signals/").status_code == 429

    def test_recommendations_get_429_at_limit(self, client) -> None:
        _fill(_TEST_IP, "read", rl._READ_LIMIT)
        assert client.get("/api/v1/recommendations/test-user").status_code == 429


# ── 429 response format ───────────────────────────────────────────────────────


class TestRateLimitResponse:
    def test_429_detail_message(self, client) -> None:
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT)
        response = client.get("/health")
        assert response.json()["detail"] == "Rate limit exceeded. Please slow down."

    def test_429_has_retry_after_header(self, client) -> None:
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT)
        response = client.get("/health")
        assert "retry-after" in response.headers

    def test_retry_after_is_positive_integer_within_window(self, client) -> None:
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT)
        response = client.get("/health")
        retry_after = int(response.headers["retry-after"])
        assert 0 < retry_after <= rl._WINDOW_SECONDS


# ── CORS preflight bypass ─────────────────────────────────────────────────────


class TestOptionsAlwaysBypasses:
    def test_options_bypasses_write_limit(self, client) -> None:
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.options("/api/v1/goals/").status_code != 429

    def test_options_bypasses_read_limit(self, client) -> None:
        _fill(_TEST_IP, "read", rl._READ_LIMIT)
        assert client.options("/api/v1/signals/").status_code != 429


# ── Per-IP isolation ──────────────────────────────────────────────────────────


class TestRateLimitIsolation:
    def test_different_ips_have_independent_counters(self, client) -> None:
        # Exhaust read limit for a different IP — testclient should still pass
        _fill("192.168.1.99", "read", rl._READ_LIMIT)
        assert client.get("/api/v1/recommendations/test-user").status_code != 429

    def test_x_forwarded_for_header_is_used_as_ip(self, client) -> None:
        _fill("10.0.0.1", "read", rl._READ_LIMIT)
        response = client.get(
            "/api/v1/recommendations/test-user",
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert response.status_code == 429

    def test_write_and_read_buckets_are_independent(self, client) -> None:
        # Exhausting the write bucket must not affect the read bucket
        _fill(_TEST_IP, "write", rl._WRITE_LIMIT)
        assert client.get("/api/v1/recommendations/test-user").status_code != 429

    def test_health_bucket_is_independent_of_read(self, client) -> None:
        # Exhausting /health bucket must not affect other GET requests
        _fill(_TEST_IP, "health", rl._HEALTH_LIMIT)
        assert client.get("/api/v1/recommendations/test-user").status_code != 429
