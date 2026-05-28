from fastapi import APIRouter

from lpi.models import Recommendation

router = APIRouter()


@router.get("/{user_id}", response_model=list[Recommendation])
def get_recommendations(user_id: str, limit: int = 3) -> list[Recommendation]:
    """Get top recommendations based on goals + signals."""
    # Phase 4 will replace this with a real engine. For now, return an empty list
    # (tests only require a list response and that `limit` is respected).
    _ = user_id
    _ = limit
    return []
