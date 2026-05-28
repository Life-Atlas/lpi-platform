from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter

from lpi.models import Goal, GoalCreate, GoalUpdate
from lpi.storage import store

router = APIRouter()


@router.post("/", response_model=Goal)
def create_goal(goal: GoalCreate) -> Goal:
    """Create a new goal with SMILE phase tracking."""
    now = datetime.now(UTC)
    created = Goal(
        id=str(uuid4()),
        user_id="default-user",
        created_at=now,
        updated_at=now,
        **goal.model_dump(),
    )
    with store.lock:
        store.goals_by_id[created.id] = created
    return created


@router.get("/", response_model=list[Goal])
def list_goals(user_id: str | None = None) -> list[Goal]:
    """List goals, optionally filtered by user."""
    with store.lock:
        goals = list(store.goals_by_id.values())
    if user_id:
        goals = [g for g in goals if g.user_id == user_id]
    return goals


@router.get("/{goal_id}", response_model=Goal)
def get_goal(goal_id: str) -> Goal:
    """Get a specific goal."""
    with store.lock:
        goal = store.goals_by_id.get(goal_id)
    if not goal:
        # Keep it simple for now; CRUD tests beyond create/list are currently skipped.
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}", response_model=Goal)
def update_goal(goal_id: str, update: GoalUpdate) -> Goal:
    """Update a goal (including SMILE phase transitions)."""
    from fastapi import HTTPException

    with store.lock:
        existing = store.goals_by_id.get(goal_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Goal not found")

        patch = update.model_dump(exclude_unset=True)
        updated = existing.model_copy(update=patch | {"updated_at": datetime.now(UTC)})
        store.goals_by_id[goal_id] = updated
        return updated


@router.delete("/{goal_id}")
def delete_goal(goal_id: str) -> dict:
    """Delete a goal."""
    with store.lock:
        store.goals_by_id.pop(goal_id, None)
    return {"ok": True}
