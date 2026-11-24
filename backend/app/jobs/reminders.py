"""Daily check-in reminder: at 8 PM in each user's own timezone, email the users who haven't
checked in at all that day. One check-in (any part of the day) means no email.

Runs every few minutes from the scheduler (jobs/nightly.py) and sends while the user's local
time is between REMINDER_HOUR and REMINDER_HOUR + REMINDER_WINDOW_HOURS, so a restart around
8 PM doesn't lose the day's reminder. A row in `reminders` is claimed *before* sending
(primary key user + local date), so nobody ever gets two on the same day.

Not sent when: reminders are off for the user, they haven't finished onboarding, check-in
consent is off, the address can't receive mail (demo accounts), or the last
REMINDER_PAUSE_AFTER reminders all went unanswered (resumes after their next check-in).

    python -m app.jobs.reminders --dry-run              # who would get one right now
    python -m app.jobs.reminders --at 2026-11-24T14:35Z # pretend it's that moment (UTC)
"""

from __future__ import annotations

import argparse
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_token
from app.core.timeutil import tz_of
from app.models import Checkin, Reminder, TwinProfile, User
from app.services import email as mail

log = logging.getLogger("twin.reminders")


@dataclass
class RunResult:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    due: list[str] = field(default_factory=list)  # dry run: would be sent
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def in_window(local: datetime) -> bool:
    return (
        settings.reminder_hour
        <= local.hour
        < settings.reminder_hour + settings.reminder_window_hours
    )


def _checked_in_days(db: Session, user_id, since: date) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(Checkin.date))).where(
                Checkin.user_id == user_id, Checkin.date >= since
            )
        )
        or 0
    )


def _unanswered(db: Session, user_id) -> int:
    """Reminders sent since the user's last check-in."""
    last = db.scalar(select(func.max(Checkin.date)).where(Checkin.user_id == user_id))
    q = select(func.count()).where(Reminder.user_id == user_id, Reminder.status == "sent")
    if last is not None:
        q = q.where(Reminder.for_date > last)
    return db.scalar(q) or 0


def build_email(db: Session, user: User, today: date) -> mail.Email:
    name = (user.name or "there").split()[0]
    days = _checked_in_days(db, user.id, today - timedelta(days=6))
    checkin_url = f"{settings.app_url.rstrip('/')}/checkin"
    off_url = (
        f"{settings.app_url.rstrip('/')}/reminders/off?token={create_token(user.id, 'unsubscribe')}"
    )
    streak = (
        f"You checked in on {days} of the last 7 days. One more keeps your twin learning."
        if days
        else "Your twin learns from your check-ins. One today is enough."
    )
    text = (
        f"Hi {name},\n\n"
        "You haven't checked in today. It takes about 20 seconds: mood, energy, focus and "
        "sleep.\n"
        f"{streak}\n\n"
        f"Check in: {checkin_url}\n\n"
        "Your twin needs at least one check-in a day to spot your patterns and predict "
        "tomorrow.\n\n"
        f"Don't want these emails? Turn them off: {off_url}\n"
        "(or in Settings → Reminders)\n"
    )
    h = html.escape
    html_body = f"""<!doctype html><html><body style="margin:0;background:#fbfaf7;
font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#16213a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center"
style="padding:32px 16px"><table role="presentation" width="100%" style="max-width:480px;
background:#ffffff;border:1px solid #e5e2da;border-radius:10px"><tr><td style="padding:28px">
<p style="margin:0 0 4px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;
color:#be400e">Twin</p>
<h1 style="margin:0 0 12px;font-size:20px">Hi {h(name)}, a quick check-in?</h1>
<p style="margin:0 0 8px;font-size:15px;line-height:1.5">You haven't checked in today. It takes
about 20 seconds: mood, energy, focus and sleep.</p>
<p style="margin:0 0 20px;font-size:15px;line-height:1.5;color:#5a6170">{h(streak)}</p>
<a href="{h(checkin_url)}" style="display:inline-block;background:#be400e;color:#ffffff;
text-decoration:none;font-weight:600;padding:11px 20px;border-radius:6px">Check in now</a>
<p style="margin:24px 0 0;font-size:12px;line-height:1.5;color:#6b7280">You get this at 8 PM
only on days without a check-in. <a href="{h(off_url)}" style="color:#6b7280">Turn off
reminders</a></p>
</td></tr></table></td></tr></table></body></html>"""
    return mail.Email(
        to=user.email,
        subject="Quick check-in? Your twin hasn't heard from you today",
        text=text,
        html=html_body,
        headers={"List-Unsubscribe": f"<{off_url}>"},
    )


def send_due(
    session_factory: Callable[[], Session], now: datetime | None = None, dry_run: bool = False
) -> RunResult:
    from app.api.privacy import consent_map

    now = (now or datetime.now(UTC)).astimezone(UTC)
    res = RunResult()
    if not settings.reminders_enabled:
        res.skip("disabled")
        return res
    with session_factory() as db:
        users = db.execute(
            select(User, TwinProfile.onboarding)
            .join(TwinProfile, TwinProfile.user_id == User.id)
            .where(User.email_reminders.is_(True))
        ).all()
        for user, onboarding in users:
            local = now.astimezone(tz_of(user))
            today = local.date()
            if not in_window(local):
                res.skip("not 8 PM there")
                continue
            if not onboarding:
                res.skip("not onboarded")
                continue
            if db.scalar(
                select(Checkin.id).where(Checkin.user_id == user.id, Checkin.date == today).limit(1)
            ):
                res.skip("checked in today")
                continue
            if db.get(Reminder, (user.id, today)) is not None:
                res.skip("already reminded")
                continue
            if not mail.deliverable(user.email):
                res.skip("undeliverable address")
                continue
            if not consent_map(db, user.id)["checkin"]:
                res.skip("check-in consent off")
                continue
            if _unanswered(db, user.id) >= settings.reminder_pause_after:
                res.skip("paused (unanswered)")
                continue
            if dry_run:
                res.due.append(user.email)
                continue
            # Claim the day first: a second worker or a retry finds the row and stops.
            claimed = db.execute(
                insert(Reminder)
                .values(user_id=user.id, for_date=today, status="sending")
                .on_conflict_do_nothing()
                .returning(Reminder.user_id)
            ).first()
            db.commit()
            if claimed is None:
                res.skip("already reminded")
                continue
            row = db.get(Reminder, (user.id, today))
            try:
                mail.send(build_email(db, user, today))
                row.status, row.detail = "sent", settings.email_provider
                res.sent.append(user.email)
            except mail.EmailError as exc:
                row.status, row.detail = "failed", str(exc)
                res.failed.append(user.email)
                log.warning("reminder to user %s failed: %s", user.id, exc)
            db.commit()
    if res.sent or res.failed:
        log.info("reminders: %d sent, %d failed", len(res.sent), len(res.failed))
    return res


def main() -> None:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="list who is due, send nothing")
    ap.add_argument("--at", help="pretend the time is this ISO moment (e.g. 2026-11-24T14:35Z)")
    args = ap.parse_args()
    at = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else None
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    r = send_due(SessionLocal, now=at, dry_run=args.dry_run)
    print(f"due: {len(r.due)}  sent: {len(r.sent)}  failed: {len(r.failed)}")
    for e in r.due or r.sent:
        print("  ", e)
    print("skipped:", r.skipped)


if __name__ == "__main__":
    main()
