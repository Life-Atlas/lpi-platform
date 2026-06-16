"""Tests for Activity Signals.

Signal ingestion (POST) is a Phase 3 task — the endpoint returns 501.
Signal listing (GET) is wired and returns an empty list until Phase 3.

All tests are marked no_store: signals don't touch the database store.
"""

import pytest

pytestmark = pytest.mark.no_store


class TestIngestSignal:
    def test_ingest_returns_501(self, client, sample_signal) -> None:
        """POST /api/v1/signals/ returns 501 — Phase 3 not yet implemented."""
        response = client.post("/api/v1/signals/", json=sample_signal)
        assert response.status_code == 501

    def test_ingest_from_different_streams_all_501(self, client) -> None:
        """All streams return 501 until Phase 3 is implemented."""
        streams = ["boardy", "datapro", "vsab", "altiostar", "security"]
        for stream in streams:
            signal = {"stream": stream, "event_type": "test", "payload": {}}
            response = client.post("/api/v1/signals/", json=signal)
            assert response.status_code == 501


class TestQuerySignals:
    def test_list_signals_returns_200(self, client) -> None:
        """GET /api/v1/signals/ is wired — returns 200 with an empty list."""
        response = client.get("/api/v1/signals/")
        assert response.status_code == 200
        assert response.json() == []

    def test_filter_by_stream_returns_200(self, client) -> None:
        """Query param is accepted — returns 200 (filtering deferred to Phase 3)."""
        response = client.get("/api/v1/signals/?stream=boardy")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
