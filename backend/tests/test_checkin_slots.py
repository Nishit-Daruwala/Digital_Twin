"""Check-in slots through the API: timezone, defaults, quick check-ins, validation, chat."""

import json
from datetime import UTC, datetime, timedelta

from tests.conftest import auth


def tz_where_local_hour(lo: int, hi: int) -> tuple[str, datetime]:
    """A fixed-offset timezone whose local hour is in [lo, hi) right now (CI-time proof)."""
    now = datetime.now(UTC)
    for off in range(-12, 15):
        local = now + timedelta(hours=off)
        if lo <= local.hour < hi and local.hour < 23:  # not right before a slot/day change
            name = "Etc/GMT" if off == 0 else f"Etc/GMT{'-' if off > 0 else '+'}{abs(off)}"
            return name, local
    raise AssertionError("no timezone found")


def use_tz(client, h, lo, hi) -> datetime:
    name, local = tz_where_local_hour(lo, hi)
    r = client.patch("/me", headers=h, json={"timezone": name})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["timezone"] == name
    return local


FULL = {"mood": 4, "energy": 4, "stress": 2, "focus": 4, "sleep_hours": 7.5}


def test_timezone_is_validated(client, user):
    h = auth(user)
    assert client.patch("/me", headers=h, json={"timezone": "Mars/Olympus"}).status_code == 422
    r = client.patch("/me", headers=h, json={"timezone": "Asia/Kolkata"})
    assert r.status_code == 200 and r.json()["user"]["timezone"] == "Asia/Kolkata"
    assert client.get("/me", headers=h).json()["user"]["timezone"] == "Asia/Kolkata"


def test_checkin_defaults_to_local_day_and_slot(client, user):
    h = auth(user)
    local = use_tz(client, h, 13, 16)  # afternoon
    day = client.get("/checkins/today", headers=h).json()
    assert day["date"] == local.date().isoformat() and day["current_slot"] == "afternoon"
    started = {s["slot"]: s["started"] for s in day["slots"]}
    assert started == {"morning": True, "afternoon": True, "evening": False}
    assert not day["full_done"] and all(s["checkin"] is None for s in day["slots"])

    r = client.post("/checkins", headers=h, json=FULL)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["slot"] == "afternoon" and c["date"] == local.date().isoformat()
    assert c["checked_at"] is not None

    day = client.get("/checkins/today", headers=h).json()
    assert day["full_done"]
    assert [s["slot"] for s in day["slots"] if s["checkin"]] == ["afternoon"]


def test_quick_checkins_add_up_and_updates_keep_other_fields(client, user):
    h = auth(user)
    local = use_tz(client, h, 13, 16)
    today = local.date().isoformat()
    assert client.post("/checkins", headers=h, json={**FULL, "slot": "morning"}).status_code == 200
    quick = client.post("/checkins", headers=h, json={"mood": 3, "energy": 2, "slot": "afternoon"})
    assert quick.status_code == 200, quick.text
    assert quick.json()["stress"] is None and quick.json()["sleep_hours"] is None

    rows = client.get(f"/checkins?from={today}&to={today}", headers=h).json()
    assert [(r["slot"], r["energy"]) for r in rows] == [("morning", 4), ("afternoon", 2)]

    # saving the morning again with just mood/energy keeps its sleep and stress
    again = client.post("/checkins", headers=h, json={"mood": 5, "energy": 5, "slot": "morning"})
    assert again.status_code == 200
    m = again.json()
    assert (m["mood"], m["stress"], m["sleep_hours"]) == (5, 2, 7.5)
    assert len(client.get(f"/checkins?from={today}&to={today}", headers=h).json()) == 2

    # the dashboard chart shows one point per day: the mean of that day's check-ins
    series = client.get("/dashboard", headers=h).json()["series"]
    point = next(p for p in series if p["date"] == today)
    assert point["energy"] == 3.5 and point["mood"] == 4.0


def test_slots_that_have_not_started_are_rejected(client, user):
    h = auth(user)
    local = use_tz(client, h, 6, 11)  # morning
    r = client.post("/checkins", headers=h, json={"mood": 3, "energy": 3, "slot": "evening"})
    assert r.status_code == 422 and "hasn't started" in r.json()["detail"]
    tomorrow = (local.date() + timedelta(days=1)).isoformat()
    r = client.post("/checkins", headers=h, json={**FULL, "date": tomorrow})
    assert r.status_code == 422
    # a past day's evening is fine (filling in yesterday)
    yesterday = (local.date() - timedelta(days=1)).isoformat()
    r = client.post("/checkins", headers=h, json={**FULL, "date": yesterday, "slot": "evening"})
    assert r.status_code == 200 and r.json()["slot"] == "evening"


def chat_card(client, h, message, today):
    r = client.post("/chat", headers=h, json={"message": message, "today": today.isoformat()})
    assert r.status_code == 200, r.text
    events = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    ext = next(e for e in events if e["type"] == "extraction")
    return ext["message_id"], ext["card"]


def test_chat_checkin_lands_in_the_slot_the_message_names(client, user):
    h = auth(user)
    local = use_tz(client, h, 18, 22)  # evening
    msg_id, card = chat_card(client, h, "This afternoon my energy was 2.", local.date())
    assert card["checkin"]["slot"] == "afternoon" and card["checkin"]["energy"] == 2
    out = client.post(f"/chat/extractions/{msg_id}/confirm", headers=h, json=card).json()
    assert out["checkin"]["slot"] == "afternoon"

    # no part of day mentioned: the slot of when the message was sent
    msg_id, card = chat_card(client, h, "Energy 4 right now.", local.date())
    assert card["checkin"]["slot"] is None
    out = client.post(f"/chat/extractions/{msg_id}/confirm", headers=h, json=card).json()
    assert out["checkin"]["slot"] == "evening"

    rows = client.get("/checkins", headers=h).json()
    assert sorted(r["slot"] for r in rows) == ["afternoon", "evening"]
