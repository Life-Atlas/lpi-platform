"""Yashika's first test."""

def test_health_endpoint(client):
    """GET /health should return 200 OK."""

    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert "version" in data