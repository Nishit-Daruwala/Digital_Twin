"""Baselines and anomalies (plan section 5).

- Rolling 14-day personal baseline (mean, sd) per metric, from PREVIOUS days only.
- A day is flagged when |z| >= 2.
- A streak is flagged when a metric is on the worse side of its baseline 3+ days in a row.
- Stretch: an Isolation Forest over the daily vector flags unusual combinations.

Only recent days (default: the last 3) produce insights; older anomalies are history.
Imputed (gap-filled) days are never flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.labels import fmt_num

# metric -> which direction is "worse"
METRICS = {"mood": -1, "energy": -1, "focus": -1, "stress": +1, "sleep_hours": -1}
NAMES = {
    "mood": "mood",
    "energy": "energy",
    "focus": "focus",
    "stress": "stress",
    "sleep_hours": "sleep",
}
WINDOW, MIN_PERIODS, Z_THRESHOLD, STREAK = 14, 7, 2.0, 3


@dataclass
class Anomaly:
    key: str
    kind: str  # spike / streak / unusual_day
    metric: str | None
    day: date
    text: str
    evidence: dict = field(default_factory=dict)
    severity: float = 0.0


def _unit(metric: str, v: float) -> str:
    return f"{fmt_num(v)} h" if metric == "sleep_hours" else fmt_num(v)


def baseline(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    prev = series.shift(1)
    mean = prev.rolling(WINDOW, min_periods=MIN_PERIODS).mean()
    sd = prev.rolling(WINDOW, min_periods=MIN_PERIODS).std()
    return mean, sd.clip(lower=0.35)  # a perfectly steady baseline shouldn't explode z


def detect(f: pd.DataFrame, today: date, recent_days: int = 3) -> list[Anomaly]:
    if f is None or f.empty:
        return []
    # continuous calendar index so "previous 14 days" means days, not rows
    idx = pd.date_range(min(f.index), max(f.index), freq="D")
    df = f.copy()
    df.index = pd.to_datetime(df.index)
    df = df.reindex(idx)
    real = df["imputed"].fillna(1) == 0 if "imputed" in df else df["mood"].notna()
    since = pd.Timestamp(today - timedelta(days=recent_days - 1))
    out: list[Anomaly] = []

    for m, worse in METRICS.items():
        if m not in df:
            continue
        s = df[m].where(real)
        mean, sd = baseline(s)
        z = (s - mean) / sd

        # --- single-day spikes ---
        for ts in z.index[(z.index >= since) & (z.abs() >= Z_THRESHOLD)]:
            zz, v = float(z[ts]), float(s[ts])
            bad = np.sign(zz) == worse
            word = "unusually low" if zz < 0 else "unusually high"
            day = ts.date()
            when = "today" if day == today else f"on {day.strftime('%a %d %b')}"
            out.append(
                Anomaly(
                    key=f"anomaly:spike:{m}:{day.isoformat()}",
                    kind="spike",
                    metric=m,
                    day=day,
                    text=(
                        f"Your {NAMES[m]} {when} ({_unit(m, v)}) was {word} for you; "
                        f"your 2-week normal is {_unit(m, float(mean[ts]))}."
                    ),
                    evidence={
                        "metric": m,
                        "value": v,
                        "baseline_mean": float(mean[ts]),
                        "baseline_sd": float(sd[ts]),
                        "z": round(zz, 2),
                        "worse": bool(bad),
                    },
                    severity=abs(zz) * (1.5 if bad else 0.7),
                )
            )

        # --- streaks on the worse side of the baseline, ending in the recent window ---
        worse_side = (s - mean) * worse > 0
        run, start = 0, None
        for ts, flag in worse_side.items():
            if bool(flag) and not np.isnan(s[ts]):
                run += 1
                start = ts if run == 1 else start
            else:
                run, start = 0, None
            last = ts
        if run >= STREAK and last >= since:
            word = "above" if worse > 0 else "below"
            out.append(
                Anomaly(
                    key=f"anomaly:streak:{m}:{start.date().isoformat()}",
                    kind="streak",
                    metric=m,
                    day=last.date(),
                    text=(
                        f"Your {NAMES[m]} has been {word} your usual for {run} days in a row "
                        f"(since {start.strftime('%a %d %b')})."
                    ),
                    evidence={
                        "metric": m,
                        "days": run,
                        "since": start.date().isoformat(),
                        "baseline_mean": float(mean[last]) if not np.isnan(mean[last]) else None,
                    },
                    severity=1.0 + 0.3 * run,
                )
            )

    out.extend(_unusual_combination(df, real, since))
    return sorted(out, key=lambda a: a.severity, reverse=True)


def _unusual_combination(df: pd.DataFrame, real: pd.Series, since: pd.Timestamp) -> list[Anomaly]:
    """Isolation Forest over the daily vector (stretch goal): days whose COMBINATION is rare."""
    from sklearn.ensemble import IsolationForest

    cols = [
        c for c in ("mood", "energy", "stress", "focus", "sleep_hours", "active_min") if c in df
    ]
    X = df.loc[real, cols].dropna()
    if len(X) < 30:
        return []
    z = (X - X.mean()) / X.std(ddof=0).replace(0, 1)
    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=0).fit(z)
    scores = pd.Series(model.decision_function(z), index=z.index)
    flagged = scores[(scores.index >= since) & (model.predict(z) == -1)]
    out = []
    for ts, sc in flagged.items():
        top = z.loc[ts].abs().sort_values(ascending=False).index[:2]
        parts = [
            f"{NAMES.get(c, 'active time')} {'high' if z.loc[ts, c] > 0 else 'low'}" for c in top
        ]
        out.append(
            Anomaly(
                key=f"anomaly:unusual:{ts.date().isoformat()}",
                kind="unusual_day",
                metric=None,
                day=ts.date(),
                text=(
                    f"{ts.strftime('%a %d %b')} was an unusual mix for you "
                    f"({' and '.join(parts)})."
                ),
                evidence={"score": round(float(sc), 3), "drivers": list(top)},
                severity=0.8 + abs(float(sc)) * 5,
            )
        )
    return out
