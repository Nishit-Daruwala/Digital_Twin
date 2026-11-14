"""Chat: streaming, extraction card, confirm/dismiss, memory recall, consent, limits."""

import json
from datetime import date, timedelta

import pytest

from app.core.config import settings
from tests.conftest import auth, register

TODAY = date.today()


def chat(client, headers, message, today=TODAY):
    r = client.post("/chat", headers=headers, json={"message": message, "today": today.isoformat()})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def by_type(events, t):
    return [e for e in events if e["type"] == t]


# ---------- the week-3 checkpoint ----------


def test_slept_and_studied_creates_rows_only_after_confirm(client, user):
    h = auth(user)
    events = chat(client, h, "Slept 5 hours, studied 2h. Mood 2 today.")
    types = [e["type"] for e in events]
    # extraction runs in parallel with the reply, so the card can arrive between tokens
    assert types[0] == "user_message" and types[-1] == "done"
    assert types.count("extraction") == 1 and "token" in types

    card = by_type(events, "extraction")[0]["card"]
    assert card["checkin"]["sleep_hours"] == 5
    assert card["checkin"]["mood"] == 2
    assert card["activities"][0] == {
        "title": "Study",
        "category": "Study",
        "duration_min": 120,
        "planned": False,
        "completed": True,
        "start_time": None,
    }

    # Nothing saved yet
    assert client.get("/checkins", headers=h).json() == []
    assert client.get("/activities", headers=h).json() == []

    msg_id = by_type(events, "extraction")[0]["message_id"]
    r = client.post(f"/chat/extractions/{msg_id}/confirm", headers=h, json=card)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checkin"]["sleep_hours"] == 5 and out["checkin"]["source"] == "ai"
    assert out["activities"][0]["duration_min"] == 120
    assert out["message"]["extraction_status"] == "confirmed"

    assert client.get("/checkins", headers=h).json()[0]["mood"] == 2
    acts = client.get("/activities", headers=h).json()
    assert len(acts) == 1 and acts[0]["source"] == "ai"


def test_twin_recalls_past_messages(client, user):
    h = auth(user)
    chat(client, h, "My exam on graph algorithms is next Friday and I'm nervous")
    chat(client, h, "Had pasta for dinner")
    events = chat(client, h, "How should I prepare for the graph algorithms exam?")
    reply = "".join(e["text"] for e in by_type(events, "token"))
    assert "graph algorithms is next Friday" in reply  # fake twin quotes the top memory


def test_reply_uses_recent_checkins(client, user):
    h = auth(user)
    client.post(
        "/checkins",
        headers=h,
        json={"date": TODAY.isoformat(), "mood": 4, "energy": 3, "stress": 2, "focus": 3},
    )
    events = chat(client, h, "how am I doing?")
    reply = "".join(e["text"] for e in by_type(events, "token"))
    assert f"({TODAY.isoformat()}) had mood 4" in reply
    assert by_type(events, "extraction") == []  # nothing to extract


# ---------- confirm details ----------


def test_confirm_uses_edited_values_and_merges_checkin(client, user):
    h = auth(user)
    client.post(
        "/checkins",
        headers=h,
        json={
            "date": TODAY.isoformat(),
            "mood": 3,
            "energy": 3,
            "stress": 3,
            "focus": 3,
            "note": "manual",
        },
    )
    events = chat(client, h, "slept 6 hours and studied 90 min, decided to skip the party")
    ext = by_type(events, "extraction")[0]
    card = ext["card"]
    card["checkin"]["sleep_hours"] = 6.5  # user edits
    card["activities"][0]["duration_min"] = 100
    assert card["decisions"][0]["choice"] == "skip the party"

    r = client.post(f"/chat/extractions/{ext['message_id']}/confirm", headers=h, json=card)
    assert r.status_code == 200
    ck = client.get("/checkins", headers=h).json()
    assert len(ck) == 1
    assert ck[0]["sleep_hours"] == 6.5
    assert ck[0]["mood"] == 3 and ck[0]["note"] == "manual"  # untouched fields preserved
    assert client.get("/activities", headers=h).json()[0]["duration_min"] == 100
    decisions = client.get("/decisions", headers=h).json()
    assert decisions[0]["source"] == "ai" and decisions[0]["choice"] == "skip the party"


def test_confirm_twice_conflicts_and_dismiss(client, user):
    h = auth(user)
    e1 = by_type(chat(client, h, "studied 1h"), "extraction")[0]
    url = f"/chat/extractions/{e1['message_id']}"
    assert client.post(url + "/confirm", headers=h, json=e1["card"]).status_code == 200
    assert client.post(url + "/confirm", headers=h, json=e1["card"]).status_code == 409
    assert client.post(url + "/dismiss", headers=h).status_code == 409

    e2 = by_type(chat(client, h, "studied 2h"), "extraction")[0]
    r = client.post(f"/chat/extractions/{e2['message_id']}/dismiss", headers=h)
    assert r.status_code == 200 and r.json()["extraction_status"] == "dismissed"
    assert len(client.get("/activities", headers=h).json()) == 1  # only the confirmed one


def test_confirm_rejects_invalid_edits(client, user):
    h = auth(user)
    ext = by_type(chat(client, h, "studied 1h"), "extraction")[0]
    url = f"/chat/extractions/{ext['message_id']}/confirm"
    bad = ext["card"] | {"checkin": {"mood": 9}}
    assert client.post(url, headers=h, json=bad).status_code == 422
    bad = ext["card"] | {"activities": [{"title": "X", "category": "Gaming"}]}
    assert client.post(url, headers=h, json=bad).status_code == 422
    far = ext["card"] | {"date": (TODAY - timedelta(days=30)).isoformat()}
    assert client.post(url, headers=h, json=far).status_code == 422
    # still pending, nothing written
    assert client.get("/activities", headers=h).json() == []
    assert client.post(url, headers=h, json=ext["card"]).status_code == 200


def test_yesterday_message_targets_yesterday(client, user):
    h = auth(user)
    ext = by_type(chat(client, h, "yesterday I slept 8 hours"), "extraction")[0]
    assert ext["card"]["date"] == (TODAY - timedelta(days=1)).isoformat()


def test_unknown_category_is_not_extracted(client, user):
    ext = by_type(chat(client, auth(user), "gamed 3h and studied 1h"), "extraction")[0]
    assert [a["category"] for a in ext["card"]["activities"]] == ["Study"]


# ---------- history, isolation ----------


def test_history_and_isolation(client, user):
    h = auth(user)
    events = chat(client, h, "studied 1h")
    ext = by_type(events, "extraction")[0]
    hist = client.get("/chat/history", headers=h).json()
    assert [m["role"] for m in hist] == ["user", "twin"]
    assert hist[0]["extraction_status"] == "pending"

    other = register(client)
    ho = auth(other)
    assert client.get("/chat/history", headers=ho).json() == []
    url = f"/chat/extractions/{ext['message_id']}"
    assert client.post(url + "/confirm", headers=ho, json=ext["card"]).status_code == 404
    assert client.post(url + "/dismiss", headers=ho).status_code == 404
    # B's chat never recalls A's messages
    reply = "".join(e["text"] for e in by_type(chat(client, ho, "studied 1h"), "token"))
    assert "You told me before" not in reply


# ---------- consent ----------


def test_chat_consent_off_saves_but_never_learns(client, user):
    h = auth(user)
    client.put("/privacy/consents", headers=h, json={"source": "chat", "allowed": False})
    chat(client, h, "My secret project codename is BLUEBIRD")
    hist = client.get("/chat/history", headers=h).json()
    assert hist[0]["text"].endswith("BLUEBIRD") and hist[0]["learnable"] is False

    client.put("/privacy/consents", headers=h, json={"source": "chat", "allowed": True})
    reply = "".join(
        e["text"] for e in by_type(chat(client, h, "what is my project codename"), "token")
    )
    assert "BLUEBIRD" not in reply  # sent while consent was off -> never recalled


def test_checkin_consent_off_removes_checkin_part_of_card(client, user):
    h = auth(user)
    client.put("/privacy/consents", headers=h, json={"source": "checkin", "allowed": False})
    ext = by_type(chat(client, h, "slept 5 hours and studied 1h"), "extraction")[0]
    assert ext["card"]["checkin"]["sleep_hours"] is None
    assert len(ext["card"]["activities"]) == 1


# ---------- limits and errors ----------


def test_message_validation(client, user):
    h = auth(user)
    assert client.post("/chat", headers=h, json={"message": "   "}).status_code == 422
    assert client.post("/chat", headers=h, json={"message": "x" * 2001}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_rate_limit(client, user, monkeypatch):
    from app.api import chat as chat_api

    monkeypatch.setattr(chat_api.limiter, "limit", 3)
    h = auth(user)
    for _ in range(3):
        chat(client, h, "hi")
    r = client.post("/chat", headers=h, json={"message": "hi"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    # other users are unaffected
    assert (
        client.post("/chat", headers=auth(register(client)), json={"message": "hi"}).status_code
        == 200
    )


def test_llm_not_configured_returns_503(client, user, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "your-openai-api-key-here")
    r = client.post("/chat", headers=auth(user), json={"message": "hi"})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_extraction_failure_does_not_break_chat(client, user, monkeypatch):
    from app.services.llm import FakeProvider, LLMError

    def boom(*a, **k):
        raise LLMError("down")

    monkeypatch.setattr(FakeProvider, "extract", boom)
    events = chat(client, auth(user), "studied 1h")
    assert by_type(events, "extraction") == []
    assert by_type(events, "done")


def test_reply_failure_emits_error_event(client, user, monkeypatch):
    from app.services.llm import FakeProvider, LLMError

    def boom(*a, **k):
        raise LLMError("OpenAI rate limit or quota reached. Try again shortly.")
        yield  # pragma: no cover

    monkeypatch.setattr(FakeProvider, "stream_reply", boom)
    events = chat(client, auth(user), "hello")
    assert events[-1] == {
        "type": "error",
        "detail": "OpenAI rate limit or quota reached. Try again shortly.",
    }
    # the user's message is still saved; no twin message
    hist = client.get("/chat/history", headers=auth(user)).json()
    assert [m["role"] for m in hist] == ["user"]


@pytest.mark.parametrize("delta", [5, -5])
def test_client_today_is_clamped(client, user, delta):
    ext = by_type(
        chat(client, auth(user), "studied 1h", today=TODAY + timedelta(days=delta)), "extraction"
    )[0]
    assert ext["card"]["date"] == TODAY.isoformat()


# ---------- embedding model still loading ----------


def test_chat_works_while_model_loads_and_backfill_catches_up(client, user, monkeypatch):
    from app.services import embeddings
    from tests.conftest import TestSession

    h = auth(user)
    monkeypatch.setattr(embeddings, "ready", lambda: False)
    events = chat(client, h, "My cat is called Pixel")
    assert by_type(events, "done")  # the user is not kept waiting

    monkeypatch.setattr(embeddings, "ready", lambda: True)
    assert embeddings.backfill_missing(TestSession) == 1
    reply = "".join(e["text"] for e in by_type(chat(client, h, "what is my cat called"), "token"))
    assert "My cat is called Pixel" in reply  # now part of memory
    assert embeddings.backfill_missing(TestSession) == 0  # idempotent


def test_backfill_skips_messages_without_consent(client, user):
    from app.services import embeddings
    from tests.conftest import TestSession

    h = auth(user)
    client.put("/privacy/consents", headers=h, json={"source": "chat", "allowed": False})
    chat(client, h, "private note")
    assert embeddings.backfill_missing(TestSession) == 0


def test_reply_does_not_wait_for_slow_extraction(client, user, monkeypatch):
    """The first token must not be blocked by the extraction call."""
    import threading

    from app.services.llm import FakeProvider

    release = threading.Event()
    original = FakeProvider.extract

    def slow_extract(self, *a, **k):
        release.wait(5)  # blocks until the reply has started streaming
        return original(self, *a, **k)

    def reply(self, messages):
        yield "first "
        release.set()  # only reachable if streaming started before extraction finished
        yield "second"

    monkeypatch.setattr(FakeProvider, "extract", slow_extract)
    monkeypatch.setattr(FakeProvider, "stream_reply", reply)
    events = chat(client, auth(user), "studied 1h")
    types = [e["type"] for e in events]
    assert types.index("token") < types.index("extraction")
    assert types[-1] == "done"


def test_recall_survives_hnsw_filtering(client, user):
    """400 near-identical messages from another user, and the planner tempted onto the HNSW
    index: the user must still get all 3 of their own memories. (With an approximate
    per-table index this returned 0, the reason recall uses exact per-user search.)"""
    import uuid as _uuid

    from sqlalchemy import insert, text

    from app.models import Message, User
    from app.services import memory
    from app.services.embeddings import embed
    from tests.conftest import TestSession

    h = auth(user)
    for t in ("I love hiking in the hills", "Hiking in the hills in May", "Hills hiking again"):
        chat(client, h, t)
    with TestSession() as db:
        other = User(email=f"bulk-{_uuid.uuid4().hex[:6]}@example.com", password_hash="x", name="B")
        db.add(other)
        db.flush()
        texts = [f"hiking note number {i} about hills" for i in range(400)]
        db.execute(
            insert(Message),
            [
                {"user_id": other.id, "role": "user", "text": t, "embedding": v, "learnable": True}
                for t, v in zip(texts, embed(texts), strict=True)
            ],
        )
        db.commit()
        me = db.scalar(select_user_id(user))
        db.execute(text("SET LOCAL enable_sort = off"))  # tempt the planner onto the HNSW index
        db.execute(text("SET LOCAL enable_seqscan = off"))
        got = memory.recall(db, me, embed(["hiking in the hills"])[0], k=5)
    assert len(got) == 3, [m.text for m in got]
    assert all("ik" in m.text for m in got)


def select_user_id(tokens):
    from sqlalchemy import select

    from app.models import User

    return select(User.id).where(User.email == tokens["email"])
