"""LLM access. Two providers with the same interface:

- OpenAIProvider: real model calls (structured extraction + streamed replies).
- FakeProvider:   deterministic, offline. Used by tests and when LLM_PROVIDER=fake.

The rest of the app only calls `get_llm()`, `extract()` and `stream_reply()`.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from datetime import date
from functools import lru_cache
from typing import Protocol

from app.core.config import settings

log = logging.getLogger("twin.llm")


class LLMNotConfigured(Exception):
    """No usable LLM (e.g. missing API key)."""


class LLMError(Exception):
    """A user-presentable LLM failure."""


class LLMProvider(Protocol):
    def extract(self, message: str, categories: list[str], today: date) -> dict: ...

    def stream_reply(self, messages: list[dict]) -> Iterator[str]: ...


# --------------------------------------------------------------------------------------
# Extraction prompt + JSON schema (strict structured output)
# --------------------------------------------------------------------------------------

EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "day",
        "sleep_hours",
        "mood",
        "energy",
        "stress",
        "focus",
        "activities",
        "decisions",
        "topics",
        "sentiment",
    ],
    "properties": {
        "day": {"type": "string", "enum": ["today", "yesterday"]},
        "sleep_hours": {"type": ["number", "null"]},
        "mood": {"type": ["integer", "null"]},
        "energy": {"type": ["integer", "null"]},
        "stress": {"type": ["integer", "null"]},
        "focus": {"type": ["integer", "null"]},
        "activities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "category",
                    "duration_min",
                    "planned",
                    "completed",
                    "start_time",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "duration_min": {"type": ["integer", "null"]},
                    "planned": {"type": "boolean"},
                    "completed": {"type": "boolean"},
                    "start_time": {"type": ["string", "null"]},
                },
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "options", "choice", "reasoning"],
                "properties": {
                    "text": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "choice": {"type": ["string", "null"]},
                    "reasoning": {"type": ["string", "null"]},
                },
            },
        },
        "topics": {"type": "array", "items": {"type": "string"}},
        "sentiment": {"type": "number"},
    },
}


def extraction_prompt(categories: list[str], today: date) -> str:
    return (
        "You extract structured diary data from ONE chat message written by a user to their "
        "personal assistant. Today is "
        f"{today.isoformat()} ({today.strftime('%A')}).\n"
        "Rules:\n"
        "- Extract only what the message states or clearly implies. Use null for anything "
        "not mentioned. Never guess numbers.\n"
        "- mood, energy, stress, focus are integers 1-5 (1 = very low, 5 = very high). Only "
        "fill them when the user rates them or describes them unambiguously.\n"
        "- sleep_hours: hours slept last night, only if stated.\n"
        f"- Activities may ONLY use one of these categories: {json.dumps(categories)}. "
        "If an activity fits none, leave it out.\n"
        "- title: a short capitalised label for the activity (e.g. 'Study session', "
        "'5 km run'), not a verb copied from the message.\n"
        "- duration_min is the actual minutes spent (convert hours). planned=true only for "
        "things the user plans to do later; then completed=false and duration_min is the "
        "planned length.\n"
        "- start_time is 24h HH:MM if stated, else null.\n"
        "- decisions: choices the user is making or made. text = the question in a few words "
        "(e.g. 'Football or study tonight?'); options = the alternatives; choice = the option "
        "they picked, written as an action (e.g. 'Skip football'), never 'yes'/'no'; "
        "reasoning = their reason if stated.\n"
        "- day: 'yesterday' if the message is about yesterday, else 'today'.\n"
        "- topics: up to 5 short lowercase tags. sentiment: -1 (very negative) to 1 "
        "(very positive)."
    )


# --------------------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------------------


class OpenAIProvider:
    def __init__(self, api_key: str):
        from openai import OpenAI  # imported lazily so tests never need it configured

        self.client = OpenAI(api_key=api_key, timeout=30, max_retries=2)

    @staticmethod
    def _translate(exc: Exception) -> LLMError:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return LLMError("The OpenAI API key was rejected. Check OPENAI_API_KEY.")
        if isinstance(exc, openai.RateLimitError):
            return LLMError("OpenAI rate limit or quota reached. Try again shortly.")
        if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
            return LLMError("Couldn't reach OpenAI. Check your internet connection.")
        return LLMError("The AI service returned an error. Try again.")

    def extract(self, message: str, categories: list[str], today: date) -> dict:
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=settings.openai_extraction_model,
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extraction",
                        "strict": True,
                        "schema": EXTRACTION_SCHEMA,
                    },
                },
                messages=[
                    {"role": "system", "content": extraction_prompt(categories, today)},
                    {"role": "user", "content": message},
                ],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("extraction failed: %s", type(exc).__name__)
            raise self._translate(exc) from exc
        log.info("extraction in %.0f ms", (time.perf_counter() - t0) * 1000)
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("The AI returned malformed data.") from exc

    def stream_reply(self, messages: list[dict]) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=settings.openai_chat_model,
                temperature=0.6,
                max_tokens=450,
                stream=True,
                messages=messages,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:  # noqa: BLE001
            log.warning("reply stream failed: %s", type(exc).__name__)
            raise self._translate(exc) from exc

    def reword_insights(self, items: list[dict]) -> dict[str, str]:
        """items: [{id, sentence}] -> {id: reworded}. One call for all of a user's insights."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "text"],
                        "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                    },
                }
            },
        }
        try:
            resp = self.client.chat.completions.create(
                model=settings.openai_extraction_model,
                temperature=0.3,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "insights", "strict": True, "schema": schema},
                },
                messages=[
                    {"role": "system", "content": INSIGHT_PROMPT},
                    {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
                ],
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001
            raise self._translate(exc) from exc
        return {i["id"]: i["text"] for i in data.get("items", []) if "id" in i}


INSIGHT_PROMPT = (
    "You rewrite short statistical findings about ONE person into one friendly, plain "
    "sentence each, speaking to them as 'you'. Rules:\n"
    "- Keep every number EXACTLY as given (same digits, same units). Add no new numbers.\n"
    "- Keep the timing EXACTLY: 'The day after' must stay 'the day after' (or 'the next "
    "day'); 'Two days after' must stay two days; 'On days when' means the same day.\n"
    "- Describe a link, never a cause: say 'tends to', 'is linked with'. "
    "Never say 'causes', 'because' or give advice.\n"
    "- At most 30 words. No emoji. Return the same ids."
)


# --------------------------------------------------------------------------------------
# Fake (offline, deterministic)
# --------------------------------------------------------------------------------------

_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"(h|hr|hrs|hours?|m|min|mins|minutes?)\b"
_POS = {
    "good",
    "great",
    "happy",
    "productive",
    "calm",
    "energised",
    "energized",
    "awesome",
    "relaxed",
    "focused",
    "fine",
    "nice",
    "better",
}
_NEG = {
    "tired",
    "bad",
    "stressed",
    "anxious",
    "sad",
    "exhausted",
    "awful",
    "low",
    "drained",
    "terrible",
    "worse",
    "overwhelmed",
}


def _to_minutes(value: str, unit: str) -> int:
    v = float(value)
    return int(round(v * 60)) if unit.startswith("h") else int(round(v))


def _match_category(word: str, categories: list[str]) -> str | None:
    w = word.lower()
    for c in categories:
        cl = c.lower()
        if w == cl or (len(w) >= 4 and len(cl) >= 4 and w[:4] == cl[:4]):
            return c
    return None


class FakeProvider:
    """Regex-based extraction and template replies. Good enough to exercise the full flow."""

    def extract(self, message: str, categories: list[str], today: date) -> dict:
        text = message.lower()
        out: dict = {
            "day": "yesterday" if "yesterday" in text else "today",
            "sleep_hours": None,
            "mood": None,
            "energy": None,
            "stress": None,
            "focus": None,
            "activities": [],
            "decisions": [],
            "topics": [],
            "sentiment": 0.0,
        }
        m = re.search(rf"slept\s+(?:for\s+)?{_NUM}\s*{_UNIT}", text) or re.search(
            rf"{_NUM}\s*{_UNIT}\s+(?:of\s+)?sleep", text
        )
        if m:
            out["sleep_hours"] = _to_minutes(m.group(1), m.group(2)) / 60
            out["topics"].append("sleep")
        for metric in ("mood", "energy", "stress", "focus"):
            m = re.search(rf"{metric}\s*(?:is|was|:|=|at)?\s*(\d)\b", text)
            if m:
                out[metric] = int(m.group(1))

        seen: set[str] = set()
        patterns = [
            rf"(\w+)\s+(?:for\s+)?{_NUM}\s*{_UNIT}",  # "studied 2h", "ran for 30 min"
            rf"{_NUM}\s*{_UNIT}\s+(?:of\s+)?(\w+)",  # "2 hours of study"
        ]
        for i, pat in enumerate(patterns):
            for m in re.finditer(pat, text):
                word, num, unit = (
                    (m.group(1), m.group(2), m.group(3))
                    if i == 0
                    else (m.group(3), m.group(1), m.group(2))
                )
                cat = _match_category(word, categories)
                if cat and cat not in seen:
                    seen.add(cat)
                    out["activities"].append(
                        {
                            "title": cat,
                            "category": cat,
                            "duration_min": _to_minutes(num, unit),
                            "planned": False,
                            "completed": True,
                            "start_time": None,
                        }
                    )
                    out["topics"].append(cat.lower())

        m = re.search(r"decided to ([^.!?\n]+)", text)
        if m:
            choice = m.group(1).strip()
            out["decisions"].append(
                {"text": f"Decided to {choice}", "options": [], "choice": choice, "reasoning": None}
            )

        words = set(re.findall(r"[a-z]+", text))
        score = len(words & _POS) - len(words & _NEG)
        out["sentiment"] = max(-1.0, min(1.0, score / 3))
        return out

    def stream_reply(self, messages: list[dict]) -> Iterator[str]:
        facts = next(
            (
                m["content"]
                for m in messages
                if m["role"] == "system" and m["content"].startswith("FACTS")
            ),
            "",
        )
        memories = re.findall(r'^- \(\d{4}-\d{2}-\d{2}\) "(.+)"$', facts, flags=re.M)
        parts = ["(Offline twin) I'm running without an AI model, so this is a simple reply."]
        if memories:
            parts.append(f'You told me before: "{memories[0]}".')
        checkin = re.search(r"^- (\d{4}-\d{2}-\d{2}): mood (\d)", facts, flags=re.M)
        if checkin:
            parts.append(f"Your latest check-in ({checkin.group(1)}) had mood {checkin.group(2)}.")
        for word in " ".join(parts).split(" "):
            yield word + " "

    def reword_insights(self, items: list[dict]) -> dict[str, str]:
        return {i["id"]: i["sentence"] for i in items}  # templates are already readable


# --------------------------------------------------------------------------------------


@lru_cache
def _openai_provider(api_key: str) -> OpenAIProvider:
    return OpenAIProvider(api_key)


def llm_configured() -> bool:
    if settings.llm_provider == "fake":
        return True
    key = settings.openai_api_key.strip()
    return bool(key) and not key.startswith("your-")


def get_llm() -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    if not llm_configured():
        raise LLMNotConfigured(
            "The AI isn't configured yet. Add OPENAI_API_KEY to backend/.env and restart."
        )
    return _openai_provider(settings.openai_api_key.strip())
