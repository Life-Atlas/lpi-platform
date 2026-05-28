from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter

from lpi.models import Signal, SignalCreate
from lpi.storage import store

router = APIRouter()


@router.post("/", response_model=Signal)
def ingest_signal(signal: SignalCreate) -> Signal:
    """Ingest an activity signal from any stream."""
    created = Signal(
        id=str(uuid4()),
        user_id="default-user",
        timestamp=datetime.now(UTC),
        **signal.model_dump(),
    )
    with store.lock:
        store.signals_by_id[created.id] = created
    return created


@router.get("/", response_model=list[Signal])
def list_signals(
    user_id: str | None = None,
    stream: str | None = None,
    limit: int = 50,
) -> list[Signal]:
    """Query signals by user, stream, or both."""
    with store.lock:
        signals = list(store.signals_by_id.values())

    if user_id:
        signals = [s for s in signals if s.user_id == user_id]
    if stream:
        signals = [s for s in signals if s.stream == stream]

    # newest first
    signals.sort(key=lambda s: s.timestamp, reverse=True)
    return signals[: max(0, limit)]
