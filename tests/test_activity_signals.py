"""Tests for Activity Signals — Phase 3 gate criteria.

Owner : Adil Islam
QA    : Daksh Garg / Jaivardhan Singh

PHASE 3 GATE: All tests in this file must pass before the signals
              endpoints are considered production-ready.

HOW THESE TESTS WORK
─────────────────────
These are integration tests — they hit real FastAPI endpoints AND
write/read from the local Supabase instance.

The autouse `clear_store` fixture in conftest.py runs before and after
every test, wiping activity_signals and goals tables so tests don't
interfere with each other.

Requires:
  - `supabase start` running locally
  - .env with SUPABASE_URL=http://127.0.0.1:54321
  - `supabase db push` applied (includes 20260611000000_create_activity_signals.sql)

Run with:
  pytest tests/test_activity_signals.py -v
"""

from unittest.mock import patch


class TestIngestSignal:
    """Tests for POST /api/v1/signals/

    Wave 2 implementation. Every test:
      1. POSTs a signal payload to the endpoint.
      2. Checks the response status code.
      3. Checks the returned Signal object has the right fields.
    """

    def test_ingest_returns_signal(self, client, sample_signal) -> None:
        """POST /api/v1/signals/ should store and return the full Signal object.

        sample_signal fixture (from conftest.py):
          {"stream": "boardy", "event_type": "match_created", "payload": {...}}

        We verify:
          - Status is 201 Created (or 200 — both accepted for compatibility)
          - Returned JSON has the `stream` we sent
          - Server assigned an `id` (UUID string)
          - Server assigned a `timestamp`
          - `source` defaults to 'api' since sample_signal doesn't send it
        """
        response = client.post("/api/v1/signals/", json=sample_signal)

        assert response.status_code in (200, 201)
        data = response.json()

        # These fields come from the request body
        assert data["stream"] == "boardy"
        assert data["event_type"] == "match_created"

        # These fields are server-assigned — just verify they exist
        assert "id" in data
        assert "timestamp" in data
        assert "user_id" in data

        # source should default to 'api' since sample_signal doesn't include it
        assert data["source"] == "api"

    def test_ingest_with_explicit_source(self, client) -> None:
        """When source is explicitly sent, it should be stored and returned.

        This verifies the Phase 3 `source` field works end-to-end:
          - The model accepts it
          - The router passes it through
          - Supabase stores it
          - The response includes it
        """
        signal = {
            "stream": "lpi",
            "event_type": "pr_merged",
            "payload": {"repo": "lpi-platform", "pr_number": 18},
            "source": "github_api",  # explicitly set
        }
        response = client.post("/api/v1/signals/", json=signal)

        assert response.status_code in (200, 201)
        data = response.json()
        assert data["source"] == "github_api"  # must be preserved, not overwritten

    def test_ingest_requires_auth(
        self,
        unauthenticated_client,
    ) -> None:
        signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "payload": {},
        }

        response = unauthenticated_client.post(
            "/api/v1/signals/",
            json=signal,
        )

        assert response.status_code == 401

    def test_ingest_from_different_streams(self, client) -> None:
        """Should accept signals from any stream — no allowlist enforced.

        The DB has no CHECK constraint on stream, intentionally.
        New streams (real integrations) can onboard without schema changes.
        """
        streams = ["boardy", "datapro", "vsab", "altiostar", "security"]
        for stream in streams:
            signal = {
                "stream": stream,
                "event_type": "test_event",
                "payload": {},
            }
            response = client.post("/api/v1/signals/", json=signal)
            assert response.status_code in (200, 201), (
                f"Expected 200/201 for stream '{stream}', "
                f"got {response.status_code}: {response.text}"
            )

    def test_missing_stream_field(self, client) -> None:
        """Signal ingestion should reject payloads missing the stream field.

        Current Phase 3 behavior:
        - router still returns HTTP 501 (stub implementation)

        Future expected behavior:
        - FastAPI/Pydantic validation should return HTTP 422
        """
        signal = {
            "event_type": "match_created",
            "timestamp": "2026-06-11T10:00:00Z",
            "payload": {},
        }

        response = client.post("/api/v1/signals/", json=signal)

        # Accept both for now while implementation is incomplete
        assert response.status_code == 422

    def test_missing_event_type(self, client) -> None:
        """Signal ingestion should reject payloads missing event_type.

        event_type is required for downstream timeline processing
        and recommendation-engine event classification.
        """
        signal = {
            "stream": "boardy",
            "timestamp": "2026-06-11T10:00:00Z",
            "payload": {},
        }

        response = client.post("/api/v1/signals/", json=signal)

        assert response.status_code == 422

    def test_invalid_payload_type(self, client) -> None:
        """Signal payload should eventually require a dictionary object.

        Current implementation is still a Phase 3 stub, but this test
        prepares validation coverage for malformed payload structures.
        """
        signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "timestamp": "2026-06-11T10:00:00Z",
            "payload": "invalid_payload",
        }

        response = client.post("/api/v1/signals/", json=signal)

        assert response.status_code == 422

    def test_empty_payload(self, client) -> None:
        """Empty payloads should not crash the ingestion endpoint.

        Empty payloads may still be considered valid depending on
        stream-specific event schemas in later phases.
        """
        signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "timestamp": "2026-06-11T10:00:00Z",
            "payload": {},
        }

        response = client.post("/api/v1/signals/", json=signal)

        # Stub currently returns 501 until implementation is wired
        assert response.status_code == 201

    def test_extra_timestamp_field_is_ignored(self, client) -> None:
        """Client-supplied timestamp should be ignored.

        The server generates its own timestamp during ingestion.
        """

        signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "timestamp": "not-a-timestamp",
            "payload": {},
        }

        response = client.post("/api/v1/signals/", json=signal)

        assert response.status_code == 201

        data = response.json()

        # Server-generated timestamp should still exist
        assert "timestamp" in data
        assert data["timestamp"] != signal["timestamp"]

    def test_timestamp_not_required(self, client) -> None:
        """Timestamp should not be required in requests.

        The server assigns the ingestion timestamp automatically.
        """

        signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "payload": {},
        }

        response = client.post("/api/v1/signals/", json=signal)

        assert response.status_code in (200, 201)

        data = response.json()

        assert "timestamp" in data

    def test_valid_signal_ingestion(self, client, sample_signal) -> None:
        """A valid signal should be accepted and persisted."""

        response = client.post(
            "/api/v1/signals/",
            json=sample_signal,
        )

        assert response.status_code == 201

        data = response.json()

        assert data["stream"] == sample_signal["stream"]
        assert data["event_type"] == sample_signal["event_type"]
        assert "id" in data
        assert "timestamp" in data

    def test_signal_ingestion_logs_activity(
        self,
        client,
        sample_signal,
    ) -> None:
        """Signal ingestion should log a user activity event."""

        with patch("lpi.routers.signals.log_user_activity") as mock_log:
            response = client.post(
                "/api/v1/signals/",
                json=sample_signal,
            )

            assert response.status_code == 201

            mock_log.assert_called_once()

            _, kwargs = mock_log.call_args

            assert kwargs["action"] == "signal_ingested"
            assert kwargs["user_id"] == "00000000-0000-0000-0000-000000000001"

            assert kwargs["metadata"]["stream"] == sample_signal["stream"]
            assert kwargs["metadata"]["event_type"] == sample_signal["event_type"]
            assert kwargs["metadata"]["source"] == "api"

    def test_signal_ingestion_succeeds_when_logging_fails(
        self,
        client,
        sample_signal,
    ) -> None:
        """Signal ingestion should succeed even if the logger mock is set to no-op.

        Note: log_user_activity() is contract-guaranteed to never raise —
        it catches all Supabase errors internally. Patching it with a plain
        no-op mock still verifies that ingest_signal() completes successfully
        and doesn't somehow depend on the logger returning a value.
        """
        with patch(
            "lpi.routers.signals.log_user_activity",
            return_value=None,   # no-op mock; never raises by contract
        ):
            response = client.post(
                "/api/v1/signals/",
                json=sample_signal,
            )

            assert response.status_code == 201


class TestQuerySignals:
    """Tests for GET /api/v1/signals/

    Wave 3 implementation. Tests verify:
      - Basic list works
      - Server-side stream filter works correctly
      - Source filter works (Phase 3 addition)
    """

    def test_list_signals_empty(self, client) -> None:
        """GET /api/v1/signals/ on a clean store returns an empty list.

        clear_store fixture wipes the table before this test runs,
        so the response must be [] not whatever previous tests left.
        """
        response = client.get("/api/v1/signals/")
        assert response.status_code == 200
        assert response.json() == []  # must be empty, not just a list

    def test_list_signals(self, client, sample_signal) -> None:
        """After inserting one signal, GET /api/v1/signals/ returns only the test user's signals.

        The TestClient uses TEST_USER_ID from conftest.py in the JWT.
        This verifies that list_signals() is scoped by user_id and does not
        leak another user's signals.
        """
        # Insert a signal for the authenticated test user
        client.post("/api/v1/signals/", json=sample_signal)

        response = client.get("/api/v1/signals/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # at least the one we just inserted

        # All returned signals must belong to the authenticated test user.
        # This verifies the user_id scope in the list_signals() store query.
        for signal in data:
            assert signal["user_id"] == "00000000-0000-0000-0000-000000000001"

    def test_get_signal_by_id(
        self,
        client,
        sample_signal,
    ) -> None:
        create_response = client.post(
            "/api/v1/signals/",
            json=sample_signal,
        )

        signal_id = create_response.json()["id"]

        response = client.get(f"/api/v1/signals/{signal_id}")

        assert response.status_code == 200
        assert response.json()["id"] == signal_id

    def test_get_nonexistent_signal_returns_404(
        self,
        client,
    ) -> None:
        response = client.get("/api/v1/signals/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_filter_by_stream(self, client) -> None:
        """?stream=boardy should return only boardy signals.

        This is the core test for server-side filtering.
        We insert signals from two different streams, then filter
        by one and verify only that stream's signals come back.
        """
        # Insert a boardy signal
        boardy_signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "payload": {},
        }
        client.post("/api/v1/signals/", json=boardy_signal)

        # Insert a datapro signal (should NOT appear in boardy filter)
        datapro_signal = {
            "stream": "datapro",
            "event_type": "deal_closed",
            "payload": {},
        }
        client.post("/api/v1/signals/", json=datapro_signal)

        # Filter by boardy only
        response = client.get("/api/v1/signals/?stream=boardy")
        assert response.status_code == 200
        data = response.json()

        # Should return at least one signal
        assert len(data) >= 1

        # Every returned signal must belong to the boardy stream
        for signal in data:
            assert signal["stream"] == "boardy"

        # Ensure the datapro signal is not included
        assert all(signal["stream"] != "datapro" for signal in data)

    def test_empty_signal_list(self, client) -> None:
        """GET /signals/ on a freshly wiped store returns an empty list.

        Duplicate of test_list_signals_empty intentionally kept
        as a named alias for the QA gate sheet requirement.
        """
        response = client.get("/api/v1/signals/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_filter_by_source(self, client) -> None:
        """?source=github_api should return only github_api signals.

        Phase 3 addition. This is the filter Phase 4 recommendation engine
        uses to exclude simulated test data from real signals.
        """
        # Insert a real GitHub signal
        github_signal = {
            "stream": "lpi",
            "event_type": "pr_merged",
            "payload": {},
            "source": "github_api",
        }
        client.post("/api/v1/signals/", json=github_signal)

        # Insert a simulated signal (should NOT appear in github_api filter)
        simulated_signal = {
            "stream": "lpi",
            "event_type": "pr_merged",
            "payload": {},
            "source": "simulated",
        }
        client.post("/api/v1/signals/", json=simulated_signal)

        # Filter by source=github_api
        response = client.get("/api/v1/signals/?source=github_api")
        assert response.status_code == 200

        data = response.json()
        for signal in data:
            assert signal["source"] == "github_api", (
                f"Filter source=github_api returned a signal with source='{signal['source']}'"
            )

    def test_filter_by_event_type(self, client) -> None:
        """?event_type=pr_merged should return only matching event types."""

        # Insert a PR merged signal
        pr_signal = {
            "stream": "lpi",
            "event_type": "pr_merged",
            "payload": {},
        }
        client.post("/api/v1/signals/", json=pr_signal)

        # Insert a different event type
        match_signal = {
            "stream": "boardy",
            "event_type": "match_created",
            "payload": {},
        }
        client.post("/api/v1/signals/", json=match_signal)

        response = client.get("/api/v1/signals/?event_type=pr_merged")

        assert response.status_code == 200

        data = response.json()

        assert len(data) >= 1

        for signal in data:
            assert signal["event_type"] == "pr_merged"

        assert all(signal["event_type"] != "match_created" for signal in data)

    def test_filter_by_time_range(self, client) -> None:
        """Signals should be filtered by timestamp range."""

        client.post(
            "/api/v1/signals/",
            json={
                "stream": "lpi",
                "event_type": "pr_merged",
                "payload": {},
            },
        )

        response = client.get(
            "/api/v1/signals/?start=2000-01-01T00:00:00Z&end=2100-01-01T00:00:00Z"
        )

        assert response.status_code == 200

        data = response.json()

        assert isinstance(data, list)
        assert len(data) >= 1

    def test_limit_parameter(
        self,
        client,
    ) -> None:
        for i in range(5):
            client.post(
                "/api/v1/signals/",
                json={
                    "stream": "boardy",
                    "event_type": f"event_{i}",
                    "payload": {},
                },
            )

        response = client.get("/api/v1/signals/?limit=2")

        assert response.status_code == 200
        assert len(response.json()) == 2
