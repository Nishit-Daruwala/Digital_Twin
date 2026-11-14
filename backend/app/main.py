import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import (
    activities,
    auth,
    chat,
    checkins,
    decisions,
    demo,
    intelligence,
    privacy,
    profile,
)
from app.api.deps import DB
from app.core.config import settings
from app.db import SessionLocal
from app.jobs import nightly
from app.services import embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("twin")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the local embedding model in the background (can take minutes on a cold
    # machine), then embed any messages that were saved while it was loading.
    embeddings.warm_up_in_background(lambda: embeddings.backfill_missing(SessionLocal))
    nightly.start()  # nightly ML pipeline (SCHEDULER_ENABLED)
    yield
    nightly.stop()


app = FastAPI(
    lifespan=lifespan,
    title="Twin API",
    description="Digital Doppelgänger: a personal AI twin that learns, predicts and recommends.",
    version="0.1.0",
)

# Auth uses a Bearer header, not cookies, so credentials mode is unnecessary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Log the details server-side; never leak a stack trace or SQL to the client.
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for r in (
    auth.router,
    profile.router,
    checkins.router,
    activities.router,
    chat.router,
    decisions.router,
    intelligence.router,
    privacy.router,
    demo.router,
):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health(db: DB) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse(
            {
                "status": "ok",
                "database": "ok",
                "embeddings": "ready" if embeddings.ready() else "loading",
            }
        )
    except SQLAlchemyError:
        log.exception("Health check: database unreachable")
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
