"""
RT Knits Agentic CMMS — FastAPI Application Entry Point

Startup sequence:
  1. Configure structured logging
  2. Run Alembic migrations (head)
  3. Initialise the Orchestrator singleton with all injected dependencies
  4. Start APScheduler (Loop 1 nightly planning + P0 escalation host)
  5. Mount all API routers

Shutdown sequence:
  1. Stop APScheduler gracefully
"""
from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging

# ── Configure logging first ───────────────────────────────────────────────────
configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()
BACKEND_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan context manager
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup → yield → shutdown."""

    # ── 1. Run DB migrations ──────────────────────────────────────────────────
    log.info("startup_running_migrations")
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True, text=True, cwd=BACKEND_ROOT
        )
        if result.returncode != 0:
            log.error("migration_failed", stderr=result.stderr)
        else:
            log.info("migrations_applied", stdout=result.stdout.strip())
    except Exception as exc:
        log.error("migration_error", error=str(exc))

    # ── 2. Initialise Orchestrator singleton ──────────────────────────────────
    log.info("startup_initialising_orchestrator")
    from app.agents.orchestrator import init_orchestrator
    from app.db.session import db_context
    from app.services.rating_gate import check_rating_gate
    from app.services.requester_resolver import get_or_create_requester
    from app.services.whatsapp import send_whatsapp_message

    init_orchestrator(
        db_factory=db_context,
        send_whatsapp_fn=send_whatsapp_message,
        check_rating_gate_fn=check_rating_gate,
        get_or_create_requester_fn=get_or_create_requester,
    )
    log.info("orchestrator_ready")

    # ── 3. Start APScheduler ──────────────────────────────────────────────────
    log.info("startup_starting_scheduler")
    from app.services.scheduler import start_scheduler
    scheduler = start_scheduler()
    log.info("scheduler_ready", jobs=len(scheduler.get_jobs()))

    yield  # ── Application is running ────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("shutdown_stopping_scheduler")
    from app.services.scheduler import stop_scheduler
    stop_scheduler()
    log.info("shutdown_complete")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="RT Knits Agentic CMMS",
    description=(
        "AI-powered WhatsApp CMMS for RT Knits factory maintenance. "
        "CBBR-NATEC Innovation Cup 2026."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS — allow supervisor dashboard origin in production ────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

from app.api.webhook import router as webhook_router
from app.api.work_orders import router as work_orders_router
from app.api.technicians import router as technicians_router
from app.api.planning import router as planning_router
from app.api.analytics import router as analytics_router
from app.api.knowledge import router as knowledge_router
from app.api.assets import router as assets_router

app.include_router(webhook_router)
app.include_router(work_orders_router, prefix="/api/v1")
app.include_router(technicians_router, prefix="/api/v1")
app.include_router(planning_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")

# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    from app.db.session import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "status": "ok",
        "version": "1.0.0",
        "env": settings.app_env,
        "db": db_status,
    }


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "name": "RT Knits Agentic CMMS",
        "docs": "/docs",
        "health": "/health",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Global exception handler
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. The team has been notified."},
    )
