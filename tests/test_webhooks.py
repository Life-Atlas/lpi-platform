from fastapi.testclient import TestClient

from lpi.main import app

client = TestClient(app)
WEBHOOK_URL = "/api/v1/webhooks/github"


def test_github_webhook_push_event():
    # Simulate a standard GitHub push event payload
    mock_github_payload = {
        "ref": "refs/heads/main",
        "commits": [{"id": "abc1234", "message": "feat: phase 4 ai agent integration"}],
        "repository": {"name": "lpi-platform"},
    }

    # GitHub sends the event type in the headers
    headers = {"X-GitHub-Event": "push"}

    response = client.post(WEBHOOK_URL, json=mock_github_payload, headers=headers)

    # Depending on how your webhooks.py handles responses, it usually returns 200 OK
    assert response.status_code == 200
