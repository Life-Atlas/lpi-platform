# new implementation with working code
"""Module 1 — Goal/Intent Registry.

Owner : Adil Islam  (Phase 2)
QA    : Daksh Garg

This is the clean, merged version of goals.py. The PR #11 version had
duplicate decorators and unreachable raise NotImplementedError statements
left inside every function — those have been removed here. This file
contains exactly one definition of each route, with the full working
implementation.

Data lives in lpi.store (not a local dict) so the pytest autouse fixture
can clear it between tests. Phase 3 swaps store lookups for Supabase calls.

SMILE transition rules (enforced here, not in Pydantic):
  Forward one step   SENSE→MODEL→INTERVENE→LEARN→EVOLVE  ✅
  Backward any step  LEARN→SENSE, INTERVENE→MODEL         ✅
  Skip forward       SENSE→INTERVENE, MODEL→LEARN         ❌ 422
  Same phase         SENSE→SENSE                          ❌ 422
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from lpi import store
from lpi.models import DeleteResponse, Goal, GoalCreate, GoalUpdate, SmilePhase
from lpi.smile import validate_phase_transition
from lpi.utils.logging import log_transition

router = APIRouter()


# ── POST /api/v1/goals/ ───────────────────────────────────────────────────────

@router.post("/", response_model=Goal, status_code=status.HTTP_201_CREATED)
def create_goal(goal: GoalCreate) -> Goal:
    """Create a new goal and return it with a server-assigned UUID.

    Returns HTTP 201 (not 200) to match the OpenAPI contract.
    user_id is hard-coded to "default_user" in Phase 2; Phase 3 will
    extract it from the JWT bearer token via get_current_user().
    """
    now = datetime.now(timezone.utc) # noqa: UP017
    new_goal = Goal(
        id=str(uuid.uuid4()),
        user_id="default_user",
        created_at=now,
        updated_at=now,
        **goal.model_dump(),        # spread GoalCreate fields (Pydantic v2)
    )
    with store._goals_lock:
        store._goals[new_goal.id] = new_goal
    return new_goal


# ── GET /api/v1/goals/ ────────────────────────────────────────────────────────

@router.get("/", response_model=list[Goal])
def list_goals(
    user_id: str | None = None,
    smile_phase: SmilePhase | None = None,
) -> list[Goal]:
    """List all goals. Optional filters: user_id, smile_phase.

    Example: GET /api/v1/goals/?smile_phase=sense
    All filters are AND-combined. Returns [] if no goals exist.
    """
    with store._goals_lock:
        goals = list(store._goals.values())

    if user_id is not None:
        goals = [g for g in goals if g.user_id == user_id]
    if smile_phase is not None:
        goals = [g for g in goals if g.smile_phase == smile_phase]

    return goals


# ── GET /api/v1/goals/{goal_id} ───────────────────────────────────────────────

@router.get("/{goal_id}", response_model=Goal)
def get_goal(goal_id: str) -> Goal:
    """Fetch a single goal by UUID. Returns 404 if it does not exist."""
    with store._goals_lock:
        goal = store._goals.get(goal_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    return goal


# ── PATCH /api/v1/goals/{goal_id} ────────────────────────────────────────────

@router.patch("/{goal_id}", response_model=Goal)
def update_goal(goal_id: str, update: GoalUpdate) -> Goal:
    """Partially update a goal. All request fields are optional.

    The lock wraps read → validate → write atomically so two concurrent
    PATCH requests on the same goal cannot corrupt each other.
    """
    with store._goals_lock:
        goal = store._goals.get(goal_id)
        if goal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal {goal_id} not found",
            )

        # SMILE transition validation — only checked when phase actually changes
        if update.smile_phase is not None and update.smile_phase != goal.smile_phase:
            if not validate_phase_transition(goal.smile_phase, update.smile_phase):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Invalid SMILE transition: {goal.smile_phase} → "
                        f"{update.smile_phase}. Skipping phases is not allowed."
                    ),
                )
            # Log the transition BEFORE applying the update (Yashika's spec)
            log_transition(
                goal_id=goal_id,
                from_phase=goal.smile_phase,
                to_phase=update.smile_phase,
                user_id=goal.user_id,
            )

        # exclude_unset=True ensures only the fields the caller actually sent
        # are included — without it, all None fields would overwrite real values
        update_data = update.model_dump(exclude_unset=True)
        updated_goal = goal.model_copy(
            update={**update_data, "updated_at": datetime.now(timezone.utc)} # noqa: UP017
        )
        store._goals[goal_id] = updated_goal

    return updated_goal


# ── DELETE /api/v1/goals/{goal_id} ───────────────────────────────────────────

@router.delete("/{goal_id}", response_model=DeleteResponse)
def delete_goal(goal_id: str) -> DeleteResponse:
    """Remove a goal. Returns { deleted: true, id: "..." }.

    Field name is `id` (not `goal_id`) — matches the OpenAPI contract.
    Returns 404 if the goal does not exist.
    """
    with store._goals_lock:
        if goal_id not in store._goals:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal {goal_id} not found",
            )
        store._goals.pop(goal_id)
    return DeleteResponse(deleted=True, id=goal_id)