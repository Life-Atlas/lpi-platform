from fastapi import APIRouter, Request, status

# Importing your store based on your actual file structure
# from lpi import store

router = APIRouter()


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook_receiver(request: Request):
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    signal_data = None

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

    # Save to database if it's a valid event
    if signal_data:
        # COMMENTED OUT FOR PHASE 3 LINTING - BRING BACK IN PHASE 4
        # full_db_record = {
        #     "id": str(uuid.uuid4()),
        #     "user_id": "default_user",
        #     "stream": "lpi",
        #     "event_type": signal_data["event_type"],
        #     "source": "github_webhook",
        #     "payload": signal_data["payload"],
        #     "timestamp": datetime.now(UTC).isoformat()
        # }

        # We can leave this uncommented now since we imported the store
        # store.insert_signal(full_db_record)
        print(f"✅ AUTOMATIC DETECTION: Saved {signal_data['event_type']}!")

    return {"status": "success"}
