"""Personality traits.

Phase 1: the onboarding quiz gives a prior for each trait.
Phase 3 adds data-driven traits that blend with this prior as data days grow.
"""

from app.schemas.profile import QuizAnswers

PRIOR_CONFIDENCE = 0.2  # quiz answers are weak evidence

_CHRONOTYPE = {
    "morning": "morning person",
    "afternoon": "balanced",
    "evening": "night owl",
    "night": "night owl",
}
# Expected ratio of planned_min / actual duration_min (optimism bias).
# < 1 means the user tends to underestimate how long things take.
_ESTIMATE = {"faster": 1.2, "accurate": 1.0, "slower": 0.8, "much_slower": 0.6}


def _trait(value, label: str) -> dict:
    return {"value": value, "label": label, "confidence": PRIOR_CONFIDENCE, "source": "quiz"}


def quiz_prior(quiz: QuizAnswers) -> dict:
    planner_share = (quiz.plans_ahead - 1) / 4  # 0..1
    consistency = (quiz.routine - 1) / 4  # 0..1
    ratio = _ESTIMATE[quiz.estimate_bias]
    return {
        "chronotype": _trait(_CHRONOTYPE[quiz.best_time], _CHRONOTYPE[quiz.best_time]),
        "optimism_bias": _trait(
            ratio,
            "realistic estimator" if ratio >= 1 else f"tasks take ~{1 / ratio:.1f}x your estimate",
        ),
        "planner": _trait(
            round(planner_share, 2),
            "planner" if planner_share >= 0.5 else "improviser",
        ),
        "consistency": _trait(
            round(consistency, 2),
            "steady routine" if consistency >= 0.5 else "varied routine",
        ),
        "stress_triggers": _trait([quiz.stress_source], quiz.stress_source),
        "best_conditions": _trait({}, "not enough data yet"),
    }
