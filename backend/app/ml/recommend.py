"""Recommendations (plan section 9): candidates from the twin's own outputs, ranked by how
relevant they are today x how much this person tends to like that kind of advice.

Candidate generators (templates; every number comes from the user's data):
- light_day       tomorrow's energy/mood is predicted clearly below their recent average
- peak_hours      schedule hard work in their best part of the day (time-of-day rhythm,
                  else the chronotype trait)
- pad_estimates   their tasks take longer than estimated (optimism-bias trait)
- checkin         an unusual stretch (anomaly streak or a bad-direction spike)
- pattern         act on a discovered pattern with an actionable feature (an activity,
                  sleep, start time); phrased as an association, never as a cause
- goal            a stated goal (sleep hours, "Exercise 3x a week", "Study 3h a day") that
                  the last 7 days fall short of

Ranking: score = relevance x preference(type).
- policy "thompson" (default): preference ~ Beta(2 + likes, 2 + dislikes), sampled, where
  each rating fades by 5% a day (discounted Thompson sampling). Liked types rise, disliked
  ones fall, less-tried types still get explored, and changed tastes are picked up.
- policy "weights" (the plan's rule, kept for comparison): weight = 1 + 0.1 likes - 0.15
  dislikes, clamped to [0.2, 2].
At most one per type, top 3. A suggestion given a thumbs-down is not repeated for 7 days.
Never medical or financial advice: templates only suggest everyday planning actions.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ml.labels import category_name, fmt_hour, fmt_num
from app.models import Activity, Checkin, Insight, Prediction, Recommendation, TwinProfile

TYPES = {
    "light_day": "Lighter-day plans",
    "peak_hours": "Best-hours scheduling",
    "pad_estimates": "Time-estimate padding",
    "checkin": "Check-in nudges",
    "pattern": "Acting on your patterns",
    "goal": "Goal nudges",
}
SHOW = 3
COOLDOWN_DAYS = 7
W_UP, W_DOWN, W_MIN, W_MAX = 0.1, 0.15, 0.2, 2.0
PRIOR = 2  # Beta(2, 2): no strong opinion at first, but less erratic than Beta(1, 1)
DECAY = 0.95  # per day: a rating's weight halves in about two weeks


@dataclass
class Candidate:
    type: str
    key: str  # stable id, for de-duplication and the thumbs-down cooldown
    text: str
    reason: str
    relevance: float  # 0..1
    evidence: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Selection (pure: also used by the adaptation simulation in ml/evaluate.py)
# --------------------------------------------------------------------------------------


def preference(stats: dict, type_: str, policy: str, rng: np.random.Generator) -> float:
    likes, dislikes = stats.get(type_, (0, 0))
    if policy == "thompson":
        return float(rng.beta(PRIOR + likes, PRIOR + dislikes))
    if policy == "weights":
        return float(np.clip(1 + W_UP * likes - W_DOWN * dislikes, W_MIN, W_MAX))
    return 1.0  # "relevance": no learning, the baseline in the simulation


def choose(
    cands: list[Candidate],
    stats: dict,
    policy: str,
    rng: np.random.Generator,
    k: int = SHOW,
    exclude: set[str] = frozenset(),
) -> list[tuple[Candidate, float]]:
    """Top-k by relevance x preference, at most one per type."""
    best: dict[str, tuple[Candidate, float]] = {}
    for c in cands:
        if c.key in exclude:
            continue
        s = c.relevance * preference(stats, c.type, policy, rng)
        if c.type not in best or s > best[c.type][1]:
            best[c.type] = (c, s)
    return sorted(best.values(), key=lambda x: x[1], reverse=True)[:k]


def type_weight(stats: dict, type_: str) -> float:
    """What the dashboard shows: Thompson's posterior mean (the plan's weight for 'weights')."""
    likes, dislikes = stats.get(type_, (0, 0))
    return round((PRIOR + likes) / (2 * PRIOR + likes + dislikes), 2)


# --------------------------------------------------------------------------------------
# Candidate generators
# --------------------------------------------------------------------------------------


def _mins(m: float) -> str:
    m = int(round(m))
    return f"{m} min" if m < 60 else f"{m // 60}h" + (f" {m % 60:02d}m" if m % 60 else "")


def _light_day(preds: dict[str, Prediction]) -> list[Candidate]:
    out = []
    for target in ("energy", "mood"):
        p = preds.get(target)
        if not p or p.baseline is None:
            continue
        gap = p.baseline - p.predicted
        if gap >= 0.4 or p.predicted <= 2.5:
            out.append(
                Candidate(
                    "light_day",
                    f"light_day:{target}",
                    f"Tomorrow looks like a lower-{target} day for you. Keep the plan light: "
                    "pick the one or two tasks that matter most and leave room for breaks.",
                    f"Your twin predicts {target} {fmt_num(p.predicted)} tomorrow, against "
                    f"{fmt_num(p.baseline)} on average over your last 7 days.",
                    min(1.0, 0.5 + max(gap, 0)),
                    {"target": target, "predicted": p.predicted, "baseline": p.baseline},
                )
            )
    return out[:1]


def _peak_hours(rhythm: Insight | None, traits: dict) -> list[Candidate]:
    if rhythm is not None:
        e = rhythm.evidence
        return [
            Candidate(
                "peak_hours",
                f"peak_hours:{e['high_slot']}",
                f"Put your hardest task in the {e['high_slot']} tomorrow; save routine work "
                f"for the {e['low_slot']}.",
                f"Your {e['metric']} is usually higher in the {e['high_slot']} than in the "
                f"{e['low_slot']} ({fmt_num(e['mean_high'])} vs {fmt_num(e['mean_low'])}, on "
                f"{e['n']} days you checked in at both).",
                min(1.0, 0.5 + float(e.get("diff", 0)) / 2),
                {"insight": rhythm.key},
            )
        ]
    ct = traits.get("chronotype") or {}
    if ct.get("source") == "data" and ct.get("peak_hour") is not None:
        h = float(ct["peak_hour"])
        return [
            Candidate(
                "peak_hours",
                f"peak_hours:{int(h)}",
                f"Protect the time around {fmt_hour(h)} tomorrow for focused work; that's "
                "when you usually get the most done.",
                f"Your work sessions cluster around {fmt_hour(h)} ({ct.get('detail', '')}).",
                0.45 * float(ct.get("confidence", 0.5)),
                {"trait": "chronotype"},
            )
        ]
    return []


def _pad_estimates(traits: dict, planned: list[Activity]) -> list[Candidate]:
    ob = traits.get("optimism_bias") or {}
    ratio = ob.get("value")  # planned / actual minutes
    if ob.get("source") != "data" or not isinstance(ratio, int | float) or ratio <= 0:
        return []
    factor = round(1 / float(ratio), 2)  # one number for both the "x" and the "%"
    if factor < 1.15:
        return []
    total = sum(a.planned_min or a.duration_min or 0 for a in planned)
    if total:
        text = (
            f"Tomorrow's {len(planned)} planned task{'s' if len(planned) != 1 else ''} "
            f"({_mins(total)}) will likely take about {_mins(total * factor)}. Block the extra "
            "time now, or move one task."
        )
        rel = 0.8
    else:
        text = (
            f"When you plan tomorrow, add about {round((factor - 1) * 100)}% to each time estimate."
        )
        rel = 0.4
    return [
        Candidate(
            "pad_estimates",
            "pad_estimates",
            text,
            f"Your finished tasks usually take about {factor:g}x your estimate "
            f"({str(ob.get('detail', '')).lower() or 'from your log'}).",
            rel,
            {"factor": round(factor, 2), "planned_min": total},
        )
    ]


def _checkin(anomalies: list[Insight], today: date) -> list[Candidate]:
    for a in anomalies:
        e = a.evidence
        recent = e.get("day") and (today - date.fromisoformat(e["day"])).days <= 2
        bad = e.get("kind") == "streak" or e.get("worse") is True
        if recent and bad:
            return [
                Candidate(
                    "checkin",
                    f"checkin:{a.key}",
                    "Take two minutes tonight for a check-in with a one-line note on what's "
                    "been different lately. It helps your twin (and you) spot the cause.",
                    a.text,
                    0.7,
                    {"insight": a.key},
                )
            ]
    return []


ACTIONABLE = ("min_", "sleep_hours", "first_hour")


def _pattern(patterns: list[Insight], categories: list[str]) -> list[Candidate]:
    out = []
    for i in patterns:
        e = i.evidence
        feat, target, lag = e.get("feature", ""), e.get("target", ""), e.get("lag", 0)
        if not feat.startswith(ACTIONABLE) or target not in ("mood", "energy", "focus"):
            continue
        good, bad = fmt_num(e["other_mean"]), fmt_num(e["worse_mean"])
        thr = e.get("threshold", 0)
        good_side = f"your {target} averages {good} vs {bad} otherwise."
        bad_side = f"your {target} averages {bad} vs {good} otherwise."

        def when(day_clause: str, lag: int = lag) -> str:
            """'On days you do X' / 'The day after you do X' / 'Two days after you do X'."""
            if lag == 0:
                return f"On days {day_clause}"
            return f"{'The day' if lag == 1 else 'Two days'} after {day_clause}"

        if feat.startswith("min_"):
            cat = category_name(feat, categories)
            if e["worse_side"] == "low":
                text = f"Fit in some {cat} tomorrow if you can."
                why = f"{when(f'you do {cat}')}, {good_side}"
            elif not thr:  # "any vs none" split
                text = f"Keep tomorrow light on {cat} if you can."
                why = f"{when(f'with {cat}')}, {bad_side.replace('otherwise', 'without')}"
            else:
                text = f"Keep {cat} under {_mins(thr)} tomorrow if you can."
                why = f"{when(f'with more than {_mins(thr)} of {cat}')}, {bad_side}"
        elif feat == "sleep_hours":
            if e["worse_side"] != "low":
                continue
            text = f"Aim for more than {fmt_num(thr)} h of sleep tonight."
            why = f"{when(f'you sleep {fmt_num(thr)} h or less')}, {bad_side}"
        else:  # first_hour
            if e["worse_side"] != "high":
                continue
            text = f"Try to start your day before {fmt_hour(thr)} tomorrow."
            clause = (
                f"{'your day starts' if lag == 0 else 'a day that starts'} after {fmt_hour(thr)}"
            )
            why = f"{when(clause)}, {bad_side}"
        out.append(
            Candidate(
                "pattern",
                f"pattern:{i.key}",
                text,
                why + " This is a pattern in your data, not a guarantee.",
                float(i.confidence or 0.5),
                {"insight": i.key},
            )
        )
    return out


_SLEEP_GOAL = re.compile(r"sleep\D{0,12}(\d+(?:\.\d+)?)\s*h", re.I)
_WEEK_GOAL = re.compile(r"([a-z][a-z ]*?)\s+(\d+)\s*(?:x|times)\s*(?:a|per)\s*week", re.I)
_DAY_GOAL = re.compile(r"([a-z][a-z ]*?)\s+(\d+(?:\.\d+)?)\s*h(?:ours?)?\s*(?:a|per)\s*day", re.I)


def _goals(goals: list[str], categories: list[str], week: dict) -> list[Candidate]:
    out = []
    cats = {c.lower(): c for c in categories}

    def cat_of(words: str) -> str | None:
        for w in words.lower().split():
            for k, c in cats.items():
                if w[:4] == k[:4]:
                    return c
        return None

    for g in goals:
        m = _SLEEP_GOAL.search(g)
        if m and week.get("sleep_mean") is not None:
            want, have = float(m.group(1)), float(week["sleep_mean"])
            if have < want - 0.25:
                out.append(
                    Candidate(
                        "goal",
                        f"goal:{g.lower()}",
                        f"Try lights-out about {_mins((want - have) * 60)} earlier tonight.",
                        f'Your goal is "{g}"; you averaged {fmt_num(have)} h over the last 7 days.',
                        0.65,
                        {"goal": g},
                    )
                )
            continue
        m = _WEEK_GOAL.search(g)
        cat = cat_of(m.group(1)) if m else None
        if m and cat:
            want, have = int(m.group(2)), week["sessions"].get(cat, 0)
            if have < want:
                out.append(
                    Candidate(
                        "goal",
                        f"goal:{g.lower()}",
                        f"Tomorrow is a good day for some {cat}.",
                        f'Your goal is "{g}"; you did {cat} on {have} of the last 7 days.',
                        0.6,
                        {"goal": g},
                    )
                )
            continue
        m = _DAY_GOAL.search(g)
        cat = cat_of(m.group(1)) if m else None
        if m and cat:
            want, have = float(m.group(2)) * 60, week["minutes"].get(cat, 0) / 7
            if have < 0.85 * want:
                out.append(
                    Candidate(
                        "goal",
                        f"goal:{g.lower()}",
                        f"Block {_mins(want)} for {cat} in tomorrow's plan.",
                        f'Your goal is "{g}"; you averaged {_mins(have)} a day '
                        "over the last 7 days.",
                        0.6,
                        {"goal": g},
                    )
                )
    return out


# --------------------------------------------------------------------------------------
# From the database
# --------------------------------------------------------------------------------------


def feedback_stats(
    db: Session, user_id: uuid.UUID, today: date | None = None, decay: float = 1.0
) -> dict[str, tuple[float, float]]:
    """(likes, dislikes) per type. With decay < 1 a rating counts decay**age_in_days, so
    old opinions fade (discounted Thompson sampling) and changed tastes are picked up."""
    today = today or date.today()
    rows = db.execute(
        select(Recommendation.type, Recommendation.feedback, Recommendation.for_date).where(
            Recommendation.user_id == user_id, Recommendation.feedback.in_((1, -1))
        )
    ).all()
    stats: dict[str, list[float]] = {}
    for t, fb, d in rows:
        w = decay ** max(0, (today - d).days)
        s = stats.setdefault(t, [0.0, 0.0])
        s[0 if fb == 1 else 1] += w
    return {t: (s[0], s[1]) for t, s in stats.items()}


def candidates(db: Session, user_id: uuid.UUID, today: date) -> list[Candidate]:
    tomorrow = today + timedelta(days=1)
    profile = db.get(TwinProfile, user_id)
    traits = (profile.traits if profile else {}) or {}
    goals = list(profile.goals) if profile else []
    categories = list(profile.categories) if profile else []

    preds = {
        p.target: p
        for p in db.scalars(
            select(Prediction).where(
                Prediction.user_id == user_id,
                Prediction.for_date == tomorrow,
                Prediction.backtest.is_(False),
                Prediction.target.in_(("mood", "energy")),
            )
        )
    }
    insights = db.scalars(
        select(Insight)
        .where(Insight.user_id == user_id, Insight.active)
        .order_by(Insight.rank.desc().nullslast())
    ).all()
    rhythm = next(
        (i for i in insights if i.type == "rhythm" and i.evidence.get("metric") == "energy"), None
    )
    planned = db.scalars(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.date == tomorrow,
            Activity.planned,
            Activity.completed.is_(False),
        )
    ).all()
    week_start = today - timedelta(days=6)
    sleep_mean = db.scalar(
        select(func.avg(Checkin.sleep_hours)).where(
            Checkin.user_id == user_id, Checkin.date >= week_start, Checkin.date <= today
        )
    )
    acts = db.execute(
        select(Activity.category, Activity.date, Activity.duration_min).where(
            Activity.user_id == user_id,
            Activity.completed,
            Activity.date >= week_start,
            Activity.date <= today,
        )
    ).all()
    week = {
        "sleep_mean": float(sleep_mean) if sleep_mean is not None else None,
        "minutes": {},
        "sessions": {},
    }
    days_by_cat: dict[str, set] = {}
    for cat, d, mins in acts:
        week["minutes"][cat] = week["minutes"].get(cat, 0) + (mins or 0)
        days_by_cat.setdefault(cat, set()).add(d)
    week["sessions"] = {c: len(ds) for c, ds in days_by_cat.items()}

    return [
        *_light_day(preds),
        *_peak_hours(rhythm, traits),
        *_pad_estimates(traits, planned),
        *_checkin([i for i in insights if i.type == "anomaly"], today),
        *_pattern([i for i in insights if i.type == "pattern"], categories),
        *_goals(goals, categories, week),
    ]


def _rng(user_id: uuid.UUID, for_date: date, n_feedback: int) -> np.random.Generator:
    """Deterministic per user, day and amount of feedback: re-running the pipeline gives the
    same picks; new feedback gives a fresh draw."""
    h = hashlib.sha256(f"{user_id}:{for_date}:{n_feedback}".encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "big"))


def generate(db: Session, user_id: uuid.UUID, today: date, policy: str = "thompson") -> dict:
    """Refresh tomorrow's recommendations. Rated ones stay (👍 shown, 👎 hidden); the rest
    are re-picked, so feedback changes what comes next."""
    for_date = today + timedelta(days=1)
    stats = feedback_stats(db, user_id, today, DECAY if policy == "thompson" else 1.0)
    cooled = set(
        db.scalars(
            select(Recommendation.key).where(
                Recommendation.user_id == user_id,
                Recommendation.feedback == -1,
                Recommendation.for_date >= for_date - timedelta(days=COOLDOWN_DAYS),
            )
        )
    )
    db.execute(
        delete(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.for_date == for_date,
            Recommendation.feedback.is_(None),
        )
    )
    kept = db.scalars(
        select(Recommendation).where(
            Recommendation.user_id == user_id, Recommendation.for_date == for_date
        )
    ).all()
    liked = [r for r in kept if r.feedback == 1]
    taken = {r.key for r in kept} | cooled
    n_fb = len(
        db.scalars(
            select(Recommendation.id).where(
                Recommendation.user_id == user_id, Recommendation.feedback.is_not(None)
            )
        ).all()
    )
    room = SHOW - len(liked)
    cands = candidates(db, user_id, today)
    picks = choose(
        [c for c in cands if c.type not in {r.type for r in liked}],
        stats,
        policy,
        _rng(user_id, for_date, n_fb),
        k=max(room, 0),
        exclude=taken,
    )
    for rank, (c, score) in enumerate(picks, start=len(liked) + 1):
        db.add(
            Recommendation(
                user_id=user_id,
                for_date=for_date,
                type=c.type,
                key=c.key,
                text=c.text,
                reason=c.reason,
                evidence=c.evidence,
                relevance=round(c.relevance, 3),
                score=round(score, 3),
                rank=rank,
                policy=policy,
            )
        )
    db.commit()
    return {"candidates": len(cands), "shown": len(liked) + len(picks), "policy": policy}


def give_feedback(db: Session, rec: Recommendation, value: int) -> None:
    rec.feedback = None if value == 0 else value
    rec.feedback_at = None if value == 0 else datetime.now(UTC)
    db.commit()
