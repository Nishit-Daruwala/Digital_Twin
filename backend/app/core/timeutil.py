"""The user's local time. Check-in slots ("this morning") only make sense in their timezone."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


def valid_timezone(name: str) -> bool:
    return name in available_timezones()


def tz_of(user) -> ZoneInfo:
    try:
        return ZoneInfo(getattr(user, "timezone", None) or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_now(user) -> datetime:
    return datetime.now(UTC).astimezone(tz_of(user))


def to_local(user, moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(tz_of(user))
