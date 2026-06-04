"""Module 1 — Goal/Intent Registry.

Owner : Adil Islam  (Phase 2)
QA    : Daksh Garg

═══════════════════════════════════════════════════════════
TASK C CHANGE — What changed and WHY
═══════════════════════════════════════════════════════════

1. `list_goals` now sorts using sort_goals_by_score() instead of
   a raw priority sort. This makes urgency_flag and SMILE phase
   affect the order goals are returned.

   Before Task C:
     goals.sort(key=lambda g: (-g.priority, g.created_at))
     ← Only raw priority determined order

   After Task C:
     goals = sort_goals_by_score(goals)
     ← composite score (priority + phase + urgency) determines order

2. create_goal and update_goal do NOT need explicit urgency_flag changes.
   Here is WHY:

   create_goal uses `**goal.model_dump()` to spread GoalCreate fields
   into the Goal constructor. GoalCreate now has urgency_flag, so
   model_dump() includes it automatically. No code change needed.

   update_goal uses model_dump(exclude_unset=True) + model_copy().
   If the caller sends {"urgency_flag": true}, model_dump returns
   {"urgency_flag": True} and model_copy updates only that field.
   If the caller doesn't send urgency_flag, it's excluded and left
   unchanged. No code change needed — Pydantic handles it.

═══════════════════════════════════════════════════════════
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from lpi import store
from lpi.models import DeleteResponse, Goal, GoalCreate, GoalUpdate, SmilePhase

# TASK C: import the SMILE-aware sort function
from lpi.scoring import sort_goals_by_score
from lpi.smile import validate_phase_transition
from lpi.utils.logging import log_transition

router = APIRouter()


@router.post("/", response_model=Goal, status_code=status.HTTP_201_CREATED)
def create_goal(goal: GoalCreate) -> Goal:
    """Create a new goal and store it.

    urgency_flag is handled automatically:
    goal.model_dump() returns ALL GoalCreate fields including urgency_flag.
    The ** spread passes it to the Goal constructor without any explicit code.

    Example: POST with {"title": "X", "urgency_flag": true}
    → GoalCreate has urgency_flag=True
    → goal.model_dump() = {"title":"X","urgency_flag":True,"priority":5,...}
    → Goal(id=..., user_id=..., **...) gets urgency_flag=True
    """
    now = datetime.now(UTC)
    new_goal = Goal(
        id=str(uuid.uuid4()),
        user_id="default_user",     # Phase 3: use get_current_user(request)
        created_at=now,
        updated_at=now,
        **goal.model_dump(),        # includes urgency_flag automatically
    )
    with store._goals_lock:
        store._goals[new_goal.id] = new_goal
    return new_goal


@router.get("/", response_model=list[Goal])
def list_goals(
    user_id: str | None = None,
    smile_phase: SmilePhase | None = None,
) -> list[Goal]:
    """Return goals sorted by SMILE-weighted composite score.

    TASK C: replaced the raw priority sort with sort_goals_by_score().
    This makes urgency_flag and SMILE phase affect the returned order.

    Filter parameters are AND-combined:
      ?user_id=default_user         → only that user's goals
      ?smile_phase=sense            → only goals in SENSE phase
      ?user_id=X&smile_phase=sense  → both filters applied
    """
    with store._goals_lock:
        goals = list(store._goals.values())

    # Apply optional filters
    if user_id is not None:
        goals = [g for g in goals if g.user_id == user_id]
    if smile_phase is not None:
        goals = [g for g in goals if g.smile_phase == smile_phase]

    # TASK C: sort by composite score instead of raw priority
    # sort_goals_by_score() uses:
    #   (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)
    # A goal with urgency_flag=True floats above same-priority non-urgent goals.
    return sort_goals_by_score(goals)


@router.get("/{goal_id}", response_model=Goal)
def get_goal(goal_id: str) -> Goal:
    """Fetch a single goal by UUID. 404 if not found."""
    with store._goals_lock:
        goal = store._goals.get(goal_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    return goal


@router.patch("/{goal_id}", response_model=Goal)
def update_goal(goal_id: str, update: GoalUpdate) -> Goal:
    """Partially update a goal. All fields optional.

    urgency_flag is handled automatically by Pydantic:

    Case A — caller sends {"urgency_flag": true}:
      model_dump(exclude_unset=True) → {"urgency_flag": True}
      model_copy(update={"urgency_flag": True, ...}) → flag activated

    Case B — caller sends {"title": "New title"} (no urgency_flag):
      model_dump(exclude_unset=True) → {"title": "New title"}
      urgency_flag is NOT in update_data → model_copy leaves it unchanged

    The exclude_unset=True is the key: it only includes fields the caller
    actually sent, so missing fields never accidentally reset to defaults.
    """
    with store._goals_lock:
        goal = store._goals.get(goal_id)
        if goal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal {goal_id} not found",
            )

        # SMILE transition validation (only when phase actually changes)
        if update.smile_phase is not None and update.smile_phase != goal.smile_phase:
            if not validate_phase_transition(goal.smile_phase, update.smile_phase):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Invalid SMILE transition: {goal.smile_phase} → "
                        f"{update.smile_phase}. Skipping phases is not allowed."
                    ),
                )
            # Log transition before applying the update
            log_transition(
                goal_id=goal_id,
                from_phase=goal.smile_phase,
                to_phase=update.smile_phase,
                user_id=goal.user_id,
            )

        # exclude_unset=True: only send fields the caller actually included
        update_data = update.model_dump(exclude_unset=True)
        updated_goal = goal.model_copy(
            update={**update_data, "updated_at": datetime.now(UTC)}
        )
        store._goals[goal_id] = updated_goal

    return updated_goal


@router.delete("/{goal_id}", response_model=DeleteResponse)
def delete_goal(goal_id: str) -> DeleteResponse:
    """Remove a goal. Returns {"deleted": true, "id": "..."}.

    Field is `id` (not `goal_id`) — matches the OpenAPI contract.
    """
    with store._goals_lock:
        if goal_id not in store._goals:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal {goal_id} not found",
            )
        store._goals.pop(goal_id)
    return DeleteResponse(deleted=True, id=goal_id)