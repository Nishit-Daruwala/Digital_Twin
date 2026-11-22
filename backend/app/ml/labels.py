"""Human-readable names for feature columns (insight sentences, SHAP reasons, dashboard)."""

from __future__ import annotations

import math

from app.ml.features import split_feature
from app.seed.patterns import slug

METRICS = {"mood", "energy", "stress", "focus"}
DOW_NAMES = {
    "is_monday": "Monday",
    "is_tuesday": "Tuesday",
    "is_wednesday": "Wednesday",
    "is_thursday": "Thursday",
    "is_friday": "Friday",
    "is_saturday": "Saturday",
    "is_sunday": "Sunday",
}
TARGET_NAMES = {
    "mood": "mood",
    "energy": "energy",
    "focus": "focus",
    "stress": "stress",
    "completion_rate": "task completion rate",
}


def category_name(base: str, categories: list[str]) -> str | None:
    """'min_deep_work' -> 'Deep work' using the user's own spelling."""
    if not base.startswith("min_"):
        return None
    s = base[4:]
    for c in categories:
        if slug(c) == s:
            return c
    return s.replace("_", " ").capitalize()


def _missing(x) -> bool:
    """None or NaN (models impute missing inputs, so a NaN can reach a label)."""
    try:
        return x is None or math.isnan(float(x))
    except (TypeError, ValueError):
        return False


def fmt_num(x: float, digits: int = 1) -> str:
    """Compact number: 6.0 -> '6', 6.25 -> '6.2', 90.0 -> '90'."""
    if _missing(x):
        return "?"
    r = round(float(x), digits)
    return str(int(r)) if r == int(r) else f"{r:.{digits}f}"


def fmt_hour(h: float) -> str:
    if _missing(h):
        return "?"
    h = max(0.0, min(23.99, float(h)))
    m = int(round(h * 60))
    m = min(m, 23 * 60 + 59)
    return f"{m // 60:02d}:{m % 60:02d}"


def fmt_value(base: str, value: float) -> str:
    """A feature value with its unit."""
    if _missing(value):
        return "no data"
    if base == "sleep_hours":
        return f"{fmt_num(value)} h"
    if base.startswith("min_") or base == "active_min":
        return f"{fmt_num(value, 0)} min"
    if base in ("first_hour", "last_hour"):
        return fmt_hour(value)
    if base in ("completion_rate",):
        return f"{round(float(value) * 100):d}%"
    if base == "plan_ratio":
        return f"{fmt_num(value, 2)}×"
    return fmt_num(value)


def feature_name(column: str, categories: list[str]) -> str:
    """Short noun phrase for a feature column, e.g. 'Deep work minutes (yesterday)'."""
    base, kind = split_feature(column)
    when = {
        "": "",
        "lag1": " (yesterday)",
        "lag2": " (2 days ago)",
        "r3": " (3-day avg)",
        "r7": " (7-day avg)",
        "r28": " (4-week avg)",
    }.get(kind, "")
    cat = category_name(base, categories)
    if cat:
        name = f"{cat} minutes"
    elif base in DOW_NAMES:
        name = DOW_NAMES[base]
    else:
        name = {
            "sleep_hours": "Sleep",
            "active_min": "Active minutes",
            "tasks_planned": "Tasks planned",
            "tasks_completed": "Tasks completed",
            "completion_rate": "Task completion",
            "plan_ratio": "Estimate accuracy",
            "first_hour": "Day start",
            "last_hour": "Day end",
            "msg_count": "Chat messages",
            "sentiment_mean": "Chat positivity",
            "is_weekend": "Weekend",
            "weekday": "Weekday",
        }.get(base, base.replace("_", " ").capitalize())
    return name + when


def condition(base: str, high: bool, threshold: float, categories: list[str]) -> str:
    """Clause describing one side of a median split, e.g. 'you sleep 6.2 h or less'."""
    t = fmt_value(base, threshold)
    cat = category_name(base, categories)
    if base in DOW_NAMES:
        return f"it's a {DOW_NAMES[base]}" if high else f"it's not a {DOW_NAMES[base]}"
    if base == "is_weekend":
        return "it's the weekend" if high else "it's a weekday"
    if cat:
        if threshold <= 0:
            return f"you do any {cat}" if high else f"you skip {cat}"
        return f"you spend more than {t} on {cat}" if high else f"you spend {t} or less on {cat}"
    phrases = {
        "sleep_hours": ("you sleep more than {t}", "you sleep {t} or less"),
        "active_min": ("you're active for more than {t}", "you're active for {t} or less"),
        "last_hour": ("your day ends after {t}", "your day ends by {t}"),
        "first_hour": ("your day starts after {t}", "your day starts by {t}"),
        "tasks_planned": ("you plan more than {t} tasks", "you plan {t} tasks or fewer"),
        "msg_count": ("you send more than {t} messages", "you send {t} messages or fewer"),
        "sentiment_mean": ("your messages are upbeat", "your messages are downbeat"),
        "completion_rate": (
            "you finish more than {t} of your tasks",
            "you finish {t} of your tasks or fewer",
        ),
        "plan_ratio": ("your time estimates run high", "your time estimates run low"),
    }
    if base in METRICS:
        hi, lo = (f"your {base} is above {t}", f"your {base} is {t} or lower")
    else:
        hi, lo = phrases.get(base, (f"{base} is above {{t}}", f"{base} is {{t}} or lower"))
    return (hi if high else lo).format(t=t)
