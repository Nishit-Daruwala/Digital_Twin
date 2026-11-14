"""Tomorrow's predictions (plan section 6). Pure functions over the feature table.

Inputs are split honestly into
- KNOWN TONIGHT: today's values, recent averages and trends (all observed by the evening);
- PLAN-ABLE for tomorrow: tonight's sleep, tomorrow's minutes per category, tasks planned,
  and the weekday. In training these are what actually happened the next day; when
  predicting they come from the user's plans, or their typical values, or (Phase 4) the
  what-if sliders. A model that silently used tomorrow's real check-in would look great in
  testing and be useless in practice.

Model ladder (plan): < 14 training days -> personal mean; 14-30 -> Ridge / logistic;
> 30 -> XGBoost (shallow, regularised). Every candidate must beat the naive baseline
("tomorrow = 7-day mean"; for tasks: the personal completion rate) in walk-forward
validation, or the baseline is used instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.features import split_feature

REG_TARGETS = ("energy", "mood")
CHECKIN = ["sleep_hours", "mood", "energy", "stress", "focus"]
ACTIVITY = [
    "active_min",
    "tasks_planned",
    "completion_rate",
    "last_hour",
    "msg_count",
    "sentiment_mean",
]
DOW = [
    "is_monday",
    "is_tuesday",
    "is_wednesday",
    "is_thursday",
    "is_friday",
    "is_saturday",
    "is_sunday",
]
MIN_DAYS_MODEL, MIN_DAYS_XGB = 14, 30
WF_FOLDS, WF_TEST = 4, 7


# --------------------------------------------------------------------------------------
# Feature construction
# --------------------------------------------------------------------------------------


def calendar_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Feature table on a continuous daily index (gaps become NaN rows), plus a 28-day
    personal norm per check-in metric (steadier than the 7-day mean; see start_point)."""
    df = f.copy()
    df.index = pd.to_datetime(df.index)
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="D"))
    for c in CHECKIN:
        if c in df:
            df[f"{c}_r28"] = df[c].rolling(28, min_periods=7).mean()
    return df


def category_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("min_") and split_feature(c)[1] == ""]


def known_cols(df: pd.DataFrame) -> list[str]:
    # Deliberately compact: with ~30-90 days of data, every extra column is a chance to
    # overfit. Today's value + the 7-day trend per check-in metric, today's activity mix.
    cols = []
    for c in CHECKIN:
        cols += [c, f"{c}_lag1", f"{c}_r7", f"{c}_r28"]
    cols += ACTIVITY + ["completion_rate_r7"]
    cols += category_cols(df)
    return [c for c in cols if c in df.columns]


def planable_cols(df: pd.DataFrame) -> list[str]:
    return (
        ["next_sleep_hours", "next_tasks_planned"]
        + [f"next_{c}" for c in category_cols(df)]
        + ["next_is_weekend"]
        + [f"next_{d}" for d in DOW]
    )


def _calendar_flags(day: pd.Timestamp) -> dict:
    flags = {f"next_{d}": int(day.weekday() == i) for i, d in enumerate(DOW)}
    flags["next_is_weekend"] = int(day.weekday() >= 5)
    return flags


def training_rows(f: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """X (one row per day t), y = target on day t+1, baseline = 7-day mean known on day t."""
    df = calendar_frame(f)
    known = df[known_cols(df)]
    nxt = df.shift(-1)
    plan = pd.DataFrame(index=df.index)
    plan["next_sleep_hours"] = nxt["sleep_hours"]
    plan["next_tasks_planned"] = nxt.get("tasks_planned")
    for c in category_cols(df):
        plan[f"next_{c}"] = nxt[c]
    cal = pd.DataFrame([_calendar_flags(d + timedelta(days=1)) for d in df.index], index=df.index)
    X = pd.concat([known, plan, cal], axis=1)
    y = nxt[target]
    real_next = (nxt["imputed"] == 0) if "imputed" in nxt else y.notna()
    base = df[target].rolling(7, min_periods=1).mean()
    ok = y.notna() & real_next & known[target].notna() if target in known else y.notna()
    return X[ok], y[ok], base[ok]


def assumed_plan(
    f: pd.DataFrame,
    tomorrow: date,
    planned_minutes: dict[str, float] | None = None,
    planned_tasks: int | None = None,
    overrides: dict[str, float] | None = None,
) -> tuple[dict, dict]:
    """Plan-able inputs for tomorrow: user's plans, else their typical values.
    Returns (values, source) where source[col] is 'planned' / 'typical' / 'set'."""
    df = calendar_frame(f)
    tail14 = df.tail(14)
    weekend = tomorrow.weekday() >= 5
    same_type = df[(df.index.weekday >= 5) == weekend].tail(28)
    vals: dict[str, float] = {}
    src: dict[str, str] = {}
    vals["next_sleep_hours"] = float(tail14["sleep_hours"].mean())
    src["next_sleep_hours"] = "typical"
    if planned_tasks:
        vals["next_tasks_planned"], src["next_tasks_planned"] = float(planned_tasks), "planned"
    else:
        vals["next_tasks_planned"] = float(same_type.get("tasks_planned", pd.Series()).mean())
        src["next_tasks_planned"] = "typical"
    for c in category_cols(df):
        if planned_minutes and planned_minutes.get(c):
            vals[f"next_{c}"], src[f"next_{c}"] = float(planned_minutes[c]), "planned"
        else:
            vals[f"next_{c}"], src[f"next_{c}"] = float(same_type[c].mean()), "typical"
    vals.update(_calendar_flags(pd.Timestamp(tomorrow)))
    for k, v in (overrides or {}).items():
        vals[k], src[k] = float(v), "set"
    vals = {
        k: (np.nan if v is None or (isinstance(v, float) and np.isnan(v)) else v)
        for k, v in vals.items()
    }
    return vals, src


def tonight_row(f: pd.DataFrame, plan: dict, columns: list[str]) -> pd.DataFrame:
    df = calendar_frame(f)
    last = df.iloc[-1]
    row = {c: last[c] if c in last.index else np.nan for c in known_cols(df)}
    row.update(plan)
    return pd.DataFrame([row]).reindex(columns=columns).astype(float)


# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------


@dataclass
class Trained:
    target: str
    kind: str  # mean / mean7 / ridge / xgboost / rate / logistic
    features: list[str]
    model: object | None = None
    constant: float | None = None
    metrics: dict = field(default_factory=dict)
    background: pd.DataFrame | None = None  # for SHAP


def _regressor(kind: str):
    if kind == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import RidgeCV
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            RidgeCV(alphas=[3, 10, 30, 100, 300, 1000]),
        )
    from xgboost import XGBRegressor

    return XGBRegressor(
        n_estimators=200,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5.0,
        min_child_weight=3,
        random_state=0,
        n_jobs=1,
    )


def start_point(X: pd.DataFrame, target: str) -> pd.Series:
    """What the model adjusts: the person's 28-day norm known tonight (falling back to the
    7-day mean, then today's value). Models learn the *deviation* from it, so a heavily
    regularised model falls back to a sensible personal norm instead of doing worse.
    (Measured: the deviation from a 7-day mean is noisier than the score itself.)"""
    s = pd.Series(np.nan, index=X.index)
    for c in (f"{target}_r28", f"{target}_r7", target):
        if c in X:
            s = s.fillna(X[c])
    return s.fillna(3.0)


SCREEN_K = 10
MAX_ADJUST = 1.5  # a model may move a prediction at most this far from the personal norm
MIN_FOLDS = 3  # a learned model needs >= 3 walk-forward folds (21+ unseen days) to be trusted


def screen(X: pd.DataFrame, r: pd.Series, target: str | None, k: int = SCREEN_K) -> list[str]:
    """Keep the k inputs most (rank-)correlated with what the model must learn, plus the
    start-point columns. Each person has only a handful of real drivers among ~40 inputs;
    feeding all of them to a model with 30-90 rows mostly fits noise. Called inside every
    walk-forward fold on that fold's training rows only (no peeking at the test days)."""
    keep = [c for c in (f"{target}_r28", f"{target}_r7", target) if target and c in X.columns]
    scores = {}
    rr = r.rank()
    for c in X.columns:
        if c in keep:
            continue
        x = X[c]
        ok = x.notna() & r.notna()
        if ok.sum() < 10 or x[ok].nunique() < 2:
            continue
        v = x[ok].rank().corr(rr[ok])
        if v == v:
            scores[c] = abs(v)
    best = sorted(scores, key=lambda c: (-scores[c], c))[:k]
    return keep + [c for c in X.columns if c in best]  # stable column order


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    make,
    folds=WF_FOLDS,
    test=WF_TEST,
    min_train=10,
    target: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Train only on the past, test on the following days. Returns (pred, actual, index).
    With `target`, models are fitted on the deviation from start_point(), on inputs
    screened from that fold's training rows."""
    n = len(X)
    b = start_point(X, target) if target else pd.Series(0.0, index=X.index)
    preds, acts, idx = [], [], []
    for i in range(folds):
        end = n - (folds - i) * test
        if end < min_train:
            continue
        resid = y.iloc[:end] - b.iloc[:end]
        cols = screen(X.iloc[:end], resid, target)
        m = make().fit(X.iloc[:end][cols], resid)
        adj = np.clip(m.predict(X.iloc[end : end + test][cols]), -MAX_ADJUST, MAX_ADJUST)
        p = adj + b.iloc[end : end + test].values
        preds.extend(p)
        acts.extend(y.iloc[end : end + test])
        idx.extend(range(end, min(end + test, n)))
    return np.array(preds), np.array(acts), np.array(idx)


def train_regression(f: pd.DataFrame, target: str) -> Trained:
    X, y, base = training_rows(f, target)
    n = len(X)
    feats = list(X.columns)
    recent = float(f[target].dropna().tail(14).mean()) if target in f else np.nan
    if n < MIN_DAYS_MODEL:
        return Trained(
            target,
            "mean",
            feats,
            constant=recent,
            metrics={"n_train": n, "reason": "fewer than 14 days"},
        )

    kinds = ["ridge"] + (["xgboost"] if n > MIN_DAYS_XGB else [])
    results = {}
    for kind in kinds:
        p, a, idx = walk_forward(X, y, lambda k=kind: _regressor(k), target=target)
        if len(p) >= MIN_FOLDS * WF_TEST:
            p = np.clip(p, 1, 5)
            results[kind] = (float(np.mean(np.abs(p - a))), p, a, idx)
    if results:
        _, _, a_any, idx_any = next(iter(results.values()))
    else:  # too little data to validate a model: score the simple norms on the last days
        idx_any = np.arange(max(0, n - 2 * WF_TEST), n)
        a_any = y.iloc[idx_any].values

    # Simple personal averages on the same test days. "mean7" is the plan's baseline;
    # "mean28" (a steadier personal norm) measured 2-7% better on the synthetic users.
    norm28 = X[f"{target}_r28"].fillna(base) if f"{target}_r28" in X else base
    simple = {"mean7": base, "mean28": norm28}
    simple_mae = {
        k: float(np.mean(np.abs(v.iloc[idx_any].values - a_any))) if len(idx_any) else np.nan
        for k, v in simple.items()
    }
    base_mae = simple_mae["mean7"]
    candidates = {k: round(v[0], 3) for k, v in results.items()} | {
        k: round(v, 3) for k, v in simple_mae.items() if v == v
    }
    # Fallback is always the 28-day norm: across the synthetic users it beat the 7-day mean
    # at every horizon, and choosing between the two on ~4 weeks of test days is mostly noise.
    best_simple = "mean28"

    # A learned model must beat the personal norm by a clear margin (5%) in
    # walk-forward validation. With ~4 weeks of test days a smaller "win" is mostly luck,
    # and an unlucky model costs accuracy for users whose tomorrow isn't predictable.
    best = min(results, key=lambda k: results[k][0]) if results else None
    simple_ref = simple_mae[best_simple]
    if best is None or not results[best][0] < 0.95 * simple_ref:
        days = 28 if best_simple == "mean28" else 7
        return Trained(
            target,
            best_simple,
            feats,
            constant=float(f[target].dropna().tail(days).mean()),
            metrics={
                "n_train": n,
                "mae": simple_mae[best_simple] if len(idx_any) else None,
                "baseline_mae": base_mae if len(idx_any) else None,
                "reason": "no model clearly beat your personal average",
                "candidates": candidates,
            },
        )
    mae, p, a, _ = results[best]
    resid = y - start_point(X, target)
    feats = screen(X, resid, target)
    model = _regressor(best).fit(X[feats], resid)
    resid_sd = float(np.std(p - a))
    return Trained(
        target,
        best,
        feats,
        model=model,
        background=X[feats].tail(60),
        metrics={
            "n_train": n,
            "mae": round(mae, 3),
            "baseline_mae": round(base_mae, 3),
            "resid_sd": round(resid_sd, 3),
            "candidates": candidates,
        },
    )


def predict_value(t: Trained, row: pd.DataFrame) -> float:
    if t.model is None:
        # Averages are read from tonight's row (always the latest), not frozen at training.
        live = None
        if t.kind == "mean28":
            live = float(start_point(row, t.target).iloc[0])
        elif t.kind == "mean7" and f"{t.target}_r7" in row and row[f"{t.target}_r7"].notna().all():
            live = float(row[f"{t.target}_r7"].iloc[0])
        value = live if live is not None else t.constant
        return float(np.clip(value if value is not None else 3.0, 1, 5))
    start = float(start_point(row, t.target).iloc[0])
    adj = float(np.clip(t.model.predict(row[t.features])[0], -MAX_ADJUST, MAX_ADJUST))
    return float(np.clip(start + adj, 1, 5))


def interval(t: Trained, value: float) -> tuple[float, float]:
    sd = t.metrics.get("resid_sd") or t.metrics.get("baseline_mae") or 0.8
    sd = 0.8 if not sd or np.isnan(sd) else sd
    return max(1.0, value - 1.28 * sd), min(5.0, value + 1.28 * sd)  # ~80% range


# --------------------------------------------------------------------------------------
# Task completion (classification)
# --------------------------------------------------------------------------------------


def _task_frame(acts: pd.DataFrame, f: pd.DataFrame, categories_slugs: list[str]) -> pd.DataFrame:
    df = calendar_frame(f)
    a = acts[acts["planned"]].copy()
    if a.empty:
        return pd.DataFrame()
    a["date"] = pd.to_datetime(a["date"])
    rows = []
    for _, r in a.iterrows():
        d = r["date"]
        prev = df.loc[d - timedelta(days=1)] if (d - timedelta(days=1)) in df.index else None
        today = df.loc[d] if d in df.index else None
        row = {
            "planned_min": r["planned_min"],
            "start_hour": (r["start_time"].hour + r["start_time"].minute / 60)
            if r["start_time"] is not None and not pd.isna(r["start_time"])
            else np.nan,
            "tasks_that_day": float((a["date"] == d).sum()),
            "next_sleep_hours": today["sleep_hours"] if today is not None else np.nan,
            "next_is_weekend": int(d.weekday() >= 5),
        }
        for m in ("mood", "energy", "focus", "stress", "completion_rate_r7", "active_min"):
            row[f"prev_{m}"] = prev[m] if prev is not None and m in prev.index else np.nan
        for s in categories_slugs:
            row[f"cat_{s}"] = int(_slug(r["category"]) == s)
        row["_date"], row["_label"] = d, int(bool(r["completed"]))
        row["_category"] = r["category"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("_date").reset_index(drop=True)


def _slug(name: str) -> str:
    from app.seed.patterns import slug

    return slug(name)


def _classifier(kind: str):
    if kind == "logistic":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=1000),
        )
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=150,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5.0,
        min_child_weight=3,
        random_state=0,
        n_jobs=1,
        eval_metric="logloss",
    )


def _rate(y: pd.Series) -> float:
    return float((y.sum() + 1) / (len(y) + 2))  # smoothed personal completion rate


def train_tasks(acts: pd.DataFrame, f: pd.DataFrame, categories: list[str], today: date) -> Trained:
    slugs = [_slug(c) for c in categories]
    t = (
        _task_frame(acts[pd.to_datetime(acts["date"]) < pd.Timestamp(today)], f, slugs)
        if not acts.empty
        else pd.DataFrame()
    )
    if t.empty:
        return Trained("task", "rate", [], constant=0.5, metrics={"n_train": 0})
    feats = [c for c in t.columns if not c.startswith("_")]
    X, y = t[feats].astype(float), t["_label"]
    days = t["_date"].nunique()
    rate = _rate(y)
    if days < MIN_DAYS_MODEL or y.nunique() < 2:
        return Trained(
            "task",
            "rate",
            feats,
            constant=rate,
            metrics={"n_train": len(t), "days": days, "rate": round(rate, 3)},
        )

    from sklearn.metrics import brier_score_loss, roc_auc_score

    kinds = ["logistic"] + (["xgboost"] if days > MIN_DAYS_XGB else [])
    # walk-forward by day
    day_list = sorted(t["_date"].unique())
    test_days = day_list[-WF_FOLDS * WF_TEST :]
    results = {}
    for kind in kinds:
        ps, ys, bs = [], [], []
        folds_run = 0
        for i in range(WF_FOLDS):
            chunk = test_days[i * WF_TEST : (i + 1) * WF_TEST]
            if not chunk:
                continue
            tr = t["_date"] < chunk[0]
            te = t["_date"].isin(chunk)
            if tr.sum() < 20 or t.loc[tr, "_label"].nunique() < 2 or te.sum() == 0:
                continue
            m = _classifier(kind).fit(X[tr], y[tr])
            folds_run += 1
            ps.extend(m.predict_proba(X[te])[:, 1])
            ys.extend(y[te])
            bs.extend([_rate(y[tr])] * int(te.sum()))
        if len(set(map(str, ps))) and folds_run >= MIN_FOLDS:
            results[kind] = (brier_score_loss(ys, ps), ps, ys, bs)
    if not results:
        return Trained("task", "rate", feats, constant=rate, metrics={"n_train": len(t)})
    best = min(results, key=lambda k: results[k][0])
    brier, ps, ys, bs = results[best]
    base_brier = brier_score_loss(ys, bs)
    auc = roc_auc_score(ys, ps) if len(set(ys)) > 1 else None
    metrics = {
        "n_train": len(t),
        "days": days,
        "brier": round(brier, 4),
        "baseline_brier": round(base_brier, 4),
        "auc": round(auc, 3) if auc else None,
        "rate": round(rate, 3),
    }
    # Paired test (Diebold-Mariano style): per task, model error minus base-rate error.
    # The model must be better by more than 2 standard errors; ~50 validation tasks make
    # 10% "wins" by pure luck common.
    d = (np.array(ps) - np.array(ys)) ** 2 - (np.array(bs) - np.array(ys)) ** 2
    se = float(np.std(d, ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("inf")
    metrics["improvement_se"] = round(float(-d.mean() / se), 2) if se > 0 else None
    if not (d.mean() < 0 and -d.mean() > 2 * se):
        return Trained(
            "task",
            "rate",
            feats,
            constant=rate,
            metrics=metrics | {"reason": "no model beat the personal rate"},
        )
    model = _classifier(best).fit(X, y)
    return Trained("task", best, feats, model=model, background=X.tail(120), metrics=metrics)


def task_rows(
    planned: pd.DataFrame,
    f: pd.DataFrame,
    categories: list[str],
    tomorrow: date,
    sleep_assumed: float,
) -> pd.DataFrame:
    """Feature rows for tomorrow's planned tasks (same layout as training)."""
    slugs = [_slug(c) for c in categories]
    df = calendar_frame(f)
    prev = df.iloc[-1]
    rows = []
    for _, r in planned.iterrows():
        st = r.get("start_time")
        row = {
            "planned_min": r.get("planned_min"),
            "start_hour": st.hour + st.minute / 60
            if st is not None and not pd.isna(st)
            else np.nan,
            "tasks_that_day": float(len(planned)),
            "next_sleep_hours": sleep_assumed,
            "next_is_weekend": int(tomorrow.weekday() >= 5),
        }
        for m in ("mood", "energy", "focus", "stress", "completion_rate_r7", "active_min"):
            row[f"prev_{m}"] = prev[m] if m in prev.index else np.nan
        for s in slugs:
            row[f"cat_{s}"] = int(_slug(r["category"]) == s)
        rows.append(row)
    return pd.DataFrame(rows)


def predict_task(t: Trained, row: pd.DataFrame) -> float:
    if t.model is None:
        return float(t.constant if t.constant is not None else 0.5)
    return float(t.model.predict_proba(row.reindex(columns=t.features).astype(float))[0, 1])
