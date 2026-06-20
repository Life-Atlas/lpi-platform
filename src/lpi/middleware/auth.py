"""Auth middleware — Supabase email/password JWT verification.

Every route that needs the caller identity depends on get_current_user.
It reads the `Authorization: Bearer <token>` header, verifies the JWT,
and returns the `sub` claim — the Supabase auth user's UUID.

Supabase signs tokens one of two ways depending on project/CLI version:
  - Legacy: HS256 with a shared secret (SUPABASE_JWT_SECRET, from
    Supabase Studio -> Project Settings -> API, or `supabase status`).
  - Current: ES256/RS256 with a per-project key pair, verified via the
    project's JWKS endpoint (SUPABASE_URL + /auth/v1/.well-known/jwks.json).

We pick the verification method based on the token's own `alg` header.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from lpi.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = jwt.PyJWKClient(jwks_url)
    return _jwks_client


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Return the authenticated Supabase user's id (UUID string).

    Raises 401 if the Authorization header is missing, malformed, or
    the token fails JWT verification (bad signature, expired, etc.).

    Uses HTTPBearer so FastAPI registers a bearer security scheme in the
    OpenAPI schema, which makes the Swagger UI "Authorize" button appear.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = credentials.credentials

    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            key = settings.supabase_jwt_secret
            algorithms = ["HS256"]
        else:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            key = signing_key.key
            algorithms = ["ES256", "RS256"]

        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return payload["sub"]


class UserContext(BaseModel):
    user_id: str
    is_admin: bool


def get_current_user_context(
    user_id: str = Depends(get_current_user),
) -> UserContext:
    """Return the authenticated user's ID and whether they are an admin."""
    is_admin = user_id in settings.admin_ids_list
    return UserContext(user_id=user_id, is_admin=is_admin)
