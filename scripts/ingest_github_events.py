"""GitHub Events Ingestion Script — LPI Platform Phase 3.

Owner  : Adil Islam
Purpose: Pull real activity events from the lpi-platform GitHub repo
         and POST them to the LPI signals API as activity signals.

WHY THIS SCRIPT EXISTS
──────────────────────
For demo day (June 27), we need real signals — not simulated ones.
This script reads the actual PR merges, commits, and code reviews
your team did on the lpi-platform repo and stores them as signals.

This means the admin dashboard will show REAL evidence of team activity,
and the recommendation engine will have genuine data to work with.

HOW TO RUN
───────────
1. Make sure your local LPI server is running:
       uvicorn lpi.main:app --reload
   (in another terminal / or use the staging URL)

2. Optionally set a GitHub token (avoids 60 req/hour rate limit):
       set GITHUB_TOKEN=ghp_your_token_here   (Windows CMD)
       $env:GITHUB_TOKEN="ghp_..."            (PowerShell)

3. Run this script:
       python scripts/ingest_github_events.py

4. Check results:
       curl http://localhost:8000/api/v1/signals/?source=github_api

WHAT IT DOES
─────────────
1. Calls GitHub API: GET /repos/{owner}/{repo}/events
   Returns the last ~30 public events on the repo.

2. Filters to meaningful event types:
     PullRequestEvent  → pr_merged (only merged PRs, not opened/closed)
     PushEvent         → commit_pushed (each push = one signal)
     PullRequestReviewEvent → pr_reviewed
     IssuesEvent       → issue_closed (only closed issues)
     CreateEvent       → branch_created (new branches)

3. Maps each event to the Signal schema:
     stream     = 'lpi'            (all events are about LPI platform work)
     event_type = e.g. 'pr_merged'
     payload    = relevant fields from the GitHub event JSON
     source     = 'github_api'     (marks these as real, not simulated)

4. POSTs each signal to POST /api/v1/signals/.

RATE LIMITS
────────────
Without a token: 60 requests/hour per IP.
With a token:    5000 requests/hour.
This script makes 1 request to GitHub + N POSTs to your local API.
The GitHub request is the only one that counts against rate limits.

GITHUB TOKEN (optional but recommended)
─────────────────────────────────────────
Go to: https://github.com/settings/tokens
Create a fine-grained token with "Public Repositories (read-only)".
Set it as GITHUB_TOKEN environment variable before running.
"""

import json
import os
import sys

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

# GitHub repo to pull events from.
# Change these if pulling from a fork or a different org repo.
GITHUB_OWNER = "Life-Atlas"
GITHUB_REPO = "lpi-platform"

# Where your LPI API is running.
# Change to the staging URL for staging: https://la-backend-staging.lifeatlas.online
LPI_API_BASE = "http://localhost:8000"

# The stream name all GitHub events belong to.
# These are all LPI platform events, so stream = 'lpi'.
LPI_STREAM = "lpi"

# GitHub personal access token (optional — avoids rate limits).
# Set GITHUB_TOKEN environment variable, or leave blank for unauthenticated.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ── GitHub event → LPI signal mapping ────────────────────────────────────────

def map_github_event(event: dict) -> dict | None:
    """Convert a raw GitHub event dict to an LPI SignalCreate payload.

    Returns None if the event type is not one we care about, or if
    the event doesn't meet our filter criteria (e.g. PR not merged).

    GitHub event types reference:
    https://docs.github.com/en/developers/webhooks-and-events/events/github-event-types

    We only map event types that represent REAL completed work.
    """
    event_type = event.get("type", "")
    payload = event.get("payload", {})
    actor = event.get("actor", {}).get("login", "unknown")
    repo = event.get("repo", {}).get("name", GITHUB_REPO)

    # ── PullRequestEvent ──────────────────────────────────────────────────────
    # GitHub fires this for opened, closed, merged, labeled, etc.
    # We only care about MERGED PRs — that's real completed work.
    if event_type == "PullRequestEvent":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        merged = pr.get("merged", False)

        # Only ingest merged PRs — ignore opened/closed without merge
        if action == "closed" and merged:
            return {
                "stream": LPI_STREAM,
                "event_type": "pr_merged",
                "source": "github_api",
                "payload": {
                    "repo": repo,
                    "pr_number": pr.get("number"),
                    "title": pr.get("title", ""),
                    "author": actor,
                    "merged_at": pr.get("merged_at", ""),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changed_files", 0),
                    # This is the field Phase 4 rec engine will use most:
                    # what was the PR about?
                    "body_snippet": (pr.get("body") or "")[:200],
                },
            }
        return None

    # ── PushEvent ─────────────────────────────────────────────────────────────
    # Fired on every git push. Each push = one signal.
    # We include the commit count and branch name.
    if event_type == "PushEvent":
        commits = payload.get("commits", [])
        branch = payload.get("ref", "").replace("refs/heads/", "")

        # Skip pushes with no commits (force-push resets, etc.)
        if not commits:
            return None

        return {
            "stream": LPI_STREAM,
            "event_type": "commit_pushed",
            "source": "github_api",
            "payload": {
                "repo": repo,
                "branch": branch,
                "author": actor,
                "commit_count": len(commits),
                # Store the last commit message — most meaningful one
                "last_commit_message": commits[-1].get("message", "")[:200],
                "last_commit_sha": commits[-1].get("sha", "")[:8],
            },
        }

    # ── PullRequestReviewEvent ────────────────────────────────────────────────
    # Fired when someone reviews a PR (approves, requests changes, comments).
    if event_type == "PullRequestReviewEvent":
        pr = payload.get("pull_request", {})
        review = payload.get("review", {})

        return {
            "stream": LPI_STREAM,
            "event_type": "pr_reviewed",
            "source": "github_api",
            "payload": {
                "repo": repo,
                "pr_number": pr.get("number"),
                "pr_title": pr.get("title", ""),
                "reviewer": actor,
                "review_state": review.get("state", ""),  # APPROVED, CHANGES_REQUESTED, COMMENTED
            },
        }

    # ── IssuesEvent ───────────────────────────────────────────────────────────
    # Only ingest closed issues — that represents completed work.
    if event_type == "IssuesEvent":
        action = payload.get("action", "")
        issue = payload.get("issue", {})

        if action == "closed":
            return {
                "stream": LPI_STREAM,
                "event_type": "issue_closed",
                "source": "github_api",
                "payload": {
                    "repo": repo,
                    "issue_number": issue.get("number"),
                    "title": issue.get("title", ""),
                    "author": actor,
                },
            }
        return None

    # ── CreateEvent ───────────────────────────────────────────────────────────
    # Fired when a branch or tag is created. Only care about branches.
    if event_type == "CreateEvent":
        ref_type = payload.get("ref_type", "")

        if ref_type == "branch":
            return {
                "stream": LPI_STREAM,
                "event_type": "branch_created",
                "source": "github_api",
                "payload": {
                    "repo": repo,
                    "branch": payload.get("ref", ""),
                    "author": actor,
                },
            }
        return None

    # All other event types (WatchEvent, ForkEvent, etc.) are not meaningful
    # for the recommendation engine — skip them.
    return None


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def fetch_github_events() -> list[dict]:
    """Call the GitHub Events API and return the raw events list.

    Returns the last ~30 events for the configured repo.
    GitHub caps this at 300 events with the /events endpoint.
    """
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/events"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Add token if available — raises rate limit from 60/hr to 5000/hr
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        print("[github] Using authenticated requests (token found)")
    else:
        print("[github] No GITHUB_TOKEN set — using unauthenticated (60 req/hr limit)")

    print(f"[github] Fetching events from {GITHUB_OWNER}/{GITHUB_REPO}...")

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 404:
        print(f"[github] ERROR: Repo {GITHUB_OWNER}/{GITHUB_REPO} not found or private.")
        print("         Check GITHUB_OWNER and GITHUB_REPO at the top of this script.")
        sys.exit(1)

    if response.status_code == 403:
        print("[github] ERROR: Rate limited. Set GITHUB_TOKEN env variable.")
        sys.exit(1)

    response.raise_for_status()
    events = response.json()
    print(f"[github] Fetched {len(events)} raw events.")
    return events


def post_signal(signal_payload: dict) -> bool:
    """POST a single signal to the LPI API.

    Returns True on success (201/200), False on failure.
    Never raises — we want to continue processing even if one signal fails.
    """
    url = f"{LPI_API_BASE}/api/v1/signals/"
    try:
        response = requests.post(url, json=signal_payload, timeout=5)
        if response.status_code in (200, 201):
            return True
        print(
            f"  [lpi] WARN: POST returned {response.status_code}: {response.text[:100]}"
        )
        return False
    except requests.exceptions.ConnectionError:
        print(f"  [lpi] ERROR: Cannot connect to {LPI_API_BASE}.")
        print("         Is the LPI server running? (`uvicorn lpi.main:app --reload`)")
        return False
    except Exception as exc:
        print(f"  [lpi] ERROR: {exc}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("LPI GitHub Events Ingestion Script")
    print(f"Repo   : {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"API    : {LPI_API_BASE}")
    print(f"Stream : {LPI_STREAM}")
    print("=" * 60)

    # Step 1: Pull events from GitHub
    raw_events = fetch_github_events()

    # Step 2: Map to LPI signal format, skipping unmapped events
    signals = []
    skipped = 0
    for event in raw_events:
        mapped = map_github_event(event)
        if mapped:
            signals.append(mapped)
        else:
            skipped += 1

    print(f"[map]    {len(signals)} signals mapped, {skipped} events skipped (not relevant).")

    if not signals:
        print("[done]   No signals to ingest. Repo may have no recent merged PRs or pushes.")
        return

    # Step 3: POST each signal to the LPI API
    print(f"[ingest] Posting {len(signals)} signals to {LPI_API_BASE}/api/v1/signals/...")
    succeeded = 0
    failed = 0

    for i, signal in enumerate(signals, 1):
        event_type = signal["event_type"]
        # Shorten payload display for readability
        payload_preview = json.dumps(signal["payload"])[:60]
        print(f"  [{i}/{len(signals)}] {event_type}: {payload_preview}...")

        ok = post_signal(signal)
        if ok:
            succeeded += 1
        else:
            failed += 1

    # Step 4: Summary
    print("=" * 60)
    print(f"[done]   {succeeded} signals ingested, {failed} failed.")
    print(f"         Verify: GET {LPI_API_BASE}/api/v1/signals/?source=github_api")
    print("=" * 60)


if __name__ == "__main__":
    main()
