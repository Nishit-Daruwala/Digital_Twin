from datetime import date, time, timedelta

import pandas as pd

from app.ml.traits import chronotype, compute_traits, quiz_prior
from app.schemas.profile import QuizAnswers

D0 = date(2026, 9, 1)
QUIZ = QuizAnswers(
    best_time="morning",
    plans_ahead=4,
    estimate_bias="accurate",
    routine=4,
    stress_source="workload",
)


def acts(hours: list[int], planned=True, ratio=0.6) -> pd.DataFrame:
    rows = []
    for i in range(30):
        for h in hours:
            rows.append(
                {
                    "date": D0 + timedelta(days=i),
                    "category": "Study",
                    "start_time": time(h, 0),
                    "duration_min": 100.0,
                    "planned": planned,
                    "completed": True,
                    "planned_min": 100.0 * ratio,
                }
            )
    return pd.DataFrame(rows)


def features(n=30, active=None):
    idx = [D0 + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {
            "active_min": active or [300.0] * n,
            "focus": [3.0] * n,
            "stress": [3.0] * n,
            "imputed": [0] * n,
        },
        index=idx,
    )


def test_chronotype_from_when_work_happens():
    assert chronotype(acts([21, 22]))[1] == "night owl"
    assert chronotype(acts([8, 9]))[1] == "morning person"
    assert chronotype(acts([14]))[1] == "balanced"


def test_quiz_prior_until_14_days_then_data():
    prior = quiz_prior(QUIZ)
    early = compute_traits(features(10), acts([22]), ["Study"], prior, data_days=10)
    assert (
        early["chronotype"]["source"] == "quiz" and early["chronotype"]["value"] == "morning person"
    )
    later = compute_traits(features(30), acts([22]), ["Study"], prior, data_days=30)
    assert later["chronotype"]["source"] == "data" and later["chronotype"]["value"] == "night owl"
    assert later["chronotype"]["confidence"] > early["chronotype"]["confidence"]


def test_optimism_planner_and_consistency():
    t = compute_traits(features(30, [300.0, 100.0] * 15), acts([9], ratio=0.625), ["Study"], {}, 30)
    assert t["optimism_bias"]["value"] == 0.625
    assert "1.6×" in t["optimism_bias"]["label"]
    assert t["planner"]["value"] == 1.0 and t["planner"]["label"] == "planner"
    assert t["consistency"]["label"] == "varied routine"
    steady = compute_traits(features(30), acts([9]), ["Study"], {}, 30)
    assert steady["consistency"]["label"] == "steady routine"
