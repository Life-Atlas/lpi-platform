"""Supabase-backed store — Phase 3 update.

WHAT CHANGED IN PHASE 3 (Adil Islam)
──────────────────────────────────────
The signal functions previously used an in-memory dict (_signals).
That was a Phase 2 stub — signals were never persisted to Supabase.

Phase 3 replaces all three signal functions (insert / list / get)
with real Supabase calls, exactly mirroring the goals pattern.

Specifically:
  - _signals dict and _signals_lock removed (no longer needed)
  - insert_signal() → writes to 'activity_signals' Supabase table
  - list_signals()  → queries 'activity_signals' with server-side filters
  - get_signal()    → fetches a single signal by id
  - clear_all()     → now also truncates 'activity_signals'

PHASE 3 FOLLOW-UP (this pass)
────────────────────────────────
  - list_signals() gained `start`/`end` params for time-range filtering
    (closes the §4.3 gate gap — was the largest discrepancy between the
    spec sheet and the running code).
  - get_user_activity_logs() added: a thin read helper over the
    `user_activity_logs` table, used by tests to verify the audit trail
    for signal ingestion actually exists in Supabase (not just in the
    in-memory mirror in utils/logging.py, which always succeeds even if
    the real Supabase write silently failed).

HOW THE STORE CONNECTS TO SUPABASE
────────────────────────────────────
Every function calls _get_client() which creates a supabase-py client
using SUPABASE_URL and SUPABASE_KEY from the .env file. In local dev,
that URL is http://127.0.0.1:54321 (Supabase CLI local instance).
In staging/production, it's the real Supabase project URL.

The application code doesn't know or care which environment it's in —
it always calls the same _get_client() function.

SERVER-SIDE FILTERING IN list_signals()
──────────────────────────────────────────
Server-side means the WHERE clause runs IN the database (Postgres),
not in Python after fetching all rows.

  BAD (client-side):
    all_rows = query.execute().data          # fetches ALL rows
    return [s for s in all_rows if s.stream == stream]  # filters in Python

  GOOD (server-side):
    query = query.eq("stream", stream)       # WHERE stream = 'boardy'
    return query.execute().data              # only matching rows sent back

Why it matters: at 10,000 signals, client-side fetches 10,000 rows to
return 50. Server-side fetches and returns 50. The indexes in the migration
(idx_as_stream, idx_as_event_type, etc.) make this O(log n) instead of O(n).
The same logic applies to the new start/end range filter below — it uses
idx_as_timestamp, which already existed but had no filter wired to it.

FOR TESTS
──────────
Tests run against a LOCAL Supabase instance. Ensure .env has:
    SUPABASE_URL=http://127.0.0.1:54321
    SUPABASE_KEY=<local service_role key from `supabase status`>

In this backend code, SUPABASE_KEY is expected to be the service role key
so server-side writes can bypass RLS. If you prefer, set
SUPABASE_SERVICE_ROLE_KEY instead of overwriting SUPABASE_KEY.

Run `supabase start` then `supabase db push` before running tests.
The clear_all() helper wipes both tables between test runs.
"""

import threading
from datetime import datetime
from typing import TYPE_CHECKING, cast

from lpi.config import settings
from lpi.models import Goal, Signal

if TYPE_CHECKING:
    from supabase import Client  # type: ignore[attr-defined]


def _get_client() -> "Client":
    """Create and return a Supabase client.

    Called on every store function — supabase-py manages connection
    pooling internally, so creating a client per-call is safe and
    the intended usage pattern for this library.

    Uses SUPABASE_SERVICE_ROLE_KEY if set, otherwise falls back to
    SUPABASE_KEY. Backend code should prefer a service role key so
    authenticated server-side operations bypass RLS as designed.
    """
    from supabase import create_client  # type: ignore[attr-defined]

    key = settings.supabase_service_role_key or settings.supabase_key
    if not key:
        raise RuntimeError(
            "Supabase service role key is required for backend writes. "
            "Set SUPABASE_SERVICE_ROLE_KEY or use a service role value in SUPABASE_KEY."
        )
    if key.startswith("sb_publishable_"):
        raise RuntimeError(
            "Detected a publishable Supabase key for backend writes. "
            "Use the service role key instead so row-level security policies can be bypassed."
        )
    return create_client(settings.supabase_url, key)


# ── Lock (kept for goals — goals still use in-memory + Supabase dual writes) ──
# Signals no longer need this lock since they're purely Supabase-backed.
_goals_lock = threading.Lock()


# ── Goals ──────────────────────────────────────────────────────────────────────


def get_goal(goal_id: str) -> Goal | None:
    """Fetch a single goal by its UUID. Returns None if not found."""
    result = _get_client().table("goals").select("*").eq("id", goal_id).execute()
    if not result.data:
        return None
    return Goal(**cast(dict, result.data[0]))


def list_goals(
    user_id: str | None = None,
    smile_phase: str | None = None,
) -> list[Goal]:
    """Return all goals, optionally filtered by user_id and/or smile_phase.

    Both filters are server-side: the WHERE clause runs in Postgres,
    not in Python. Only matching rows are sent over the network.
    """
    query = _get_client().table("goals").select("*")
    if user_id:
        query = query.eq("user_id", user_id)
    if smile_phase:
        query = query.eq("smile_phase", smile_phase)
    result = query.execute()
    return [Goal(**cast(dict, row)) for row in result.data]


def insert_goal(goal: Goal) -> Goal:
    """Insert a new goal row into Supabase."""
    _get_client().table("goals").insert(goal.model_dump(mode="json")).execute()
    return goal


def update_goal(goal_id: str, updates: dict) -> Goal:
    """Apply a partial update dict to a goal row. Returns the updated goal."""
    result = _get_client().table("goals").update(updates).eq("id", goal_id).execute()
    return Goal(**cast(dict, result.data[0]))


def delete_goal(goal_id: str) -> None:
    """Delete a goal row by its UUID."""
    _get_client().table("goals").delete().eq("id", goal_id).execute()


# ── Signals (Phase 3 — Supabase-backed) ──────────────────────────────────────
#
# These replace the Phase 2 in-memory dict stub.
# The table 'activity_signals' is created by:
#   supabase/migrations/20260611000000_create_activity_signals.sql


def insert_signal(signal: Signal) -> Signal:
    """Persist a new signal row to the activity_signals Supabase table.

    signal.model_dump(mode="json") converts the Pydantic model to a plain
    dict with JSON-serializable types (datetime → ISO string, etc.).
    That dict maps directly to the activity_signals column names.

    Returns the original signal unchanged (Supabase returns the inserted
    row but we already have it — no need to re-parse it).
    """
    _get_client().table("activity_signals").insert(signal.model_dump(mode="json")).execute()
    return signal


def list_signals(
    user_id: str | None = None,
    stream: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Signal]:
    """Return signals from Supabase with optional server-side filters.

    user_id filter added post-auth PR — signals are now user-scoped,
    exactly like goals. Without this filter every user would see every
    other user's signals, which is a data isolation bug.

    ALL filtering happens inside Postgres (server-side), not in Python.
    Each .eq()/.gte()/.lte() call adds a WHERE clause — only matching
    rows come back.

    Args:
        user_id    : Scope results to the authenticated user's signals.
                     If omitted, no user scoping is applied.
        stream     : Filter to one business stream (e.g. 'boardy', 'lpi').
        event_type : Filter to one event type (e.g. 'pr_merged').
        source     : Filter by ingestion origin (e.g. 'github_api').
                     Phase 4 rec engine uses this to exclude 'simulated'.
        start      : Inclusive lower bound on `timestamp`. Closes the
                     §4.3 gate gap — "Timeline queryable by user and time
                     range" was a named success criterion that previously
                     had no router/store wiring at all.
        end        : Inclusive upper bound on `timestamp`.
        limit      : Max rows to return per page (default 50, max 200).
                     Prevents accidentally fetching thousands of rows.
        offset     : How many rows to skip (for pagination).
                     Page 1 = offset 0, Page 2 = offset 50, etc.

    TIME-RANGE FILTERING EXPLAINED
    ─────────────────────────────────
    `.gte("timestamp", start.isoformat())` → WHERE timestamp >= start
    `.lte("timestamp", end.isoformat())`   → WHERE timestamp <= end
    Both bounds are inclusive. Either can be supplied alone:
      - only `start`  → "everything since X"
      - only `end`    → "everything up to X"
      - both          → a closed window
      - neither       → unchanged behavior (no time filter), so this is
                        fully backward-compatible with existing callers.

    `.isoformat()` is required because the Supabase REST/PostgREST layer
    expects a string, not a Python datetime object, the same reason
    insert_signal() calls signal.model_dump(mode="json") rather than
    passing a raw Pydantic model. Incoming `start`/`end` should be
    timezone-aware (the router enforces ISO-8601 with an offset/Z) so the
    comparison against the TIMESTAMPTZ column in Postgres is unambiguous.

    This filter uses idx_as_timestamp DESC, which already existed in the
    Phase 3 migration but had no corresponding .gte()/.lte() call until
    now — an index without a matching filter is dead weight; a filter
    without a matching index is a full table scan waiting to happen.
    Adding the filter here is what actually makes the existing index useful.

    PAGINATION EXPLAINED
    ─────────────────────
    If 500 rows match a filter and limit=50:
      - First call  (offset=0)   → Postgres returns rows 1–50 only.
                                   Rows 51–500 are never read or sent.
      - Second call (offset=50)  → Postgres returns rows 51–100 only.
      Each page is a fast, bounded query. No call is ever slow because
      of how many total rows exist — it only depends on limit.

    The recommendation engine typically calls with a small limit (e.g. 20)
    because it only needs the most recent signals, not all of history.

    ORDER
    ──────
    Results are sorted newest-first (timestamp DESC).
    The idx_as_timestamp DESC index in the migration makes this free —
    Postgres doesn't need to sort after fetching; the index is already ordered.
    """
    # Start with a base query selecting all columns from activity_signals
    query = _get_client().table("activity_signals").select("*")

    # Scope to authenticated user — same pattern as list_goals(user_id=...)
    if user_id:
        query = query.eq("user_id", user_id)

    # Add filters only when the caller provided them.
    # Each .eq() adds: WHERE column = 'value'
    # Chaining calls adds: WHERE col1 = 'v1' AND col2 = 'v2' AND ...
    if stream:
        query = query.eq("stream", stream)
    if event_type:
        query = query.eq("event_type", event_type)
    if source:
        query = query.eq("source", source)

    # Time-range filter (new). `if start:` / `if end:` works correctly here
    # because datetime instances are always truthy in Python (no __bool__
    # override) — this is the same truthy-check idiom already used for
    # stream/event_type/source above, just applied to a datetime instead
    # of a string.
    if start:
        query = query.gte("timestamp", start.isoformat())
    if end:
        query = query.lte("timestamp", end.isoformat())

    # Sort newest-first, then apply pagination.
    # .order("timestamp", desc=True) → ORDER BY timestamp DESC
    # .limit(limit)                  → LIMIT 50
    # .offset(offset)                → OFFSET 0
    query = query.order("timestamp", desc=True).limit(limit).offset(offset)

    result = query.execute()

    # Convert each raw dict row from Supabase into a typed Signal object.
    # cast(dict, row) tells mypy "trust me, this is a dict" — supabase-py
    # returns untyped data but it's always a list of dicts.
    return [Signal(**cast(dict, row)) for row in result.data]


def get_signal(signal_id: str) -> Signal | None:
    """Fetch a single signal by its UUID. Returns None if not found.

    Used by GET /api/v1/signals/{signal_id}.
    """
    result = _get_client().table("activity_signals").select("*").eq("id", signal_id).execute()
    if not result.data:
        return None
    return Signal(**cast(dict, result.data[0]))


# ── Audit log verification (new — used by tests, also useful for admin tooling) ─


def get_user_activity_logs(
    resource_id: str | None = None,
    action: str | None = None,
) -> list[dict]:
    """Read rows directly from the user_activity_logs Supabase table.

    WHY THIS EXISTS
    ─────────────────
    utils/logging.py's in-memory `user_activity_logs` list is appended to
    unconditionally, BEFORE the Supabase insert is attempted — so it
    always "succeeds" even if the real database write silently fails
    (e.g. a CHECK constraint mismatch, exactly what shipped with
    signal_ingested logging). Asserting against that in-memory list in a
    test therefore cannot catch that class of bug.

    This function queries Supabase directly, which is the only reliable
    way to confirm a log row actually exists in the database — used by
    the regression test in tests/test_activity_signals.py
    (test_ingest_writes_audit_log) and available for any admin/debug
    tooling that needs to inspect the real audit trail.

    Args:
        resource_id : Filter to logs for one specific goal/signal UUID.
        action      : Filter to one action string, e.g. "signal_ingested".

    Returns:
        Raw list of matching rows (dicts), newest behavior not enforced —
        callers needing order/pagination should add it the same way
        list_signals() does, if this grows beyond test/debug usage.
    """
    query = _get_client().table("user_activity_logs").select("*")
    if resource_id:
        query = query.eq("resource_id", resource_id)
    if action:
        query = query.eq("action", action)
    return cast(list[dict], query.execute().data)  # ← always reached


# ── Test helper ───────────────────────────────────────────────────────────────


def clear_all() -> None:
    """Wipe all data from goals and activity_signals. Call ONLY from tests.

    WHY .neq("user_id", "__sentinel_never_exists__")?
    ───────────────────────────────────────────────────
    supabase-py v2 requires at least one filter on DELETE to prevent
    accidental full-table wipes. We can't use a filterless DELETE.

    We use .neq("user_id", "__sentinel__") because:
      - user_id is TEXT in both tables → safe to compare to any string
      - The sentinel value never matches any real row → deletes everything
      - Using .neq("id", "") would fail on UUID columns (type cast error)

    This is called before AND after every test by the autouse fixture
    in conftest.py, so tests never see each other's data.

    NOTE: this does NOT wipe user_activity_logs. If you add a test that
    relies on a clean audit-log table between runs (e.g. counting rows
    rather than filtering by resource_id), wipe it the same way here.
    The current regression test avoids this by filtering on resource_id,
    which is unique per signal and doesn't require a clean table.
    """
    # Wipe all goals rows
    _get_client().table("goals").delete().neq("user_id", "__sentinel_never_exists__").execute()

    # Wipe all activity_signals rows (Phase 3 addition)
    _get_client().table("activity_signals").delete().neq(
        "user_id", "__sentinel_never_exists__"
    ).execute()
