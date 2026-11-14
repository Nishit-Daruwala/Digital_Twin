"""features.py on small fixed datasets (plan: pytest unit tests with fixed data)."""

from datetime import date, time, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml.features import build_features

D0 = date(2026, 11, 2)  # a Monday
CATS = ["Study", "Deep work"]


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def checkins(rows):
    return pd.DataFrame(rows, columns=["date", "sleep_hours", "mood", "energy", "stress", "focus"])


def acts(rows):
    cols = ["date", "category", "start_time", "duration_min", "planned", "completed", "planned_min"]
    df = pd.DataFrame(rows, columns=cols)
    for c in ("duration_min", "planned_min"):
        df[c] = pd.to_numeric(df[c])
    return df


EMPTY_ACTS = acts([])
EMPTY_MSGS = pd.DataFrame(columns=["date", "sentiment"])


def test_basic_columns_lags_and_calendar():
    ck = checkins([(day(i), 6 + i, 3, 3, 2, 1 + i) for i in range(4)])
    f = build_features(ck, EMPTY_ACTS, EMPTY_MSGS, CATS)
    assert list(f.index) == [day(i) for i in range(4)]
    assert f.loc[day(2), "sleep_hours"] == 8
    assert f.loc[day(2), "sleep_hours_lag1"] == 7 and f.loc[day(2), "sleep_hours_lag2"] == 6
    assert np.isnan(f.loc[day(0), "sleep_hours_lag1"])
    assert f.loc[day(2), "focus_r3"] == pytest.approx((1 + 2 + 3) / 3)
    assert np.isnan(f.loc[day(2), "focus_r7"])  # needs 4 observations
    assert f.loc[day(3), "focus_r7"] == pytest.approx((1 + 2 + 3 + 4) / 4)
    assert f.loc[day(0), "is_monday"] == 1 and f.loc[day(0), "weekday"] == 0
    assert f.loc[day(0), "is_weekend"] == 0


def test_one_missing_day_is_filled_two_are_dropped():
    ck = checkins(
        [
            (day(0), 7, 3, 3, 3, 3),
            (day(2), 8, 4, 4, 4, 4),  # day 1 missing
            (day(5), 5, 2, 2, 2, 2),
        ]
    )  # days 3, 4 missing
    f = build_features(ck, EMPTY_ACTS, EMPTY_MSGS, CATS)
    assert list(f.index) == [day(0), day(1), day(2), day(3), day(5)]
    assert f.loc[day(1), "mood"] == 3 and f.loc[day(1), "imputed"] == 1  # filled from day 0
    assert f.loc[day(3), "mood"] == 4 and f.loc[day(3), "imputed"] == 1
    assert day(4) not in f.index
    # lags are calendar-based: day 5's lag1 is day 4 (dropped -> NaN), not day 3
    assert np.isnan(f.loc[day(5), "mood_lag1"])
    assert f.loc[day(5), "mood_lag2"] == 4


def test_activity_aggregates():
    a = acts(
        [
            (day(0), "Study", time(21, 0), 90, True, True, 60),
            (day(0), "Study", time(23, 0), 60, False, True, None),
            (day(0), "Deep work", time(9, 30), 120, True, True, 120),
            (day(0), "Deep work", None, None, True, False, 30),  # planned, not done
            (day(1), "Study", time(10, 0), 30, False, True, None),
        ]
    )
    ck = checkins([(day(0), 7, 3, 3, 3, 3), (day(1), 7, 3, 3, 3, 3), (day(2), 7, 3, 3, 3, 3)])
    f = build_features(ck, a, EMPTY_MSGS, CATS)
    r = f.loc[day(0)]
    assert r["min_study"] == 150 and r["min_deep_work"] == 120 and r["active_min"] == 270
    assert r["tasks_planned"] == 3 and r["tasks_completed"] == 2
    assert r["completion_rate"] == pytest.approx(2 / 3)
    assert r["plan_ratio"] == pytest.approx(np.median([60 / 90, 1.0]))
    assert r["first_hour"] == 9.5
    assert r["last_hour"] == pytest.approx(23.99)  # 23:00 + 60 min, capped
    r1 = f.loc[day(1)]
    assert r1["min_deep_work"] == 0 and r1["tasks_planned"] == 0
    assert np.isnan(r1["completion_rate"])  # nothing planned -> undefined, not 0
    # a check-in-only day counts as 0 minutes, not missing
    assert f.loc[day(2), "active_min"] == 0


def test_chat_features_and_categories_not_in_profile():
    msgs = pd.DataFrame({"date": [day(0), day(0), day(1)], "sentiment": [0.5, -0.5, 1.0]})
    a = acts([(day(0), "Old hobby", None, 30, False, True, None)])
    f = build_features(checkins([]), a, msgs, CATS)
    assert f.loc[day(0), "msg_count"] == 2 and f.loc[day(0), "sentiment_mean"] == 0
    assert f.loc[day(1), "msg_count"] == 1
    assert f.loc[day(0), "min_old_hobby"] == 30


def test_empty_inputs():
    assert build_features(checkins([]), EMPTY_ACTS, EMPTY_MSGS, CATS).empty


def test_leakage_rule():
    from app.ml.features import is_leaky, split_feature

    assert split_feature("mood_lag1") == ("mood", "lag1")
    assert split_feature("min_deep_work_r7") == ("min_deep_work", "r7")
    # the target itself (or a rolling mean that includes today) is not a discovery
    assert is_leaky("mood", "mood") and is_leaky("mood_r3", "mood")
    assert not is_leaky("mood_lag1", "mood")  # yesterday's mood is legitimate
    # completion_rate is computed from the same day's task rows
    for f in ("tasks_completed", "tasks_planned", "min_study", "active_min_r3", "plan_ratio"):
        assert is_leaky(f, "completion_rate"), f
    assert not is_leaky("tasks_completed_lag1", "completion_rate")
    assert not is_leaky("min_study", "focus") and not is_leaky("sleep_hours", "mood")
