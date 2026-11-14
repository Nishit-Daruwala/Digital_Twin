from tests.conftest import auth, register


def test_decision_crud_and_isolation(client, user):
    h = auth(user)
    r = client.post(
        "/decisions",
        headers=h,
        json={
            "text": "Take the internship offer?",
            "options": ["Accept", " Decline ", ""],
            "choice": "Accept",
            "reasoning": "Good mentors",
        },
    )
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["options"] == ["Accept", "Decline"] and d["source"] == "manual"
    assert d["outcome_rating"] is None

    r = client.patch(f"/decisions/{d['id']}", headers=h, json={"outcome_rating": 4})
    assert r.status_code == 200 and r.json()["outcome_rating"] == 4
    assert (
        client.patch(f"/decisions/{d['id']}", headers=h, json={"outcome_rating": 6}).status_code
        == 422
    )
    assert client.patch(f"/decisions/{d['id']}", headers=h, json={}).status_code == 422

    other = auth(register(client))
    assert client.get("/decisions", headers=other).json() == []
    assert (
        client.patch(f"/decisions/{d['id']}", headers=other, json={"outcome_rating": 1}).status_code
        == 404
    )
    assert client.delete(f"/decisions/{d['id']}", headers=other).status_code == 404

    assert client.delete(f"/decisions/{d['id']}", headers=h).status_code == 204
    assert client.get("/decisions", headers=h).json() == []


def test_decision_validation(client, user):
    h = auth(user)
    assert client.post("/decisions", headers=h, json={"text": "  "}).status_code == 422
    assert (
        client.post("/decisions", headers=h, json={"text": "x", "options": ["o"] * 9}).status_code
        == 422
    )
