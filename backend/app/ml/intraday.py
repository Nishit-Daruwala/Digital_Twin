"""Time of day: check-in slots, the person's daily rhythm, and per-slot forecasts.

A day has three optional check-in slots. Mood and energy follow a daily rhythm (many people
dip in the afternoon or fade in the evening), so a 9 AM and a 10 PM answer measure different
things. The rhythm is learned only from *within-day* comparisons (days with 2+ check-ins):
comparing slots across different days would mix in "I only check in at night on bad days".

- learn(ck):    per metric and slot, the usual offset from that day's average (shrunk
                toward 0 while there is little evidence)
- daily(ck):    one row per day, each check-in adjusted for its slot, then averaged; this is
                what the pattern miner and the daily models learn from
- forecast():   tomorrow by slot = daily prediction + the person's slot offset
- insights():   "Your energy is usually higher in the morning than in the evening", only when
                a paired test over enough days supports it
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats

SLOTS = ("morning", "afternoon", "evening")
SLOT_LABEL = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}
SLOT_WINDOW = {"morning": "until 12:00", "afternoon": "12:00–17:00", "evening": "after 17:00"}
DAY_START_HOUR = 4  # 00:00-03:59 still belongs to the previous day's evening
AFTERNOON_HOUR, EVENING_HOUR = 12, 17

METRICS = ("mood", "energy", "stress", "focus")
RHYTHM_METRICS = ("energy", "mood")  # asked in every check-in, so they have a rhythm to learn
SHRINK = 5.0  # an offset seen on n days counts n / (n + SHRINK)
MIN_PAIRED_DAYS = 8
MIN_DIFF = 0.4  # rating points
MAX_P = 0.05  # Bonferroni-corrected over all slot pairs and metrics tested


def slot_for(local: datetime) -> tuple[date, str]:
    """(day, slot) for a local time. A 1 AM check-in is the previous day's evening."""
    h = local.hour
    if h < DAY_START_HOUR:
        return local.date() - timedelta(days=1), "evening"
    if h < AFTERNOON_HOUR:
        return local.date(), "morning"
    if h < EVENING_HOUR:
        return local.date(), "afternoon"
    return local.date(), "evening"


def slot_started(day: date, slot: str, local_now: datetime) -> bool:
    """Has this slot begun? (You can fill in this morning at 3 PM, not this evening.)"""
    today, current = slot_for(local_now)
    if day != today:
        return day < today
    return SLOTS.index(slot) <= SLOTS.index(current)


def _has_slots(ck: pd.DataFrame) -> bool:
    return ck is not None and not ck.empty and "slot" in ck.columns


def learn(ck: pd.DataFrame) -> dict:
    """The person's daily rhythm: {"days_multi": n, "metrics": {m: {slot: {offset, n}}}}."""
    empty = {m: {s: {"offset": 0.0, "n": 0} for s in SLOTS} for m in METRICS}
    if not _has_slots(ck):
        return {"days_multi": 0, "metrics": empty}
    days_multi = int((ck.groupby("date")["slot"].nunique() >= 2).sum())
    out = {}
    for m in METRICS:
        if m not in ck:
            out[m] = empty[m]
            continue
        d = ck[["date", "slot", m]].dropna()
        d = d[d.groupby("date")[m].transform("count") >= 2]
        raw = _two_way_offsets(d, m)
        out[m] = {}
        for s in SLOTS:
            n = int((d["slot"] == s).sum())
            out[m][s] = {"offset": round(raw.get(s, 0.0) * n / (n + SHRINK), 3), "n": n}
    return {"days_multi": days_multi, "metrics": out}


def _two_way_offsets(d: pd.DataFrame, m: str, iters: int = 50) -> dict:
    """Least-squares fit of value = day level + slot offset on days with 2+ check-ins
    (alternating means). Unlike "deviation from the day's own mean", this stays unbiased
    when days have different sets of slots (morning+afternoon one day, afternoon+evening
    the next). Offsets are centred so the average check-in has offset 0."""
    if d.empty:
        return {}
    v = d[m].astype(float).to_numpy()
    day_codes, _ = pd.factorize(d["date"])
    slot_codes, slot_names = pd.factorize(d["slot"])
    off = np.zeros(len(slot_names))
    for _ in range(iters):
        level = np.bincount(day_codes, v - off[slot_codes]) / np.bincount(day_codes)
        new = np.bincount(slot_codes, v - level[day_codes]) / np.bincount(slot_codes)
        new -= np.average(new, weights=np.bincount(slot_codes))
        if np.allclose(new, off, atol=1e-6):
            off = new
            break
        off = new
    return {str(s): float(o) for s, o in zip(slot_names, off, strict=True)}


def offset(rhythm: dict | None, metric: str, slot: str) -> float:
    if not rhythm:
        return 0.0
    return float(rhythm.get("metrics", {}).get(metric, {}).get(slot, {}).get("offset", 0.0))


def daily(ck: pd.DataFrame, rhythm: dict | None = None) -> pd.DataFrame:
    """One row per day: slot-adjusted means of the day's check-ins; sleep from any of them.

    Frames without a `slot` column (one check-in per day) pass through unchanged."""
    if not _has_slots(ck):
        return ck
    rhythm = rhythm or learn(ck)
    adj = ck.copy()
    for m in METRICS:
        if m in adj:
            shift = adj["slot"].map(lambda s, m=m: offset(rhythm, m, s))
            adj[m] = pd.to_numeric(adj[m], errors="coerce") - shift
    adj["sleep_hours"] = pd.to_numeric(adj.get("sleep_hours"), errors="coerce")
    agg = {m: "mean" for m in METRICS if m in adj}
    agg["sleep_hours"] = "max"  # asked once a day; max ignores the empty quick check-ins
    out = adj.groupby("date", as_index=False).agg(agg)
    return out[["date", *[c for c in ("sleep_hours", *METRICS) if c in out]]]


def forecast(value: float, rhythm: dict | None, metric: str) -> dict:
    """Tomorrow by slot for one metric, plus how much the person's rhythm says about it."""
    slots = {}
    for s in SLOTS:
        o = offset(rhythm, metric, s)
        n = int((rhythm or {}).get("metrics", {}).get(metric, {}).get(s, {}).get("n", 0))
        slots[s] = {"value": round(float(np.clip(value + o, 1, 5)), 2), "offset": o, "n": n}
    learned = any(v["n"] > 0 for v in slots.values())
    return {"slots": slots, "learned": learned}


def insights(ck: pd.DataFrame) -> list[dict]:
    """Supported rhythm statements, strongest first. Numbers come from the paired days."""
    if not _has_slots(ck):
        return []
    pairs = [(a, b) for i, a in enumerate(SLOTS) for b in SLOTS[i + 1 :]]
    n_tests = len(pairs) * len(RHYTHM_METRICS)
    found = []
    for m in RHYTHM_METRICS:
        if m not in ck:
            continue
        wide = ck.pivot_table(index="date", columns="slot", values=m, aggfunc="mean")
        best = None
        for a, b in pairs:
            if a not in wide or b not in wide:
                continue
            both = wide[[a, b]].dropna()
            n = int(len(both))
            if n < MIN_PAIRED_DAYS:
                continue
            diff = both[a] - both[b]
            if abs(float(diff.mean())) < MIN_DIFF or (diff == 0).all():
                continue
            p = float(stats.wilcoxon(both[a], both[b], zero_method="zsplit").pvalue)
            p_adj = min(1.0, p * n_tests)
            if p_adj > MAX_P:
                continue
            hi, lo = (a, b) if diff.mean() > 0 else (b, a)
            cand = {
                "metric": m,
                "high_slot": hi,
                "low_slot": lo,
                "mean_high": round(float(both[hi].mean()), 1),
                "mean_low": round(float(both[lo].mean()), 1),
                "n": n,
                "p": p,
                "p_adj": p_adj,
                "diff": round(abs(float(diff.mean())), 2),
            }
            if best is None or cand["diff"] * np.sqrt(n) > best["diff"] * np.sqrt(best["n"]):
                best = cand
        if best:
            best["text"] = (
                f"Your {best['metric']} is usually higher in the {best['high_slot']} than in "
                f"the {best['low_slot']} ({best['mean_high']:g} vs {best['mean_low']:g}, "
                f"on {best['n']} days you checked in at both)."
            )
            best["confidence"] = round(min(1.0, best["n"] / 20) * min(1.0, best["diff"] / 1.0), 2)
            found.append(best)
    return sorted(found, key=lambda x: x["diff"] * np.sqrt(x["n"]), reverse=True)
