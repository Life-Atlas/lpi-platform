from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from lpi.main import app
from lpi.routers.github_auth import token_db

client = TestClient(app)
PREFIX = "/api/v1/github"

@patch("lpi.routers.github_auth.httpx.AsyncClient.post", new_callable=AsyncMock)
def test_exchange_github_token_success(mock_post):
    # Setup the mock response
    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "fake_mock_token"}
    mock_post.return_value = mock_response

    payload = {"code": "12345", "user_id": "test_user_aditi"}
    response = client.post(f"{PREFIX}/exchange-token", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify the token was securely saved in our dictionary
    assert token_db.get("test_user_aditi") == "fake_mock_token"

 
@patch("lpi.routers.github_auth.httpx.AsyncClient.get", new_callable=AsyncMock)
def test_list_user_repositories(mock_get):
    # Setup the mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": 1, 
            "name": "lpi-platform", 
            "full_name": "user/lpi-platform", 
            "private": True, 
            "owner": {"login": "test_user_aditi"}, 
            "html_url": "https://github.com/user/lpi-platform"
        }
    ]
    mock_get.return_value = mock_response

    # Inject a fake token so the backend thinks the user is authenticated
    token_db["test_user_aditi"] = "fake_mock_token"

    response = client.get(f"{PREFIX}/user-repositories/test_user_aditi")
    
    assert response.status_code == 200
    data = response.json()
    assert "repositories" in data
    assert len(data["repositories"]) == 1
    assert data["repositories"][0]["name"] == "lpi-platform"


@patch("lpi.routers.github_auth.httpx.AsyncClient.post", new_callable=AsyncMock)
def test_track_repo_success(mock_post):
    # Setup the mock response for GitHub successfully creating a webhook
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_post.return_value = mock_response

    # Ensure the user is "authenticated"
    token_db["test_user_aditi"] = "fake_mock_token"

    payload = {
        "user_id": "test_user_aditi",
        "repo_owner": "test_user_aditi",
        "repo_name": "lpi-platform"
    }
    
    response = client.post(f"{PREFIX}/track-repo", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"