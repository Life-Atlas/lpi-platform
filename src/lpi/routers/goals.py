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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from lpi import store
from lpi.middleware.auth import UserContext, get_current_user, get_current_user_context
from lpi.models import DeleteResponse, Goal, GoalCreate, GoalUpdate, SmilePhase

# TASK C: import the SMILE-aware sort function
from lpi.scoring import sort_goals_by_score
from lpi.smile import validate_phase_transition
from lpi.utils.logging import log_transition, log_user_activity

router = APIRouter()


@router.post("/", response_model=Goal, status_code=status.HTTP_201_CREATED)
def create_goal(goal: GoalCreate, user_id: str = Depends(get_current_user)) -> Goal:
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
        user_id=user_id,
        created_at=now,
        updated_at=now,
        **goal.model_dump(),  # includes urgency_flag automatically
    )
    store.insert_goal(new_goal)

    # USER ACTIVITY LOG — dual-sync: in-memory + Supabase user_activity_logs
    log_user_activity(
        user_id=new_goal.user_id,
        action="goal_created",
        resource_id=new_goal.id,
        metadata={
            "title": new_goal.title,
            "priority": new_goal.priority,
            "smile_phase": str(new_goal.smile_phase),
            "urgency_flag": new_goal.urgency_flag,
        },
    )

    return new_goal


@router.get("/", response_model=list[Goal])
def list_goals(
    smile_phase: SmilePhase | None = None,
    fetch_all: bool = Query(False, alias="all"),
    user_context: UserContext = Depends(get_current_user_context),
) -> list[Goal]:
    """Return the caller's goals, sorted by SMILE-weighted composite score.

    TASK C: replaced the raw priority sort with sort_goals_by_score().
    This makes urgency_flag and SMILE phase affect the returned order.

    Results are always scoped to the authenticated user unless all=True and user is admin. Optional filter:
      ?smile_phase=reality-emulation → only goals in REALITY_EMULATION phase
    """
    target_user_id = None if (fetch_all and user_context.is_admin) else user_context.user_id
    goals = store.list_goals(user_id=target_user_id, smile_phase=smile_phase)

    # TASK C: sort by composite score instead of raw priority
    # sort_goals_by_score() uses:
    #   (priority × 0.5) + (phase_weight × 0.3) + (urgency_flag × 0.2)
    # A goal with urgency_flag=True floats above same-priority non-urgent goals.
    return sort_goals_by_score(goals)


@router.get("/{goal_id}", response_model=Goal)
def get_goal(goal_id: str, user_context: UserContext = Depends(get_current_user_context)) -> Goal:
    """Fetch a single goal by UUID. 404 if not found or not owned by the caller (unless admin)."""
    goal = store.get_goal(goal_id)
    if goal is None or (goal.user_id != user_context.user_id and not user_context.is_admin):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    return goal


@router.patch("/{goal_id}", response_model=Goal)
def update_goal(goal_id: str, update: GoalUpdate, user_id: str = Depends(get_current_user)) -> Goal:
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
    goal = store.get_goal(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )

    # SMILE transition validation (only when phase actually changes)
    if update.smile_phase is not None and update.smile_phase != goal.smile_phase:
        if not validate_phase_transition(goal.smile_phase, update.smile_phase):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Invalid SMILE transition: {goal.smile_phase} → "
                    f"{update.smile_phase}. Skipping phases is not allowed."
                ),
            )
        # TRANSITION LOG — dual-sync: in-memory + Supabase goal_phase_transitions
        # Written before applying the update so the from_phase is still correct.
        # str(SmilePhase) returns the slug automatically — no literal strings here.
        log_transition(
            goal_id=goal_id,
            from_phase=goal.smile_phase,
            to_phase=update.smile_phase,
            user_id=goal.user_id,
        )

    # exclude_unset=True: only send fields the caller actually included
    update_data = update.model_dump(exclude_unset=True)
    updated_goal = store.update_goal(
        goal_id,
        {**update_data, "updated_at": datetime.now(UTC).isoformat()},
    )

    # USER ACTIVITY LOG — dual-sync: in-memory + Supabase user_activity_logs
    log_user_activity(
        user_id=goal.user_id,
        action="goal_updated",
        resource_id=goal_id,
        metadata={"updated_fields": list(update_data.keys())},
    )

    return updated_goal


@router.delete("/{goal_id}", response_model=DeleteResponse)
def delete_goal(goal_id: str, user_id: str = Depends(get_current_user)) -> DeleteResponse:
    """Remove a goal. Returns {"deleted": true, "id": "..."}.

    Field is `id` (not `goal_id`) — matches the OpenAPI contract.
    """
    goal = store.get_goal(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found",
        )
    store.delete_goal(goal_id)

    # USER ACTIVITY LOG — dual-sync: in-memory + Supabase user_activity_logs
    log_user_activity(
        user_id=goal.user_id,
        action="goal_deleted",
        resource_id=goal_id,
        metadata={"title": goal.title},
    )

    return DeleteResponse(deleted=True, id=goal_id)
