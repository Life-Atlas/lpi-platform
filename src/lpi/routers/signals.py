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

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from lpi import store
from lpi.middleware.auth import UserContext, get_current_user, get_current_user_context
from lpi.models import Signal, SignalCreate
from lpi.utils.logging import log_user_activity

router = APIRouter()


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

    print(new_signal.model_dump())
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