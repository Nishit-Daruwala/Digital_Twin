"""The LLM may reword insights but never change, invent or drop numbers, or imply causes."""

from app.core.config import settings
from app.services import insight_wording as iw
from app.services.llm import FakeProvider, LLMError

TPL = "The day after you sleep 6.2 h or less, your focus averages 1.9 (vs 2.8 otherwise)."


def test_verified_accepts_faithful_rewording():
    ok = "After nights of 6.2 h or less sleep, your focus the next day tends to be 1.9, not 2.8."
    assert iw.verified(TPL, ok)
    two = "Two days after your stress is above 3, your mood averages 3.2 (vs 3.8 otherwise)."
    assert iw.verified(two, "2 days after stress above 3, your mood tends to be 3.2, not 3.8.")


def test_verified_rejects_invented_changed_or_missing_numbers():
    assert not iw.verified(TPL, "After 6.2 h or less sleep, focus drops 32% to 1.9 vs 2.8.")
    assert not iw.verified(TPL, "After 6 h or less sleep, your focus averages 1.9 vs 2.8.")
    assert not iw.verified(TPL, "Short sleep is linked with lower focus the next day.")


def test_verified_rejects_causal_claims():
    assert not iw.verified(TPL, "Sleeping 6.2 h or less causes your focus to fall to 1.9 from 2.8.")
    assert not iw.verified(TPL, "Because you slept 6.2 h or less, focus is 1.9 not 2.8.")


def test_reword_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(
        FakeProvider,
        "reword_insights",
        lambda self, items: {i["id"]: "Your focus soars by 50% 🙂" for i in items},
    )
    assert iw.reword({"a": TPL}) == {"a": (TPL, "template")}

    def boom(self, items):
        raise LLMError("down")

    monkeypatch.setattr(FakeProvider, "reword_insights", boom)
    assert iw.reword({"a": TPL}) == {"a": (TPL, "template")}


def test_reword_uses_llm_when_it_passes(monkeypatch):
    good = "After nights of 6.2 h or less sleep, your focus the next day tends to be 1.9, not 2.8."
    monkeypatch.setattr(FakeProvider, "reword_insights", lambda self, items: {"a": good})
    assert iw.reword({"a": TPL}) == {"a": (good, "llm")}
    monkeypatch.setattr(settings, "insight_llm_wording", False)
    assert iw.reword({"a": TPL}) == {"a": (TPL, "template")}


def test_timing_must_survive_rewording():
    lag1 = "The day after you skip Exercise, your mood averages 3.2 (vs 4 otherwise)."
    assert not iw.verified(lag1, "On days when you skip exercise, your mood tends to be 3.2 vs 4.")
    assert iw.verified(lag1, "The day after you skip exercise, your mood tends to be 3.2 vs 4.")
    assert iw.verified(lag1, "When you skip exercise, the next day your mood averages 3.2 vs 4.")
    lag2 = "Two days after your stress is above 3, your mood averages 3.2 (vs 3.8 otherwise)."
    assert not iw.verified(
        lag2, "On days when your stress is above 3, your mood averages 3.2 vs 3.8."
    )
    assert not iw.verified(lag2, "The day after stress above 3, your mood averages 3.2 vs 3.8.")
    assert iw.verified(
        lag2, "2 days after your stress is above 3, your mood tends to be 3.2, not 3.8."
    )
    same = "On Mondays, your mood averages 2.3 (vs 3.3 on other days)."
    assert not iw.verified(same, "The day after a Monday, your mood averages 2.3 vs 3.3.")
    assert iw.verified(
        same, "Your mood tends to dip to 2.3 on Mondays, compared with 3.3 otherwise."
    )
