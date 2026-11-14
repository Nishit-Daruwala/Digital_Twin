"""Personality traits.

Phase 1: the onboarding quiz gives a prior for each trait.
Phase 3 adds data-driven traits that blend with this prior as data days grow.
"""

from app.schemas.profile import QuizAnswers

PRIOR_CONFIDENCE = 0.2  # quiz answers are weak evidence

_CHRONOTYPE = {
    "morning": "morning person",
    "afternoon": "balanced",
    "evening": "night owl",
    "night": "night owl",
}
# Expected ratio of planned_min / actual duration_min (optimism bias).
# < 1 means the user tends to underestimate how long things take.
_ESTIMATE = {"faster": 1.2, "accurate": 1.0, "slower": 0.8, "much_slower": 0.6}


def _trait(value, label: str) -> dict:
    return {"value": value, "label": label, "confidence": PRIOR_CONFIDENCE, "source": "quiz"}


def quiz_prior(quiz: QuizAnswers) -> dict:
    planner_share = (quiz.plans_ahead - 1) / 4  # 0..1
    consistency = (quiz.routine - 1) / 4  # 0..1
    ratio = _ESTIMATE[quiz.estimate_bias]
    return {
        "chronotype": _trait(_CHRONOTYPE[quiz.best_time], _CHRONOTYPE[quiz.best_time]),
        "optimism_bias": _trait(
            ratio,
            "realistic estimator" if ratio >= 1 else f"tasks take ~{1 / ratio:.1f}x your estimate",
        ),
        "planner": _trait(
            round(planner_share, 2),
            "planner" if planner_share >= 0.5 else "improviser",
        ),
        "consistency": _trait(
            round(consistency, 2),
            "steady routine" if consistency >= 0.5 else "varied routine",
        ),
        "stress_triggers": _trait([quiz.stress_source], quiz.stress_source),
        "best_conditions": _trait({}, "not enough data yet"),
    }


# --------------------------------------------------------------------------------------
# Data-driven traits (plan section 8). They replace the quiz prior once ~14 days of data
# exist; confidence grows with the number of data days.
# --------------------------------------------------------------------------------------

MIN_DAYS = 14


def _confidence(days: int) -> float:
    return round(max(0.25, min(0.95, days / 60)), 2)


def _data_trait(value, label: str, days: int, **extra) -> dict:
    return {
        "value": value,
        "label": label,
        "confidence": _confidence(days),
        "source": "data",
        **extra,
    }


def _hour_profile(acts):
    """Completed minutes per hour of day (0-23), spreading each activity over its hours."""
    import numpy as np

    prof = np.zeros(24)
    for st, dur in zip(acts["start_time"], acts["duration_min"], strict=True):
        if st is None or dur is None or dur != dur:
            continue
        t, left = st.hour + st.minute / 60, float(dur)
        while left > 0 and t < 24:
            step = min(left, (int(t) + 1 - t) * 60)
            prof[int(t)] += step
            left -= step
            t = int(t) + 1
    return prof


def chronotype(acts) -> tuple[float, str] | None:
    """Centre of the busiest 4-hour window of *work*.

    The plan says "hour-weighted mean of completed-activity minutes". Two refinements, chosen
    by measuring against the synthetic ground truth (26/33 correct vs 11/33 for the plain
    rule): a peak window instead of a mean (a morning lecture block + late-night study must
    not average to "afternoon"), and only work-like categories: ones the person plans tasks
    in, or mostly does before 18:00. Evening-only unplanned categories (leisure, family,
    social) say nothing about when someone is sharpest.
    """
    import numpy as np

    done = acts[acts["completed"] & acts["duration_min"].notna() & acts["start_time"].notna()]
    if len(done) < 10:
        return None
    med_start = done.groupby("category")["start_time"].apply(
        lambda ts: float(np.median([t.hour + t.minute / 60 for t in ts]))
    )
    work_cats = set(med_start[med_start < 18].index) | set(acts.loc[acts["planned"], "category"])
    work = done[done["category"].isin(work_cats)]
    if len(work) < 10:
        work = done
    prof = _hour_profile(work)
    w = 4
    window = np.array([sum(prof[(h + j) % 24] for j in range(w)) for h in range(24)])
    peak = float((int(window.argmax()) + w / 2) % 24)
    label = "morning person" if peak < 13 else "night owl" if peak > 18 else "balanced"
    return peak, label


def _stress_triggers(f, categories, days):
    from scipy import stats

    from app.ml.labels import feature_name

    skip_bases = {"stress", "imputed", "weekday"}
    cand = []
    for col in f.columns:
        base = col.split("_lag")[0]
        if base in skip_bases or col.endswith(("_r3", "_r7", "_lag2")):
            continue
        if base in ("mood", "energy", "focus") and "_lag" not in col:
            continue  # same check-in, same moment
        x, y = f[col], f["stress"]
        ok = x.notna() & y.notna()
        if ok.sum() < 14 or x[ok].nunique() < 2:
            continue
        r, p = stats.spearmanr(x[ok], y[ok])
        if r == r and r >= 0.3 and p < 0.05:
            cand.append((r, col))
    cand.sort(reverse=True)
    names: list[str] = []
    for _, col in cand:
        n = feature_name(col, categories)
        if n not in names:
            names.append(n)
        if len(names) == 3:
            break
    return _data_trait(names, ", ".join(names) if names else "no clear trigger yet", days)


def _best_conditions(f, categories, days):
    from app.ml.labels import feature_name, fmt_value

    top = f["focus"] >= f["focus"].quantile(0.8)
    cols = ["sleep_hours", "last_hour_lag1", "active_min"] + [
        c
        for c in f.columns
        if c.startswith("min_") and "_lag" not in c and not c.endswith(("_r3", "_r7"))
    ]
    diffs = []
    for c in cols:
        if c not in f:
            continue
        a, b = f.loc[top, c].dropna(), f.loc[~top, c].dropna()
        sd = f[c].std()
        if len(a) >= 4 and len(b) >= 4 and sd and sd > 0:
            diffs.append((abs(a.mean() - b.mean()) / sd, c, a.mean(), b.mean()))
    diffs.sort(reverse=True)
    conds, parts = {}, []
    for _, c, a, b in [d for d in diffs if d[0] >= 0.5][:3]:
        base = c.split("_lag")[0]
        name = feature_name(c, categories)
        conds[c] = {"best": round(float(a), 2), "other": round(float(b), 2), "name": name}
        parts.append(f"{name} {fmt_value(base, a)} (vs {fmt_value(base, b)})")
    return _data_trait(conds, "; ".join(parts) if parts else "no clear pattern yet", days)


def compute_traits(f, acts, categories: list[str], prior: dict, data_days: int) -> dict:
    """Data traits where computable; the quiz prior otherwise (or with < 14 days)."""
    import numpy as np

    from app.ml.labels import fmt_hour

    traits = dict(prior or {})
    if data_days < MIN_DAYS or f is None or f.empty:
        return traits

    if acts is not None and not acts.empty:
        ct = chronotype(acts)
        if ct:
            traits["chronotype"] = _data_trait(
                ct[1],
                ct[1],
                data_days,
                peak_hour=ct[0],
                detail=f"Busiest work hours around {fmt_hour(ct[0])}",
            )
        pc = acts[
            acts["planned"]
            & acts["completed"]
            & (acts["duration_min"] > 0)
            & acts["planned_min"].notna()
        ]
        if len(pc) >= 5:
            ratio = float((pc["planned_min"] / pc["duration_min"]).median())
            if ratio < 0.9:
                label = f"tasks take ~{1 / ratio:.1f}× your estimate"
            elif ratio > 1.1:
                label = "you overestimate task length"
            else:
                label = "realistic estimator"
            traits["optimism_bias"] = _data_trait(
                round(ratio, 3), label, data_days, detail=f"Median of {len(pc)} finished tasks"
            )
        share = float(acts["planned"].mean())
        traits["planner"] = _data_trait(
            round(share, 2),
            "planner" if share >= 0.5 else "improviser",
            data_days,
            detail=f"{round(share * 100)}% of activities were planned ahead",
        )

    if "active_min" in f:
        active = f["active_min"].dropna()
        active = active[active > 0]
        if len(active) >= 10:
            cv = float(active.std() / active.mean())
            cons = float(np.clip(1 - cv, 0, 1))
            traits["consistency"] = _data_trait(
                round(cons, 2),
                "steady routine" if cons >= 0.6 else "varied routine",
                data_days,
                detail=f"Daily active time varies by ±{round(cv * 100)}%",
            )

    if "stress" in f and f["stress"].notna().sum() >= 14:
        traits["stress_triggers"] = _stress_triggers(f, categories, data_days)
    if "focus" in f and f["focus"].notna().sum() >= 15:
        traits["best_conditions"] = _best_conditions(f, categories, data_days)
    return traits
