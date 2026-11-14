"""SHAP explanations (plan section 7): top-3 contributors with their sign.

Linear models (Ridge / logistic) use shap.LinearExplainer on the scaled inputs; XGBoost uses
shap.TreeExplainer. Average-based fallbacks get an honest "based on your recent average".
For task completion the SHAP values are in log-odds; we report their sign and relative size.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features import split_feature
from app.ml.labels import feature_name, fmt_value
from app.ml.predict import Trained

NEXT_NAMES = {
    "next_sleep_hours": "Sleep tonight",
    "next_tasks_planned": "Tasks planned tomorrow",
    "next_is_weekend": "Tomorrow is a weekend day",
}


def describe(
    column: str, value: float, categories: list[str], sources: dict[str, str] | None = None
) -> str:
    """'Sleep tonight: 5.1 h (typical)', 'Stress today: 4', 'Monday tomorrow'."""
    src = (sources or {}).get(column)
    tag = {"typical": " (your usual)", "planned": " (planned)", "set": ""}.get(src, "")
    if column.startswith("next_is_"):
        day = column[len("next_is_") :].capitalize()
        if column == "next_is_weekend":
            return "Tomorrow is a weekend day" if value else "Tomorrow is a weekday"
        return f"Tomorrow is {day}" if value else f"Tomorrow isn't {day}"
    if column.startswith("next_"):
        base = column[len("next_") :]
        name = NEXT_NAMES.get(column) or feature_name(base, categories) + " tomorrow"
        return f"{name}: {fmt_value(base, value)}{tag}"
    if column.startswith("prev_"):
        base = column[len("prev_") :]
        return f"{feature_name(base, categories)} today: {fmt_value(split_feature(base)[0], value)}"
    if column.startswith("cat_"):
        return "Task category"
    if column == "planned_min":
        return f"Estimated length: {fmt_value('active_min', value)}"
    if column == "start_hour":
        return f"Planned start: {fmt_value('first_hour', value)}"
    if column == "tasks_that_day":
        return f"Tasks planned that day: {fmt_value('tasks_planned', value)}"
    base, kind = split_feature(column)
    when = {"": " today", "r3": " (3-day avg)", "r7": " (7-day avg)"}.get(kind, "")
    name = feature_name(base, categories)
    return f"{name}{when}: {fmt_value(base, value)}"


def _shap_values(t: Trained, row: pd.DataFrame) -> tuple[np.ndarray, float]:
    import shap

    X = row[t.features].astype(float)
    bg = t.background[t.features].astype(float)
    if t.kind in ("ridge", "logistic"):
        pre, est = t.model[:-1], t.model[-1]
        explainer = shap.LinearExplainer(est, pre.transform(bg))
        vals = explainer.shap_values(pre.transform(X))
        base = explainer.expected_value
    else:
        explainer = shap.TreeExplainer(t.model)
        vals = explainer.shap_values(X)
        base = explainer.expected_value
    vals = np.asarray(vals).reshape(-1)[: len(t.features)]
    base = float(np.asarray(base).reshape(-1)[0])
    return vals, base


def explain(
    t: Trained,
    row: pd.DataFrame,
    categories: list[str],
    sources: dict[str, str] | None = None,
    top: int = 3,
) -> dict:
    if t.model is None:
        what = {
            "mean": "your average over the last 2 weeks",
            "mean7": "your average over the last 7 days",
            "mean28": "your average over the last 4 weeks",
            "rate": "how often you usually finish planned tasks",
        }.get(t.kind, "your history")
        return {
            "model": t.kind,
            "summary": f"Based on {what}.",
            "contributors": [],
            "metrics": t.metrics,
        }
    try:
        vals, base = _shap_values(t, row)
    except Exception as exc:  # noqa: BLE001  explanations must never break predictions
        return {
            "model": t.kind,
            "summary": "Explanation unavailable.",
            "contributors": [],
            "error": type(exc).__name__,
            "metrics": t.metrics,
        }

    x = row[t.features].iloc[0]
    # Contributions this small are noise; don't present them as "reasons".
    min_impact = 0.15 if t.target == "task" else 0.05  # log-odds / rating points
    order = np.argsort(-np.abs(vals))
    total = float(np.sum(np.abs(vals))) or 1.0
    contributors = []
    for i in order:
        if len(contributors) >= top or abs(vals[i]) < min_impact:
            break
        col = t.features[i]
        if col.startswith("cat_") and not x[col]:
            continue  # "not in category X" is noise for people
        contributors.append(
            {
                "feature": col,
                "label": describe(col, x[col], categories, sources),
                "value": None if pd.isna(x[col]) else float(x[col]),
                "impact": round(float(vals[i]), 4),
                "share": round(abs(float(vals[i])) / total, 3),
                "direction": "up" if vals[i] > 0 else "down",
            }
        )
    summary = None if contributors else "No single factor stands out; close to your usual."
    start = None
    if t.target != "task":
        from app.ml.predict import start_point

        start = round(float(start_point(row[t.features], t.target).iloc[0]), 2)
    return {
        "model": t.kind,
        "base_value": round(base, 4),
        "contributors": contributors,
        "summary": summary,
        "start_from": start,  # the 7-day average the reasons adjust (None for tasks)
        "units": "log-odds" if t.target == "task" else "points",
        "metrics": t.metrics,
    }
