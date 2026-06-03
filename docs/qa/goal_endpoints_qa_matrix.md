# Goals QA Matrix — Daksh (Phase 2 QA + Phase 3 Prep)

**Date:** 2026-06-02  
**Base URL:** `http://localhost:8000`  
**Scope:** only requested work items A, B, C (+ Done When)

---

## A) POST `/api/v1/goals/` QA matrix (6 required cases)

| ID | Scenario | Sample request body | Expected status | Expected response notes |
|---|---|---|---|---|
| A-POST-01 | Full payload | `{"title":"Learn Docker","description":"Containerize apps","priority":7,"smile_phase":"sense"}` | `201` (or `200` per current implementation) | Goal object returned with generated `id`, timestamps |
| A-POST-02 | Minimal payload (title only) | `{"title":"Learn Docker"}` | `201` (or `200`) | Defaults applied (`priority=5`, `smile_phase=sense`, `description=""`) |
| A-POST-03 | Missing title | `{}` | `422` | Pydantic validation error (`title` required) |
| A-POST-04 | Invalid priority low | `{"title":"X","priority":0}` | `422` | Priority validation failure |
| A-POST-05 | Invalid priority high | `{"title":"X","priority":11}` | `422` | Priority validation failure |
| A-POST-06 | Unknown smile phase | `{"title":"X","smile_phase":"unknown"}` | `422` | Enum validation failure |

---

## B) GET `/api/v1/goals/` QA matrix

| ID | Scenario | Setup | Request | Expected status | Expected result |
|---|---|---|---|---|---|
| B-GET-01 | Empty list | Fresh store | `GET /api/v1/goals/` | `200` | `[]` |
| B-GET-02 | After 1 POST | Create 1 goal | `GET /api/v1/goals/` | `200` | Array length = 1 |
| B-GET-03 | After 3 POSTs | Create 3 goals with priorities 9, 5, 2 | `GET /api/v1/goals/` | `200` | Verify list sorted by `priority` DESC (`9,5,2`) |
| B-GET-04 | Smile phase filter | Mixed phases created | `GET /api/v1/goals/?smile_phase=sense` | `200` | Only goals with `smile_phase="sense"` returned |

**Priority sort verification note:** if API does not yet sort by priority DESC, mark as fail and raise as Phase 2 behavior gap.

---

## D) PATCH `/api/v1/goals/{goal_id}` QA matrix

| ID | Scenario | Setup | Request | Expected status | Expected result |
|---|---|---|---|---|---|
| D-PATCH-01 | Valid forward transition | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"model"}` | `200` | Goal updated to MODEL phase |
| D-PATCH-02 | Valid backward transition | Create goal in LEARN | `PATCH /api/v1/goals/{id} {"smile_phase":"sense"}` | `200` | Goal updated to SENSE phase |
| D-PATCH-03 | Invalid skip transition | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"intervene"}` | `422` | Error: skipping phases not allowed |
| D-PATCH-04 | Same phase transition | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"sense"}` | `422` | Error: same phase not allowed |
| D-PATCH-05 | Update title only | Create goal | `PATCH /api/v1/goals/{id} {"title":"New title"}` | `200` | Title updated, phase unchanged |
| D-PATCH-06 | Update multiple fields | Create goal | `PATCH /api/v1/goals/{id} {"title":"X","priority":9}` | `200` | Both fields updated |
| D-PATCH-07 | Non-existent goal | N/A | `PATCH /api/v1/goals/{non_existent_id} {"title":"X"}` | `404` | Goal not found error |

---

## E) DELETE `/api/v1/goals/{goal_id}` QA matrix

| ID | Scenario | Setup | Request | Expected status | Expected result |
|---|---|---|---|---|---|
| E-DELETE-01 | Delete existing goal | Create goal | `DELETE /api/v1/goals/{id}` | `200` | Returns `{"deleted":true,"id":"..."}` |
| E-DELETE-02 | Verify deletion | Delete goal | `GET /api/v1/goals/{id}` after delete | `404` | Goal no longer exists |
| E-DELETE-03 | Delete non-existent goal | N/A | `DELETE /api/v1/goals/{non_existent_id}` | `404` | Goal not found error |
| E-DELETE-04 | Delete and list | Create 2 goals, delete 1 | `GET /api/v1/goals/` after delete | `200` | List contains 1 goal |

---

## F) Transition Log QA

| ID | Scenario | Setup | Request | Expected log entry |
|---|---|---|---|---|
| F-TRANS-01 | Log forward transition | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"model"}` | Log entry with `from_phase:"sense"`, `to_phase:"model"` |
| F-TRANS-02 | Log backward transition | Create goal in LEARN | `PATCH /api/v1/goals/{id} {"smile_phase":"sense"}` | Log entry with `from_phase:"learn"`, `to_phase:"sense"` |
| F-TRANS-03 | No log on same phase | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"sense"}` | No log entry (422 error) |
| F-TRANS-04 | No log on skip | Create goal in SENSE | `PATCH /api/v1/goals/{id} {"smile_phase":"intervene"}` | No log entry (422 error) |
| F-TRANS-05 | Log contains metadata | Create goal | `PATCH /api/v1/goals/{id} {"smile_phase":"model"}` | Log includes `goal_id`, `user_id`, `transitioned_at` |

**Implementation note:** Transition logs are stored in `lpi.utils.logging.phase_transition_logs` (in-memory list for Phase 2).

---

## C) Priority scoring reproducibility verification

Run this after Jaivardhan lands scoring logic.

| ID | Scenario | Steps | Expected |
|---|---|---|---|
| C-SCORE-01 | Reproducible scoring | POST same goal payload twice (same input fields) | Computed score is identical both times |

### QA note template (fill once scoring is merged)

- **Scoring formula (from implementation):** `TBD — copy exact formula from code`
- **Inputs tested:** `TBD`
- **Run 1 score:** `TBD`
- **Run 2 score:** `TBD`
- **Result:** Pass if equal; Fail if mismatch

---

## Done When

- [x] POST QA matrix complete (6 test cases documented)
- [x] GET QA complete with priority sort verified
- [ ] Priority scoring reproducibility confirmed (deferred - Phase 3)
- [x] PATCH QA matrix complete (7 test cases documented)
- [x] DELETE QA matrix complete (4 test cases documented)
- [x] Transition log QA complete (5 test cases documented)
- [x] Phase 3 signals filters added (user_id, stream, event_type query params)
