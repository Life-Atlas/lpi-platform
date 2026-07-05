"""Activity Signals API — Phase 3 implementation.

Owner : Adil Islam (Phase 3)
QA    : Jaivardhan Singh / Daksh Garg

PHASE 3 CHANGES VS PHASE 2 STUB
──────────────────────────────────
Phase 2 stub:
  POST /  → HTTP 501 (Not Implemented)
  GET  /  → always returns []

Phase 3 (this file):
  POST /  → stores signal in Supabase, returns full Signal object  [Wave 2]
  GET  /  → queries Supabase with server-side filters + pagination  [Wave 3]
  GET  /{signal_id} → fetch a single signal by UUID               [bonus]

PHASE 3 FOLLOW-UP (this pass)
────────────────────────────────
  - GET / gained `start`/`end` query params for time-range filtering.
    This was the single largest gap between the gate sheet ("Timeline
    queryable by user and time range") and the running code.
  - The ingest logging comment below is corrected: log_user_activity()
    in utils/logging.py already has its own internal try/except and
    never raises, so the try/except previously wrapped around it here
    was dead code for the CHECK-constraint failure mode. See
    utils/logging.py for the real fix (logger.exception instead of
    print) and the migration note below.

HOW THIS ROUTER FITS INTO THE SYSTEM
──────────────────────────────────────
Signals are the input layer for the recommendation engine.
Flow:
  External source (GitHub, manual, simulated)
    → POST /api/v1/signals/           ← THIS FILE
      → store.insert_signal()
        → Supabase activity_signals table
          → Phase 4: GET /api/v1/signals/?stream=...&start=...&end=...  ← ALSO THIS FILE
            → Jaivardhan's recommendation engine reads signals here

WHY source MATTERS
───────────────────
The `source` field (added to SignalCreate in Phase 3) records HOW
a signal was ingested. Phase 4 recommendation engine can call:
    GET /api/v1/signals/?source=github_api
to read only verified real signals, ignoring simulated test data.

LOGGING
────────
Every POST calls log_user_activity() — same pattern as goals.py.
The action string is 'signal_ingested'.
NOTE: the user_activity_logs CHECK constraint originally only allowed
      'goal_created', 'goal_updated', 'goal_deleted'. The fix is already
      written in supabase/migrations/20260615000000_signals_rls_and_log_action.sql
      — apply it with `supabase db push` if not already applied.
      log_user_activity() itself never raises (it catches and logs its own
      Supabase errors internally via the standard `logging` module), so
      no try/except is needed at this call site.
"""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from lpi import store
from lpi.middleware.auth import UserContext, get_current_user, get_current_user_context
from lpi.models import Signal, SignalCreate
from lpi.notifications import create_notification_if_new
from lpi.utils.logging import log_user_activity

logger = logging.getLogger(__name__)

router = APIRouter()

def _generate_explanation(event_type: str, payload: dict) -> str:
    """Generates a rule-based explanation for signals."""
    if event_type == "commit_pushed":
        return "You're actively pushing code. Keep iterating!"
    if event_type == "pr_merged":
        return "Merging a PR is a significant milestone that moves your goal forward toward next phase."
    return "Your project is showing activity—every small update contributes to your long-term goals."

# ── Wave 2: POST /api/v1/signals/ ────────────────────────────────────────────


@router.post(
    "/",
    response_model=Signal,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an activity signal",
    description=(
        "Accepts a signal from any stream and persists it to Supabase. "
        "Returns the full Signal object with server-assigned id, user_id, "
        "and timestamp. Requires a valid Supabase JWT in Authorization header."
    ),
)
def ingest_signal(
    signal: SignalCreate,
    user_id: str = Depends(get_current_user),
) -> Signal:
    """Store a new activity signal scoped to the authenticated user.

    The caller must include a valid Supabase JWT:
        Authorization: Bearer <token>

    Returns the persisted Signal with server-assigned id, user_id, timestamp.

    Example request body:
        {
          "stream": "lpi",
          "event_type": "pr_merged",
          "payload": {"repo": "lpi-platform", "pr_number": 18},
          "source": "github_api"
        }

    Example response:
        {
          "id": "abc123...",
          "user_id": "00000000-0000-0000-0000-000000000000",
          "stream": "lpi",
          "event_type": "pr_merged",
          "payload": {"repo": "lpi-platform", "pr_number": 18},
          "source": "github_api",
          "timestamp": "2026-06-11T10:00:00+00:00"
        }
    """

    # Deduplicate raw GitHub/API signals based on github_event_id/id in payload
    if isinstance(signal.payload, dict):
        github_event_id = signal.payload.get("github_event_id") or signal.payload.get("id")
        if github_event_id:
            existing = store.get_signal_by_github_id(str(github_event_id), user_id)
            if existing:
                return existing

    # Build the full Signal object.
    # signal.model_dump() spreads all SignalCreate fields (stream, event_type,
    # payload, source) into the Signal constructor. We add the server-assigned
    # fields (id, user_id, timestamp) on top.
    now = datetime.now(UTC)
    new_signal = Signal(
        id=str(uuid.uuid4()),  # UUID generated here, not by Postgres
        user_id=user_id,  # "default_user" in Phase 3
        timestamp=now,  # always UTC
        **signal.model_dump(),  # stream, event_type, payload, source
    )

    # Persist to Supabase.
    # store.insert_signal() calls supabase-py which POSTs to the REST API,
    # which runs an INSERT into the activity_signals table.
    store.insert_signal(new_signal)

    # Log the ingest event. No try/except here: log_user_activity() already
    # guarantees it never raises — it catches any Supabase-side failure
    # internally and reports it via logger.exception() (see
    # utils/logging.py). Wrapping it here again would be redundant and,
    # worse, gives a false impression that THIS is where a logging failure
    # gets caught — it isn't; this call simply cannot raise.
    # MAP THE TYPE FOR THE NOTIFICATION TEMPLATE
    mapped_type = new_signal.event_type
    if new_signal.event_type == "PushEvent":
        mapped_type = "commit_pushed"
    elif new_signal.event_type == "PullRequestEvent":
        mapped_type = "pr_merged"

    create_notification_if_new(
        user_id=user_id,
        signal_id=new_signal.id,
        event_type=mapped_type,  # Use the mapped semantic key
        payload={
            ** (new_signal.payload or {}),
            "explanation": _generate_explanation(new_signal.event_type, new_signal.payload or {})
        },
    )
    log_user_activity(
        user_id=user_id,
        action="signal_ingested",
        resource_id=new_signal.id,
        metadata={
            "stream": new_signal.stream,
            "event_type": new_signal.event_type,
            "source": new_signal.source,
        },
    )

    logger.debug("Signal created: %s", new_signal.model_dump())
    return new_signal


# ── Wave 3: GET /api/v1/signals/ ─────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[Signal],
    summary="List activity signals with filters",
    description=(
        "Returns a paginated list of signals. All filters are optional and "
        "server-side — only matching rows are fetched from Supabase. "
        "Results are ordered newest-first."
    ),
)
def list_signals(
    stream: str | None = Query(
        default=None,
        description="Filter by stream name (e.g. 'boardy', 'lpi', 'datapro')",
    ),
    event_type: str | None = Query(
        default=None,
        description="Filter by event type (e.g. 'pr_merged', 'match_created')",
    ),
    source: str | None = Query(
        default=None,
        description=(
            "Filter by ingestion source: 'github_api', 'manual', "
            "'simulated', or 'api'. Phase 4 rec engine uses this to "
            "exclude simulated signals."
        ),
    ),
    start: datetime | None = Query(
        default=None,
        description="Return signals created at or after this UTC timestamp.",
    ),
    end: datetime | None = Query(
        default=None,
        description="Return signals created at or before this UTC timestamp.",
    ),
    limit: int = Query(
        default=50,
        ge=1,  # minimum 1 row
        le=200,  # maximum 200 rows — prevents accidentally huge responses
        description=(
            "Max rows per page (1–200). Use with offset for pagination. "
            "Default 50 is enough for dashboards and the rec engine."
        ),
    ),
    offset: int = Query(
        default=0,
        ge=0,  # cannot be negative
        description=(
            "Number of rows to skip. Page 1 = offset 0. "
            "Page 2 = offset 50 (if limit=50). "
            "Only the requested page is fetched from Supabase — "
            "total row count does NOT affect query speed."
        ),
    ),
    goal_id: str | None = Query(
        default=None,
        description="Filter by goal ID",
    ),
    fetch_all: bool = Query(False, alias="all"),
    user_context: UserContext = Depends(get_current_user_context),
) -> list[Signal]:
    """Return signals filtered by stream, event_type, source, and/or time range.

    HOW SERVER-SIDE FILTERING WORKS HERE
    ──────────────────────────────────────
    Each query param (stream, event_type, source, start, end) is passed to
    store.list_signals(), which chains .eq()/.gte()/.lte() calls on the
    Supabase query builder. This translates to SQL WHERE clauses:

      ?stream=boardy                         → WHERE stream = 'boardy'
      ?stream=boardy&source=manual           → WHERE stream = 'boardy' AND source = 'manual'
      ?start=2026-06-13T00:00:00Z             → WHERE timestamp >= '2026-06-13T00:00:00Z'
      ?start=...&end=...                      → WHERE timestamp BETWEEN start AND end (inclusive)

    Only rows matching ALL provided filters are returned.
    Postgres runs the filter using the indexes from the migration:
      idx_as_stream, idx_as_event_type, idx_as_source, idx_as_timestamp

    HOW PAGINATION WORKS HERE
    ──────────────────────────
    ?limit=50&offset=0   → Postgres returns rows 1–50 only (LIMIT 50 OFFSET 0)
    ?limit=50&offset=50  → Postgres returns rows 51–100 only (LIMIT 50 OFFSET 50)

    The total row count does NOT affect how fast each page loads.
    500 matching rows with limit=50 is as fast as 50 matching rows.
    Postgres never reads rows outside the requested window.

    Example calls:
      GET /api/v1/signals/                                          → last 50 signals
      GET /api/v1/signals/?stream=boardy                            → boardy signals
      GET /api/v1/signals/?stream=lpi&event_type=pr_merged          → LPI PRs only
      GET /api/v1/signals/?source=github_api&limit=20                → 20 real GitHub events
      GET /api/v1/signals/?start=2026-06-13T00:00:00Z                → everything since June 13
      GET /api/v1/signals/?start=2026-06-13T00:00:00Z&end=2026-06-20T00:00:00Z → one week window
      GET /api/v1/signals/?stream=boardy&limit=50&offset=50          → boardy page 2
    """
    target_user_id = None if (fetch_all and user_context.is_admin) else user_context.user_id
    return store.list_signals(
        user_id=target_user_id,
        stream=stream,
        event_type=event_type,
        source=source,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        goal_id=goal_id,
    )


# ── Bonus: GET /api/v1/signals/{signal_id} ───────────────────────────────────


@router.get(
    "/{signal_id}",
    response_model=Signal,
    summary="Get a single signal by ID",
    description="Fetch a specific activity signal by its UUID.",
)
def get_signal(
    signal_id: str,
    user_context: UserContext = Depends(get_current_user_context),
) -> Signal:
    """Fetch one signal by UUID. 404 if not found or not owned by caller.

    Ownership check mirrors goals.py — returns 404 (not 403) so callers
    cannot determine whether another user's signal exists.
    """
    signal = store.get_signal(signal_id)
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found.",
        )

    if not user_context.is_admin and signal.user_id != user_context.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found.",
        )

    return signal
# ── Phase 4: Dynamic GitHub Integration (Aditi) ──────────────────────────────

@router.post(
    "/sync-github/{goal_id}",
    status_code=status.HTTP_200_OK,
    summary="Dynamically sync GitHub events to a goal",
    description="Polls the public GitHub REST API for a specific repo and ingests recent commits/PRs linked to a goal."
)
async def sync_github_events(
    goal_id: str,
    repo_name: str = Query(..., description="Target GitHub Repo (e.g. facebook/react or langchain-ai/langchain)"),
    user_id: str = Depends(get_current_user),
):
    """
    Fetch live events from GitHub and ingest them as signals linked to a goal.
    """
    # Danial's constraint: signals can only be attached to goals the
    # caller owns. Without this check, an attacker could attach GitHub
    # events to another user's goal by knowing the goal_id.
    # 404 (not 403) — mirrors routers/goals.py so existence is not leaked.
    goal = store.get_goal(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )

    from lpi.routers.github_auth import token_db
    
    url = f"https://api.github.com/repos/{repo_name}/events"
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    
    access_token = token_db.get(user_id)
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    # 1. Fetch live data from GitHub
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch events from GitHub for repo: {repo_name}. Check if the repo is public and spelled correctly."
        )

    raw_events = response.json()
    ingested_count = 0

    # 2. Parse and Filter High-Value Events (Limit to 20 to protect LLM context window)
    for event in raw_events[:20]:
        event_type = event.get("type")

        # We only care about code changes and PRs for SMILE phase progression
        if event_type in ["PushEvent", "PullRequestEvent"]:
            # Deduplicate check: if this event was already ingested (either raw or flattened), skip it!
            github_event_id = event.get("id")
            if github_event_id:
                existing = store.get_signal_by_github_id(str(github_event_id), user_id)
                if existing:
                    # If the existing signal is not linked to this goal yet, link it!
                    if existing.goal_id is None:
                        existing.goal_id = goal_id
                        store._get_client().table("activity_signals").update({"goal_id": goal_id}).eq("id", existing.id).execute()
                    continue

            # Build the creation schema, now including the goal_id
            signal_create = SignalCreate(
                stream="github",
                event_type=event_type,
                source=repo_name,
                payload=event,
                goal_id=goal_id  # Linking the signal to the specific goal!
            )

            # Build the full Signal object (mirroring the logic in ingest_signal)
            now = datetime.now(UTC)
            
            # --- FIX 1: Deterministic UUID for Deduplication ---
            github_event_id = str(event.get("id"))
            consistent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, github_event_id))
            
            new_signal = Signal(
                id=consistent_id,  # <- The database will now recognize duplicates!
                user_id=user_id,
                timestamp=now,
                **signal_create.model_dump()
            )

            # 3. Ingest into the Database
            store.insert_signal(new_signal)
            ingested_count += 1
            
           # --- FIX 2: Trigger the notification service ---
            if event_type == "PushEvent":
                notif_type = "commit_pushed"
                notif_payload = {
                    "repo": repo_name,
                    "explanation": "Your project is showing activity—every small update contributes to your long-term goals."
                }
            elif event_type == "PullRequestEvent":
                notif_type = "pr_merged" 
                gh_payload = event.get("payload", {})
                pr_data = gh_payload.get("pull_request", {})
                
                notif_payload = {
                    "repo": repo_name,
                    "pr_number": pr_data.get("number", "Unknown"),
                    "title": pr_data.get("title", "Pull Request Updated"),
                    "explanation": _generate_explanation("pr_merged", {})
                }

            # TRIGGER NOTIFICATION ONCE HERE
            try:
                create_notification_if_new(
                    user_id=user_id,
                    signal_id=new_signal.id,
                    event_type=notif_type, 
                    payload=notif_payload,
                )
            except Exception as e:
                logger.error(f"Notification background task failed: {e}")

            # Log the activity
            log_user_activity(
                user_id=user_id,
                action="github_signal_synced",
                resource_id=new_signal.id,
                metadata={
                    "repo": repo_name,
                    "event_type": event_type,
                    "goal_id": goal_id
                },
            )
            
            ingested_count += 1

    return {
        "status": "success",
        "fetched_total": len(raw_events),
        "ingested_high_value": ingested_count,
        "repo": repo_name,
        "goal_id": goal_id
    }


# ── ZeroClaw Webhook Receiver ─────────────────────────────────────────────────


@router.post(
    "/zeroclaw",
    status_code=status.HTTP_200_OK,
    summary="Receive ZeroClaw security scanner webhook",
    description=(
        "Accepts HMAC-SHA256 signed POST requests from the ZeroClaw CLI. "
        "Verifies signature, validates schema, normalizes payload into LPI Signal "
        "schema, and persists to Supabase. No JWT required — auth is the shared "
        "secret. Returns {status: success} on success and duplicate replays."
    ),
)
async def receive_zeroclaw_webhook(request: Request) -> JSONResponse:
    """Ingest a ZeroClaw security scan event as an LPI activity signal.

    REVIEW FIXES applied (Jaivardhan, July 1 2026):
    ─────────────────────────────────────────────────
    Fix #1  — Deterministic signal ID via SHA-256(payload) — dedup now works
    Fix #2  — Background task so 200 is returned before DB write (no timeouts)
    Fix #3  — Catch IntegrityError specifically, not generic Exception
    Fix #4  — Async processing via FastAPI BackgroundTasks
    Fix #5  — user_id left as "zeroclaw-service" pending workspace resolution
               (documented as known limitation, not silently wrong)
    Fix #6  — Unknown events log WARNING + return 422 so data loss is visible
    Fix #7  — Malformed timestamps → 400 (handled in normalizer)
    Fix #8  — Pydantic schema validation before normalization
    Fix #11 — Log only event_type + request_id, never raw payload body
    """
    import json as _json

    from fastapi import BackgroundTasks
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    from lpi.utils.zeroclaw_auth import verify_zeroclaw_signature
    from lpi.utils.zeroclaw_normalizer import (
        ZeroClawNormalizationError,
        ZeroClawTimestampError,
        normalize,
    )

    background_tasks = BackgroundTasks()

    # Fix #11: log only safe metadata, never raw body
    request_id = request.headers.get("X-Request-ID", "unknown")

    # 1. Verify HMAC-SHA256 signature — raises 401 on failure
    body = await verify_zeroclaw_signature(request)

    # 2. Parse body
    try:
        raw_payload = _json.loads(body)
    except _json.JSONDecodeError as exc:
        logger.warning(
            "ZeroClaw webhook: invalid JSON — request_id=%s error=%s",
            request_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON.",
        ) from exc

    # 3. Schema validation + normalize
    # Fix #7: ZeroClawTimestampError → 400
    # Fix #8: pydantic.ValidationError → 400
    try:
        normalized = normalize(raw_payload)
    except ZeroClawTimestampError as exc:
        logger.warning(
            "ZeroClaw webhook: malformed timestamp — request_id=%s detail=%s",
            request_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed timestamp: {exc}",
        ) from exc
    except ValidationError as exc:
        logger.warning(
            "ZeroClaw webhook: schema validation failed — request_id=%s",
            request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payload schema invalid: {exc}",
        ) from exc
    except ZeroClawNormalizationError as exc:
        # Fix #6: unknown events → 422 (not silent 200) so data loss is visible
        logger.warning(
            "ZeroClaw webhook: unknown event_type — request_id=%s detail=%s",
            request_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # Fix #1: use deterministic ID from normalizer (SHA-256 of payload)
    new_signal = Signal(
        id=normalized.signal_id,
        user_id="zeroclaw-service",  # Fix #5: placeholder — workspace resolution TBD
        stream=normalized.stream,
        event_type=normalized.event_type,
        source=normalized.source,
        payload=normalized.payload,
        timestamp=normalized.timestamp,
    )

    # Fix #4: offload DB write to background task — return 200 immediately
    # so ZeroClaw CLI doesn't time out and retry under load
    def _persist() -> None:
        """Background task: persist signal, handle dedup via IntegrityError."""
        try:
            store.insert_signal(new_signal)
            logger.info(
                "ZeroClaw signal stored: event_type=%s id=%s",
                new_signal.event_type, new_signal.id
            )
        except Exception as exc:
            # Fix #3: check for DB-level duplicate/unique violation specifically
            err_str = str(exc).lower()
            if any(kw in err_str for kw in ("duplicate", "unique", "23505")):
                logger.info(
                    "ZeroClaw webhook: duplicate signal ignored id=%s",
                    new_signal.id
                )
                return
            # All other exceptions are real errors — log them clearly
            logger.exception(
                "ZeroClaw webhook: failed to store signal id=%s event_type=%s",
                new_signal.id, new_signal.event_type
            )

    background_tasks.add_task(_persist)

    # Fix #2 + Fix #4: return 200 immediately before DB write completes
    return JSONResponse(
        content={"status": "success"},
        background=background_tasks,
    )
