import os

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

load_dotenv()

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# --- Pydantic Models for Request Validation ---


class TokenExchangeRequest(BaseModel):
    code: str
    user_id: str


class FetchRepoRequest(BaseModel):
    user_id: str
    repo_owner: str
    repo_name: str


class TrackRepoRequest(BaseModel):
    user_id: str
    repo_owner: str
    repo_name: str


# --- Mock Database ---
# In production, this saves to your database table: user_id -> github_access_token
token_db: dict[str, str] = {}

# --- Configuration ---
# Your webhook receiver URL.
# Update this to your real production domain when deploying, or keep updated with Ngrok for local testing.
WEBHOOK_TARGET_URL = "https://balance-suburb-singular.ngrok-free.dev/api/v1/webhooks/github"


# --- Endpoints ---


@router.post("/exchange-token", status_code=status.HTTP_200_OK)
async def exchange_github_token(request: TokenExchangeRequest):
    """
    1. The frontend passes the temporary 'code' here.
    2. We trade it using our application's secret keys.
    3. We securely save the resulting access token for this specific user.
    """
    url = "https://github.com/login/oauth/access_token"
    payload = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": request.code,
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        data = response.json()

    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=data.get("error_description", "Authentication failed"),
        )

    access_token = data.get("access_token")

    # Securely save this token tied to the user's profile
    token_db[request.user_id] = access_token

    # Example production integration:
    # store.save_github_token(request.user_id, access_token)

    return {"status": "success", "message": "GitHub account linked securely!"}


@router.get("/user-repositories/{user_id}", status_code=status.HTTP_200_OK)
async def list_user_repositories(user_id: str):
    """
    Dynamically fetches all repositories (including private ones)
    that this specific user owns, so the frontend can populate a selection dropdown.
    """
    access_token = token_db.get(user_id)
    if not access_token:
        raise HTTPException(status_code=404, detail="User has not connected their GitHub account.")

    # GitHub API endpoint to list repositories for the authenticated user
    url = "https://api.github.com/user/repos?per_page=100&sort=updated"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "LPI-Platform-Backend",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code, detail="Failed to fetch repositories from GitHub."
        )

    repos = response.json()

    # Filter out clean structural data for the frontend dropdown selection
    repo_list = [
        {
            "id": repo["id"],
            "name": repo["name"],
            "full_name": repo["full_name"],
            "private": repo["private"],
            "owner": repo["owner"]["login"],
            "html_url": repo["html_url"],
        }
        for repo in repos
    ]

    return {"repositories": repo_list}


@router.post("/track-repo", status_code=status.HTTP_200_OK)
async def auto_register_webhook(request: TrackRepoRequest):
    """
    The frontend hits this when the user selects a specific repo from the dropdown.
    We use their saved token to automatically attach our webhook to that exact repo.
    """
    # Grab the user's saved token from the database
    access_token = token_db.get(request.user_id)
    if not access_token:
        raise HTTPException(status_code=401, detail="No GitHub account linked.")

    # Tell GitHub to create a webhook on this specific repository
    url = f"https://api.github.com/repos/{request.repo_owner}/{request.repo_name}/hooks"

    payload = {
        "name": "web",
        "active": True,
        "events": ["push", "pull_request", "pull_request_review"],
        "config": {"url": WEBHOOK_TARGET_URL, "content_type": "json"},
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code not in [200, 201]:
        # If it returns 422, it usually means the webhook already exists on that repo
        if response.status_code == 422:
            return {"status": "success", "message": "Webhook already tracking this repo!"}
        raise HTTPException(status_code=response.status_code, detail="Failed to register webhook.")

    # Example production integration to mark this as the active tracked repo:
    # store.set_active_repo(request.user_id, request.repo_name)

    return {"status": "success", "message": f"Successfully tracking {request.repo_name}!"}
