import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, status

from lpi import store
from lpi.models import Signal
from lpi.routers.github_auth import repo_db

router = APIRouter()


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook_receiver(request: Request):
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    signal_data: dict[str, Any] | None = None

    # 1. Catch Merged PRs
    if (
        event_type == "pull_request"
        and payload.get("action") == "closed"
        and payload.get("pull_request", {}).get("merged")
    ):
        signal_data = {
            "event_type": "pr_merged",
            "payload": {
                "repo": payload["repository"]["name"],
                "pr_number": payload["pull_request"]["number"],
                "title": payload["pull_request"]["title"],
            },
        }

    # 2. Catch PR Approvals
    elif event_type == "pull_request_review" and payload.get("action") == "submitted":
        signal_data = {
            "event_type": "pr_reviewed",
            "payload": {
                "repo": payload["repository"]["name"],
                "pr_number": payload["pull_request"]["number"],
                "reviewer": payload["review"]["user"]["login"],
                "state": payload["review"]["state"],
            },
        }

    # 3. Catch Pushed Commits
    elif event_type == "push" and payload.get("commits"):
        signal_data = {
            "event_type": "commit_pushed",
            "payload": {
                "repo": payload["repository"]["name"],
                "branch": payload.get("ref", "").replace("refs/heads/", ""),
                "commit_count": len(payload["commits"]),
                "last_commit_message": payload["commits"][-1]["message"],
            },
        }

    if signal_data:
        repo_full_name = payload.get("repository", {}).get("full_name")
        user_id = repo_db.get(repo_full_name) if repo_full_name else None

        if not user_id:
            print(f"⚠️ Webhook received for unregistered repo '{repo_full_name}', skipping save.")
            return {"status": "success"}

        # Auto-detect matching goal linked to this repository
        target_goal_id = None
        try:
            active_goals = store.list_goals(user_id=user_id)
            for g in active_goals:
                if repo_full_name.lower() in (g.description or "").lower():
                    target_goal_id = g.id
                    break
        except Exception as e:
            print(f"Goal lookup failed during webhook receive: {e}")

        signal = Signal(
            id=str(uuid.uuid4()),
            user_id=user_id,
            stream="lpi",
            event_type=signal_data["event_type"],
            source="github_webhook",
            payload=signal_data["payload"],
            timestamp=datetime.now(UTC),
            goal_id=target_goal_id,
        )
        store.insert_signal(signal)
        print(f"✅ AUTOMATIC DETECTION: Saved {signal_data['event_type']} for user {user_id} and goal {target_goal_id}!")

    return {"status": "success"}
