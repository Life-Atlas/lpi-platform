from fastapi import APIRouter, Depends

from lpi.middleware.auth import UserContext, get_current_user_context

router = APIRouter()


@router.get("/", response_model=UserContext)
def get_me(user_context: UserContext = Depends(get_current_user_context)) -> UserContext:
    """Return the authenticated user's context (including admin status)."""
    return user_context
