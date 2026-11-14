"""Evaluation against planted ground truth (plan: "Testing, evaluation and demo plan").

Runs entirely in memory on freshly generated synthetic users (no database), using the
exact same feature, pattern, prediction and trait code as production.

Metrics
- Pattern recall: share of planted patterns found in the user's top-5 insights (same
  feature, target, lag and direction). Plan target >= 80%. Planted patterns whose target is
  stress are reported separately: the plan's insight targets are mood, energy, focus and
  completion rate; stress links surface through the "stress triggers" trait instead.
- False insights: insights found for pure-noise users. Plan target 0-1.
- Learning curve: MAE of the twin vs the "7-day mean" baseline after 14..60 days of data.
- Task completion: AUC of the completion model on later days.
- Traits: chronotype vs truth, optimism-bias error.

CLI:  python -m app.ml.evaluate                 (4 personas + 30 users + 10 noise users)
      python -m app.ml.evaluate --quick         (what CI runs)
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml import patterns as pat
from app.ml import predict as P
from app.ml.features import build_features
from app.ml.traits import compute_traits
from app.seed.archetypes import ARCHETYPES
from app.seed.synthetic_users import Generated, persona_spec, random_spec, simulate

END = date(2026, 11, 14)
IN_SCOPE = set(pat.TARGETS)


@dataclass
class User:
    name: str
    gen: Generated
    noise: bool = False

    @property
    def categories(self) -> list[str]:
        return [c.name for c in self.gen.archetype.cats]


def features(gen: Generated, until: date | None = None) -> pd.DataFrame:
    ck = pd.DataFrame(gen.checkins)[["date", "sleep_hours", "mood", "energy", "stress", "focus"]]
    ac = pd.DataFrame(gen.activities)
    ms = pd.DataFrame(
        [{"date": m["created_at"].date(), "sentiment": m["sentiment"]} for m in gen.messages],
        columns=["date", "sentiment"],
    )
    if until:
        ck, ac, ms = ck[ck["date"] <= until], ac[ac["date"] <= until], ms[ms["date"] <= until]
    return build_features(ck, ac, ms, [c.name for c in gen.archetype.cats])


def make_users(n_generated: int = 30, n_noise: int = 10, days: int = 90) -> list[User]:
    users = []
    for k in ("student", "developer", "founder", "noise"):
        a, p, noise, s = persona_spec(k)
        users.append(User(k, simulate(a, p, days=days, end=END, seed=s, noise=noise), noise))
    for i in range(n_generated):
        a, p, s, sd = random_spec(i)
        users.append(
            User(
                f"user{i + 1:02d}.{a.key}", simulate(a, p, days=days, end=END, seed=s, noise_sd=sd)
            )
        )
    for i in range(n_noise):
        a = ARCHETYPES["generalist"]
        users.append(
            User(
                f"noise{i + 1:02d}",
                simulate(a, [], days=days, end=END, seed=9100 + i, noise=True),
                True,
            )
        )
    return users


# --------------------------------------------------------------------------------------


def pattern_metrics(users: list[User], top_k: int = 5) -> dict:
    rows, false_counts = [], {}
    for u in users:
        found = pat.discover(features(u.gen), u.categories)
        if u.noise:
            false_counts[u.name] = len(found)
            continue
        top = [(p.feature, p.target, p.lag, p.direction) for p in found[:top_k]]
        for t in u.gen.truth()["patterns"]:
            rows.append(
                {
                    "user": u.name,
                    "pattern": t["id"],
                    "target": t["target"],
                    "in_scope": t["target"] in IN_SCOPE,
                    "found": (t["feature"], t["target"], t["lag"], t["direction"]) in top,
                }
            )
    df = pd.DataFrame(rows)
    scoped = df[df["in_scope"]]
    return {
        "recall_at_5": round(float(scoped["found"].mean()), 3) if len(scoped) else None,
        "planted_in_scope": int(len(scoped)),
        "planted_stress_target": int((~df["in_scope"]).sum()),
        "recall_by_pattern": scoped.groupby("pattern")["found"].mean().round(2).to_dict(),
        "false_insights": false_counts,
        "false_insights_max": max(false_counts.values()) if false_counts else None,
        "false_insights_mean": round(float(np.mean(list(false_counts.values()))), 2)
        if false_counts
        else None,
    }


def learning_curve(users: list[User], checkpoints=(14, 21, 30, 45, 60), horizon: int = 14) -> dict:
    """Train once with the first d days, then predict each of the next `horizon` days from
    the evening before (plan-able inputs = typical values, exactly as in production)."""
    out = {}
    for d in checkpoints:
        twin, base = [], []
        for u in users:
            if u.noise:
                continue
            start = min(c["date"] for c in u.gen.checkins)
            cutoff = start + timedelta(days=d - 1)
            f_train = features(u.gen, until=cutoff)
            f_all = features(u.gen)
            idx = pd.to_datetime(pd.Index(f_all.index))
            for target in P.REG_TARGETS:
                t = P.train_regression(f_train, target)
                for k in range(1, horizon + 1):
                    day = cutoff + timedelta(days=k)
                    past = f_all[idx < pd.Timestamp(day)]
                    truth = f_all[idx == pd.Timestamp(day)]
                    if (
                        truth.empty
                        or int(truth["imputed"].iloc[0])
                        or pd.isna(truth[target].iloc[0])
                    ):
                        continue
                    plan, _ = P.assumed_plan(past, day)
                    pred = P.predict_value(t, P.tonight_row(past, plan, t.features))
                    actual = float(truth[target].iloc[0])
                    twin.append(abs(pred - actual))
                    base.append(abs(float(past[target].dropna().tail(7).mean()) - actual))
        out[d] = {
            "twin_mae": round(float(np.mean(twin)), 3),
            "baseline_mae": round(float(np.mean(base)), 3),
            "n": len(twin),
        }
    return out


def task_metrics(users: list[User], train_days: int = 60) -> dict:
    from sklearn.metrics import roc_auc_score

    ps, ys, kinds = [], [], []
    for u in users:
        if u.noise:
            continue
        start = min(c["date"] for c in u.gen.checkins)
        cutoff = start + timedelta(days=train_days)
        acts = pd.DataFrame(u.gen.activities)
        f_all = features(u.gen)
        t = P.train_tasks(
            acts[acts["date"] < cutoff],
            features(u.gen, until=cutoff - timedelta(days=1)),
            u.categories,
            cutoff,
        )
        kinds.append(t.kind)
        test = P._task_frame(
            acts[acts["date"] >= cutoff], f_all, [P._slug(c) for c in u.categories]
        )
        if test.empty:
            continue
        for _, r in test.iterrows():
            row = pd.DataFrame([r]).reindex(columns=t.features)
            ps.append(P.predict_task(t, row))
            ys.append(int(r["_label"]))
    auc = roc_auc_score(ys, ps) if len(set(ys)) > 1 else None
    return {
        "auc": round(float(auc), 3) if auc else None,
        "n_tasks": len(ys),
        "models": pd.Series(kinds).value_counts().to_dict(),
    }


def trait_metrics(users: list[User]) -> dict:
    hits, opt_err = [], []
    for u in users:
        if u.noise:
            continue
        tr = compute_traits(features(u.gen), pd.DataFrame(u.gen.activities), u.categories, {}, 90)
        truth = u.gen.truth()["traits"]
        if "chronotype" in tr and tr["chronotype"].get("source") == "data":
            hits.append(tr["chronotype"]["label"] == truth["chronotype"])
        if "optimism_bias" in tr and tr["optimism_bias"].get("source") == "data":
            opt_err.append(abs(tr["optimism_bias"]["value"] - truth["optimism_ratio"]))
    return {
        "chronotype_accuracy": round(float(np.mean(hits)), 3) if hits else None,
        "optimism_abs_error": round(float(np.mean(opt_err)), 3) if opt_err else None,
    }


def run(n_generated: int = 30, n_noise: int = 10, quick: bool = False) -> dict:
    t0 = time.perf_counter()
    users = make_users(n_generated, n_noise)
    curve_users = users if not quick else [u for u in users if not u.noise][:6]
    result = {
        "users": {"total": len(users), "noise": sum(u.noise for u in users)},
        "patterns": pattern_metrics(users),
        "learning_curve": learning_curve(
            curve_users, checkpoints=(14, 30, 60) if quick else (14, 21, 30, 45, 60)
        ),
        "tasks": task_metrics(users if not quick else curve_users),
        "traits": trait_metrics(users),
    }
    result["seconds"] = round(time.perf_counter() - t0, 1)
    return result


def main() -> None:
    import warnings

    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller run (CI)")
    ap.add_argument("--generated", type=int, default=30)
    ap.add_argument("--noise", type=int, default=10)
    args = ap.parse_args()
    r = run(
        args.generated if not args.quick else 9,
        args.noise if not args.quick else 3,
        quick=args.quick,
    )
    from app.core.config import BACKEND_DIR

    out = BACKEND_DIR / "data" / "evaluation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    p = r["patterns"]
    print(
        f"\nPattern recall@5: {p['recall_at_5']:.0%} of {p['planted_in_scope']} planted "
        f"(+{p['planted_stress_target']} stress-target patterns, see traits)"
    )
    print(
        f"False insights on noise users: max {p['false_insights_max']}, "
        f"mean {p['false_insights_mean']}"
    )
    print("Learning curve (MAE, lower is better):")
    for d, v in r["learning_curve"].items():
        better = (1 - v["twin_mae"] / v["baseline_mae"]) * 100
        print(
            f"  {d:>3} days: twin {v['twin_mae']:.3f} vs 7-day mean {v['baseline_mae']:.3f} "
            f"({better:+.0f}%), n={v['n']}"
        )
    print(
        f"Task completion AUC: {r['tasks']['auc']} on {r['tasks']['n_tasks']} tasks "
        f"(models: {r['tasks']['models']})"
    )
    print(
        f"Traits: chronotype {r['traits']['chronotype_accuracy']:.0%} correct, "
        f"optimism error {r['traits']['optimism_abs_error']}"
    )
    print(f"({r['seconds']}s) -> {out}")


if __name__ == "__main__":
    main()
