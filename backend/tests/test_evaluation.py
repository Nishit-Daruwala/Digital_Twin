"""Evaluation as a CI gate: the twin must keep finding planted patterns, stay quiet on noise
and beat the plan's baseline. Deterministic (fixed seeds); ~40 s."""

import pytest

from app.ml.evaluate import run


@pytest.fixture(scope="module")
def result():
    return run(n_generated=9, n_noise=3, quick=True)


def test_pattern_recall_meets_plan_target(result):
    assert result["patterns"]["recall_at_5"] >= 0.80, result["patterns"]


def test_noise_users_get_at_most_one_insight(result):
    assert result["patterns"]["false_insights_max"] <= 1, result["patterns"]["false_insights"]


def test_twin_beats_the_seven_day_mean(result):
    for days in (30, 60):
        lc = result["learning_curve"][days]
        assert lc["twin_mae"] < lc["baseline_mae"], (days, lc)


def test_traits_track_ground_truth(result):
    assert result["traits"]["chronotype_accuracy"] >= 0.5
    assert result["traits"]["optimism_abs_error"] <= 0.05


def test_time_of_day_rhythm_is_learned(result):
    t = result["time_of_day"]
    assert t["best_slot_accuracy"] >= 0.8, t
    assert t["statement_recall"] >= 0.8, t
    assert t["false_statements_max"] <= 1, t["false_statements"]
    assert t["slot_mae_with_rhythm"] < t["slot_mae_without"], t  # the rhythm helps
