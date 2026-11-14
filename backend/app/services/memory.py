"""Twin memory: recall similar past messages (pgvector) and assemble the reply prompt.

Privacy rules (from the plan):
- Only the current message, a few recent turns, and retrieved snippets go to the LLM,
  never the whole history.
- No name or email is ever put in a prompt.
- Messages sent while chat consent was off (learnable=False) are never recalled, and
  nothing is recalled while chat consent is currently off.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Checkin, Insight, Message, TwinProfile

SYSTEM_PROMPT = """You are the user's digital twin: a reflective version of them that has \
learned from their own check-ins, activity logs and conversations.

How to respond:
- Speak as their reflective self, warmly and concisely (2-6 sentences unless asked for more).
- Use ONLY the facts in the FACTS message and the conversation. Never invent numbers, dates \
or events.
- When you make a claim about their patterns or data, cite what it is based on \
(e.g. "your check-in on 12 Nov", "you mentioned on 3 Nov").
- If the facts don't cover the question, say you're not sure yet and suggest what to log \
so you can learn it.
- Frame observations as patterns, never diagnoses. Never give medical or financial advice; \
for health concerns suggest talking to a professional.
- Don't repeat the facts back as a list unless asked."""


@dataclass
class Memory:
    text: str
    created_at: datetime
    similarity: float


def recall(
    db: Session,
    user_id: uuid.UUID,
    query_vec: list[float],
    *,
    exclude_id: uuid.UUID | None = None,
    k: int | None = None,
) -> list[Memory]:
    """Top-k most similar past messages of THIS user, by exact cosine distance.

    Deliberately exact, not via the HNSW index: an approximate index searches the whole
    table and applies `user_id = ...` afterwards, so with many users it can silently return
    fewer (even zero) of this user's memories, a failure tests/test_chat.py reproduces.
    A user's own history is small (thousands of rows), so an exact scan through the
    (user_id, created_at) index takes milliseconds and is always correct.
    """
    k = k or settings.memory_top_k
    distance = Message.embedding.cosine_distance(query_vec)
    q = (
        select(Message.text, Message.created_at, distance.label("dist"))
        .where(
            Message.user_id == user_id,
            Message.role == "user",
            Message.learnable.is_(True),
            Message.embedding.is_not(None),
        )
        # "+ 0" makes the sort key an expression the HNSW index can't serve -> exact search
        .order_by(distance + 0)
        .limit(k)
    )
    if exclude_id is not None:
        q = q.where(Message.id != exclude_id)
    rows = db.execute(q).all()
    return [
        Memory(text=r.text, created_at=r.created_at, similarity=round(1 - r.dist, 3))
        for r in rows
        if r.dist <= settings.memory_max_distance
    ]


def recent_turns(
    db: Session, user_id: uuid.UUID, *, exclude_id: uuid.UUID, n: int = 4
) -> list[Message]:
    rows = db.scalars(
        select(Message)
        .where(Message.user_id == user_id, Message.id != exclude_id)
        .order_by(Message.created_at.desc())
        .limit(n)
    ).all()
    return list(reversed(rows))


def _fmt_checkin(c: Checkin) -> str:
    parts = [
        f"{k} {getattr(c, k)}"
        for k in ("mood", "energy", "stress", "focus")
        if getattr(c, k) is not None
    ]
    if c.sleep_hours is not None:
        parts.append(f"sleep {c.sleep_hours:g}h")
    line = f"- {c.date.isoformat()}: " + ", ".join(parts)
    if c.note:
        line += f' (note: "{c.note[:120]}")'
    return line


def build_facts(
    db: Session,
    user_id: uuid.UUID,
    *,
    today: date,
    memories: list[Memory],
    checkins_allowed: bool,
) -> str:
    profile = db.get(TwinProfile, user_id)
    lines = [f"FACTS (today is {today.isoformat()}, {today.strftime('%A')})"]

    if profile:
        if profile.goals:
            lines.append("Goals: " + "; ".join(profile.goals))
        traits = [
            f"{k.replace('_', ' ')}: {t.get('label')} (confidence {t.get('confidence', 0):.0%},"
            f" from {t.get('source', 'quiz')})"
            for k, t in (profile.traits or {}).items()
            if isinstance(t, dict) and t.get("label") and t.get("label") != "not enough data yet"
        ]
        if traits:
            lines.append("Personality traits:\n" + "\n".join(f"- {t}" for t in traits))

    insights = db.scalars(
        select(Insight)
        .where(Insight.user_id == user_id, Insight.active.is_(True))
        .order_by(Insight.confidence.desc().nullslast())
        .limit(5)
    ).all()
    if insights:
        lines.append("Discovered patterns:\n" + "\n".join(f"- {i.text}" for i in insights))

    if checkins_allowed:
        week = db.scalars(
            select(Checkin)
            .where(Checkin.user_id == user_id, Checkin.date >= today - timedelta(days=6))
            .order_by(Checkin.date.desc())
        ).all()
        if week:
            lines.append(
                "Check-ins, last 7 days (1-5 scales):\n" + "\n".join(_fmt_checkin(c) for c in week)
            )
        else:
            lines.append("Check-ins, last 7 days: none logged.")

    if memories:
        lines.append(
            "Related things the user said before:\n"
            + "\n".join(f'- ({m.created_at.date().isoformat()}) "{m.text[:300]}"' for m in memories)
        )
    return "\n\n".join(lines)


def build_prompt(facts: str, turns: list[Message], message: str) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": facts},
    ]
    for t in turns:
        msgs.append({"role": "user" if t.role == "user" else "assistant", "content": t.text[:1500]})
    msgs.append({"role": "user", "content": message})
    return msgs
