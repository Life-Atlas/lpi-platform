# Activity Signals Backend Documentation

## Data Fields
* `id`: UUID primary key generated automatically by the server.
* `user_id`: UUID mapping to the application user triggering the event.
* `stream`: String grouping identifier for the source system (e.g., `goal_registry`, `boardy_match`).
* `event_type`: String action slug tracking specific user behaviors (e.g., `goal_created`, `phase_changed`).
* `payload`: Flexible JSONB dictionary holding stream-specific nested metadata.
* `timestamp`: TIMESTAMPTZ server-generated ingestion timestamp.

## Indexing Strategy
To optimize downstream recommendation engine evaluations and protect platform query speeds, the following performance indexes are applied:
* **Single-Column B-Tree Indexes:** Dedicated lookups on `user_id`, `stream`, `event_type`, and `timestamp` (DESC) to isolate high-volume event data.
* **Composite Timeline Index (`idx_activity_signals_user_time`):** A multi-column index on `(user_id, timestamp DESC)`. This directly optimizes the high-frequency frontend timeline view query (`WHERE user_id = X ORDER BY timestamp DESC`) into a single-pass scan.
* **JSONB Inverted Index (`idx_activity_signals_payload`):** A Generalized Inverted Index (GIN) applied to the `payload` column to ensure lightning-fast queries inside nested JSONB metadata without defaulting to costly sequential table scans.

## Security & Access Control (Row-Level Security)
To ensure isolation and prevent cross-tenant data leaks, Supabase Row-Level Security (RLS) is strictly enforced on this table:
* **Read Access (SELECT):** Authenticated users can only view activity signals where the entry's `user_id` matches their verified session identity via `auth.uid()`.
* **Write Access (INSERT):** Authenticated users can only inject new activity signals if the `user_id` field strictly matches their verified session identity via `auth.uid()`. Cross-tenant data injection or spoofing is programmatically blocked at the database level.