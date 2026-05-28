import pytest
from fastapi.testclient import TestClient

try:
    from lpi.main import app
except ModuleNotFoundError:
    # Allow `pytest` to run from a fresh clone without requiring an editable install.
    # If `lpi` is installed properly, this block is never used.
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))
    from lpi.main import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_goal() -> dict:
    return {
        "title": "Learn Docker",
        "description": "Containerize my applications",
        "priority": 7,
        "smile_phase": "sense",
    }


@pytest.fixture
def sample_signal() -> dict:
    return {
        "stream": "boardy",
        "event_type": "match_created",
        "payload": {"person_a": "Alice", "person_b": "Bob", "score": 0.85},
    }
