"""Shared pytest fixtures for the LPI Platform.

SMILE correction: sample_goal now uses "reality-emulation" (Phase 1 of
the correct 6-phase framework) instead of the hallucinated "sense" value.

The autouse `clear_store` fixture is the most important thing in this file.
Without it, a goal created in TestCreateGoal leaks into TestReadGoal,
making test_list_goals see unexpected data and fail non-deterministically
depending on test execution order. autouse=True applies it to every test
automatically without any explicit request.

SUPABASE IN TESTS
─────────────────
Tests run against a LOCAL Supabase instance. Ensure your .env file has:
    SUPABASE_URL=http://127.0.0.1:54321
    SUPABASE_KEY=<local service_role key from `supabase status`>

If Supabase is unavailable, tests that require a live DB connection will
be skipped automatically (pytest.skip) rather than failing with a
connection error. Run `supabase start` in the project root to enable them.

Tests that do NOT touch the store (e.g. test_scoring.py) are unaffected
by Supabase availability — they always run.
"""

import time
import uuid
from collections.abc import Generator

import jwt
import pytest
from fastapi.testclient import TestClient

from lpi import store
from lpi.config import settings
from lpi.main import app
from lpi.middleware.rate_limit import (
    _store as _rate_limit_store,  # Access the in-memory rate-limit store to reset it in tests
)
from lpi.utils.logging import clear_all_logs

# Fixed test secret + user id so every test gets a valid Supabase-style JWT
# without needing a live Supabase Auth server.
TEST_JWT_SECRET = "test-secret-for-lpi-platform-tests-only-32-chars"
TEST_USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))


def _make_token(user_id: str = TEST_USER_ID) -> str:
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def _supabase_available() -> bool:
    """Return True only when the local Supabase instance is reachable.

    Attempts a lightweight query (list goals with limit 0). If it raises
    for any reason — missing env vars, connection refused, auth error —
    returns False so the caller can skip the test rather than crash.
    """
    try:
        store.list_goals()
        return True
    except Exception as e:
        print("SUPABASE CHECK FAILED:", repr(e))
        return False


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure get_current_user can verify the test JWT regardless of .env."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def clear_store() -> Generator[None, None, None]:
    """Wipe all Supabase + in-memory state before and after every test.

    The `yield` splits setup (before) from teardown (after).
    Both sides are cleared so a failing test cannot pollute the next one.

    If Supabase is unreachable the fixture skips the test with a clear
    message instead of raising a cryptic connection error. Tests that
    only use in-memory scoring (test_scoring.py) create no Goals and
    never call the store, so they run fine regardless.
    """
    if not _supabase_available():
        pytest.skip("Local Supabase is not running. Start it with `supabase start` then re-run.")

    store.clear_all()
    clear_all_logs()
    _rate_limit_store.clear()  # Reset the in-memory rate-limit counters
    yield
    store.clear_all()
    clear_all_logs()
    _rate_limit_store.clear()  # Reset the in-memory rate-limit counters

@pytest.fixture
def client() -> TestClient:
    """FastAPI test client — shared across all test modules.

    Pre-authenticated with a valid Supabase-style JWT (TEST_USER_ID) so
    authenticated routes work without a live Supabase Auth server.
    """
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": f"Bearer {_make_token()}"})
    return test_client


@pytest.fixture
def unauthenticated_client() -> TestClient:
    """FastAPI test client without Authorization header."""
    return TestClient(app)

@pytest.fixture
def admin_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI test client whose JWT subject is treated as an admin.

    Reuses TEST_USER_ID's token but flips settings.admin_user_ids so
    get_current_user_context() resolves is_admin=True for the duration of
    this test only (monkeypatch auto-reverts after the test). Needed for
    any endpoint gated like GET /api/v1/users/map or
    GET /api/v1/metrics/team.
    """
    monkeypatch.setattr(settings, "admin_user_ids", TEST_USER_ID)
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": f"Bearer {_make_token()}"})
    return test_client


@pytest.fixture
def sample_goal() -> dict:
    """A minimal valid goal payload.

    SMILE correction: smile_phase changed from "sense" (hallucinated) to
    "reality-emulation" (Phase 1 of the correct SMILE framework).
    This is the default starting phase for any new LPI goal.
    """
    return {
        "title": "Learn Docker",
        "description": "Containerize my applications",
        "priority": 7,
        "smile_phase": "reality-emulation",  # CORRECTED: was "sense"
    }


@pytest.fixture
def sample_signal() -> dict:
    return {
        "stream": "boardy",
        "event_type": "match_created",
        "timestamp": "2026-06-11T10:00:00Z",
        "payload": {"person_a": "Alice", "person_b": "Bob", "score": 0.85},
    }
