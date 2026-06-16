"""LPI middleware package — Phase 2 scaffold.

Exposes:
    get_current_user   — returns "default_user" (Phase 2 stub)
    register_middleware — wires CORS + timing onto the FastAPI app

Phase 3: get_current_user will decode a real JWT Bearer token.
         Only auth.py changes — no router file needs to be touched.

IMPORTANT: Supabase is imported lazily inside TimingMiddleware.dispatch()
so that test environments that don't set SUPABASE_URL / SUPABASE_KEY
can still import this module without error. The top-level import of
create_client was removed for this reason.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from lpi.middleware.auth import get_current_user  # re-exported for convenience

__all__ = ["get_current_user", "register_middleware"]


class TimingMiddleware(BaseHTTPMiddleware):
    """Adds X-Process-Time and X-Request-ID to every response.

    X-Process-Time lets the team verify the <3s recommendation target.
    X-Request-ID lets log entries across services be correlated.
    Neither header blocks or rejects any request.

    Supabase request logging is best-effort: if the Supabase client
    cannot be created (missing env vars in test) the error is swallowed
    silently so the middleware never breaks a request.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        rid = str(uuid.uuid4())
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        response.headers["X-Request-ID"] = rid

        if "/api/v1/goals" in request.url.path:
            try:
                from lpi.config import settings
                from supabase import create_client  # type: ignore[attr-defined]

                key = settings.supabase_service_role_key or settings.supabase_key
                db = create_client(settings.supabase_url, key)
                db.table("request_logs").insert(
                    {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                        "request_id": rid,
                    }
                ).execute()
            except Exception:
                pass  # never let logging break the request

        return response


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the app. Call once in main.py before routers."""
    app.add_middleware(TimingMiddleware)  # inner: measures route time only
    app.add_middleware(  # outer: handles CORS pre-flight
        CORSMiddleware,
        allow_origins=["*"],  # Phase 3: restrict to frontend URL
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
