"""Pattern discovery: the AI-derived insights (plan section 4).

For every (feature, target, lag) pair: Spearman rho and p-value, Benjamini-Hochberg across
all tests, keep |rho| >= 0.4, adjusted p <= 0.05, n >= 10; rank by |rho| * sqrt(n);
effect size from a median split. Pure functions; no database, no LLM.

Lags: 0 (same day), 1 (next day) and 2. The plan names lag 0/1, but its own founder persona
("stress rises 2 days before mood drops") needs lag 2 to be discoverable.

Pairs that would be "true by construction" are never tested:
- leakage (features.is_leaky): e.g. tasks_completed vs completion_rate on the same day
- a target's own history (yesterday's mood vs mood): true but uninformative
- same-day pairs between self-reported scores (mood vs energy, answered in the same
  check-in) and chat sentiment vs same-day scores (a proxy of the same feeling)
- rolling means: they duplicate the base feature; one insight per idea
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

from app.ml.features import is_leaky, split_feature
from app.ml.labels import METRICS, TARGET_NAMES, condition, fmt_num

TARGETS = ["mood", "energy", "focus", "completion_rate"]
LAGS = (0, 1, 2)
CALENDAR = {
    "is_weekend",
    "is_monday",
    "is_tuesday",
    "is_wednesday",
    "is_thursday",
    "is_friday",
    "is_saturday",
    "is_sunday",
}
SKIP_BASES = {"imputed", "weekday", "tasks_completed"}

MIN_RHO = 0.4
MAX_P_ADJ = 0.05
MIN_N = 10
MIN_GROUP = 5  # each side of a split needs this many days...
MIN_GROUP_SHARE = 0.20  # ...and this share of them for continuous splits (1-5 ratings bunch
# around one value, so a lopsided "mood above 2" split of 49 vs 10 days is a chance finding)


@dataclass
class Pattern:
    key: str
    feature: str  # base feature, e.g. "sleep_hours"
    column: str  # column tested, e.g. "sleep_hours_lag1"
    target: str
    lag: int
    r: float
    p: float
    p_adj: float
    n: int
    rank: float
    direction: str  # "+" or "-"
    threshold: float
    worse_side: str  # "high" or "low": which side of the split has the worse outcome
    worse_mean: float
    other_mean: float
    n_worse: int
    n_other: int
    binary: bool
    template: str = ""
    confidence: float = 0.0

    def evidence(self) -> dict:
        d = asdict(self)
        d.pop("key")
        for k in ("r", "p", "p_adj", "rank", "threshold", "worse_mean", "other_mean", "confidence"):
            d[k] = float(round(d[k], 4))
        return d


def pattern_key(feature: str, target: str, lag: int) -> str:
    return f"pattern:{feature}>{target}@{lag}"


def _candidates(f: pd.DataFrame) -> list[tuple[str, str, int]]:
    bases = [c for c in f.columns if split_feature(c)[1] == "" and c not in SKIP_BASES]
    out = []
    for target in TARGETS:
        if target not in f.columns:
            continue
        for base in bases:
            if base == target:
                continue  # its own history
            for lag in LAGS:
                if base in CALENDAR and lag > 0:
                    continue
                if lag == 0 and base in METRICS and target in METRICS:
                    continue  # same check-in, same moment
                if lag == 0 and base == "sentiment_mean" and target in METRICS:
                    continue  # chat tone is a proxy for the same feeling
                col = base if lag == 0 else f"{base}_lag{lag}"
                if col not in f.columns or is_leaky(col, target):
                    continue
                out.append((col, target, lag))
    return out


def _test(x: pd.Series, y: pd.Series) -> tuple[float, float, int] | None:
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    n = int(len(x))
    if n < MIN_N or x.nunique() < 2 or y.nunique() < 2:
        return None
    r, p = stats.spearmanr(x, y)
    if r is None or np.isnan(r):
        return None
    return float(r), float(p), n


def _split(x: pd.Series, y: pd.Series, target: str, r: float):
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    binary = set(x.unique()) <= {0, 1}
    # Rare extremes of a continuous feature mislead (a "mood above 3" group of 4 days);
    # 10% for continuous splits let such chance findings through in tests. On/off flags
    # such as weekdays are 1/7 of days by design, so they get 10%.
    need = max(MIN_GROUP, (0.10 if binary else MIN_GROUP_SHARE) * len(x))
    if binary:
        threshold = 0.5
    elif base_is_minutes(x.name) and (x == 0).mean() >= 0.3:
        threshold = 0.0  # often zero: "any Exercise" vs "none" reads better than a median
    else:
        threshold = _balanced_threshold(x, need)
        if threshold is None:
            return None
    high = x > threshold
    if high.sum() < need or (~high).sum() < need:
        return None
    m_hi, m_lo = float(y[high].mean()), float(y[~high].mean())
    # "worse" = lower value for every target we mine (mood, energy, focus, completion)
    worse_high = m_hi < m_lo
    return {
        "threshold": threshold,
        "binary": binary,
        "worse_side": "high" if worse_high else "low",
        "worse_mean": m_hi if worse_high else m_lo,
        "other_mean": m_lo if worse_high else m_hi,
        "n_worse": int(high.sum() if worse_high else (~high).sum()),
        "n_other": int((~high).sum() if worse_high else high.sum()),
    }


def _balanced_threshold(x: pd.Series, need: float) -> float | None:
    """Most even split "x > t" whose groups both have at least `need` days.

    1-5 ratings tie heavily at the median: stress {3: 28, 4: 25, 5: 5} split at "> 4" gives
    5 vs 53 days and a real pattern would be dropped, while "4 or more" (> 3) gives 30 vs 28.
    """
    med = float(x.median())
    options = {med}
    lower = x[x < med]
    if len(lower):
        options.add(float(lower.max()))  # "at or above the median"
    if (x == 0).any():
        options.add(0.0)  # "any" vs "none"
    best: tuple[int, float] | None = None
    for t in sorted(options):
        hi = int((x > t).sum())
        lo = len(x) - hi
        if min(hi, lo) < need:
            continue
        if best is None or abs(hi - lo) < best[0]:
            best = (abs(hi - lo), t)
    return None if best is None else best[1]


def base_is_minutes(column) -> bool:
    return str(split_feature(str(column))[0]).startswith("min_")


DOW_PLURAL = {
    "is_monday": "Mondays",
    "is_tuesday": "Tuesdays",
    "is_wednesday": "Wednesdays",
    "is_thursday": "Thursdays",
    "is_friday": "Fridays",
    "is_saturday": "Saturdays",
    "is_sunday": "Sundays",
    "is_weekend": "weekends",
}


def _fmt_target(target: str, v: float) -> str:
    return f"{round(v * 100):d}%" if target == "completion_rate" else fmt_num(v)


def template_sentence(p: Pattern, categories: list[str]) -> str:
    """Plain, factual sentence. Every number in it comes from the evidence."""
    tname = TARGET_NAMES.get(p.target, p.target)
    worse = _fmt_target(p.target, p.worse_mean)
    other_v = _fmt_target(p.target, p.other_mean)
    if p.feature in DOW_PLURAL:  # calendar flags are only tested on the same day
        days = DOW_PLURAL[p.feature]
        if p.worse_side == "high":
            return f"On {days}, your {tname} averages {worse} (vs {other_v} on other days)."
        return f"Except on {days}, your {tname} averages {worse} (vs {other_v} on {days})."
    cond = condition(p.feature, p.worse_side == "high", p.threshold, categories)
    when = {0: "On days when", 1: "The day after", 2: "Two days after"}[p.lag]
    return f"{when} {cond}, your {tname} averages {worse} (vs {other_v} otherwise)."


def discover(f: pd.DataFrame, categories: list[str]) -> list[Pattern]:
    """All significant patterns for one user's feature table, best first."""
    if f is None or f.empty:
        return []
    tests = []
    for col, target, lag in _candidates(f):
        res = _test(f[col].astype(float), f[target].astype(float))
        if res:
            tests.append((col, target, lag, *res))
    if not tests:
        return []
    p_adj = stats.false_discovery_control([t[4] for t in tests], method="bh")

    found: dict[tuple[str, str], Pattern] = {}
    for (col, target, lag, r, p, n), pa in zip(tests, p_adj, strict=True):
        if abs(r) < MIN_RHO or pa > MAX_P_ADJ or n < MIN_N:
            continue
        split = _split(f[col].astype(float), f[target].astype(float), target, r)
        if split is None:
            continue
        base = split_feature(col)[0]
        pat = Pattern(
            key=pattern_key(base, target, lag),
            feature=base,
            column=col,
            target=target,
            lag=lag,
            r=r,
            p=p,
            p_adj=float(pa),
            n=n,
            rank=abs(r) * math.sqrt(n),
            direction="+" if r > 0 else "-",
            **split,
        )
        pat.confidence = round(min(1.0, n / 45) * min(1.0, abs(r) / 0.7), 2)
        pat.template = template_sentence(pat, categories)
        # one insight per (feature, target): keep the strongest lag
        prev = found.get((base, target))
        if prev is None or pat.rank > prev.rank:
            found[(base, target)] = pat
    return sorted(found.values(), key=lambda p: p.rank, reverse=True)
