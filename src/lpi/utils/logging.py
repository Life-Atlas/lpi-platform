"""SMILE phase transition logger — Phase 2 (Supabase-backed, dual-sync).

Design spec : Yashika Verma
Updated     : Adil Islam — Phase 2 Supabase integration — all 3 log types

WHY THIS FILE WAS CHANGED
─────────────────────────
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

If the Supabase write fails for any reason, the error is caught, printed
to stdout, and the request continues normally. Logging must NEVER break
an API endpoint.

  log_transition()     → goal_phase_transitions  (SMILE phase changes only)
  log_user_activity()  → user_activity_logs      (create, update, delete)
  log_system_event()   → system_logs             (startup, errors, warnings)

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

from datetime import UTC, datetime
from typing import cast

from lpi.models import SmilePhase

JsonData = bool | int | float | str | None | list["JsonData"] | dict[str, "JsonData"]

# ── In-memory mirrors (kept for test assertions) ───────────────────────────────
# Tests call clear_*() helpers in their autouse fixture.
# In production these lists fill up but are never read — the real record
# is in Supabase. This is acceptable for Phase 2; Phase 3 can remove them.
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
    is caught and logged to stdout so it never breaks the goal update request.
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

    except Exception as exc:
        # Never let a logging failure break the update endpoint.
        # Print is visible in `uvicorn` stdout and Supabase Edge Function logs.
        print(
            f"[log_transition] WARNING: Supabase insert failed for "
            f"goal {goal_id} ({from_phase}→{to_phase}): {exc}"
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
    """Record a user-initiated mutation on a goal.

    Writes to TWO places:
      1. Supabase `user_activity_logs` table  ← visible in Studio
      2. In-memory `user_activity_logs` list  ← inspectable in tests

    If the Supabase insert fails, the error is caught and logged to stdout
    so it never breaks the calling endpoint.

    action values (use exactly these strings — must match CHECK constraint):
      "goal_created"  → POST /api/v1/goals/
      "goal_updated"  → PATCH /api/v1/goals/{id}
      "goal_deleted"  → DELETE /api/v1/goals/{id}

    metadata: optional context dict, e.g.:
      {"title": "Learn Docker", "priority": 7}       on create
      {"updated_fields": ["title", "urgency_flag"]}  on update
      {"title": "Learn Docker"}                       on delete

    Args:
        user_id     : Owner of the goal (Phase 3: real JWT subject)
        action      : One of the three action strings above
        resource_id : UUID of the goal being acted on
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

    except Exception as exc:
        # Never let a logging failure break the calling endpoint.
        print(
            f"[log_user_activity] WARNING: Supabase insert failed for "
            f"user {user_id} action={action} resource={resource_id}: {exc}"
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

    If the Supabase insert fails, the error is caught and logged to stdout
    so it never breaks the calling code.

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

    except Exception as exc:
        # Never let a logging failure break the calling code.
        print(
            f"[log_system_event] WARNING: Supabase insert failed for "
            f"event={event} level={level}: {exc}"
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
