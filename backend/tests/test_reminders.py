"""8 PM check-in reminder: sent only on days without any check-in, in the user's timezone."""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.core.config import settings
from app.core.security import create_token
from app.jobs import reminders
from app.models import Checkin, Reminder, User
from app.services import email as mail
from tests.conftest import ONBOARDING, TestSession, auth, register

KOLKATA_8PM = datetime(2026, 11, 24, 14, 35, tzinfo=UTC)  # 20:05 in Asia/Kolkata (UTC+5:30)
DAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def _outbox():
    mail.outbox.clear()
    yield
    mail.outbox.clear()


def make_user(client, email="asha@twinmail.org", tz="Asia/Kolkata", onboard=True) -> dict:
    tokens = register(client, email=email)
    h = auth(tokens)
    if onboard:
        assert client.post("/onboarding", json=ONBOARDING, headers=h).status_code == 200
    assert client.patch("/me", json={"timezone": tz}, headers=h).status_code == 200
    return {**tokens, "h": h, "id": client.get("/me", headers=h).json()["user"]["id"]}


def checkin(user_id, day=DAY, slot="morning"):
    with TestSession() as db:
        db.add(Checkin(user_id=uuid.UUID(user_id), date=day, slot=slot, mood=3, energy=3))
        db.commit()


def run(at=KOLKATA_8PM, **kw):
    return reminders.send_due(TestSession, now=at, **kw)


def test_no_checkin_all_day_gets_one_email_at_8pm(client):
    u = make_user(client)
    r = run()
    assert r.sent == ["asha@twinmail.org"]
    [m] = mail.outbox
    assert m.to == "asha@twinmail.org"
    assert "haven't checked in today" in m.text
    assert f"{settings.app_url}/checkin" in m.text
    assert "/reminders/off?token=" in m.text and "List-Unsubscribe" in m.headers
    assert m.html and "Check in now" in m.html
    with TestSession() as db:
        assert db.get(Reminder, (uuid.UUID(u["id"]), DAY)).status == "sent"
    # the job runs every 5 minutes: never a second email the same day
    assert run(at=datetime(2026, 11, 24, 14, 50, tzinfo=UTC)).sent == []
    assert run(at=datetime(2026, 11, 24, 16, 0, tzinfo=UTC)).sent == []
    assert len(mail.outbox) == 1


@pytest.mark.parametrize("slot", ["morning", "afternoon", "evening"])
def test_any_checkin_today_means_no_email(client, slot):
    u = make_user(client)
    checkin(u["id"], slot=slot)
    r = run()
    assert r.sent == [] and mail.outbox == []
    assert r.skipped.get("checked in today") == 1


def test_yesterdays_checkin_does_not_count(client):
    u = make_user(client)
    checkin(u["id"], day=date(2026, 11, 23))
    assert run().sent == ["asha@twinmail.org"]
    assert "1 of the last 7 days" in mail.outbox[0].text


@pytest.mark.parametrize(
    ("utc", "sent"),
    [
        (datetime(2026, 11, 24, 14, 25, tzinfo=UTC), False),  # 19:55 local: too early
        (datetime(2026, 11, 24, 14, 30, tzinfo=UTC), True),  # 20:00 local
        (datetime(2026, 11, 24, 16, 25, tzinfo=UTC), True),  # 21:55: catch-up after a restart
        (datetime(2026, 11, 24, 16, 35, tzinfo=UTC), False),  # 22:05: too late to nag
    ],
)
def test_sent_from_8pm_local_with_a_catch_up_window(client, utc, sent):
    make_user(client)
    assert bool(run(at=utc).sent) is sent


def test_each_user_gets_it_at_their_own_8pm(client):
    make_user(client, email="india@twinmail.org", tz="Asia/Kolkata")
    make_user(client, email="ny@twinmail.org", tz="America/New_York")
    # 01:05 UTC on 25 Nov = 20:05 on 24 Nov in New York (UTC-5), 06:35 in Kolkata
    assert run(at=datetime(2026, 11, 25, 1, 5, tzinfo=UTC)).sent == ["ny@twinmail.org"]
    assert run(at=KOLKATA_8PM).sent == ["india@twinmail.org"]


def test_checkin_on_the_users_local_date_blocks_reminder(client):
    u = make_user(client, email="ny@twinmail.org", tz="America/New_York")
    checkin(u["id"], day=date(2026, 11, 24), slot="evening")  # still 24 Nov in New York
    assert run(at=datetime(2026, 11, 25, 1, 5, tzinfo=UTC)).sent == []


def test_opt_out_in_settings_and_back_in(client):
    u = make_user(client)
    r = client.patch("/me", json={"email_reminders": False}, headers=u["h"])
    assert r.status_code == 200 and r.json()["user"]["email_reminders"] is False
    assert r.json()["user"]["timezone"] == "Asia/Kolkata"  # untouched
    assert run().sent == []
    client.patch("/me", json={"email_reminders": True}, headers=u["h"])
    assert run().sent == ["asha@twinmail.org"]


def test_unsubscribe_link_turns_reminders_off(client):
    u = make_user(client)
    run()
    token = mail.outbox[0].text.split("/reminders/off?token=")[1].split()[0]
    r = client.post("/reminders/unsubscribe", json={"token": token})
    assert r.status_code == 200 and r.json() == {"email_reminders": False}
    assert client.get("/me", headers=u["h"]).json()["user"]["email_reminders"] is False


def test_unsubscribe_rejects_other_tokens_and_cannot_be_used_to_log_in(client):
    u = make_user(client)
    assert (
        client.post("/reminders/unsubscribe", json={"token": u["access_token"]}).status_code == 400
    )
    assert client.post("/reminders/unsubscribe", json={"token": "x" * 40}).status_code == 400
    unsub = create_token(uuid.UUID(u["id"]), "unsubscribe")
    assert client.get("/me", headers={"Authorization": f"Bearer {unsub}"}).status_code == 401


def test_not_sent_without_onboarding_consent_or_real_address(client):
    make_user(client, email="new@twinmail.org", onboard=False)
    c = make_user(client, email="private@twinmail.org")
    r = client.put(
        "/privacy/consents", json={"source": "checkin", "allowed": False}, headers=c["h"]
    )
    assert r.status_code == 200
    make_user(client, email="student@demo.example.com")
    r = run()
    assert r.sent == []
    assert r.skipped["not onboarded"] == 1
    assert r.skipped["check-in consent off"] == 1
    assert r.skipped["undeliverable address"] == 1


def test_pauses_after_unanswered_reminders_and_resumes_after_a_checkin(client, monkeypatch):
    monkeypatch.setattr(settings, "reminder_pause_after", 2)
    u = make_user(client)
    for d in (22, 23):
        assert run(at=datetime(2026, 11, d, 14, 35, tzinfo=UTC)).sent
    r = run()  # third evening in a row with no answer
    assert r.sent == [] and r.skipped["paused (unanswered)"] == 1
    checkin(u["id"], day=DAY)  # they came back
    assert run(at=datetime(2026, 11, 25, 14, 35, tzinfo=UTC)).sent == ["asha@twinmail.org"]


def test_failed_send_is_recorded_and_not_retried_the_same_day(client, monkeypatch):
    u = make_user(client)

    def boom(_email):
        raise mail.EmailError("SMTPAuthenticationError: bad login")

    monkeypatch.setattr(mail, "send", boom)
    r = run()
    assert r.failed == ["asha@twinmail.org"] and r.sent == []
    with TestSession() as db:
        row = db.get(Reminder, (uuid.UUID(u["id"]), DAY))
        assert row.status == "failed" and "bad login" in row.detail
    monkeypatch.undo()
    assert run().sent == []  # one attempt per day, no retry storm


def test_dry_run_sends_nothing_and_global_switch(client, monkeypatch):
    make_user(client)
    r = run(dry_run=True)
    assert r.due == ["asha@twinmail.org"] and mail.outbox == []
    monkeypatch.setattr(settings, "reminders_enabled", False)
    assert run().sent == []


def test_test_email_endpoint(client):
    u = make_user(client)
    r = client.post("/reminders/test", headers=u["h"])
    assert r.status_code == 200
    assert r.json() == {"sent_to": "asha@twinmail.org", "provider": "fake"}
    assert mail.outbox[0].to == "asha@twinmail.org"
    for _ in range(2):
        client.post("/reminders/test", headers=u["h"])
    assert client.post("/reminders/test", headers=u["h"]).status_code == 429
    demo = make_user(client, email="dev@demo.example.com")
    assert client.post("/reminders/test", headers=demo["h"]).status_code == 400
    assert client.post("/reminders/test").status_code == 401


def test_export_includes_reminders_and_delete_removes_them(client):
    u = make_user(client)
    run()
    data = client.get("/privacy/export", headers=u["h"]).json()
    assert data["reminder_emails"][0]["status"] == "sent"
    r = client.request("DELETE", "/me", json={"confirm_email": "asha@twinmail.org"}, headers=u["h"])
    assert r.status_code in (200, 204)
    with TestSession() as db:
        assert db.query(Reminder).count() == 0 and db.query(User).count() == 0


@pytest.mark.parametrize(
    ("address", "ok"),
    [
        ("a@gmail.com", True),
        ("a@christuniversity.in", True),
        ("a@notexample.com", True),
        ("a@example.com", False),
        ("a@demo.example.com", False),
        ("a@host.test", False),
        ("a@x.invalid", False),
        ("a@localhost", False),
    ],
)
def test_deliverable(address, ok):
    assert mail.deliverable(address) is ok
