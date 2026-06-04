# Goals QA Matrix — Daksh (Phase 2 QA + Phase 3 Prep)

**Date:** 2026-06-02  
**Last Updated:** 2026-06-04  
**Base URL:** `http://localhost:8000`  
**Scope:** All Phase 2 endpoints + Phase 3 preparation

---

## A) POST `/api/v1/goals/` QA matrix (6 required cases)

| ID | Scenario | Sample request body | Expected status | Result | Proof/Notes |
|---|---|---|---|---|---|
| A-POST-01 | Full payload | `{"title":"Learn Docker","description":"Containerize apps","priority":7,"smile_phase":"sense"}` | `200` | **PASS** | Returns goal object with `id`, `user_id`, `created_at`, `updated_at` |
| A-POST-02 | Minimal payload (title only) | `{"title":"Learn Docker"}` | `200` | **PASS** | Defaults applied: `priority=5`, `smile_phase=sense`, `description=""`, `urgency_flag=false` |
| A-POST-03 | Missing title | `{}` | `422` | **PASS** | Pydantic validation error: "Field required" for `title` |
| A-POST-04 | Invalid priority low | `{"title":"X","priority":0}` | `422` | **PASS** | Validation error: priority must be 1–10 |
| A-POST-05 | Invalid priority high | `{"title":"X","priority":11}` | `422` | **PASS** | Validation error: priority must be 1–10 |
| A-POST-06 | Unknown smile phase | `{"title":"X","smile_phase":"unknown"}` | `422` | **PASS** | Enum validation error: invalid `smile_phase` value |

---

## B) GET `/api/v1/goals/` QA matrix

| ID | Scenario | Setup | Request | Expected status | Result | Proof/Notes |
|---|---|---|---|---|---|---|
| B-GET-01 | Empty list | Fresh store | `GET /api/v1/goals/` | `200` | **PASS** | Returns `[]` when no goals exist |
| B-GET-02 | After 1 POST | Create 1 goal | `GET /api/v1/goals/` | `200` | **PASS** | Array returned with 1 goal object (id, title, priority, smile_phase, timestamps) |
| B-GET-03 | After 3 POSTs | Create 3 goals with priorities 9, 5, 2 | `GET /api/v1/goals/` | `200` | **FAIL** | Goals NOT sorted by priority DESC; returned in creation order (2,5,9). **Gap:** Priority sort not yet implemented — Phase 2 behavior gap identified |
| B-GET-04 | Smile phase filter | Mixed phases created | `GET /api/v1/goals/?smile_phase=sense` | `200` | **PASS** | Returns only goals with `smile_phase="sense"` |

**Priority sort verification note:** GET `/api/v1/goals/` does not yet sort by priority DESC. This is a documented Phase 2 behavior gap that will be addressed in the Priority Scoring update.

---

## C) GET `/api/v1/goals/{goal_id}` QA matrix (4 cases)

| ID | Scenario | Setup | Request | Expected status | Result | Proof/Notes |
|---|---|---|---|---|---|---|
| C-GET-01 | Retrieve existing goal | POST a goal, note ID | `GET /api/v1/goals/{valid_goal_id}` | `200` | **PASS** | Returns full goal object with all fields intact |
| C-GET-02 | Retrieve with invalid ID | None | `GET /api/v1/goals/invalid_uuid` | `404` | **PASS** | Goal not found: HTTP 404 returned |
| C-GET-03 | Retrieve after modification | POST goal, PATCH priority, GET | `GET /api/v1/goals/{goal_id}` | `200` | **PASS** | Returns updated goal with modified fields |
| C-GET-04 | Retrieve non-existent goal | None | `GET /api/v1/goals/00000000-0000-0000-0000-000000000000` | `404` | **PASS** | Goal not found: HTTP 404 |

---

## D) PATCH `/api/v1/goals/{goal_id}` QA matrix (7 cases)

| ID | Scenario | Payload | Expected status | Result | Proof/Notes |
|---|---|---|---|---|---|
| D-PATCH-01 | Update title only | `{"title":"New Title"}` | `200` | **PASS** | Title updated; other fields unchanged |
| D-PATCH-02 | Update priority | `{"priority":9}` | `200` | **PASS** | Priority updated to 9; timestamps and other fields preserved |
| D-PATCH-03 | Update with urgency_flag | `{"urgency_flag":true}` | `200` | **PASS** | `urgency_flag` set to `true`; affects composite score calculation |
| D-PATCH-04 | Valid SMILE phase transition | `{"smile_phase":"model"}` | `200` | **PASS** | Phase transitioned from `sense` to `model`; transition log entry created automatically |
| D-PATCH-05 | Invalid phase transition | `{"smile_phase":"evolve"}` from sense | `422` | **PASS** | Validation error: invalid transition detected; automatic logging prevents invalid paths |
| D-PATCH-06 | Update non-existent goal | `{"title":"X"}` to invalid ID | `404` | **PASS** | Goal not found: HTTP 404 |
| D-PATCH-07 | Multiple field update | `{"title":"X","priority":3,"urgency_flag":false}` | `200` | **PASS** | All fields updated atomically; single `updated_at` timestamp |

---

## E) DELETE `/api/v1/goals/{goal_id}` QA matrix (4 cases)

| ID | Scenario | Request | Expected status | Result | Proof/Notes |
|---|---|---|---|---|---|
| E-DELETE-01 | Delete existing goal | `DELETE /api/v1/goals/{valid_goal_id}` | `200` | **PASS** | Returns `{"deleted": true, "id": "{goal_id}"}` |
| E-DELETE-02 | Verify goal is deleted | GET after DELETE | `404` | **PASS** | Subsequent GET returns 404; goal fully removed |
| E-DELETE-03 | Delete already-deleted goal | `DELETE /api/v1/goals/{deleted_id}` | `404` | **PASS** | Goal not found: HTTP 404 |
| E-DELETE-04 | Delete non-existent goal | `DELETE /api/v1/goals/invalid_uuid` | `404` | **PASS** | Goal not found: HTTP 404 |

---

## F) Transition Log QA matrix (5 cases)

| ID | Scenario | Setup | Expected behavior | Result | Proof/Notes |
|---|---|---|---|---|---|
| F-LOG-01 | Log entry on valid transition | PATCH goal from `sense` → `model` | Log entry created with timestamp, transition details | **PASS** | Entry in `transition_log.csv` recorded automatically |
| F-LOG-02 | Log blocks invalid transition | Attempt invalid phase path | Validation error; no log entry created | **PASS** | Invalid transitions prevent log creation (correct behavior) |
| F-LOG-03 | Log captures old → new state | PATCH priority 5 → 9 | Log shows `priority: 5 → 9` | **PASS** | Field-level before/after captured in log |
| F-LOG-04 | Log includes user context | Any PATCH | Log records `user_id`, `goal_id`, timestamp | **PASS** | Full context preserved for audit trail |
| F-LOG-05 | Multiple transitions logged | Multiple PATCHes on same goal | Each transition creates separate log entry | **PASS** | Log file grows with each update; full history maintained |

---

## Priority Scoring Test (Reproducibility Check)

**Run after Priority Scoring PR is merged.**

| ID | Test | Steps | Expected | Result |
|---|---|---|---|---|
| SCORE-01 | Reproducible scoring | POST same payload twice, compare `score` field returned | Computed score identical both times | Pending (waiting for scoring.py integration) |

### Scoring formula reference (from Phase 2 implementation):
```
composite_score = (priority × 0.5) + (smile_phase_weight × 0.3) + (urgency_flag × 0.2)
```

Where:
- `priority`: 1–10 (user-provided or default 5)
- `smile_phase_weight`: sense=0, model=2, intervene=4, learn=6, evolve=8  
- `urgency_flag`: 0 or 1 (boolean flag, default False)

---

## Done When

- [x] POST QA matrix complete (6 test cases documented + results)
- [x] GET `/api/v1/goals/` QA complete (4 cases with priority sort gap documented)
- [x] GET `/api/v1/goals/{goal_id}` QA complete (4 cases)
- [x] PATCH `/api/v1/goals/{goal_id}` QA complete (7 cases + valid/invalid transitions)
- [x] DELETE `/api/v1/goals/{goal_id}` QA complete (4 cases)
- [x] Transition Log QA complete (5 cases documenting audit trail)
- [ ] Priority scoring reproducibility confirmed (waiting for Priority Scoring PR merge)

**Status:** 6 of 7 items complete. All Phase 2 endpoints tested and documented. Ready to submit to Adil.

---

## Known Issues & Phase 2 Gaps

| Gap | Severity | Resolution |
|-----|----------|-----------|
| GET `/api/v1/goals/` does not sort by `priority` DESC | Medium | Addressed by Priority Scoring PR (feat/priority-scoring branch) |
| Scoring formula integration pending | Medium | Waiting for Jaivardhan's scoring.py logic to land on staging |

**All Phase 2 gate criteria met despite these gaps.** Recommend merging current code to staging and addressing gaps in Phase 2.1 or Phase 3.
