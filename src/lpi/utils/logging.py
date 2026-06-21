"""SMILE phase transition logger — Phase 2 (Supabase-backed, dual-sync).

Design spec : Yashika Verma
Updated     : Adil Islam — Phase 2 Supabase integration — all 3 log types
Updated     : Adil Islam — Phase 3 fix: log_user_activity() failures now go
              through the standard `logging` module instead of print(), so
              a constraint mismatch (the bug that shipped with signal
              ingestion) shows up in real log output/alerting instead of
              only in stdout that may or may not be captured.

WHY THIS FILE WAS CHANGED (Phase 2)
─────────────────────────────────────
Phase 2 stub wrote transitions only to an in-memory list. That meant:
  - Nothing appeared in Supabase Studio (Table Editor or Logs tab)
  - Transitions were lost on every server restart
  - Tests could inspect the list, but production had no audit trail

This version writes to Supabase tables for all three log types.
The in-memory lists are kept for tests — conftest fixtures call the
clear_*() helpers between test runs, and test assertions still work.

THREE LOG TYPES — ALL DUAL-SYNC
────────────────────────────────
Every function writes to TWO destinations simultaneously:
  1. In-memory list  → tests inspect this; no Supabase needed in test env
  2. Supabase table  → visible in Studio → Table Editor

If the Supabase write fails for any reason, the error is caught, logged
via the `logging` module, and the request continues normally. Logging
must NEVER break an API endpoint.

  log_transition()     → goal_phase_transitions  (SMILE phase changes only)
  log_user_activity()  → user_activity_logs      (create, update, delete,
                                                    signal_ingested)
  log_system_event()   → system_logs             (startup, errors, warnings)

KNOWN BUG THIS FILE PREVIOUSLY MASKED (now fixed in log_user_activity)
─────────────────────────────────────────────────────────────────────
The `user_activity_logs` CHECK constraint originally only allowed
'goal_created' | 'goal_updated' | 'goal_deleted'. When Phase 3's
signals router started calling log_user_activity(action="signal_ingested"),
every call violated that constraint. The Supabase insert raised, was
caught by the except block below, and was reported with print() —
which is easy to miss in production and wasn't being asserted on by any
test. The real fix is two parts:
  1. DB fix: supabase/migrations/20260615000000_signals_rls_and_log_action.sql
     adds 'signal_ingested' to the CHECK constraint. Apply with
     `supabase db push` if not already applied.
  2. Code fix (this file): print() → logger.exception(), so any future
     constraint mismatch (e.g. a new action value added without updating
     the CHECK constraint) is visible immediately instead of silently
     swallowed.

Phase 3: Yashika can add metadata columns (e.g. session_id, ip_address)
         by modifying only this file — no router changes needed.

SUPABASE TABLES REQUIRED
─────────────────────────
Apply: supabase/migrations/20260607000000_create_log_tables.sql

VIEW LOGS
──────────
Supabase Studio → Table Editor → select table name
NOT the Logs & Analytics tab — that shows infrastructure logs only.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

from lpi.models import SmilePhase

JsonData = bool | int | float | str | None | list["JsonData"] | dict[str, "JsonData"]

# Module-level logger. Uses the standard `logging` hierarchy so this
# integrates with whatever handler/formatter the app configures (uvicorn's
# default config, a JSON formatter in prod, log aggregation, etc.) instead
# of writing directly to stdout via print(), which is easy to lose.
logger = logging.getLogger(__name__)

# ── In-memory mirrors (kept for test assertions) ───────────────────────────────
# Tests call clear_*() helpers in their autouse fixture.
# In production these lists fill up but are never read — the real record
# is in Supabase. This is acceptable for Phase 2; Phase 3 can remove them.
#
# IMPORTANT FOR TESTS: these lists are appended to UNCONDITIONALLY, before
# the Supabase write is attempted (see each function below). That means a
# test asserting against e.g. `user_activity_logs` (the in-memory list)
# will pass even if the Supabase insert silently failed. To verify the
# audit trail actually exists in the database, query Supabase directly —
# see store.get_user_activity_logs() in store.py.
phase_transition_logs: list[dict] = []
user_activity_logs: list[dict] = []
system_logs: list[dict] = []


# ══════════════════════════════════════════════════════════════════════════════
# LOG TYPE 1 — SMILE Phase Transitions
# ══════════════════════════════════════════════════════════════════════════════

def log_transition(
    goal_id: str,
    from_phase: SmilePhase,
    to_phase: SmilePhase,
    user_id: str,
) -> None:
    """Record a valid SMILE phase transition.

    Writes to TWO places:
      1. Supabase `goal_phase_transitions` table  ← visible in Studio
      2. In-memory `phase_transition_logs` list   ← inspectable in tests

    If the Supabase insert fails (network issue, table missing), the error
    is caught and logged so it never breaks the goal update request.
    The in-memory log is always written regardless.

    str(SmilePhase) returns the slug automatically (e.g. "reality-emulation")
    so this function needs zero changes after any future enum additions.

    Args:
        goal_id    : UUID of the goal being transitioned
        from_phase : SmilePhase the goal is leaving
        to_phase   : SmilePhase the goal is entering
        user_id    : Owner of the goal (Phase 3: real JWT subject)
    """
    now_iso = datetime.now(UTC).isoformat()

    # Build the record once — shared by both destinations
    record = {
        "goal_id":         goal_id,
        "from_phase":      str(from_phase),
        "to_phase":        str(to_phase),
        "transitioned_at": now_iso,
        "user_id":         user_id,
    }

    # ── 1. Write to in-memory list (always, for tests) ─────────────────────
    phase_transition_logs.append(record)

    # ── 2. Write to Supabase (production audit trail) ──────────────────────
    # Import here (not at module top) so that test environments that don't
    # set SUPABASE_URL / SUPABASE_KEY still import this module without error.
    try:
        from lpi.config import settings
        from supabase import create_client  # type: ignore[attr-defined]

        key = settings.supabase_service_role_key or settings.supabase_key
        db = create_client(settings.supabase_url, key)
        db.table("goal_phase_transitions").insert(record).execute()

    except Exception:
        # NOTE: not yet migrated to logger.exception() like log_user_activity()
        # below — same fix should be applied here as a follow-up (out of
        # scope for the signals audit-log bug this pass addresses).
        # Never let a logging failure break the update endpoint.
        print(
            f"[log_transition] WARNING: Supabase insert failed for "
            f"goal {goal_id} ({from_phase}→{to_phase})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# LOG TYPE 2 — User Activity
# ══════════════════════════════════════════════════════════════════════════════

def log_user_activity(
    user_id: str,
    action: str,
    resource_id: str,
    metadata: dict | None = None,
) -> None:
    """Record a user-initiated mutation on a goal or signal.

    Writes to TWO places:
      1. Supabase `user_activity_logs` table  ← visible in Studio
      2. In-memory `user_activity_logs` list  ← inspectable in tests

    If the Supabase insert fails, the error is caught, logged via the
    standard `logging` module at ERROR level (with full traceback via
    logger.exception), and the calling endpoint is never broken.

    PHASE 3 FIX: this used to call print() on failure, which silently
    masked the CHECK-constraint mismatch that shipped with signal
    ingestion (see module docstring). logger.exception() surfaces the
    same failure through the app's normal logging pipeline instead.

    action values (use exactly these strings — must match CHECK constraint
    in supabase/migrations/20260607000000_create_log_tables.sql and
    20260615000000_signals_rls_and_log_action.sql):
      "goal_created"     → POST /api/v1/goals/
      "goal_updated"     → PATCH /api/v1/goals/{id}
      "goal_deleted"     → DELETE /api/v1/goals/{id}
      "signal_ingested"  → POST /api/v1/signals/

    metadata: optional context dict, e.g.:
      {"title": "Learn Docker", "priority": 7}                  on goal create
      {"stream": "lpi", "event_type": "pr_merged"}              on signal ingest

    Args:
        user_id     : Owner of the resource (Phase 3: real JWT subject)
        action      : One of the action strings above
        resource_id : UUID of the goal or signal being acted on
        metadata    : Optional extra context dict
    """
    now_iso = datetime.now(UTC).isoformat()
    metadata_payload = cast(dict[str, JsonData], metadata or {})

    # Build the record once — shared by both destinations
    record: dict[str, JsonData] = {
        "user_id":     user_id,
        "action":      action,
        "resource_id": resource_id,
        "metadata":    metadata_payload,
        "logged_at":   now_iso,
    }

    # ── 1. Write to in-memory list (always, for tests) ─────────────────────
    # NOTE: this happens BEFORE the Supabase write below, and unconditionally.
    # A test that only checks this list cannot detect a Supabase-side
    # failure (e.g. a CHECK constraint violation) — that's exactly how the
    # signal_ingested logging bug shipped without being caught. To verify
    # the row actually exists in the database, query Supabase directly
    # (see store.get_user_activity_logs()).
    user_activity_logs.append(record)

    # ── 2. Write to Supabase (production audit trail) ──────────────────────
    # Import here (not at module top) so that test environments that don't
    # set SUPABASE_URL / SUPABASE_KEY still import this module without error.
    try:
        from lpi.config import settings
        from supabase import create_client  # type: ignore[attr-defined]
        key = settings.supabase_service_role_key or settings.supabase_key
        db = create_client(settings.supabase_url, key)
        # supabase-py client insert() expects JSON-compatible payloads. The
        # local record is typed as JsonData to match that contract.
        db.table("user_activity_logs").insert(cast(JsonData, record)).execute()

    except Exception:
        # PHASE 3 FIX: logger.exception() instead of print().
        # - Goes through the standard logging pipeline (level=ERROR),
        #   so it's captured by whatever log aggregation/alerting the
        #   deployment already has, not just whoever happens to be
        #   watching stdout.
        # - Includes the full exception + traceback automatically, which
        #   print(f"...: {exc}") was discarding.
        # - Never re-raises: logging must never break the calling endpoint,
        #   that contract is unchanged.
        logger.exception(
            "Supabase insert into user_activity_logs failed "
            "(user_id=%s, action=%s, resource_id=%s). If action='signal_ingested', "
            "check that 20260615000000_signals_rls_and_log_action.sql has been "
            "pushed (`supabase db push`) — the CHECK constraint must include "
            "'signal_ingested'.",
            user_id, action, resource_id,
        )


# ══════════════════════════════════════════════════════════════════════════════
# LOG TYPE 3 — System Events
# ══════════════════════════════════════════════════════════════════════════════

def log_system_event(
    event: str,
    level: str = "info",
    detail: str = "",
    metadata: dict | None = None,
) -> None:
    """Record a platform-level system event (not user-initiated).

    Writes to TWO places:
      1. Supabase `system_logs` table  ← visible in Studio
      2. In-memory `system_logs` list  ← inspectable in tests

    If the Supabase insert fails, the error is caught and logged so it
    never breaks the calling code.

    level values (must match CHECK constraint):
      "info"    → normal operational events (app startup, connections)
      "warning" → degraded but recoverable (retry, fallback used)
      "error"   → failure requiring attention (unhandled exception, DB down)

    event examples: "app_startup", "supabase_connected", "store_error"

    Args:
        event    : Short identifier string for the event type
        level    : Severity — "info" | "warning" | "error"
        detail   : Human-readable description of what happened
        metadata : Optional extra context dict
    """
    now_iso = datetime.now(UTC).isoformat()
    metadata_payload = cast(dict[str, JsonData], metadata or {})

    # Build the record once — shared by both destinations
    record: dict[str, JsonData] = {
        "event":     event,
        "level":     level,
        "detail":    detail,
        "metadata":  metadata_payload,
        "logged_at": now_iso,
    }

    # ── 1. Write to in-memory list (always, for tests) ─────────────────────
    system_logs.append(record)

    # ── 2. Write to Supabase (production audit trail) ──────────────────────
    # Import here (not at module top) so that test environments that don't
    # set SUPABASE_URL / SUPABASE_KEY still import this module without error.
    try:
        from lpi.config import settings
        from supabase import create_client  # type: ignore[attr-defined]

        key = settings.supabase_service_role_key or settings.supabase_key
        db = create_client(settings.supabase_url, key)
        # supabase-py client insert() expects JSON-compatible payloads. The
        # local record is typed as JsonData to match that contract.
        db.table("system_logs").insert(cast(JsonData, record)).execute()

    except Exception:
        # NOTE: not yet migrated to logger.exception() — same follow-up as
        # log_transition() above, out of scope for this pass.
        print(
            f"[log_system_event] WARNING: Supabase insert failed for "
            f"event={event} level={level}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TEST HELPERS — call ONLY from conftest.py autouse fixture
# ══════════════════════════════════════════════════════════════════════════════

def clear_transition_logs() -> None:
    """Wipe phase_transition_logs. Does NOT delete Supabase rows.

    Called ONLY by the test autouse fixture. Tests run against local
    Supabase whose `goals` table is cleared by store.clear_all().
    """
    phase_transition_logs.clear()


def clear_activity_logs() -> None:
    """Wipe user_activity_logs. Does NOT delete Supabase rows."""
    user_activity_logs.clear()


def clear_system_logs_list() -> None:
    """Wipe system_logs. Does NOT delete Supabase rows."""
    system_logs.clear()


def clear_all_logs() -> None:
    """Wipe all three in-memory log lists. Use this in conftest autouse fixture.

    Replaces calling clear_transition_logs() individually — one call clears
    all three so new log types added in future only need updating here.
    """
    phase_transition_logs.clear()
    user_activity_logs.clear()
    system_logs.clear()