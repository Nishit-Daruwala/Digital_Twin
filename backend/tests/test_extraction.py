"""The sanitiser never trusts the LLM: each bad field is dropped on its own."""

from datetime import date

from app.services.extraction import sanitize
from app.services.llm import FakeProvider

TODAY = date(2026, 11, 14)
CATS = ["Study", "Exercise", "Deep work"]
ALL = {"checkin": True, "activities": True, "decisions": True, "chat": True}


def raw(**over):
    base = {
        "day": "today",
        "sleep_hours": None,
        "mood": None,
        "energy": None,
        "stress": None,
        "focus": None,
        "activities": [],
        "decisions": [],
        "topics": [],
        "sentiment": 0,
    }
    return base | over


def test_invalid_scores_dropped_individually():
    r = sanitize(
        raw(mood=7, energy=4, stress=0, focus="high", sleep_hours=30),
        categories=CATS,
        today=TODAY,
        consents=ALL,
    )
    c = r.card.checkin
    assert (c.mood, c.energy, c.stress, c.focus, c.sleep_hours) == (None, 4, None, None, None)


def test_sleep_rounded_to_quarter_hours():
    r = sanitize(raw(sleep_hours=6.6), categories=CATS, today=TODAY, consents=ALL)
    assert r.card.checkin.sleep_hours == 6.5


def test_activities_only_known_categories_and_canonical_case():
    acts = [
        {
            "title": "Gym",
            "category": "exercise",
            "duration_min": 45.4,
            "planned": False,
            "completed": True,
            "start_time": "07:30",
        },
        {
            "title": "Gaming",
            "category": "Games",
            "duration_min": 60,
            "planned": False,
            "completed": True,
            "start_time": None,
        },
        {
            "title": "Run",
            "category": "Exercise",
            "duration_min": -5,
            "planned": False,
            "completed": True,
            "start_time": "25:99",
        },
        {
            "title": "  ",
            "category": "Study",
            "duration_min": 10,
            "planned": False,
            "completed": True,
            "start_time": None,
        },
        "not a dict",
    ]
    r = sanitize(raw(activities=acts), categories=CATS, today=TODAY, consents=ALL)
    out = [(a.title, a.category, a.duration_min, a.start_time) for a in r.card.activities]
    assert out[0][:3] == ("Gym", "Exercise", 45) and str(out[0][3]) == "07:30:00"
    assert out[1] == ("Run", "Exercise", None, None)  # bad fields dropped, activity kept
    assert len(out) == 2


def test_planned_tasks_are_not_completed():
    acts = [
        {
            "title": "Essay",
            "category": "Study",
            "duration_min": 60,
            "planned": True,
            "completed": True,
            "start_time": None,
        }
    ]
    r = sanitize(raw(activities=acts), categories=CATS, today=TODAY, consents=ALL)
    assert r.card.activities[0].planned and not r.card.activities[0].completed


def test_consents_filter_sections():
    data = raw(
        mood=3,
        activities=[
            {
                "title": "S",
                "category": "Study",
                "duration_min": 5,
                "planned": False,
                "completed": True,
                "start_time": None,
            }
        ],
        decisions=[{"text": "Quit?", "options": ["yes"], "choice": None, "reasoning": None}],
    )
    r = sanitize(
        data,
        categories=CATS,
        today=TODAY,
        consents={"checkin": False, "activities": False, "decisions": False},
    )
    assert r.card.is_empty()


def test_sentiment_topics_and_garbage_input():
    r = sanitize(
        raw(sentiment=5, topics=["Sleep", "sleep", "x" * 50, "a", "b", "c", "d"]),
        categories=CATS,
        today=TODAY,
        consents=ALL,
    )
    assert r.sentiment == 1.0
    assert r.topics[0] == "sleep" and len(r.topics) == 5 and len(r.topics[1]) == 30
    assert sanitize("garbage", categories=CATS, today=TODAY, consents=ALL).card.is_empty()


def test_yesterday():
    r = sanitize(raw(day="yesterday", mood=3), categories=CATS, today=TODAY, consents=ALL)
    assert r.card.date == date(2026, 11, 13)


def test_fake_provider_extraction():
    out = FakeProvider().extract(
        "Slept 7.5 hours, did 2 hours of deep work and ran for 30 min. " "Energy 4. Feeling great!",
        CATS,
        TODAY,
    )
    assert out["sleep_hours"] == 7.5 and out["energy"] == 4
    assert [(a["category"], a["duration_min"]) for a in out["activities"]] == [("Deep work", 120)]
    assert out["sentiment"] > 0
