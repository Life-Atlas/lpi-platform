"""Signals API — Phase 3 prep; not a Phase 2 gate requirement."""

from fastapi import APIRouter

from lpi.models import Signal, SignalCreate

# Phase 3 prep only — not part of Phase 2 gate requirements.
_signals: dict[str, Signal] = {}


def create_signal_stub() -> None:
    """
    Phase 3 preparation only.
    Actual implementation deferred.
    """
    pass


router = APIRouter()


@router.post("/", response_model=Signal)
def ingest_signal(signal: SignalCreate) -> Signal:
    """Ingest an activity signal from any stream."""
    create_signal_stub()
    raise NotImplementedError("Phase 3 task: signal ingestion not implemented")


@router.get("/", response_model=list[Signal])
def list_signals(
    user_id: str | None = None,
    stream: str | None = None,
    event_type: str | None = None,
) -> list[Signal]:
    """Phase 3 prep only — GET /signals/ skeleton with query params.
    
    Query parameters:
    - user_id: Filter signals by user ID
    - stream: Filter signals by stream name
    - event_type: Filter signals by event type
    
    All filters are AND-combined. Returns [] until real signal querying is implemented.
    """
    # Phase 3 prep only – not part of Phase 2 gate requirements.
    # Always return [] until real signal querying is implemented.
    return []
