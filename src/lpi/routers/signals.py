"""Activity Signals API — Phase 3 implementation.

from fastapi import APIRouter, HTTPException, status
from starlette.requests import Request

from lpi.middleware.rate_limit import limiter
from lpi.models import Signal, SignalCreate
from lpi.utils.logging import log_user_activity

router = APIRouter()


@router.post("/", response_model=Signal, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def ingest_signal(request: Request, signal: SignalCreate) -> Signal:
    """Ingest an activity signal from any stream.

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
        id=str(uuid.uuid4()),   # UUID generated here, not by Postgres
        user_id=user_id,        # "default_user" in Phase 3
        timestamp=now,          # always UTC
        **signal.model_dump(),  # stream, event_type, payload, source
    )

    # Persist to Supabase.
    # store.insert_signal() calls supabase-py which POSTs to the REST API,
    # which runs an INSERT into the activity_signals table.
    store.insert_signal(new_signal)

    # Log the ingest event.
    # Wrapped in try/except because the user_activity_logs CHECK constraint
    # may not yet include 'signal_ingested' — a constraint mismatch raises
    # an exception in supabase-py. We log the warning but never break the
    # ingest endpoint. Update the CHECK constraint migration to fix properly.
    try:
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
    except Exception as exc:
        # Log to stdout — visible in uvicorn logs. Never breaks the endpoint.
        print(f"[ingest_signal] WARNING: logging failed for signal {new_signal.id}: {exc}")

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
    limit: int = Query(
        default=50,
        ge=1,           # minimum 1 row
        le=200,         # maximum 200 rows — prevents accidentally huge responses
        description=(
            "Max rows per page (1–200). Use with offset for pagination. "
            "Default 50 is enough for dashboards and the rec engine."
        ),
    ),
    offset: int = Query(
        default=0,
        ge=0,           # cannot be negative
        description=(
            "Number of rows to skip. Page 1 = offset 0. "
            "Page 2 = offset 50 (if limit=50). "
            "Only the requested page is fetched from Supabase — "
            "total row count does NOT affect query speed."
        ),
    ),
    user_id: str = Depends(get_current_user),
) -> list[Signal]:
    """Return signals filtered by stream, event_type, and/or source.

    HOW SERVER-SIDE FILTERING WORKS HERE
    ──────────────────────────────────────
    Each query param (stream, event_type, source) is passed to
    store.list_signals(), which chains .eq() calls on the Supabase
    query builder. This translates to SQL WHERE clauses:

      ?stream=boardy               → WHERE stream = 'boardy'
      ?stream=boardy&source=manual → WHERE stream = 'boardy' AND source = 'manual'

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
      GET /api/v1/signals/                                 → last 50 signals
      GET /api/v1/signals/?stream=boardy                   → boardy signals
      GET /api/v1/signals/?stream=lpi&event_type=pr_merged → LPI PRs only
      GET /api/v1/signals/?source=github_api&limit=20      → 20 real GitHub events
      GET /api/v1/signals/?stream=boardy&limit=50&offset=50 → boardy page 2
    """
    return store.list_signals(
        user_id=user_id,
        stream=stream,
        event_type=event_type,
        source=source,
        limit=limit,
        offset=offset,
    )


# ── Bonus: GET /api/v1/signals/{signal_id} ───────────────────────────────────

@router.get("/", response_model=list[Signal])
@limiter.limit("60/minute")
def list_signals(request: Request) -> list[Signal]:
    """Phase 3 prep only — GET /signals/ skeleton.

    Ownership check mirrors goals.py — returns 404 (not 403) so callers
    cannot determine whether another user's signal exists.
    """
    signal = store.get_signal(signal_id)
    if signal is None or signal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Signal '{signal_id}' not found.",
        )
    return signal
