"""Prediction: honest inputs, model ladder, baselines, explanations."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml import predict as P
from app.ml.explain import explain
from app.ml.features import build_features
from app.seed.synthetic_users import persona_spec, persona_strength, simulate

END = date(2026, 11, 14)


def persona_features(key: str, days: int = 90):
    a, p, noise, s = persona_spec(key)
    gen = simulate(a, p, days=days, end=END, seed=s, noise=noise, strength=persona_strength(key))
    ck = pd.DataFrame(gen.checkins)[
        ["date", "slot", "sleep_hours", "mood", "energy", "stress", "focus"]
    ]
    ms = pd.DataFrame(
        [{"date": m["created_at"].date(), "sentiment": m["sentiment"]} for m in gen.messages]
    )
    cats = [c.name for c in a.cats]
    return build_features(ck, pd.DataFrame(gen.activities), ms, cats), cats, gen


def test_training_rows_never_see_tomorrows_checkin():
    f, _, _ = persona_features("student", 40)
    X, y, _ = P.training_rows(f, "mood")
    tomorrow_cols = [c for c in X.columns if c.startswith("next_")]
    # only plan-able inputs about tomorrow: sleep tonight, planned minutes/tasks, calendar
    allowed = {"next_sleep_hours", "next_tasks_planned", "next_is_weekend"}
    for c in tomorrow_cols:
        assert c in allowed or c.startswith(("next_min_", "next_is_")), c
    assert not {"next_mood", "next_energy", "next_focus", "next_stress"} & set(X.columns)
    # y on row t is the next calendar day's value
    df = P.calendar_frame(f)
    t0 = X.index[5]
    assert y.loc[t0] == df.loc[t0 + timedelta(days=1), "mood"]


def test_ladder_starts_with_personal_average():
    f, _, _ = persona_features("developer", 12)
    t = P.train_regression(f, "energy")
    assert t.kind == "mean" and t.model is None
    assert P.predict_value(t, pd.DataFrame([{}])) == np.clip(t.constant, 1, 5)


def test_learned_model_only_when_it_clearly_beats_the_norm():
    f, cats, _ = persona_features("founder", 90)
    t = P.train_regression(f, "mood")
    assert t.kind in ("ridge", "xgboost")  # exercise -> next-day mood is predictable
    assert t.metrics["mae"] < 0.95 * t.metrics["candidates"]["mean28"]
    assert t.metrics["mae"] < t.metrics["baseline_mae"]
    plan, src = P.assumed_plan(f, END + timedelta(days=1))
    row = P.tonight_row(f, plan, t.features)
    v = P.predict_value(t, row)
    lo, hi = P.interval(t, v)
    assert 1 <= lo <= v <= hi <= 5
    ex = explain(t, row, cats, src)
    assert ex["start_from"] is not None
    assert all(abs(c["impact"]) >= 0.05 for c in ex["contributors"])
    assert any("Exercise" in c["label"] for c in ex["contributors"])


def test_unpredictable_users_fall_back_to_their_norm():
    """Pure-noise users: the 5% margin + walk-forward check keep learned models out. It is a
    statistical guard, so a rare chance win is allowed (about 1 in 24 fits by design)."""
    a, p, _, _ = persona_spec("noise")
    kinds = []
    for seed in range(1004, 1012):
        gen = simulate(a, p, days=90, end=END, seed=seed, noise=True)
        ck = pd.DataFrame(gen.checkins)[
            ["date", "slot", "sleep_hours", "mood", "energy", "stress", "focus"]
        ]
        f = build_features(
            ck, pd.DataFrame(gen.activities), pd.DataFrame(), [c.name for c in a.cats]
        )
        kinds += [P.train_regression(f, target).kind for target in P.REG_TARGETS]
    learned = sum(k != "mean28" for k in kinds)
    assert learned <= 2, kinds  # of 16 fits


def test_assumed_plan_uses_plans_then_typical_values():
    f, _, _ = persona_features("developer", 40)
    tomorrow = END + timedelta(days=1)
    plan, src = P.assumed_plan(
        f, tomorrow, {"min_meetings": 180}, planned_tasks=4, overrides={"next_sleep_hours": 5.0}
    )
    assert plan["next_min_meetings"] == 180 and src["next_min_meetings"] == "planned"
    assert plan["next_tasks_planned"] == 4 and src["next_tasks_planned"] == "planned"
    assert plan["next_sleep_hours"] == 5.0 and src["next_sleep_hours"] == "set"
    assert src["next_min_deep_work"] == "typical"
    assert (
        plan[
            f"next_is_{['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][tomorrow.weekday()]}"
        ]
        == 1
    )


def test_adjustments_are_bounded():
    f, _, _ = persona_features("founder", 90)
    t = P.train_regression(f, "mood")
    plan, _ = P.assumed_plan(f, END + timedelta(days=1))
    row = P.tonight_row(f, plan, t.features)
    row[t.features] = row[t.features] * 50  # absurd inputs
    start = float(P.start_point(row, "mood").iloc[0])
    assert abs(
        P.predict_value(t, row) - np.clip(start, 1, 5)
    ) <= P.MAX_ADJUST + 1e-9 or P.predict_value(t, row) in (1.0, 5.0)


def test_task_model_falls_back_to_personal_rate():
    f, cats, gen = persona_features("noise", 90)
    t = P.train_tasks(pd.DataFrame(gen.activities), f, cats, END)
    assert t.kind == "rate" and 0 < t.constant < 1
