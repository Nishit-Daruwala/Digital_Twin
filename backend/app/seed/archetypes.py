"""Who the synthetic people are: roles, categories, routines and baselines.

`kind` tags let planted patterns find the right category in any archetype
(e.g. the "exercise" pattern uses whichever category is the archetype's exercise).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cat:
    name: str
    kind: str  # deep, work, meetings, exercise, social, leisure, family, chores, learning, rest
    mean_min: float  # minutes on a day it happens (ignored for meetings: count-based)
    p_weekday: float
    p_weekend: float
    hours: tuple[float, float]  # window for the first session's start hour
    session: float = 60  # typical session length (min)
    task: bool = False  # sessions are plannable tasks (planned_min vs actual)


@dataclass(frozen=True)
class Archetype:
    key: str
    role: str
    cats: tuple[Cat, ...]
    goals: tuple[str, ...]
    stress_source: str  # quiz answer
    base: dict = field(default_factory=dict)  # mood/energy/stress/focus means (1-5)
    sleep_mean: float = 7.0
    sleep_sd: float = 0.9
    peak_hour: float = 10.0  # chronotype: when deep work happens
    planner_share: float = 0.6
    optimism: float = 0.9  # planned_min / actual minutes (<1 = underestimates)
    late_prob: float = 0.15  # chance of a session ending after 23:00
    msg_rate: float = 1.0  # chat messages per day

    def cat_of_kind(self, kind: str) -> Cat | None:
        return next((c for c in self.cats if c.kind == kind), None)

    def expected_minutes(self, kind: str) -> float:
        c = self.cat_of_kind(kind)
        if c is None:
            return 0.0
        mean = 2.2 * 45 if c.kind == "meetings" else c.mean_min
        return mean * (5 * c.p_weekday + 2 * c.p_weekend) / 7


def _b(mood, energy, stress, focus) -> dict:
    return {"mood": mood, "energy": energy, "stress": stress, "focus": focus}


ARCHETYPES: dict[str, Archetype] = {
    a.key: a
    for a in [
        Archetype(
            "student",
            "Student",
            (
                Cat("Study", "deep", 150, 0.85, 0.6, (20, 23), 60, task=True),
                Cat("Lectures", "work", 180, 0.8, 0.0, (9, 12), 90),
                Cat("Assignments", "work", 90, 0.6, 0.4, (15, 19), 60, task=True),
                Cat("Exercise", "exercise", 45, 0.4, 0.5, (17, 19), 45),
                Cat("Social", "social", 120, 0.4, 0.7, (18, 21), 120),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (21, 23), 60),
            ),
            ("Sleep 7+ hours", "Study 3h a day", "Finish tasks on time"),
            "deadlines",
            _b(3.2, 3.0, 3.0, 3.0),
            6.3,
            1.1,
            22,
            0.4,
            0.625,
            0.35,
            1.2,
        ),
        Archetype(
            "developer",
            "Developer",
            (
                Cat("Deep work", "deep", 210, 0.9, 0.1, (8, 10.5), 90, task=True),
                Cat("Meetings", "meetings", 0, 0.85, 0.0, (10, 17), 45),
                Cat("Code review", "work", 60, 0.7, 0.05, (13, 17), 30, task=True),
                Cat("Learning", "learning", 45, 0.3, 0.4, (19, 21), 45),
                Cat("Exercise", "exercise", 45, 0.5, 0.6, (6.5, 8), 45),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (20, 22.5), 60),
            ),
            ("More deep work", "Fewer meetings", "Exercise 3x a week"),
            "workload",
            _b(3.3, 3.3, 2.8, 3.3),
            7.0,
            0.7,
            9,
            0.75,
            0.9,
            0.08,
            0.9,
        ),
        Archetype(
            "founder",
            "Founder",
            (
                Cat("Strategy", "deep", 90, 0.6, 0.3, (7, 10), 60, task=True),
                Cat("Meetings", "meetings", 0, 0.9, 0.2, (9, 18), 45),
                Cat("Sales", "work", 120, 0.7, 0.1, (11, 17), 60, task=True),
                Cat("Hiring", "work", 60, 0.4, 0.05, (14, 18), 45, task=True),
                Cat("Exercise", "exercise", 50, 0.45, 0.5, (6, 8), 50),
                Cat("Family", "family", 120, 0.6, 0.95, (19, 21), 120),
            ),
            ("Less stress", "Exercise 3x a week", "Consistent routine"),
            "uncertainty",
            _b(3.1, 3.1, 3.5, 3.1),
            6.4,
            0.8,
            10,
            0.6,
            0.8,
            0.25,
            1.1,
        ),
        Archetype(
            "nurse",
            "Nurse (shift work)",
            (
                Cat("Shift", "work", 600, 0.6, 0.5, (7, 19), 600),
                Cat("Rest", "rest", 120, 0.5, 0.6, (13, 16), 120),
                Cat("Exercise", "exercise", 40, 0.35, 0.4, (10, 12), 40),
                Cat("Family", "family", 90, 0.5, 0.7, (18, 21), 90),
                Cat("Errands", "chores", 45, 0.4, 0.6, (10, 14), 45, task=True),
                Cat("Leisure", "leisure", 90, 0.6, 0.8, (20, 23), 60),
            ),
            ("Sleep 7+ hours", "Less stress", "More family time"),
            "sleep",
            _b(3.0, 3.0, 3.3, 3.0),
            6.2,
            1.3,
            15,
            0.5,
            0.9,
            0.3,
            0.8,
        ),
        Archetype(
            "teacher",
            "Teacher",
            (
                Cat("Teaching", "work", 300, 0.95, 0.0, (8, 9), 100),
                Cat("Grading", "deep", 90, 0.7, 0.4, (17, 20), 60, task=True),
                Cat("Lesson planning", "work", 60, 0.6, 0.5, (19, 21), 45, task=True),
                Cat("Exercise", "exercise", 40, 0.4, 0.6, (6.5, 7.5), 40),
                Cat("Family", "family", 120, 0.6, 0.9, (18, 20), 120),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (20, 22.5), 60),
            ),
            ("Finish grading on time", "Exercise 3x a week", "Less stress"),
            "workload",
            _b(3.3, 3.1, 3.1, 3.2),
            6.9,
            0.7,
            9,
            0.8,
            0.85,
            0.1,
            0.8,
        ),
        Archetype(
            "designer",
            "Designer",
            (
                Cat("Design", "deep", 200, 0.85, 0.2, (10, 14), 90, task=True),
                Cat("Client calls", "meetings", 0, 0.6, 0.05, (11, 17), 45),
                Cat("Research", "learning", 60, 0.5, 0.2, (14, 17), 45, task=True),
                Cat("Exercise", "exercise", 45, 0.4, 0.5, (18, 19.5), 45),
                Cat("Social", "social", 120, 0.4, 0.7, (19, 22), 120),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (21, 23), 60),
            ),
            ("More deep work", "Consistent routine", "Read more"),
            "people",
            _b(3.3, 3.1, 2.9, 3.2),
            7.1,
            0.9,
            12,
            0.5,
            0.75,
            0.25,
            1.0,
        ),
        Archetype(
            "athlete",
            "Athlete",
            (
                Cat("Training", "exercise", 150, 0.9, 0.7, (6, 8), 75),
                Cat("Recovery", "rest", 60, 0.7, 0.8, (13, 15), 60),
                Cat("Study", "deep", 90, 0.6, 0.3, (15, 18), 60, task=True),
                Cat("Meal prep", "chores", 45, 0.6, 0.6, (11, 12.5), 45, task=True),
                Cat("Social", "social", 90, 0.3, 0.6, (19, 21), 90),
                Cat("Leisure", "leisure", 60, 0.6, 0.8, (20, 22), 60),
            ),
            ("Sleep 8 hours", "Peak for competition", "Consistent routine"),
            "uncertainty",
            _b(3.5, 3.6, 2.7, 3.3),
            8.0,
            0.6,
            8,
            0.85,
            0.95,
            0.05,
            0.7,
        ),
        Archetype(
            "researcher",
            "Researcher",
            (
                Cat("Experiments", "work", 180, 0.8, 0.2, (9, 12), 90, task=True),
                Cat("Writing", "deep", 120, 0.7, 0.3, (14, 17), 60, task=True),
                Cat("Reading", "learning", 60, 0.6, 0.5, (20, 22), 45),
                Cat("Meetings", "meetings", 0, 0.6, 0.0, (10, 16), 45),
                Cat("Exercise", "exercise", 40, 0.35, 0.5, (18, 19.5), 40),
                Cat("Leisure", "leisure", 90, 0.6, 0.9, (21, 23), 60),
            ),
            ("Publish a paper", "More deep work", "Sleep 7+ hours"),
            "deadlines",
            _b(3.2, 3.1, 3.2, 3.2),
            6.8,
            0.9,
            14,
            0.6,
            0.7,
            0.2,
            0.9,
        ),
        Archetype(
            "freelancer",
            "Freelancer",
            (
                Cat("Client work", "deep", 240, 0.8, 0.4, (10, 15), 90, task=True),
                Cat("Calls", "meetings", 0, 0.5, 0.05, (11, 17), 45),
                Cat("Admin", "chores", 45, 0.5, 0.3, (16, 18), 30, task=True),
                Cat("Exercise", "exercise", 45, 0.45, 0.5, (8, 9.5), 45),
                Cat("Social", "social", 120, 0.4, 0.7, (19, 22), 120),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (21, 23), 60),
            ),
            ("Steady income", "Finish tasks on time", "Less stress"),
            "uncertainty",
            _b(3.2, 3.1, 3.1, 3.1),
            7.0,
            1.1,
            13,
            0.45,
            0.7,
            0.35,
            1.0,
        ),
        Archetype(
            "parent",
            "Parent working from home",
            (
                Cat("Work", "deep", 240, 0.85, 0.05, (9, 11), 90, task=True),
                Cat("Meetings", "meetings", 0, 0.7, 0.0, (10, 16), 45),
                Cat("Childcare", "family", 180, 0.9, 0.95, (16, 19), 120),
                Cat("Chores", "chores", 60, 0.7, 0.8, (19, 21), 45, task=True),
                Cat("Exercise", "exercise", 30, 0.3, 0.4, (6, 7), 30),
                Cat("Leisure", "leisure", 60, 0.6, 0.8, (21, 23), 60),
            ),
            ("More family time", "Exercise 3x a week", "Sleep 7+ hours"),
            "workload",
            _b(3.1, 2.9, 3.3, 3.0),
            6.5,
            0.9,
            10,
            0.7,
            0.8,
            0.15,
            0.9,
        ),
        # Used only by the pure-noise control persona.
        Archetype(
            "generalist",
            "Generalist",
            (
                Cat("Work", "work", 240, 0.8, 0.1, (9, 13), 90, task=True),
                Cat("Learning", "learning", 60, 0.4, 0.4, (19, 21), 45),
                Cat("Exercise", "exercise", 45, 0.4, 0.5, (7, 19), 45),
                Cat("Social", "social", 120, 0.4, 0.7, (18, 21), 120),
                Cat("Leisure", "leisure", 90, 0.7, 0.9, (20, 22.5), 60),
            ),
            ("Consistent routine", "Less stress"),
            "workload",
            _b(3.1, 3.1, 3.1, 3.1),
            7.0,
            1.0,
            11,
            0.6,
            0.9,
            0.15,
            1.0,
        ),
    ]
}

GENERATABLE = [k for k in ARCHETYPES if k != "generalist"]

FIRST_NAMES = [
    "Asha",
    "Mateo",
    "Lin",
    "Kwame",
    "Sofia",
    "Arjun",
    "Hana",
    "Omar",
    "Priya",
    "Lucas",
    "Zara",
    "Yuki",
    "Diego",
    "Amara",
    "Noah",
    "Fatima",
    "Ravi",
    "Elena",
    "Tariq",
    "Mei",
    "Kofi",
    "Ines",
    "Sanjay",
    "Leila",
    "Jonas",
    "Aiko",
    "Chidi",
    "Nadia",
    "Rohan",
    "Clara",
    "Ibrahim",
    "Ana",
    "Kenji",
    "Esther",
    "Malik",
    "Freya",
]
LAST_INITIALS = "ABCDEFGHJKLMNPRSTVWZ"
