"""LPI Platform — FastAPI application entry point.

Phase 2 changes vs Phase 1:
  - register_middleware() wired (CORS + timing headers)
  - GET /health returns a real ISO-8601 UTC timestamp (was missing in Phase 1)
  - lifespan hook added as a no-op scaffold for Phase 3 Supabase init
  - recommendations router now returns [] instead of crashing (500 → 200)
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from lpi.middleware import register_middleware
from lpi.routers import github_auth, goals, me, recommendations, signals, users, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hook. No-op in Phase 2.

    Phase 3: initialise Supabase connection pool on startup:
        from lpi.database import get_supabase
        get_supabase()
    """
    yield


app = FastAPI(
    title="LPI Platform",
    description=(
        "Life Programmable Interface: goal registry, activity signals, "
        "recommendation engine"
    ),
    version="0.1.0",
    lifespan=lifespan,
) 

# Middleware must be registered before routers (Starlette requirement)
register_middleware(app)

app.include_router(goals.router, prefix="/api/v1/goals", tags=["goals"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["signals"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(github_auth.router, prefix="/api/v1/github", tags=["github_auth"])
app.include_router(
    recommendations.router,
    prefix="/api/v1/recommendations",
    tags=["recommendations"],
)
app.include_router(me.router, prefix="/api/v1/me", tags=["me"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])


@app.get("/health", tags=["health"])
def health() -> dict:
    """Service liveness probe. Phase 2: timestamp now populated (was null in Phase 1)."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
    }
