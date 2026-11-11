from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import auth, company, notifications, sources, team, tenders

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()
settings.assert_production_safe()

app = FastAPI(
    title="TenderOS API",
    version="0.1.0",
    description="TenderOS application API. These are NOT government portal endpoints.",
)

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = ("/api/v1/whatsapp/webhook",)


@app.middleware("http")
async def csrf_and_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    # Cross-site forms cannot set custom headers; SameSite=Lax is the first line of defence.
    if (
        request.method in UNSAFE
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith(CSRF_EXEMPT)
        and request.headers.get("x-requested-with") != "tenderos"
    ):
        return JSONResponse({"detail": "Missing CSRF header"}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, object]:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "whatsapp_transport": "meta" if settings.whatsapp_live else "simulated",
        "storage_backend": settings.storage_backend,
    }


for r in (auth.router, company.router, tenders.router, sources.router, notifications.router, team.router):
    app.include_router(r)
