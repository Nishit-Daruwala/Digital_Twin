"""Synthetic data: determinism, planted patterns visible in the features, demo endpoint."""

from datetime import date

import pandas as pd
import pytest

from app.core.config import settings
from app.ml.features import TARGETS, build_features
from app.seed.patterns import PATTERNS
from app.seed.synthetic_users import PERSONAS, persona_spec, random_spec, simulate
from tests.conftest import auth, register

END = date(2026, 11, 14)


def features_of(gen) -> pd.DataFrame:
    ck = pd.DataFrame(gen.checkins)[["date", "sleep_hours", "mood", "energy", "stress", "focus"]]
    ac = pd.DataFrame(gen.activities)
    ms = pd.DataFrame(
        [{"date": m["created_at"].date(), "sentiment": m["sentiment"]} for m in gen.messages]
    )
    return build_features(ck, ac, ms, [c.name for c in gen.archetype.cats])


def rho(f: pd.DataFrame, feature: str, target: str, lag: int = 0) -> float:
    x = f[feature if lag == 0 else f"{feature}_lag{lag}"]
    return x.corr(f[target], method="spearman")


def persona_features(key: str, days: int = 90):
    arch, patterns, noise, seed = persona_spec(key)
    return features_of(simulate(arch, patterns, days=days, end=END, seed=seed, noise=noise))


def test_generation_is_deterministic():
    arch, patterns, noise, seed = persona_spec("student")
    a = simulate(arch, patterns, days=30, end=END, seed=seed)
    b = simulate(arch, patterns, days=30, end=END, seed=seed)
    assert a.checkins == b.checkins and a.activities == b.activities
    c = simulate(arch, patterns, days=30, end=END, seed=seed + 1)
    assert a.checkins != c.checkins


def test_student_planted_patterns():
    f = persona_features("student")
    assert rho(f, "sleep_hours", "focus", lag=1) >= 0.5  # <6h sleep -> lower next-day focus
    arch, *_ = persona_spec("student")
    gen = simulate(arch, [], days=90, end=END, seed=1)
    study = [a for a in gen.activities if a["category"] == "Study"]
    assert sum(a["start_time"].hour >= 20 for a in study) / len(study) > 0.8  # night owl
    planned = [a for a in gen.activities if a["planned"] and a["completed"]]
    ratio = pd.Series([a["planned_min"] / a["duration_min"] for a in planned]).median()
    assert ratio == pytest.approx(0.625, abs=0.06)  # tasks take ~1.6x the estimate


# Thresholds = the plan's Phase 3 discovery bar (|rho| >= 0.4), so the personas are
# guaranteed to be discoverable, not just "somewhat correlated".


def test_developer_planted_patterns():
    f = persona_features("developer")
    assert rho(f, "min_meetings", "energy") <= -0.4
    assert rho(f, "is_monday", "mood") <= -0.4
    deep = f[f["min_deep_work"] > 0]
    assert deep["first_hour"].median() < 11  # morning person


def test_founder_planted_patterns():
    f = persona_features("founder")
    assert rho(f, "stress", "mood", lag=2) <= -0.4
    assert rho(f, "min_exercise", "mood", lag=1) >= 0.4


PLANTED = {
    "student": [("sleep_hours", "focus", 1, +1)],
    "developer": [("min_meetings", "energy", 0, -1), ("is_monday", "mood", 0, -1)],
    "founder": [("stress", "mood", 2, -1), ("min_exercise", "mood", 1, +1)],
}


@pytest.mark.parametrize("persona", list(PLANTED))
def test_planted_patterns_are_strong_across_seeds(persona):
    """The generator itself (not one lucky seed): mean |rho| over 5 seeds clears the bar."""
    arch, patterns, noise, _ = persona_spec(persona)
    for feature, target, lag, sign in PLANTED[persona]:
        values = []
        for seed in range(7000, 7005):
            f = features_of(simulate(arch, patterns, days=90, end=END, seed=seed, noise=noise))
            values.append(rho(f, feature, target, lag) * sign)
        assert min(values) > 0.2, (feature, values)  # always clearly present
        assert sum(values) / len(values) >= 0.4, (feature, values)


def test_noise_control_has_no_strong_correlations():
    f = persona_features("noise")
    base = [
        "sleep_hours",
        "stress",
        "active_min",
        "min_exercise",
        "min_social",
        "min_leisure",
        "is_weekend",
        "is_monday",
        "msg_count",
        "sentiment_mean",
    ]
    calendar = {"is_weekend", "is_monday"}  # calendar columns have no lagged versions
    strongest = max(
        abs(rho(f, feat, t, lag))
        for feat in base
        for t in TARGETS
        for lag in ((0,) if feat in calendar else (0, 1))
        if feat != t and not f[feat].isna().all()
    )
    assert strongest < 0.4, strongest


def test_generated_users_are_varied_and_consistent():
    specs = [random_spec(i) for i in range(30)]
    assert len({a.key for a, *_ in specs}) == 10  # all archetypes used
    for arch, patterns, _seed, _sd in specs:
        assert 2 <= len(patterns) <= 3
        assert all(p.compatible(arch) for p in patterns)
    # every planted feature exists as a column in that user's feature table
    arch, patterns, seed, sd = specs[0]
    f = features_of(simulate(arch, patterns, days=60, end=END, seed=seed, noise_sd=sd))
    for p in patterns:
        t = p.truth(arch)
        assert t["feature"] in f.columns, t


def test_every_pattern_is_usable_by_some_archetype():
    from app.seed.archetypes import ARCHETYPES

    for p in PATTERNS.values():
        assert any(p.compatible(a) for a in ARCHETYPES.values()), p.id


# ---------- POST /demo/seed ----------


def test_demo_seed_replaces_only_my_data(client, user):
    h = auth(user)
    client.post(
        "/checkins",
        headers=h,
        json={"date": END.isoformat(), "mood": 1, "energy": 1, "stress": 1, "focus": 1},
    )
    other = auth(register(client))
    client.post("/decisions", headers=other, json={"text": "Keep me"})

    r = client.post("/demo/seed", headers=h, json={"persona": "developer", "days": 30})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checkins"] >= 25 and out["activities"] > 50
    assert out["planted_patterns"] == PERSONAS["developer"]["patterns"]

    me = client.get("/me", headers=h).json()
    assert me["user"]["role"] == "Developer"
    assert "Meetings" in me["profile"]["categories"]
    assert me["profile"]["data_days"] == out["checkins"]
    assert len(client.get("/checkins", headers=h).json()) == out["checkins"]
    assert len(client.get("/chat/history?limit=200", headers=h).json()) == out["messages"]
    assert len(client.get("/decisions", headers=other).json()) == 1  # untouched


def test_demo_seed_validation_and_switch(client, user, monkeypatch):
    h = auth(user)
    assert (
        client.post("/demo/seed", headers=h, json={"persona": "wizard", "days": 30}).status_code
        == 422
    )
    assert (
        client.post("/demo/seed", headers=h, json={"persona": "student", "days": 5}).status_code
        == 422
    )
    assert client.post("/demo/seed", json={"persona": "student"}).status_code == 401
    monkeypatch.setattr(settings, "demo_enabled", False)
    assert (
        client.post("/demo/seed", headers=h, json={"persona": "student", "days": 30}).status_code
        == 404
    )
    assert client.get("/demo/personas").status_code == 404


def test_short_sleep_patterns_only_for_people_who_sleep_short():
    from app.seed.patterns import short_sleep_share

    for i in range(60):
        arch, patterns, _seed, _sd = random_spec(i)
        if any(p.id.startswith("sleep_low") for p in patterns):
            assert short_sleep_share(arch) >= 0.2, (i, arch.key, arch.sleep_mean)
