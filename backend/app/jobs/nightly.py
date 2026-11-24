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


def run_reminders() -> None:
    from app.jobs.reminders import send_due

    try:
        send_due(SessionLocal)
    except Exception:  # never let one bad run stop the scheduler
        log.exception("reminder run failed")


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
    if settings.reminders_enabled:
        # Every 5 minutes: each user gets theirs at 8 PM in their own timezone.
        _scheduler.add_job(
            run_reminders,
            "cron",
            minute="*/5",
            id="reminders",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
    _scheduler.start()
    log.info(
        "nightly pipeline scheduled at %02d:00; check-in reminders %s (email: %s)",
        settings.nightly_hour,
        f"at {settings.reminder_hour}:00 local" if settings.reminders_enabled else "off",
        settings.email_provider,
    )


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
