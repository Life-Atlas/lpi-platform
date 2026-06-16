"""Signals API — Phase 3 prep; not a Phase 2 gate requirement."""

from fastapi import APIRouter, HTTPException, status
from starlette.requests import Request

from lpi.middleware.rate_limit import limiter
from lpi.models import Signal, SignalCreate

router = APIRouter()


@router.post("/", response_model=Signal, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def ingest_signal(request: Request, signal: SignalCreate) -> Signal:
    """Ingest an activity signal from any stream.

    Phase 3 task: full implementation deferred.
    Returns HTTP 501 (Not Implemented) instead of crashing with 500.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Signal ingestion is a Phase 3 task — not yet implemented.",
    )


@router.get("/", response_model=list[Signal])
@limiter.limit("60/minute")
def list_signals(request: Request) -> list[Signal]:
    """Phase 3 prep only — GET /signals/ skeleton.

    Always returns [] until real signal querying is implemented.
    """
    return []
