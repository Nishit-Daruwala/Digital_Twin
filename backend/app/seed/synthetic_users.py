"""Synthetic users with planted patterns, for demos and for evaluating the twin.

Usage (from backend/):
    python -m app.seed.synthetic_users                 # 4 plan personas + 30 generated users
    python -m app.seed.synthetic_users --generated 50 --days 120
    python -m app.seed.synthetic_users --no-embed       # skip message embeddings (faster)

Every user's ground truth (planted patterns + true traits) is stored in
twin_profiles.onboarding["synthetic"] and written to backend/data/ground_truth.json.
Generation is deterministic: the same seed gives the same data.
"""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta

import numpy as np
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR
from app.core.security import hash_password
from app.ml.traits import quiz_prior
from app.models import (
    CONSENT_SOURCES,
    Activity,
    Checkin,
    Consent,
    Decision,
    Insight,
    Message,
    Prediction,
    Recommendation,
    TwinProfile,
    User,
)
from app.schemas.profile import QuizAnswers
from app.seed.archetypes import ARCHETYPES, FIRST_NAMES, GENERATABLE, LAST_INITIALS, Archetype
from app.seed.patterns import PATTERNS, STRUCTURAL, Pattern

log = logging.getLogger("twin.seed")

DEMO_DOMAIN = "demo.example.com"
# Day-to-day stress swings more than mood/focus; this also lets stress-driven patterns show.
STRESS_VOLATILITY = 1.3
DEMO_PASSWORD = "twin-demo-2026"

# The plan's personas (fixed patterns) plus the pure-noise control. Each demo seed is a
# typical draw where the planted patterns are clearly visible (90-day correlations vary by
# about +-0.1 between seeds); tests/test_seed.py also checks the average over many seeds.
PERSONAS: dict[str, dict] = {
    "student": {
        "archetype": "student",
        "name": "Asha (student)",
        "seed": 1001,
        "patterns": ["sleep_low_next_focus"],
    },
    "developer": {
        "archetype": "developer",
        "name": "Mateo (developer)",
        "seed": 1002,
        "patterns": ["meetings_energy", "monday_mood"],
    },
    "founder": {
        "archetype": "founder",
        "name": "Lin (founder)",
        "seed": 1403,
        "patterns": ["stress_leads_mood", "exercise_next_mood"],
    },
    "noise": {
        "archetype": "generalist",
        "name": "Kwame (control)",
        "seed": 1004,
        "patterns": [],
        "noise": True,
    },
}


@dataclass
class Generated:
    archetype: Archetype
    patterns: list[Pattern]
    noise: bool
    seed: int
    checkins: list[dict] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    tomorrow: list[dict] = field(default_factory=list)  # planned tasks, not history

    def truth(self) -> dict:
        a = self.archetype
        return {
            "archetype": a.key,
            "seed": self.seed,
            "noise_control": self.noise,
            "patterns": [p.truth(a) for p in self.patterns],
            "structural": [] if self.noise else STRUCTURAL,
            "traits": {
                "chronotype": chronotype(a.peak_hour),
                "peak_hour": round(a.peak_hour, 1),
                "optimism_ratio": round(a.optimism, 3),
                "planner_share": round(a.planner_share, 2),
            },
            "days": len({c["date"] for c in self.checkins}),
        }


def chronotype(peak_hour: float) -> str:
    if peak_hour < 13:
        return "morning person"
    if peak_hour > 18:
        return "night owl"
    return "balanced"


# --------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------

LOW = [
    "Rough day, honestly. {cat} took everything out of me.",
    "Feeling pretty drained after {cat}.",
    "Not a great day. Slept {sleep}h and it showed.",
    "Stressed and tired, couldn't focus on {cat}.",
]
MID = [
    "Okay day. Spent a while on {cat}.",
    "Pretty average day, did some {cat}.",
    "Fine overall, {cat} went alright.",
    "Normal day, {cat} in the afternoon, nothing special.",
]
HIGH = [
    "Great day! {cat} went really well.",
    "Feeling good, had a productive {cat} session.",
    "Really enjoyed {cat} today, energy was high.",
    "Slept {sleep}h and felt sharp all day.",
]
DECISIONS = [
    ("Skip {cat} to rest tonight?", ["Rest", "Push through"]),
    ("Take on an extra commitment this week?", ["Yes", "No"]),
    ("Move {cat} to the morning?", ["Morning", "Keep as is"]),
    ("Sign up for a weekend course?", ["Sign up", "Wait"]),
    ("Cut back on {cat} for a while?", ["Cut back", "Keep going"]),
]


def _hour_to_time(h: float) -> time:
    h = max(0.0, min(23.99, h))
    minutes = int(round(h * 60 / 5) * 5)
    minutes = min(minutes, 23 * 60 + 55)
    return time(minutes // 60, minutes % 60)


def _round5(x: float) -> int:
    return int(max(5, round(x / 5) * 5))


def simulate(
    arch: Archetype,
    patterns: list[Pattern],
    *,
    days: int,
    end: date,
    seed: int,
    noise: bool = False,
    noise_sd: float = 0.45,
    skip_p: float = 0.06,
) -> Generated:
    rng = np.random.default_rng(seed)
    gen = Generated(arch, patterns, noise, seed)
    start = end - timedelta(days=days - 1)
    history: list[dict] = []
    late_cat = arch.cat_of_kind("deep") or arch.cat_of_kind("leisure") or arch.cats[0]

    for i in range(days):
        d = start + timedelta(days=i)
        weekend = d.weekday() >= 5
        sleep = float(np.clip(rng.normal(arch.sleep_mean, arch.sleep_sd), 3.5, 10.5))
        sleep = round(sleep * 4) / 4

        # ---- schedule sessions ----
        sessions: list[dict] = []  # {cat, start_h, dur, task}
        meetings = 0
        for c in arch.cats:
            if rng.random() >= (c.p_weekend if weekend else c.p_weekday):
                continue
            if c.kind == "meetings":
                meetings = int(min(6, rng.poisson(2.2)))
                for _ in range(meetings):
                    sessions.append(
                        {
                            "cat": c,
                            "start": rng.uniform(*c.hours),
                            "dur": float(rng.choice([30, 45, 60])),
                            "task": False,
                        }
                    )
                continue
            total = max(15.0, rng.normal(c.mean_min, 0.3 * c.mean_min))
            n = max(1, int(round(total / c.session)))
            h = rng.uniform(*c.hours)
            for _ in range(n):
                dur = float(_round5(total / n))
                sessions.append({"cat": c, "start": h, "dur": dur, "task": c.task})
                h += dur / 60 + rng.uniform(0, 0.5)
        if rng.random() < arch.late_prob:
            sessions.append(
                {
                    "cat": late_cat,
                    "start": rng.uniform(22.5, 23.4),
                    "dur": float(rng.choice([30, 45, 60])),
                    "task": False,
                }
            )

        kind_min: dict[str, float] = {}
        for s in sessions:
            kind_min[s["cat"].kind] = kind_min.get(s["cat"].kind, 0) + s["dur"]
        active = sum(s["dur"] for s in sessions)
        last_hour = max((min(23.99, s["start"] + s["dur"] / 60) for s in sessions), default=None)

        day = {
            "date": d,
            "weekday": d.weekday(),
            "sleep": sleep,
            "meetings": meetings,
            "kind_min": kind_min,
            "active_min": active,
            "last_hour": last_hour,
        }

        # ---- latent metrics: base + planted effects + noise ----
        latent = {}
        deltas: dict[str, float] = {}
        for p in patterns:
            for k, v in p.apply(history, day, arch).items():
                deltas[k] = deltas.get(k, 0.0) + v
        for m in ("mood", "energy", "stress", "focus"):
            latent[m] = (
                arch.base[m]
                + deltas.get(m, 0.0)
                + rng.normal(0, noise_sd * (STRESS_VOLATILITY if m == "stress" else 1.0))
            )
        day.update(latent)
        history.append(day)

        recorded = rng.random() >= skip_p
        if not recorded:
            continue

        scores = {m: int(np.clip(round(latent[m]), 1, 5)) for m in latent}
        gen.checkins.append(
            {
                "date": d,
                **scores,
                "sleep_hours": None if rng.random() < 0.03 else sleep,
                "note": None,
                "source": "manual",
            }
        )

        # ---- activities ----
        # Completion of a planned task depends on the day's focus, and (knowable in advance)
        # on the task's length and whether it sits near the person's peak hours.
        # No extra random draws here, so all other generated values stay identical.
        p_focus = 0.55 + 0.12 * (latent["focus"] - 3)
        n_tasks = sum(1 for s in sessions if s["task"])  # an overloaded plan gets done less
        for s in sorted(sessions, key=lambda s: s["start"]):
            c = s["cat"]
            planned = bool(s["task"] and rng.random() < arch.planner_share)
            p_task = (
                p_focus
                + 0.15
                - 0.25 * (s["dur"] / 60 - 1)  # longer tasks
                - 0.08 * max(0, n_tasks - 2)  # busy days
                - 0.06 * abs(s["start"] - arch.peak_hour)  # far from peak hours
            )
            p_done = 0.75 if noise else float(np.clip(p_task, 0.08, 0.95))
            completed = (rng.random() < p_done) if planned else True
            planned_min = (
                _round5(s["dur"] * arch.optimism * rng.normal(1, 0.08)) if planned else None
            )
            gen.activities.append(
                {
                    "date": d,
                    "category": c.name,
                    "title": c.name,
                    "start_time": _hour_to_time(s["start"]),
                    "duration_min": int(s["dur"]) if completed else None,
                    "planned": planned,
                    "completed": completed,
                    "planned_min": planned_min,
                    "source": "manual",
                }
            )

        # ---- chat messages ----
        done_cats = [s["cat"].name for s in sessions] or [arch.cats[0].name]
        for _ in range(int(min(3, rng.poisson(arch.msg_rate)))):
            mood = scores["mood"]
            pool = LOW if mood <= 2 else HIGH if mood >= 4 else MID
            text = pool[int(rng.integers(len(pool)))].format(
                cat=str(rng.choice(done_cats)).lower(), sleep=f"{sleep:g}"
            )
            sentiment = (
                float(rng.uniform(-1, 1))
                if noise
                else float(np.clip((mood - 3) / 2 + rng.normal(0, 0.15), -1, 1))
            )
            ts = datetime.combine(d, _hour_to_time(rng.uniform(19, 23)), tzinfo=UTC)
            gen.messages.append(
                {
                    "role": "user",
                    "text": text,
                    "sentiment": round(sentiment, 3),
                    "topics": [],
                    "learnable": True,
                    "created_at": ts,
                }
            )

        # ---- occasional decisions ----
        if rng.random() < 0.06:
            q, opts = DECISIONS[int(rng.integers(len(DECISIONS)))]
            cat = str(rng.choice(done_cats)).lower()
            gen.decisions.append(
                {
                    "text": q.format(cat=cat),
                    "options": opts,
                    "choice": str(rng.choice(opts)),
                    "reasoning": None,
                    "outcome_rating": int(rng.integers(1, 6))
                    if d < end - timedelta(days=7)
                    else None,
                    "source": "manual",
                    "created_at": datetime.combine(d, time(20, 0), tzinfo=UTC),
                }
            )
    # A few tasks planned for tomorrow, so the twin has something to predict. Separate rng
    # stream: the history above is unchanged by this.
    trng = np.random.default_rng(seed + 99_999)
    task_cats = [c for c in arch.cats if c.task]
    for c in task_cats[: int(trng.integers(1, 3)) + 1]:
        dur = float(_round5(trng.normal(c.session, 0.2 * c.session)))
        gen.tomorrow.append(
            {
                "date": end + timedelta(days=1),
                "category": c.name,
                "title": f"{c.name} session",
                "start_time": _hour_to_time(trng.uniform(*c.hours)),
                "duration_min": None,
                "planned": True,
                "completed": False,
                "planned_min": _round5(dur * arch.optimism),
                "source": "manual",
            }
        )
    return gen


# --------------------------------------------------------------------------------------
# Users, profiles, persistence
# --------------------------------------------------------------------------------------


def quiz_for(a: Archetype, noise_sd: float) -> QuizAnswers:
    best = (
        "morning"
        if a.peak_hour < 12
        else "afternoon"
        if a.peak_hour < 17
        else "evening"
        if a.peak_hour < 21
        else "night"
    )
    bias = (
        "faster"
        if a.optimism >= 1.05
        else "accurate"
        if a.optimism >= 0.92
        else "slower"
        if a.optimism >= 0.72
        else "much_slower"
    )
    return QuizAnswers(
        best_time=best,
        plans_ahead=int(np.clip(1 + round(4 * a.planner_share), 1, 5)),
        estimate_bias=bias,
        routine=int(np.clip(round(5 - (noise_sd - 0.35) * 10), 1, 5)),
        stress_source=a.stress_source,
    )


def persona_spec(key: str) -> tuple[Archetype, list[Pattern], bool, int]:
    p = PERSONAS[key]
    return (
        ARCHETYPES[p["archetype"]],
        [PATTERNS[x] for x in p["patterns"]],
        bool(p.get("noise")),
        p["seed"],
    )


def random_spec(index: int, base_seed: int = 5000) -> tuple[Archetype, list[Pattern], int, float]:
    """A varied person: archetype by index, jittered routine, 2-3 random compatible patterns."""
    seed = base_seed + index
    rng = np.random.default_rng(seed)
    base = ARCHETYPES[GENERATABLE[index % len(GENERATABLE)]]
    shift = float(rng.uniform(-1.5, 1.5))
    cats = tuple(
        replace(c, hours=(max(5.0, c.hours[0] + shift), min(23.5, c.hours[1] + shift)))
        if c.kind in ("deep", "work")
        else c
        for c in base.cats
    )
    arch = replace(
        base,
        cats=cats,
        sleep_mean=float(np.clip(base.sleep_mean + rng.uniform(-0.6, 0.6), 5.5, 8.5)),
        base={
            k: float(np.clip(v + rng.uniform(-0.3, 0.3), 2.4, 3.8)) for k, v in base.base.items()
        },
        peak_hour=float(np.clip(base.peak_hour + shift, 6, 23)),
        planner_share=float(np.clip(base.planner_share + rng.uniform(-0.15, 0.15), 0.1, 0.95)),
        optimism=float(np.clip(base.optimism * rng.uniform(0.85, 1.15), 0.5, 1.3)),
        late_prob=float(np.clip(base.late_prob + rng.uniform(-0.1, 0.1), 0.02, 0.5)),
        msg_rate=float(np.clip(base.msg_rate + rng.uniform(-0.3, 0.3), 0.4, 1.6)),
    )
    pool = [p for p in PATTERNS.values() if p.compatible(arch)]
    k = int(rng.integers(2, 4))
    chosen = [pool[i] for i in rng.choice(len(pool), size=min(k, len(pool)), replace=False)]
    return arch, chosen, seed, float(rng.uniform(0.4, 0.6))


def wipe_user_data(db: Session, user_id: uuid.UUID) -> None:
    for model in (Checkin, Activity, Decision, Message, Insight, Prediction, Recommendation):
        db.execute(delete(model).where(model.user_id == user_id))


def write_generated(
    db: Session, user: User, gen: Generated, *, embed: bool = True, noise_sd: float = 0.45
) -> dict:
    """Replace the user's data and profile with the generated history. Commits."""
    from app.services import embeddings

    wipe_user_data(db, user.id)
    a = gen.archetype
    quiz = quiz_for(a, noise_sd)
    user.role = a.role
    profile = db.get(TwinProfile, user.id)
    if profile is None:
        profile = TwinProfile(user_id=user.id)
        db.add(profile)
    profile.goals = list(a.goals)
    profile.categories = [c.name for c in a.cats]
    profile.onboarding = {"quiz": quiz.model_dump(), "synthetic": gen.truth()}
    profile.traits = quiz_prior(quiz)
    profile.data_days = len(gen.checkins)
    profile.accuracy_score = None

    uid = {"user_id": user.id}
    if gen.checkins:
        db.execute(insert(Checkin), [uid | c for c in gen.checkins])
    if gen.activities:
        db.execute(insert(Activity), [uid | x for x in gen.activities])
    if gen.tomorrow:
        db.execute(insert(Activity), [uid | x for x in gen.tomorrow])
    if gen.decisions:
        db.execute(insert(Decision), [uid | x for x in gen.decisions])
    if gen.messages:
        vectors: list = [None] * len(gen.messages)
        if embed:
            try:
                vectors = embeddings.embed([m["text"] for m in gen.messages])
            except embeddings.EmbeddingError as exc:
                log.warning("seeding without embeddings: %s", exc)
        db.execute(
            insert(Message),
            [uid | m | {"embedding": v} for m, v in zip(gen.messages, vectors, strict=True)],
        )
    db.commit()
    return {
        "checkins": len(gen.checkins),
        "activities": len(gen.activities),
        "messages": len(gen.messages),
        "decisions": len(gen.decisions),
        "planted_patterns": [p.id for p in gen.patterns],
    }


def seed_persona_into_user(
    db: Session, user: User, persona: str, days: int, *, embed: bool = True
) -> dict:
    """Used by POST /demo/seed: give the current account a persona's history."""
    arch, patterns, noise, seed = persona_spec(persona)
    gen = simulate(arch, patterns, days=days, end=date.today(), seed=seed, noise=noise)
    return write_generated(db, user, gen, embed=embed)


def _upsert_demo_user(db: Session, email: str, name: str) -> User:
    old = db.scalar(select(User).where(User.email == email))
    if old:
        db.delete(old)  # cascades to all their rows
        db.flush()
    user = User(email=email, name=name, password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    db.add_all(Consent(user_id=user.id, source=s, allowed=True) for s in CONSENT_SOURCES)
    return user


def _run_pipeline(user_id, backtest_days: int) -> str:
    from app.db import SessionLocal
    from app.ml.pipeline import run_user

    try:
        return run_user(SessionLocal, user_id, trigger="seed", backtest_days=backtest_days).status
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline failed for %s: %s", user_id, exc)
        return "error"


def create_demo_users(
    db: Session,
    *,
    generated: int = 30,
    days: int = 90,
    embed: bool = True,
    pipeline: bool = True,
) -> list[dict]:
    end = date.today()
    summary = []
    for key, p in PERSONAS.items():
        arch, patterns, noise, seed = persona_spec(key)
        user = _upsert_demo_user(db, f"{key}@{DEMO_DOMAIN}", p["name"])
        gen = simulate(arch, patterns, days=days, end=end, seed=seed, noise=noise)
        counts = write_generated(db, user, gen, embed=embed)
        if pipeline:
            counts["pipeline"] = _run_pipeline(user.id, backtest_days=14)
        summary.append(
            {"email": user.email, "name": user.name, "persona": key, "truth": gen.truth(), **counts}
        )
        log.info("seeded %s", user.email)
    for i in range(generated):
        arch, patterns, seed, noise_sd = random_spec(i)
        first = FIRST_NAMES[(i + 4) % len(FIRST_NAMES)]
        name = f"{first} {LAST_INITIALS[i % len(LAST_INITIALS)]}."
        email = f"user{i + 1:02d}.{arch.key}@{DEMO_DOMAIN}"
        user = _upsert_demo_user(db, email, name)
        gen = simulate(arch, patterns, days=days, end=end, seed=seed, noise_sd=noise_sd)
        counts = write_generated(db, user, gen, embed=embed, noise_sd=noise_sd)
        if pipeline:
            counts["pipeline"] = _run_pipeline(user.id, backtest_days=7)
        summary.append(
            {"email": email, "name": name, "persona": None, "truth": gen.truth(), **counts}
        )
        log.info("seeded %s (%s)", email, ", ".join(counts["planted_patterns"]))
    return summary


def main() -> None:
    from app.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--generated", type=int, default=30, help="number of varied users (default 30)")
    ap.add_argument("--days", type=int, default=90, help="days of history per user (default 90)")
    ap.add_argument("--no-embed", action="store_true", help="skip message embeddings")
    ap.add_argument(
        "--no-pipeline",
        action="store_true",
        help="don't run the twin pipeline after seeding (faster)",
    )
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with SessionLocal() as db:
        summary = create_demo_users(
            db,
            generated=args.generated,
            days=args.days,
            embed=not args.no_embed,
            pipeline=not args.no_pipeline,
        )
    out = BACKEND_DIR / "data" / "ground_truth.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nCreated {len(summary)} demo users (password: {DEMO_PASSWORD})")
    for s in summary[:4]:
        print(f"  {s['email']:<36} {s['name']}")
    print(f"  ...and {len(summary) - 4} more. Ground truth: {out}")


if __name__ == "__main__":
    main()
