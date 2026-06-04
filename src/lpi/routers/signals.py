"""Signals API — Phase 3 prep; not a Phase 2 gate requirement.

This module provides skeleton endpoints for signal ingestion and querying.
Full implementation is deferred to Phase 3.

═══════════════════════════════════════════════════════════════════════════════
Phase 3 Preparation Scaffold
═══════════════════════════════════════════════════════════════════════════════

POST /api/v1/signals/
  - Accepts: SignalCreate payload (stream, event_type, payload)
  - Validates request schema
  - Returns: NotImplementedError (stub — actual ingestion deferred)
  - Storage backend: Phase 3 task

GET /api/v1/signals/
  - Query parameters: user_id (optional), stream (optional), event_type (optional)
  - Filtering logic: Phase 3 task
  - Returns: [] (empty list) until Phase 3 implementation
  - Use cases: Query signals by user, stream, or event type

═══════════════════════════════════════════════════════════════════════════════
"""

from fastapi import APIRouter, Query

from lpi.models import Signal, SignalCreate

# Phase 3 prep only — not part of Phase 2 gate requirements.
# In-memory storage placeholder; full persistence via Phase 3 backend.
_signals: dict[str, Signal] = {}


def ingest_signal_stub(signal: SignalCreate) -> Signal:
    """
    Phase 3 preparation only.
    
    Placeholder for signal ingestion logic.
    Phase 3 tasks:
      1. Validate signal payload
      2. Generate signal ID and timestamp
      3. Route to appropriate backend handler
      4. Store in persistent backend (DB, cache, etc.)
      5. Return constructed Signal object
    
    Args:
        signal: SignalCreate payload with stream, event_type, and optional payload
    
    Returns:
        Constructed Signal object (Phase 3 implementation)
    
    Raises:
        NotImplementedError: Until Phase 3 implementation
    """
    pass


def query_signals_stub(
    user_id: str | None = None,
    stream: str | None = None,
    event_type: str | None = None
) -> list[Signal]:
    """
    Phase 3 preparation only.
    
    Placeholder for signal query logic.
    Phase 3 tasks:
      1. Query backend by user_id (optional)
      2. Filter by stream name (optional)
      3. Filter by event_type (optional)
      4. Apply default limit (50) and pagination
      5. Return sorted Signal list
    
    Args:
        user_id: Filter signals for specific user (optional)
        stream: Filter by signal source/stream name (optional)
        event_type: Filter by event type (optional)
    
    Returns:
        List of Signal objects matching query (empty until Phase 3 implementation)
    """
    pass


router = APIRouter()


@router.post("/", response_model=Signal, status_code=201)
def ingest_signal(signal: SignalCreate) -> Signal:
    """
    Ingest an activity signal from any stream.
    
    Phase 3 preparation — actual implementation deferred.
    
    **Request body (SignalCreate):**
    - `stream` (str): Name of signal source (e.g., "calendar", "task_system", "email")
    - `event_type` (str): Type of activity (e.g., "meeting_scheduled", "task_completed")
    - `payload` (dict, optional): Event-specific data
    
    **Response (Signal):**
    - `id`: Auto-generated UUID
    - `user_id`: Assigned by server (Phase 3: from JWT token)
    - `timestamp`: Server-assigned creation time
    - Plus all SignalCreate fields
    
    **Phase 3 implementation notes:**
    - Validate payload against schema
    - Route to backend based on stream type
    - Handle retries and error cases
    """
    ingest_signal_stub(signal)
    raise NotImplementedError(
        "Phase 3 task: signal ingestion not yet implemented. "
        "See Phase 3 spec for storage backend details."
    )


@router.get("/", response_model=list[Signal])
def list_signals(
    user_id: str | None = Query(None, description="Filter signals for specific user"),
    stream: str | None = Query(None, description="Filter by signal stream name"),
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=500, description="Max results (default 50)"),
) -> list[Signal]:
    """
    Query signals by user, stream, or event type.
    
    Phase 3 preparation — skeleton with query parameters.
    
    **Query parameters:**
    - `user_id` (optional): Filter signals for specific user
    - `stream` (optional): Filter by source stream (e.g., "calendar", "email")
    - `event_type` (optional): Filter by event type (e.g., "meeting", "task_update")
    - `limit` (optional, default 50): Max results to return (1–500)
    
    **Response:**
    - Array of Signal objects matching query criteria
    - Empty until Phase 3 backend implementation
    
    **Phase 3 implementation notes:**
    - Apply filters atomically (AND logic: all filters must match)
    - Sort by timestamp DESC (most recent first)
    - Implement pagination with cursor/offset (Phase 3+)
    """
    query_signals_stub(user_id=user_id, stream=stream, event_type=event_type)
    # Phase 3 prep only – not part of Phase 2 gate requirements.
    # Always return [] until real signal querying is implemented.
    return []
