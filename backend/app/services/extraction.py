"""Turn raw LLM extraction output into a validated, consent-filtered confirmation card.

The LLM is never trusted: every field is validated on its own, so one bad value (mood 7,
an unknown category, a negative duration) is dropped without losing the rest.
Nothing here writes to the database; rows are only saved when the user confirms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import ValidationError

from app.ml.intraday import SLOTS
from app.schemas.chat import CardActivity, CardCheckin, CardDecision, ExtractionCard


@dataclass
class ExtractionResult:
    card: ExtractionCard
    sentiment: float | None = None
    topics: list[str] = field(default_factory=list)


def _int_1_5(v) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 5 and float(v) == n else None


def _sleep(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f * 4) / 4 if 0 < f <= 24 else None  # quarter-hour precision


def canonical_category(name: str, categories: list[str]) -> str | None:
    n = (name or "").strip().lower()
    for c in categories:
        if c.lower() == n:
            return c
    return None


def sanitize(
    raw: dict,
    *,
    categories: list[str],
    today: date,
    consents: dict[str, bool],
) -> ExtractionResult:
    raw = raw if isinstance(raw, dict) else {}
    day = today - timedelta(days=1) if raw.get("day") == "yesterday" else today

    checkin = CardCheckin()
    if consents.get("checkin", True):
        checkin = CardCheckin(
            mood=_int_1_5(raw.get("mood")),
            energy=_int_1_5(raw.get("energy")),
            stress=_int_1_5(raw.get("stress")),
            focus=_int_1_5(raw.get("focus")),
            sleep_hours=_sleep(raw.get("sleep_hours")),
            slot=raw.get("part_of_day") if raw.get("part_of_day") in SLOTS else None,
        )

    activities: list[CardActivity] = []
    if consents.get("activities", True):
        for item in raw.get("activities") or []:
            if not isinstance(item, dict):
                continue
            cat = canonical_category(str(item.get("category", "")), categories)
            if not cat:
                continue  # only the user's own categories
            data = dict(item, category=cat)
            if data.get("duration_min") is not None:
                try:
                    data["duration_min"] = int(round(float(data["duration_min"])))
                except (TypeError, ValueError):
                    data["duration_min"] = None
            try:
                act = CardActivity.model_validate(data)
            except ValidationError:
                try:  # keep the activity, drop only the bad optional fields
                    act = CardActivity.model_validate(
                        {**data, "duration_min": None, "start_time": None}
                    )
                except ValidationError:
                    continue
            if act.planned and act.completed:
                act.completed = False  # a planned (future) task can't be done yet
            activities.append(act)
            if len(activities) >= 20:
                break

    decisions: list[CardDecision] = []
    if consents.get("decisions", True):
        for item in raw.get("decisions") or []:
            try:
                decisions.append(CardDecision.model_validate(item))
            except ValidationError:
                continue
            if len(decisions) >= 10:
                break

    sentiment = raw.get("sentiment")
    try:
        sentiment = max(-1.0, min(1.0, float(sentiment)))
    except (TypeError, ValueError):
        sentiment = None

    topics: list[str] = []
    for t in raw.get("topics") or []:
        t = str(t).strip().lower()[:30]
        if t and t not in topics:
            topics.append(t)
        if len(topics) >= 5:
            break

    card = ExtractionCard(date=day, checkin=checkin, activities=activities, decisions=decisions)
    return ExtractionResult(card=card, sentiment=sentiment, topics=topics)
