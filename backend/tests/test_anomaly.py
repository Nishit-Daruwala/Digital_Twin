from datetime import date, timedelta

import pandas as pd

from app.ml.anomaly import detect

TODAY = date(2026, 11, 14)


def frame(values: dict[str, list[float]], imputed: list[int] | None = None) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    idx = [TODAY - timedelta(days=n - 1 - i) for i in range(n)]
    df = pd.DataFrame(values, index=idx)
    df["imputed"] = imputed or [0] * n
    return df


def test_spike_flagged_only_when_recent():
    mood = [3, 3, 4, 3, 3, 4, 3, 3, 4, 3, 3, 3, 4, 3, 3, 1]
    found = detect(frame({"mood": mood}), TODAY)
    spikes = [a for a in found if a.kind == "spike"]
    assert len(spikes) == 1 and spikes[0].metric == "mood" and spikes[0].evidence["z"] <= -2
    assert "unusually low" in spikes[0].text and "today" in spikes[0].text
    # the same spike 10 days ago is history, not an insight
    old = mood[:6] + [1] + mood[6:]
    old += [3] * 9
    assert not [a for a in detect(frame({"mood": old}), TODAY) if a.kind == "spike"]


def test_streak_below_baseline():
    energy = [4, 4, 3, 4, 4, 4, 3, 4, 4, 4, 3, 4, 2, 2, 2, 2]
    streaks = [a for a in detect(frame({"energy": energy}), TODAY) if a.kind == "streak"]
    assert streaks and streaks[0].evidence["days"] >= 3
    assert "below your usual" in streaks[0].text


def test_stress_is_bad_when_high_and_imputed_days_never_flagged():
    stress = [2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 3, 2, 2, 2, 2, 5]
    a = detect(frame({"stress": stress}), TODAY)
    assert a and a[0].metric == "stress" and a[0].evidence["worse"] is True
    imputed = [0] * 15 + [1]
    assert not [x for x in detect(frame({"stress": stress}, imputed), TODAY) if x.kind == "spike"]


def test_not_enough_history():
    assert detect(frame({"mood": [3, 1, 5]}), TODAY) == []
