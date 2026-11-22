"""Extraction accuracy (plan: "precision and recall on 50 hand-labelled chat messages").

Every labelled fact is one unit: a stated score (exact), sleep hours (within 15 min), the
part of the day, "yesterday", each activity (same category and planned/done; duration
within 15% or 10 min) and each decision. The prediction is what the user would see on the
confirmation card (LLM output after validation), so it measures the real feature.

    python -m app.ml.extraction_eval                    # the configured LLM (OpenAI)
    python -m app.ml.extraction_eval --provider fake    # the offline regex stand-in
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from app.core.config import BACKEND_DIR
from app.schemas.chat import ExtractionCard
from app.services.extraction import sanitize

CASES = BACKEND_DIR / "evals" / "extraction_cases.json"
SCORES = ("mood", "energy", "stress", "focus")


def facts_of_card(card: ExtractionCard, today: date) -> dict:
    c = card.checkin
    out = {k: getattr(c, k) for k in SCORES if getattr(c, k) is not None}
    if c.sleep_hours is not None:
        out["sleep_hours"] = c.sleep_hours
    if c.slot:
        out["part_of_day"] = c.slot
    if card.date < today:
        out["day"] = "yesterday"
    out["activities"] = [
        {"category": a.category, "duration_min": a.duration_min, "planned": a.planned}
        for a in card.activities
    ]
    out["decisions"] = len(card.decisions)
    return out


def _same_duration(a, b) -> bool:
    if a is None or b is None:
        return a == b
    return abs(a - b) <= max(10, 0.15 * b)


def score_case(expected: dict, got: dict) -> Counter:
    """Counter of tp/fp/fn per field."""
    c: Counter = Counter()
    for k in (*SCORES, "sleep_hours", "part_of_day", "day"):
        e, g = expected.get(k), got.get(k)
        if e is None and g is None:
            continue
        ok = (
            e is not None
            and g is not None
            and (abs(e - g) <= 0.25 if k == "sleep_hours" else e == g)
        )
        if ok:
            c[f"{k}:tp"] += 1
        else:
            if g is not None:
                c[f"{k}:fp"] += 1
            if e is not None:
                c[f"{k}:fn"] += 1
    left = list(got.get("activities", []))
    for e in expected.get("activities", []):
        match = next(
            (
                a
                for a in left
                if a["category"] == e["category"]
                and a["planned"] == e["planned"]
                and _same_duration(a["duration_min"], e["duration_min"])
            ),
            None,
        )
        if match:
            left.remove(match)
            c["activity:tp"] += 1
        else:
            c["activity:fn"] += 1
    c["activity:fp"] += len(left)
    e_dec, g_dec = expected.get("decisions", 0), got.get("decisions", 0)
    c["decision:tp"] += min(e_dec, g_dec)
    c["decision:fp"] += max(0, g_dec - e_dec)
    c["decision:fn"] += max(0, e_dec - g_dec)
    return c


def _pr(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {
        "precision": None if p is None else round(p, 3),
        "recall": None if r is None else round(r, 3),
        "n": tp + fn,
    }


def run(provider=None) -> dict:
    data = json.loads(Path(CASES).read_text(encoding="utf-8"))
    today = date.fromisoformat(data["today"])
    llm = provider
    if llm is None:
        from app.services.llm import get_llm

        llm = get_llm()
    total: Counter = Counter()
    misses = []
    for case in data["cases"]:
        cats = data["category_sets"][case["set"]]
        raw = llm.extract(case["message"], cats, today)
        card = sanitize(
            raw,
            categories=cats,
            today=today,
            consents=dict.fromkeys(("checkin", "activities", "decisions", "chat"), True),
        ).card
        got = facts_of_card(card, today)
        c = score_case(case["expected"], got)
        total += c
        if any(v > 0 for k, v in c.items() if k.endswith((":fp", ":fn"))):
            misses.append(
                {
                    "id": case["id"],
                    "message": case["message"],
                    "expected": case["expected"],
                    "got": got,
                }
            )
    fields = sorted({k.split(":")[0] for k in total})
    per_field = {f: _pr(total[f"{f}:tp"], total[f"{f}:fp"], total[f"{f}:fn"]) for f in fields}
    tp = sum(v for k, v in total.items() if k.endswith(":tp"))
    fp = sum(v for k, v in total.items() if k.endswith(":fp"))
    fn = sum(v for k, v in total.items() if k.endswith(":fn"))
    return {
        "cases": len(data["cases"]),
        "overall": _pr(tp, fp, fn),
        "per_field": per_field,
        "misses": misses,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--provider", choices=["configured", "fake"], default="configured")
    args = ap.parse_args()
    provider = None
    if args.provider == "fake":
        from app.services.llm import FakeProvider

        provider = FakeProvider()
    r = run(provider)
    out = BACKEND_DIR / "data" / f"extraction_eval_{args.provider}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    o = r["overall"]
    print(
        f"Extraction on {r['cases']} messages: precision {o['precision']:.0%}, "
        f"recall {o['recall']:.0%} ({o['n']} facts)"
    )
    for f, v in r["per_field"].items():
        p = "–" if v["precision"] is None else f"{v['precision']:.0%}"
        rc = "–" if v["recall"] is None else f"{v['recall']:.0%}"
        print(f"  {f:<12} precision {p:>5}  recall {rc:>5}  (n={v['n']})")
    print(f"{len(r['misses'])} messages with at least one miss -> {out}")


if __name__ == "__main__":
    main()
