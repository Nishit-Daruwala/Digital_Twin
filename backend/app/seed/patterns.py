"""Planted patterns: hidden rules baked into synthetic data that the twin must rediscover.

Each pattern adds a delta to today's latent mood/energy/stress/focus based on today's or
earlier days' drivers. Its `truth` says which feature column (as built by ml/features.py)
should correlate with which target, at which lag, in which direction.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.seed.archetypes import Archetype

Day = dict  # simulated day state (drivers + latent metrics)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def short_sleep_share(a: Archetype) -> float:
    """Expected share of nights under 6h (normal approximation)."""
    return 0.5 * (1 + math.erf((6 - a.sleep_mean) / (a.sleep_sd * math.sqrt(2))))


def _clip(x: float, lim: float = 1.2) -> float:
    return max(-lim, min(lim, x))


@dataclass(frozen=True)
class Pattern:
    id: str
    description: str
    feature: str  # feature column, or "kind:<kind>" -> min_<slug of that category>
    target: str  # mood / energy / stress / focus
    lag: int  # 0 = same day, 1 = next day, 2 = two days later
    direction: int  # +1 or -1 (sign of the correlation)
    apply: Callable[[list[Day], Day, Archetype], dict]
    requires: tuple[str, ...] = ()  # category kinds the archetype must have
    needs_late: bool = False
    needs_short_sleep: bool = False  # only meaningful if the person sometimes sleeps < 6h

    def compatible(self, a: Archetype) -> bool:
        if self.needs_late and a.late_prob < 0.2:
            return False
        if self.needs_short_sleep and short_sleep_share(a) < 0.2:
            return False
        return all(a.cat_of_kind(k) for k in self.requires)

    def truth(self, a: Archetype) -> dict:
        feat = self.feature
        if feat.startswith("kind:"):
            feat = "min_" + slug(a.cat_of_kind(feat[5:]).name)
        return {
            "id": self.id,
            "description": self.description,
            "feature": feat,
            "target": self.target,
            "lag": self.lag,
            "direction": "+" if self.direction > 0 else "-",
        }


def _prev(h: list[Day], n: int = 1) -> Day | None:
    return h[-n] if len(h) >= n else None


def _p_sleep_low_next_focus(h, d, a):
    p = _prev(h)
    return {"focus": -1.2} if p and p["sleep"] < 6 else {}


def _p_sleep_mood(h, d, a):
    return {"mood": _clip(0.55 * (d["sleep"] - a.sleep_mean))}


def _p_meetings_energy(h, d, a):
    return {"energy": -1.0} if d["meetings"] >= 3 else {}


def _p_exercise_next_mood(h, d, a):
    p = _prev(h)
    return {"mood": 0.8} if p and p["kind_min"].get("exercise", 0) > 0 else {}


def _p_stress_leads_mood(h, d, a):
    p2 = _prev(h, 2)
    return {"mood": _clip(-0.7 * (p2["stress"] - a.base["stress"]))} if p2 else {}


def _p_monday_mood(h, d, a):
    return {"mood": -1.0} if d["weekday"] == 0 else {}


def _p_deep_focus(h, d, a):
    mean = a.expected_minutes("deep") / 60
    return {"focus": _clip(0.55 * (d["kind_min"].get("deep", 0) / 60 - mean))}


def _p_late_next_energy(h, d, a):
    p = _prev(h)
    return {"energy": -1.0} if p and p["last_hour"] is not None and p["last_hour"] >= 23 else {}


def _p_weekend_mood(h, d, a):
    return {"mood": 0.9} if d["weekday"] >= 5 else {}


def _p_workload_stress(h, d, a):
    mean = sum(a.expected_minutes(c.kind) for c in a.cats) / 60
    return {"stress": _clip(0.45 * (d["active_min"] / 60 - mean))}


def _p_social_next_energy(h, d, a):
    p = _prev(h)
    return {"energy": 0.8} if p and p["kind_min"].get("social", 0) > 0 else {}


def _p_sleep_low_next_stress(h, d, a):
    p = _prev(h)
    return {"stress": 1.0} if p and p["sleep"] < 6 else {}


def _p_exercise_energy(h, d, a):
    return {"energy": 0.8} if d["kind_min"].get("exercise", 0) > 0 else {}


def _p_leisure_stress(h, d, a):
    mean = a.expected_minutes("leisure") / 60
    return {"stress": _clip(-0.6 * (d["kind_min"].get("leisure", 0) / 60 - mean))}


def _p_stress_next_focus(h, d, a):
    p = _prev(h)
    return {"focus": _clip(-0.7 * (p["stress"] - a.base["stress"]))} if p else {}


PATTERNS: dict[str, Pattern] = {
    p.id: p
    for p in [
        Pattern(
            "sleep_low_next_focus",
            "Under 6h sleep -> next-day focus -1.2",
            "sleep_hours",
            "focus",
            1,
            +1,
            _p_sleep_low_next_focus,
            needs_short_sleep=True,
        ),
        Pattern(
            "sleep_mood",
            "More sleep -> better mood the same day",
            "sleep_hours",
            "mood",
            0,
            +1,
            _p_sleep_mood,
        ),
        Pattern(
            "meetings_energy",
            "3+ meetings -> same-day energy -1",
            "kind:meetings",
            "energy",
            0,
            -1,
            _p_meetings_energy,
            ("meetings",),
        ),
        Pattern(
            "exercise_next_mood",
            "Exercise day -> next-day mood +0.8",
            "kind:exercise",
            "mood",
            1,
            +1,
            _p_exercise_next_mood,
            ("exercise",),
        ),
        Pattern(
            "stress_leads_mood",
            "Stress rises 2 days before mood drops",
            "stress",
            "mood",
            2,
            -1,
            _p_stress_leads_mood,
        ),
        Pattern("monday_mood", "Mondays -> low mood", "is_monday", "mood", 0, -1, _p_monday_mood),
        Pattern(
            "deep_focus",
            "More deep-work minutes -> higher focus",
            "kind:deep",
            "focus",
            0,
            +1,
            _p_deep_focus,
            ("deep",),
        ),
        Pattern(
            "late_next_energy",
            "Activity after 23:00 -> next-day energy -1",
            "last_hour",
            "energy",
            1,
            -1,
            _p_late_next_energy,
            needs_late=True,
        ),
        Pattern(
            "weekend_mood", "Weekends -> mood +0.9", "is_weekend", "mood", 0, +1, _p_weekend_mood
        ),
        Pattern(
            "workload_stress",
            "More active minutes -> more stress",
            "active_min",
            "stress",
            0,
            +1,
            _p_workload_stress,
        ),
        Pattern(
            "social_next_energy",
            "Social time -> next-day energy +0.8",
            "kind:social",
            "energy",
            1,
            +1,
            _p_social_next_energy,
            ("social",),
        ),
        Pattern(
            "sleep_low_next_stress",
            "Under 6h sleep -> next-day stress +1",
            "sleep_hours",
            "stress",
            1,
            -1,
            _p_sleep_low_next_stress,
            needs_short_sleep=True,
        ),
        Pattern(
            "exercise_energy",
            "Exercise -> same-day energy +0.8",
            "kind:exercise",
            "energy",
            0,
            +1,
            _p_exercise_energy,
            ("exercise",),
        ),
        Pattern(
            "leisure_stress",
            "More leisure -> lower stress",
            "kind:leisure",
            "stress",
            0,
            -1,
            _p_leisure_stress,
            ("leisure",),
        ),
        Pattern(
            "stress_next_focus",
            "High stress -> lower focus next day",
            "stress",
            "focus",
            1,
            -1,
            _p_stress_next_focus,
        ),
    ]
}

# Relationships that exist by construction (not planted insights). Phase 3 evaluation
# should not count these as false discoveries.
STRUCTURAL = [
    {
        "feature": "sentiment_mean",
        "target": "mood",
        "lag": 0,
        "why": "chat sentiment is generated from mood",
    },
    {
        "feature": "focus",
        "target": "completion_rate",
        "lag": 0,
        "why": "task completion probability depends on focus",
    },
]
