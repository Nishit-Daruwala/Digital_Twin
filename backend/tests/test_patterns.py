"""Pattern discovery on small fixed datasets."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.features import build_features
from app.ml.patterns import discover, pattern_key
from app.services.insight_wording import numbers

D0 = date(2026, 8, 3)  # a Monday
CATS = ["Study", "Exercise"]


def table(n=60, seed=0, focus_from_sleep=True, monday_low=False):
    rng = np.random.default_rng(seed)
    sleep = rng.normal(6.8, 1.1, n).round(1)
    rows, acts = [], []
    for i in range(n):
        d = D0 + timedelta(days=i)
        focus = 3 + rng.normal(0, 0.5)
        if focus_from_sleep and i > 0 and sleep[i - 1] < 6.2:
            focus -= 1.4
        mood = 3 + rng.normal(0, 0.5) - (1.2 if monday_low and d.weekday() == 0 else 0)
        rows.append(
            {
                "date": d,
                "sleep_hours": sleep[i],
                "mood": round(np.clip(mood, 1, 5)),
                "energy": round(np.clip(3 + rng.normal(0, 0.6), 1, 5)),
                "stress": round(np.clip(3 + rng.normal(0, 0.6), 1, 5)),
                "focus": round(np.clip(focus, 1, 5)),
            }
        )
        acts.append(
            {
                "date": d,
                "category": "Study",
                "start_time": None,
                "duration_min": float(rng.integers(30, 180)),
                "planned": True,
                "completed": bool(rng.random() < 0.7),
                "planned_min": 60.0,
            }
        )
    ck = pd.DataFrame(rows)
    ac = pd.DataFrame(acts)
    return build_features(ck, ac, pd.DataFrame(columns=["date", "sentiment"]), CATS)


def test_finds_planted_lagged_pattern_with_evidence():
    found = discover(table(), CATS)
    top = found[0]
    assert (top.feature, top.target, top.lag, top.direction) == ("sleep_hours", "focus", 1, "+")
    assert top.key == pattern_key("sleep_hours", "focus", 1)
    assert top.p_adj >= top.p  # Benjamini-Hochberg never lowers a p-value
    assert top.n >= 10 and abs(top.r) >= 0.4 and top.p_adj <= 0.05
    assert top.worse_side == "low" and top.worse_mean < top.other_mean
    assert top.template.startswith("The day after you sleep")
    # every number in the sentence comes from the evidence
    for num in numbers(top.template):
        assert num in {
            f"{top.threshold:g}",
            f"{round(top.worse_mean, 1):g}",
            f"{round(top.other_mean, 1):g}",
        }


def test_calendar_pattern_and_wording():
    found = discover(table(focus_from_sleep=False, monday_low=True, seed=3), CATS)
    mon = [p for p in found if p.feature == "is_monday"]
    assert mon and mon[0].target == "mood" and mon[0].lag == 0
    assert mon[0].template.startswith("On Mondays, your mood averages")


def test_pure_noise_gives_at_most_one_chance_finding():
    # Benjamini-Hochberg bounds the false-discovery rate, it can't make it zero: the plan's
    # target for a noise-only user is 0-1 insights.
    counts = [len(discover(table(focus_from_sleep=False, seed=100 + s), CATS)) for s in range(8)]
    assert max(counts) <= 1 and sum(counts) <= 2, counts


def test_never_tests_leaky_or_trivial_pairs():
    f = table()
    found = discover(f, CATS)
    for p in found:
        assert p.feature != p.target  # own history excluded
        assert not (
            p.target == "completion_rate"
            and p.lag == 0
            and (p.feature.startswith("min_") or p.feature.startswith("tasks_"))
        )
        assert not (
            p.lag == 0
            and p.feature in {"mood", "energy", "stress", "focus"}
            and p.target in {"mood", "energy", "focus"}
        )
    # one insight per (feature, target): lags are merged
    pairs = [(p.feature, p.target) for p in found]
    assert len(pairs) == len(set(pairs))


def test_too_little_data():
    assert discover(table(n=8), CATS) == []
    assert discover(pd.DataFrame(), CATS) == []
