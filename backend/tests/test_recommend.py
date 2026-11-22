"""Recommendations: ranking, learning from thumbs, guardrails, and the API."""

import numpy as np
import pytest
from sqlalchemy import select

from app.ml import recommend as R
from app.models import Recommendation, User
from tests.conftest import TestSession, auth, register

# ---------- pure ranking / learning ----------


def cand(t, rel, key=None):
    return R.Candidate(t, key or f"{t}:{rel}", f"do {t}", "because", rel)


def test_choose_one_per_type_top_k_and_exclusions():
    rng = np.random.default_rng(0)
    cands = [
        cand("goal", 0.9),
        cand("goal", 0.8),
        cand("pattern", 0.5),
        cand("checkin", 0.4),
        cand("light_day", 0.3),
    ]
    picks = R.choose(cands, {}, "relevance", rng)
    assert [c.type for c, _ in picks] == ["goal", "pattern", "checkin"]
    assert picks[0][0].relevance == 0.9  # the best of each type
    picks = R.choose(cands, {}, "relevance", rng, exclude={"goal:0.9", "goal:0.8"})
    assert "goal" not in [c.type for c, _ in picks]


def test_plan_weights_follow_the_plan_rule():
    rng = np.random.default_rng(0)
    assert R.preference({"goal": (3, 0)}, "goal", "weights", rng) == pytest.approx(1.3)
    assert R.preference({"goal": (0, 2)}, "goal", "weights", rng) == pytest.approx(0.7)
    assert R.preference({"goal": (50, 0)}, "goal", "weights", rng) == 2.0  # clamped
    assert R.preference({"goal": (0, 50)}, "goal", "weights", rng) == 0.2


def test_thompson_learns_preferences():
    rng = np.random.default_rng(1)
    liked = [R.preference({"goal": (10, 1)}, "goal", "thompson", rng) for _ in range(500)]
    disliked = [R.preference({"goal": (1, 10)}, "goal", "thompson", rng) for _ in range(500)]
    fresh = [R.preference({}, "goal", "thompson", rng) for _ in range(500)]
    assert np.mean(liked) > 0.7 > np.mean(fresh) > 0.3 > np.mean(disliked)
    assert np.std(fresh) > np.std(liked)  # untried types are still explored
    assert R.type_weight({"goal": (10, 1)}, "goal") > 0.5 > R.type_weight({"goal": (1, 10)}, "goal")


def test_texts_never_give_medical_or_financial_advice():
    import inspect

    src = inspect.getsource(R).lower()
    for word in ("medication", "doctor", "diagnos", "invest", "therapy", "supplement"):
        assert word not in src


# ---------- through the pipeline and the API ----------


def seeded(client, persona="founder"):
    tokens = register(client)
    r = client.post("/demo/seed", headers=auth(tokens), json={"persona": persona, "days": 60})
    assert r.status_code == 200 and r.json()["pipeline"] == "ok", r.text
    return tokens


def test_three_recommendations_with_reasons(client):
    h = auth(seeded(client))
    out = client.get("/recommendations", headers=h).json()
    items = out["items"]
    assert len(items) == 3 and out["policy"] == "thompson"
    assert len({i["type"] for i in items}) == 3  # one per type
    assert [i["rank"] for i in items] == [1, 2, 3]
    for i in items:
        assert i["text"] and i["reason"] and i["feedback"] is None
    assert {x["type"] for x in out["learning"]} == set(R.TYPES)
    assert all(x["likes"] == x["dislikes"] == 0 and x["preference"] == 0.5 for x in out["learning"])


def test_thumbs_down_replaces_it_and_is_not_repeated(client):
    tokens = seeded(client)
    h = auth(tokens)
    items = client.get("/recommendations", headers=h).json()["items"]
    liked, disliked = items[0], items[1]

    r = client.post(f"/recommendations/{liked['id']}/feedback", headers=h, json={"value": 1})
    assert r.status_code == 200
    r = client.post(f"/recommendations/{disliked['id']}/feedback", headers=h, json={"value": -1})
    out = r.json()
    shown = {i["id"]: i for i in out["items"]}
    assert disliked["id"] not in shown  # hidden right away...
    assert liked["id"] in shown and shown[liked["id"]]["feedback"] == 1  # ...the liked one stays
    learning = {x["type"]: x for x in out["learning"]}
    assert learning[liked["type"]]["likes"] == 1 and learning[liked["type"]]["preference"] > 0.5
    assert learning[disliked["type"]]["dislikes"] == 1
    assert learning[disliked["type"]]["preference"] < 0.5

    # a re-run (the "Update now" button) keeps the 👍, never brings the 👎 back
    assert client.post("/jobs/retrain", headers=h).status_code == 200
    with TestSession() as db:
        uid = db.scalar(select(User.id).where(User.email == tokens["email"]))
        bad_key = db.get(Recommendation, disliked["id"]).key
    again = client.get("/recommendations", headers=h).json()["items"]
    with TestSession() as db:
        keys = {db.get(Recommendation, i["id"]).key for i in again}
        assert (
            db.scalar(
                select(Recommendation).where(
                    Recommendation.user_id == uid,
                    Recommendation.key == bad_key,
                    Recommendation.feedback.is_(None),
                )
            )
            is None
        )
    assert bad_key not in keys
    assert liked["id"] in {i["id"] for i in again}

    # undo
    r = client.post(f"/recommendations/{liked['id']}/feedback", headers=h, json={"value": 0})
    assert {x["type"]: x for x in r.json()["learning"]}[liked["type"]]["likes"] == 0


def test_feedback_is_private_and_validated(client):
    h = auth(seeded(client))
    rid = client.get("/recommendations", headers=h).json()["items"][0]["id"]
    other = auth(register(client))
    assert (
        client.post(
            f"/recommendations/{rid}/feedback", headers=other, json={"value": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(f"/recommendations/{rid}/feedback", headers=h, json={"value": 5}).status_code
        == 422
    )
    assert client.get("/recommendations", headers=other).json()["items"] == []


def test_new_user_has_no_recommendations(client):
    h = auth(register(client))
    out = client.get("/recommendations", headers=h).json()
    assert out["items"] == [] and out["for_date"] is None
