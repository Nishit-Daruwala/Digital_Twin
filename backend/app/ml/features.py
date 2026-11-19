"""Daily feature matrix: one row per user per day (plan section 3).

From check-ins:  sleep_hours, mood, energy, stress, focus
From activities: min_<category> per category, active_min, tasks_planned, tasks_completed,
                 completion_rate, plan_ratio (median planned/actual), first_hour, last_hour
From chat:       msg_count, sentiment_mean (learnable user messages only)
Calendar:        weekday, is_weekend, is_monday ... is_sunday
Lags/rolling:    <col>_lag1, <col>_lag2, <col>_r3, <col>_r7 for every non-calendar column
Missing days:    forward-fill at most 1 day (marked `imputed`), otherwise the row is dropped.

Data sources whose consent is off are excluded entirely.
The pure function `build_features()` does the work; `build_user_features()` loads from the DB.
"""

from __future__ import annotations

import uuid
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.seed.patterns import slug

CHECKIN_COLS = ["sleep_hours", "mood", "energy", "stress", "focus"]
ACTIVITY_COLS = [
    "active_min",
    "tasks_planned",
    "tasks_completed",
    "completion_rate",
    "plan_ratio",
    "first_hour",
    "last_hour",
]
CHAT_COLS = ["msg_count", "sentiment_mean"]
DOW = [
    "is_monday",
    "is_tuesday",
    "is_wednesday",
    "is_thursday",
    "is_friday",
    "is_saturday",
    "is_sunday",
]
CALENDAR_COLS = ["weekday", "is_weekend", *DOW]
TARGETS = ["mood", "energy", "focus", "completion_rate"]
LAGS = (1, 2)
WINDOWS = {3: 2, 7: 4}  # window -> min_periods


_SAME_DAY_TASK_COLS = {"tasks_planned", "tasks_completed", "plan_ratio", "active_min"}


def split_feature(name: str) -> tuple[str, str]:
    """'mood_lag1' -> ('mood', 'lag1'), 'focus_r7' -> ('focus', 'r7'), 'sleep_hours' -> (.., '')."""
    for suffix in ("_lag1", "_lag2", "_r3", "_r7"):
        if name.endswith(suffix):
            return name[: -len(suffix)], suffix[1:]
    return name, ""


def is_leaky(feature: str, target: str) -> bool:
    """True when `feature` is computed from the same raw values as `target` on the same day,
    so a correlation between them is guaranteed by construction, not discovered.
    Pattern mining and models must skip these pairs. Rolling means (r3/r7) include today.
    """
    base, kind = split_feature(feature)
    same_day = kind in ("", "r3", "r7")
    if base == target and same_day:
        return True
    if target == "completion_rate" and same_day:
        return base in _SAME_DAY_TASK_COLS or base.startswith("min_")
    return False


def _hour(t) -> float | None:
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    return t.hour + t.minute / 60


def _activity_aggregates(acts: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    cat_cols = {c: "min_" + slug(c) for c in categories}
    if acts.empty:
        return pd.DataFrame(columns=[*cat_cols.values(), *ACTIVITY_COLS])

    a = acts.copy()
    a["date"] = pd.to_datetime(a["date"])
    done = a[a["completed"] & a["duration_min"].notna()]

    for c in sorted(set(done["category"]) - set(categories)):  # categories no longer in profile
        cat_cols[c] = "min_" + slug(c)
    if done.empty:
        minutes = pd.DataFrame(columns=list(cat_cols.values()), dtype=float)
    else:
        minutes = done.pivot_table(
            index="date", columns="category", values="duration_min", aggfunc="sum"
        )
        minutes = minutes.reindex(columns=list(cat_cols)).rename(columns=cat_cols)

    g = a.groupby("date")
    out = pd.DataFrame(index=g.size().index)
    out["active_min"] = done.groupby("date")["duration_min"].sum()
    out["tasks_planned"] = g["planned"].sum()
    out["tasks_completed"] = a[a["planned"] & a["completed"]].groupby("date").size()
    out["tasks_completed"] = out["tasks_completed"].fillna(0)
    out["completion_rate"] = out["tasks_completed"] / out["tasks_planned"].replace(0, np.nan)

    pr = done[done["planned"] & done["planned_min"].notna() & (done["duration_min"] > 0)]
    out["plan_ratio"] = (pr["planned_min"] / pr["duration_min"]).groupby(pr["date"]).median()

    a["start_h"] = a["start_time"].map(_hour)
    timed = a[a["start_h"].notna()].copy()
    timed["end_h"] = (timed["start_h"] + timed["duration_min"].fillna(0) / 60).clip(upper=23.99)
    out["first_hour"] = timed.groupby("date")["start_h"].min()
    out["last_hour"] = timed.groupby("date")["end_h"].max()

    return out.join(minutes, how="left")


def build_features(
    checkins: pd.DataFrame,
    activities: pd.DataFrame,
    messages: pd.DataFrame,
    categories: list[str],
) -> pd.DataFrame:
    """Pure function. Inputs:
    checkins:   date, sleep_hours, mood, energy, stress, focus (+ slot: several check-ins a
                day are adjusted for time of day and combined into one row per day)
    activities: date, category, start_time, duration_min, planned, completed, planned_min
    messages:   date, sentiment   (already filtered to learnable user messages)
    """
    from app.ml import intraday

    checkins = intraday.daily(checkins)
    dates = [pd.to_datetime(df["date"]) for df in (checkins, activities, messages) if not df.empty]
    if not dates:
        return pd.DataFrame()
    all_dates = pd.concat(dates)
    idx = pd.date_range(all_dates.min(), all_dates.max(), freq="D", name="date")

    # --- base columns on a continuous calendar ---
    if checkins.empty:
        ck = pd.DataFrame(index=idx, columns=CHECKIN_COLS, dtype=float)
    else:
        ck = checkins.assign(date=pd.to_datetime(checkins["date"])).set_index("date")
        ck = ck[CHECKIN_COLS].astype(float).reindex(idx)

    act = _activity_aggregates(activities, categories).reindex(idx)
    act_cols = list(act.columns)

    if messages.empty:
        chat = pd.DataFrame(index=idx, columns=CHAT_COLS, dtype=float)
    else:
        m = messages.assign(date=pd.to_datetime(messages["date"]))
        chat = pd.DataFrame(
            {
                "msg_count": m.groupby("date").size(),
                "sentiment_mean": m.groupby("date")["sentiment"].mean(),
            }
        ).reindex(idx)

    df = pd.concat([ck, act, chat], axis=1).astype(float)

    has_checkin = ck.notna().any(axis=1)
    has_acts = act.notna().any(axis=1) if act_cols else pd.Series(False, index=idx)
    has_msgs = chat["msg_count"].notna()
    has_data = has_checkin | has_acts | has_msgs

    # A day with data but no activities logged means 0 minutes / 0 tasks, not "unknown".
    zero_cols = [c for c in act_cols if c.startswith("min_")] + [
        "active_min",
        "tasks_planned",
        "tasks_completed",
    ]
    zero_cols = [c for c in zero_cols if c in df.columns]
    if not activities.empty:
        df.loc[has_data, zero_cols] = df.loc[has_data, zero_cols].fillna(0)
    if not messages.empty:
        df.loc[has_data, "msg_count"] = df.loc[has_data, "msg_count"].fillna(0)

    # --- missing days: forward-fill at most 1 day, otherwise drop ---
    # Only whole missing days are filled; a NaN inside a day that has data stays NaN
    # (e.g. completion_rate on a day with nothing planned is undefined, not yesterday's).
    keep = has_data | has_data.shift(1, fill_value=False)
    imputed = keep & ~has_data
    df.loc[imputed] = df.ffill(limit=1).loc[imputed]
    df.loc[~keep] = np.nan
    df["imputed"] = imputed.astype(int)

    # --- lags and rolling means (calendar-aware, before dropping rows) ---
    base_cols = [c for c in df.columns if c != "imputed"]
    extra = {}
    for c in base_cols:
        s = df[c]
        for lag in LAGS:
            extra[f"{c}_lag{lag}"] = s.shift(lag)
        for w, mp in WINDOWS.items():
            extra[f"{c}_r{w}"] = s.rolling(w, min_periods=mp).mean()
    df = pd.concat([df, pd.DataFrame(extra, index=idx)], axis=1)

    # --- calendar ---
    df["weekday"] = idx.weekday
    df["is_weekend"] = (idx.weekday >= 5).astype(int)
    for i, name in enumerate(DOW):
        df[name] = (idx.weekday == i).astype(int)

    df = df[keep.values]
    df.index = df.index.date
    df.index.name = "date"
    return df


# --------------------------------------------------------------------------------------
# DB loader
# --------------------------------------------------------------------------------------


def load_frames(
    db: Session, user_id: uuid.UUID, since: date | None = None, until: date | None = None
):
    """Load a user's raw data as DataFrames, skipping sources without consent.
    `until` (inclusive) keeps future-dated rows (tasks planned for tomorrow) out of the
    feature table; they are plans, not history."""
    from app.api.privacy import consent_map
    from app.models import Activity, Checkin, Message, TwinProfile

    consents = consent_map(db, user_id)
    profile = db.get(TwinProfile, user_id)
    categories = list(profile.categories) if profile else []

    def frame(rows, cols):
        return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows], columns=cols)

    ck_cols = ["date", "slot", *CHECKIN_COLS]
    checkins = pd.DataFrame(columns=ck_cols)
    if consents["checkin"]:
        q = select(*[getattr(Checkin, c) for c in ck_cols]).where(Checkin.user_id == user_id)
        if since:
            q = q.where(Checkin.date >= since)
        if until:
            q = q.where(Checkin.date <= until)
        checkins = frame(db.execute(q).all(), ck_cols)

    act_cols = [
        "date",
        "category",
        "start_time",
        "duration_min",
        "planned",
        "completed",
        "planned_min",
    ]
    activities = pd.DataFrame(columns=act_cols)
    if consents["activities"]:
        q = select(*[getattr(Activity, c) for c in act_cols]).where(Activity.user_id == user_id)
        if since:
            q = q.where(Activity.date >= since)
        if until:
            q = q.where(Activity.date <= until)
        activities = frame(db.execute(q).all(), act_cols)
        activities[["planned", "completed"]] = activities[["planned", "completed"]].astype(bool)
        for c in ("duration_min", "planned_min"):
            activities[c] = pd.to_numeric(activities[c], errors="coerce")

    messages = pd.DataFrame(columns=["date", "sentiment"])
    if consents["chat"]:
        q = select(Message.created_at, Message.sentiment).where(
            Message.user_id == user_id, Message.role == "user", Message.learnable.is_(True)
        )
        rows = db.execute(q).all()
        messages = pd.DataFrame(
            [{"date": r.created_at.date(), "sentiment": r.sentiment} for r in rows],
            columns=["date", "sentiment"],
        )
        if since:
            messages = messages[messages["date"] >= since]
        if until:
            messages = messages[messages["date"] <= until]
        messages["sentiment"] = pd.to_numeric(messages["sentiment"], errors="coerce")

    return checkins, activities, messages, categories


def build_user_features(
    db: Session, user_id: uuid.UUID, since: date | None = None, until: date | None = None
) -> pd.DataFrame:
    return build_features(*load_frames(db, user_id, since, until))
