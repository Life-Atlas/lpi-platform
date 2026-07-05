import logging

from fastapi import APIRouter, Depends, HTTPException, status

from lpi import store
from lpi.middleware.auth import UserContext, get_current_user_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/map")
def get_users_map(user_context: UserContext = Depends(get_current_user_context)) -> dict[str, dict]:
    """Return a mapping of user_id to user info (email, name). Admin only."""
    if not user_context.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )

    try:
        # Fetch users using Supabase service role
        client = store._get_client()
        response = client.auth.admin.list_users()
        users_map = {}
        for u in response:
            users_map[u.id] = {
                "email": u.email,
                "name": u.user_metadata.get("display_name", "")
                if hasattr(u, "user_metadata") and u.user_metadata
                else "",
            }
        return users_map
    except Exception:
        logger.exception("Error fetching users")
        return {}
