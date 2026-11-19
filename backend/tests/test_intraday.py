"""Time of day: slots, the learned daily rhythm, slot-adjusted days and rhythm insights."""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml import intraday as I

D0 = date(2026, 10, 1)


@pytest.mark.parametrize(
    ("hour", "minute", "day", "slot"),
    [
        (4, 0, D0, "morning"),
        (9, 30, D0, "morning"),
        (11, 59, D0, "morning"),
        (12, 0, D0, "afternoon"),
        (16, 59, D0, "afternoon"),
        (17, 0, D0, "evening"),
        (23, 45, D0, "evening"),
        (1, 30, D0 - timedelta(days=1), "evening"),  # after midnight = last night
    ],
)
def test_slot_for(hour, minute, day, slot):
    assert I.slot_for(datetime(2026, 10, 1, hour, minute)) == (day, slot)


def test_slot_started():
    now = datetime(2026, 10, 1, 13, 0)  # afternoon
    assert I.slot_started(D0, "morning", now)
    assert I.slot_started(D0, "afternoon", now)
    assert not I.slot_started(D0, "evening", now)
    assert I.slot_started(D0 - timedelta(days=1), "evening", now)
    assert not I.slot_started(D0 + timedelta(days=1), "morning", now)


def rows(spec):
    """spec: list of (day_index, slot, energy, mood)."""
    return pd.DataFrame(
        [{"date": D0 + timedelta(days=i), "slot": s, "energy": e, "mood": m} for i, s, e, m in spec]
    )


def test_learn_uses_only_within_day_differences():
    spec = []
    for i in range(20):  # morning 4, evening 2 on the same days
        spec += [(i, "morning", 4, 3), (i, "evening", 2, 3)]
    for i in range(20, 30):  # evening-only check-ins on bad days must not leak in
        spec.append((i, "evening", 1, 1))
    r = I.learn(rows(spec))
    e = r["metrics"]["energy"]
    assert r["days_multi"] == 20
    assert e["morning"]["n"] == 20 and e["evening"]["n"] == 20 and e["afternoon"]["n"] == 0
    # raw within-day deviation is +-1, shrunk by 20 / (20 + 5)
    assert e["morning"]["offset"] == pytest.approx(0.8)
    assert e["evening"]["offset"] == pytest.approx(-0.8)
    assert r["metrics"]["mood"]["morning"]["offset"] == 0.0  # flat mood


def test_learn_without_repeat_days_learns_nothing():
    r = I.learn(rows([(i, "evening" if i % 2 else "morning", 1 + i % 5, 3) for i in range(30)]))
    assert r["days_multi"] == 0
    assert all(v["offset"] == 0 and v["n"] == 0 for v in r["metrics"]["energy"].values())


def test_daily_adjusts_each_checkin_for_its_slot():
    spec = []
    for i in range(20):
        spec += [(i, "morning", 4, 3), (i, "evening", 2, 3)]
    spec.append((20, "evening", 2, 3))  # an evening-only day reads low without adjustment
    d = I.daily(rows(spec)).set_index("date")
    assert len(d) == 21
    both = d.loc[D0, "energy"]
    alone = d.loc[D0 + timedelta(days=20), "energy"]
    assert alone == pytest.approx(2 + 0.8)  # moved up by the evening offset
    assert both == pytest.approx(3.0)
    assert alone == pytest.approx(both, abs=0.25)  # same underlying day level


def test_daily_without_slots_passes_through():
    ck = pd.DataFrame({"date": [D0], "mood": [3], "energy": [4]})
    assert I.daily(ck) is ck


def test_forecast_by_slot():
    rhythm = I.learn(
        rows([r for i in range(20) for r in ((i, "morning", 5, 3), (i, "evening", 2, 3))])
    )
    tod = I.forecast(4.6, rhythm, "energy")
    assert tod["learned"]
    s = tod["slots"]
    assert s["morning"]["value"] == 5.0  # clipped to the scale
    assert s["evening"]["value"] < s["afternoon"]["value"] < s["morning"]["value"]
    assert not I.forecast(3.0, I.learn(pd.DataFrame()), "energy")["learned"]


def test_insight_needs_a_real_paired_difference():
    rng = np.random.default_rng(1)
    spec = []
    for i in range(14):
        noise = int(rng.integers(-1, 2))
        spec += [(i, "morning", 4 + (noise > 0), 3), (i, "evening", 2 + (noise < 0), 3)]
    found = I.insights(rows(spec))
    assert [f["metric"] for f in found] == ["energy"]  # mood is flat
    f = found[0]
    assert (f["high_slot"], f["low_slot"]) == ("morning", "evening")
    assert f["n"] == 14 and f["p_adj"] <= I.MAX_P
    assert f["text"].startswith("Your energy is usually higher in the morning than in the evening")
    for num in (f"{f['mean_high']:g}", f"{f['mean_low']:g}", "14"):
        assert num in f["text"]


def test_no_insight_from_noise_or_too_few_days():
    rng = np.random.default_rng(2)
    noise = [
        (i, s, int(rng.integers(2, 5)), int(rng.integers(2, 5)))
        for i in range(40)
        for s in ("morning", "afternoon", "evening")
    ]
    assert I.insights(rows(noise)) == []
    few = [r for i in range(5) for r in ((i, "morning", 5, 3), (i, "evening", 1, 3))]
    assert I.insights(rows(few)) == []  # fewer than MIN_PAIRED_DAYS
