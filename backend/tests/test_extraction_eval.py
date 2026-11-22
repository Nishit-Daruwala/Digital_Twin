"""The extraction benchmark: labels are well-formed and the scorer counts facts correctly."""

import json
from datetime import date

from app.ml import extraction_eval as E
from app.services.llm import FakeProvider


def test_cases_are_well_formed():
    data = json.loads(E.CASES.read_text(encoding="utf-8"))
    assert len(data["cases"]) == 50
    assert len({c["id"] for c in data["cases"]}) == 50
    for c in data["cases"]:
        cats = data["category_sets"][c["set"]]
        for a in c["expected"].get("activities", []):
            assert a["category"] in cats, (c["id"], a)
        for k in ("mood", "energy", "stress", "focus"):
            assert c["expected"].get(k) in (None, 1, 2, 3, 4, 5), c["id"]


def test_scorer():
    exp = {
        "mood": 3,
        "sleep_hours": 7,
        "activities": [{"category": "Study", "duration_min": 120, "planned": False}],
        "decisions": 1,
    }
    got = {
        "mood": 3,
        "sleep_hours": 7.25,
        "energy": 4,
        "activities": [
            {"category": "Study", "duration_min": 110, "planned": False},
            {"category": "Social", "duration_min": 30, "planned": False},
        ],
        "decisions": 0,
    }
    c = E.score_case(exp, got)
    assert c["mood:tp"] == c["sleep_hours:tp"] == c["activity:tp"] == 1
    assert c["energy:fp"] == 1 and c["activity:fp"] == 1 and c["decision:fn"] == 1


def test_runs_offline_with_the_fake_provider():
    r = E.run(FakeProvider())
    assert r["cases"] == 50 and r["overall"]["n"] >= 80
    assert r["overall"]["precision"] >= 0.8  # the regex stand-in rarely invents facts
    assert date.fromisoformat("2026-11-18")  # the benchmark's fixed "today"
