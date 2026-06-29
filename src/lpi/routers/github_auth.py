import os
import uuid
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from lpi import store
from lpi.middleware.auth import get_current_user
from lpi.models import Signal, SignalCreate

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


# ADDED: New model for the disconnect request
class DisconnectRepoRequest(BaseModel):
    user_id: str
    repo_owner: str
    repo_name: str


# --- Mock Database ---
# In production, this saves to your database table: user_id -> github_access_token
token_db: dict[str, str] = {}

# Reverse mapping: "owner/repo" -> user_id, populated when a webhook is registered.
repo_db: dict[str, str] = {}

# --- Configuration ---
# Your webhook receiver URL.
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

    repo_list = [
        {
            "id": repo["id"],
            "name": repo["name"],
            "full_name": repo["full_name"],
            "private": repo["private"],
            "owner": repo["owner"]["login"],
            "html_url": repo["html_url"],
            "permissions": repo.get("permissions", {}),
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
    access_token = token_db.get(request.user_id)
    if not access_token:
        raise HTTPException(status_code=401, detail="No GitHub account linked.")

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
        "User-Agent": "LPI-Platform-Backend",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

    # 422 means webhook already exists. 200/201 means created successfully.
    # If we get 403 or 404, it means we don't have admin rights to add a webhook,
    # but we should still proceed and sync historical events anyway!
    is_success = response.status_code in [200, 201, 422]

    if not is_success:
        print(f"⚠️ Webhook registration returned status {response.status_code} (likely no admin rights). Proceeding with historical sync.")

    repo_db[f"{request.repo_owner}/{request.repo_name}"] = request.user_id

    # --- Fetch and Ingest Historical Events immediately ---
    events_url = f"https://api.github.com/repos/{request.repo_owner}/{request.repo_name}/events"
    ingested_count = 0

    try:
        async with httpx.AsyncClient() as client:
            events_response = await client.get(events_url, headers=headers)
            
        if events_response.status_code == 200:
            raw_events = events_response.json()
            for event in raw_events[:20]:
                event_type = event.get("type")
                if event_type in ["PushEvent", "PullRequestEvent"]:
                    repo_full_name = f"{request.repo_owner}/{request.repo_name}"
                    
                    event_payload = {
                        "github_event_id": event.get("id"),
                        "repo": repo_full_name,
                        "actor": event.get("actor", {}).get("login"),
                        "created_at": event.get("created_at"),
                    }
                    
                    if event_type == "PushEvent":
                        p = event.get("payload", {})
                        event_payload["ref"] = p.get("ref")
                        event_payload["commit_count"] = len(p.get("commits", []))
                        if p.get("commits") and len(p["commits"]) > 0:
                            event_payload["latest_commit_message"] = p["commits"][0].get("message")
                    elif event_type == "PullRequestEvent":
                        p = event.get("payload", {})
                        event_payload["action"] = p.get("action")
                        event_payload["pr_title"] = p.get("pull_request", {}).get("title")
                        event_payload["pr_number"] = p.get("pull_request", {}).get("number")
                    
                    # Auto-detect matching goal linked to this repository
                    target_goal_id = None
                    try:
                        active_goals = store.list_goals(user_id=request.user_id)
                        for g in active_goals:
                            if repo_full_name.lower() in (g.description or "").lower():
                                target_goal_id = g.id
                                break
                    except Exception as e:
                        print(f"Goal lookup failed during tracking: {e}")

                    signal_create = SignalCreate(
                        stream="github",
                        event_type=event_type,
                        source=repo_full_name,
                        payload=event_payload,
                        goal_id=target_goal_id
                    )
                    
                    now = datetime.now(UTC)
                    new_signal = Signal(
                        id=str(uuid.uuid4()),
                        user_id=request.user_id,
                        timestamp=now,
                        **signal_create.model_dump()
                    )
                    store.insert_signal(new_signal)
                    ingested_count += 1
    except Exception as e:
        print(f"Failed to fetch history for tracked repo: {e}")

    return {
        "status": "success",
        "message": f"Successfully tracking {request.repo_name} and synced {ingested_count} historical signals!"
    }


# ADDED: The new Disconnect Endpoint
@router.post("/disconnect-repo", status_code=status.HTTP_200_OK)
async def disconnect_github(request: DisconnectRepoRequest):
    """
    Finds our specific webhook on the user's GitHub repo, deletes it, 
    and removes their access token from the local database.
    """
    access_token = token_db.get(request.user_id)
    if not access_token:
        raise HTTPException(status_code=404, detail="No GitHub account linked.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Try to delete webhook externally, but don't fail if we get rate-limited
    try:
        async with httpx.AsyncClient() as client:
            # Step 1: List all webhooks for this repo to find ours
            hooks_url = f"https://api.github.com/repos/{request.repo_owner}/{request.repo_name}/hooks"
            hooks_response = await client.get(hooks_url, headers=headers)

            if hooks_response.status_code == 200:
                hooks = hooks_response.json()
                target_hook_id = None

                # Find the webhook that points to our WEBHOOK_TARGET_URL
                for hook in hooks:
                    if hook.get("config", {}).get("url") == WEBHOOK_TARGET_URL:
                        target_hook_id = hook["id"]
                        break

                # Step 2: Delete the webhook if we found it
                if target_hook_id:
                    delete_url = f"{hooks_url}/{target_hook_id}"
                    await client.delete(delete_url, headers=headers)
    except Exception as e:
        print(f"⚠️ Webhook deletion from GitHub failed (likely rate-limited), proceeding with local database cleanup: {e}")

    # Step 3: Remove the token and repo mapping from our local mock DB
    if request.user_id in token_db:
        del token_db[request.user_id]
    repo_db.pop(f"{request.repo_owner}/{request.repo_name}", None)

    repo_full_name = f"{request.repo_owner}/{request.repo_name}"
    try:
        # 1. Delete signals where source is the repo name (direct match)
        store._get_client().table("activity_signals").delete().eq("user_id", request.user_id).eq("source", repo_full_name).execute()
        
        # 2. Delete signals where source is github_api or api, but payload references the repo
        store._get_client().table("activity_signals").delete().eq("user_id", request.user_id).filter("payload->>repo", "eq", repo_full_name).execute()
        store._get_client().table("activity_signals").delete().eq("user_id", request.user_id).filter("payload->repo->>name", "eq", repo_full_name).execute()
        
        # 3. Clean up any historical webhook test signals with "github_api" source containing the repo name
        store._get_client().table("activity_signals").delete().eq("user_id", request.user_id).eq("source", "github_api").filter("payload->>repo", "eq", repo_full_name).execute()
    except Exception as e:
        print(f"Failed to clean up signals on repo disconnect: {e}")

    return {"status": "success", "message": f"Successfully disconnected from {request.repo_name}."}


@router.post("/disconnect-account/{user_id}", status_code=status.HTTP_200_OK)
async def disconnect_github_account(user_id: str):
    """
    Clears the stored GitHub oauth access token for this specific user ID,
    disconnecting their entire account profile integration.
    """
    if user_id in token_db:
        del token_db[user_id]
        return {"status": "success", "message": "Successfully disconnected your GitHub account."}
    raise HTTPException(status_code=404, detail="No GitHub account linked.")


# --- ADD THIS NEW ENDPOINT ---
@router.get("/validate-public-repo/{owner}/{repo}", status_code=status.HTTP_200_OK)
async def validate_public_repo(
    owner: str, 
    repo: str,
    user_id: str = Depends(get_current_user)
):
    """Checks if a repo is public and exists. Uses user's OAuth token if linked to avoid rate limits."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    access_token = token_db.get(user_id)
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
    
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="Repo not found or private.")
    
    # Ensure it's actually public
    if response.json().get("private"):
        raise HTTPException(status_code=403, detail="Repo is private.")
        
    return {"is_public": True}

