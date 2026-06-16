-- ─────────────────────────────────────────────────────────────────────────────
-- Migration: activity_signals RLS + user_activity_logs CHECK constraint fix
-- Owner  : Adil Islam
-- Date   : 2026-06-15
-- ─────────────────────────────────────────────────────────────────────────────
--
-- TWO THINGS IN THIS MIGRATION
-- ──────────────────────────────
--
-- 1. ROW LEVEL SECURITY on activity_signals
--    The auth PR added RLS to goals (20260612) and logs (20260613) tables.
--    activity_signals was created in 20260611 — before the auth PR — so it
--    has no RLS. Adding it now keeps all tables consistent and ensures that
--    if the frontend ever queries Supabase directly (bypassing the FastAPI
--    backend), users can only see their own signals.
--
--    Note: The FastAPI backend uses the service_role key which bypasses RLS.
--    RLS is a second layer of defense — not the primary auth mechanism.
--    Primary auth = Depends(get_current_user) in the router.
--
-- 2. ADD 'signal_ingested' TO user_activity_logs CHECK CONSTRAINT
--    The CHECK constraint in 20260607 only allows:
--      'goal_created' | 'goal_updated' | 'goal_deleted'
--    The signals router calls log_user_activity(action='signal_ingested'),
--    which fails the CHECK and raises an exception.
--    Currently caught by try/except in the router, but the fix belongs here.
--    This migration drops the old constraint and adds a new one including
--    'signal_ingested'.
-- ─────────────────────────────────────────────────────────────────────────────


-- ── Part 1: RLS for activity_signals ─────────────────────────────────────────

ALTER TABLE activity_signals ENABLE ROW LEVEL SECURITY;

-- SELECT: users can only read their own signals
CREATE POLICY "Users read own signals"
    ON activity_signals
    FOR SELECT
    USING (auth.uid()::text = user_id);

-- INSERT: users can only insert signals under their own user_id
CREATE POLICY "Users insert own signals"
    ON activity_signals
    FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

-- UPDATE: users can only update their own signals
CREATE POLICY "Users update own signals"
    ON activity_signals
    FOR UPDATE
    USING (auth.uid()::text = user_id);

-- DELETE: users can only delete their own signals
CREATE POLICY "Users delete own signals"
    ON activity_signals
    FOR DELETE
    USING (auth.uid()::text = user_id);


-- ── Part 2: Fix user_activity_logs CHECK constraint ───────────────────────────

-- Drop the existing constraint (must drop before recreating with new values)
ALTER TABLE user_activity_logs
    DROP CONSTRAINT IF EXISTS user_activity_logs_action_check;

-- Add the updated constraint including 'signal_ingested'
ALTER TABLE user_activity_logs
    ADD CONSTRAINT user_activity_logs_action_check
    CHECK (action IN (
        'goal_created',
        'goal_updated',
        'goal_deleted',
        'signal_ingested'   -- added: Phase 3 signals logging
    ));
