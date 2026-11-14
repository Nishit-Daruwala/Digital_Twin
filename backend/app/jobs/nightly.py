"""Nightly scheduler: APScheduler inside the API process (plan: no extra infrastructure).

Runs the pipeline for every eligible user at NIGHTLY_HOUR (server local time). A Postgres
advisory lock in pipeline.run_all makes sure only one process runs it, even with several
API workers. Free hosting tiers sleep, so Phase 4 also adds an external trigger.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.db import SessionLocal

log = logging.getLogger("twin.nightly")
_scheduler = None


def run_nightly() -> dict:
    from app.ml.pipeline import run_all

    return run_all(SessionLocal, trigger="nightly")


def start() -> None:
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_nightly,
        "cron",
        hour=settings.nightly_hour,
        minute=0,
        id="nightly",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    log.info("nightly pipeline scheduled at %02d:00", settings.nightly_hour)


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
