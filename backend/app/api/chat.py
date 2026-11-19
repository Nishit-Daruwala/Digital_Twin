"""Chat with the twin.

POST /chat streams NDJSON events (one JSON object per line):
  {"type": "user_message", "message": {...}}        the saved user message
  {"type": "extraction",   "message_id", "card"}    only if something was extracted
  {"type": "token",        "text": "..."}            reply chunks
  {"type": "done",         "message": {...}}         the saved twin reply
  {"type": "error",        "detail": "..."}          the stream failed after it started
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.activities import check_category
from app.api.deps import DB, CurrentUser
from app.api.privacy import consent_map
from app.core.config import settings
from app.core.timeutil import local_now, to_local
from app.db import get_session_factory
from app.ml.intraday import slot_for, slot_started
from app.models import Activity, Checkin, Decision, Message, TwinProfile, User
from app.schemas.activity import ActivityOut
from app.schemas.chat import ChatIn, ConfirmOut, ExtractionCard, MessageOut
from app.schemas.checkin import CheckinOut
from app.schemas.decision import DecisionOut
from app.services import embeddings, memory
from app.services.extraction import ExtractionResult, sanitize
from app.services.llm import LLMError, LLMNotConfigured, get_llm
from app.services.rate_limit import RateLimiter

router = APIRouter(prefix="/chat", tags=["chat"])
log = logging.getLogger("twin.chat")

limiter = RateLimiter(settings.chat_rate_limit_per_min)
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="chat")

SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


def _event(obj: dict) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False) + "\n"


def _out(m: Message) -> dict:
    return MessageOut.model_validate(m).model_dump(mode="json")


def _resolve_today(client_today: date | None) -> date:
    server = date.today()
    if client_today and abs((client_today - server).days) <= 1:
        return client_today  # client's local day (timezones), within reason
    return server


@router.post("")
def send_message(
    body: ChatIn, user: CurrentUser, db: DB, session_factory: SessionFactory
) -> StreamingResponse:
    allowed, retry_after = limiter.allow(str(user.id))
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You're sending messages too quickly. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        llm = get_llm()
    except LLMNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None

    today = _resolve_today(body.today)
    consents = consent_map(db, user.id)
    learnable = consents["chat"]
    profile = db.get(TwinProfile, user.id)
    categories = list(profile.categories) if profile else []

    # Extraction is an LLM call the reply does NOT depend on, so it runs in parallel with the
    # reply stream instead of in front of it (saves seconds before the first word).
    def run_extraction() -> ExtractionResult:
        raw = llm.extract(body.message, categories, today)
        return sanitize(raw, categories=categories, today=today, consents=consents)

    f_extract = _pool.submit(run_extraction)

    # The embedding IS needed before replying (memory recall). Local: ~5 ms.
    # While the local model is still loading, skip it; the startup backfill catches up.
    vec = None
    if learnable and embeddings.ready():
        try:
            vec = embeddings.embed_one(body.message)
        except embeddings.EmbeddingError as exc:
            log.warning("embedding skipped: %s", exc)

    user_msg = Message(
        user_id=user.id, role="user", text=body.message, embedding=vec, learnable=learnable
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    memories = (
        memory.recall(db, user.id, vec, exclude_id=user_msg.id)
        if vec is not None and consents["chat"]
        else []
    )
    facts = memory.build_facts(
        db, user.id, today=today, memories=memories, checkins_allowed=consents["checkin"]
    )
    turns = memory.recent_turns(db, user.id, exclude_id=user_msg.id)
    prompt = memory.build_prompt(facts, turns, body.message)
    first_event = _event({"type": "user_message", "message": _out(user_msg)})
    user_id, message_id = user.id, user_msg.id

    def finish_extraction(wait: float | None) -> str | None:
        """Store the extraction on the user message; return an event if there is a card."""
        try:
            result = f_extract.result(timeout=wait)
        except TimeoutError:
            log.warning("extraction timed out")
            return None
        except LLMError as exc:
            log.warning("extraction skipped: %s", exc)
            return None
        except Exception:  # noqa: BLE001
            log.exception("extraction crashed")
            return None
        card = None if result.card.is_empty() else result.card
        with session_factory() as s:
            m = s.get(Message, message_id)
            m.sentiment = result.sentiment
            m.topics = result.topics
            if card:
                m.extraction = card.model_dump(mode="json")
                m.extraction_status = "pending"
            s.commit()
        if not card:
            return None
        return _event(
            {
                "type": "extraction",
                "message_id": str(message_id),
                "card": card.model_dump(mode="json"),
            }
        )

    def stream() -> Iterator[str]:
        yield first_event
        extraction_sent = False
        parts: list[str] = []
        failure: str | None = None
        try:
            for token in llm.stream_reply(prompt):
                parts.append(token)
                yield _event({"type": "token", "text": token})
                if not extraction_sent and f_extract.done():  # card appears as soon as ready
                    extraction_sent = True
                    if ev := finish_extraction(0):
                        yield ev
        except LLMError as exc:
            failure = str(exc)
        except Exception:  # noqa: BLE001
            log.exception("reply stream crashed")
            failure = "The reply failed. Try again."

        if not extraction_sent and (ev := finish_extraction(45)):
            yield ev
        if failure:
            yield _event({"type": "error", "detail": failure})
            return
        text = "".join(parts).strip() or "…"
        with session_factory() as s:
            twin_msg = Message(user_id=user_id, role="twin", text=text, learnable=False)
            s.add(twin_msg)
            s.commit()
            s.refresh(twin_msg)
            yield _event({"type": "done", "message": _out(twin_msg)})

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[MessageOut])
def history(
    user: CurrentUser,
    db: DB,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = None,
) -> list[Message]:
    q = select(Message).where(Message.user_id == user.id)
    if before:
        q = q.where(Message.created_at < before)
    rows = db.scalars(q.order_by(Message.created_at.desc()).limit(limit)).all()
    return list(reversed(rows))


def _pending_message(db: Session, user: User, message_id: uuid.UUID) -> Message:
    msg = db.get(Message, message_id)
    if msg is None or msg.user_id != user.id or msg.extraction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extraction not found")
    if msg.extraction_status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {msg.extraction_status}")
    return msg


def _card_slot(user: User, msg: Message, card: ExtractionCard) -> str:
    """The slot a chat check-in belongs to: what the message said ("this morning"), else
    when it was sent; never a part of today that hasn't started."""
    now = local_now(user)
    msg_day, msg_slot = slot_for(to_local(user, msg.created_at))
    slot = card.checkin.slot or (msg_slot if card.date == msg_day else "evening")
    if not slot_started(card.date, slot, now):
        slot = slot_for(now)[1]
    return slot


@router.post("/extractions/{message_id}/confirm", response_model=ConfirmOut)
def confirm_extraction(
    message_id: uuid.UUID, body: ExtractionCard, user: CurrentUser, db: DB
) -> ConfirmOut:
    """Save the (possibly edited) card. Only now do rows enter the user's data."""
    msg = _pending_message(db, user, message_id)
    if abs((body.date - msg.created_at.date()).days) > 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is too far from the message"
        )
    if body.date > date.today() + timedelta(days=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is in the future")

    # Validate every category before writing anything (all-or-nothing).
    categories = [check_category(db, user, a.category) for a in body.activities]

    saved_checkin: Checkin | None = None
    if not body.checkin.is_empty():
        fields = body.checkin.values()
        slot = _card_slot(user, msg, body)
        saved_checkin = db.scalar(
            select(Checkin).where(
                Checkin.user_id == user.id, Checkin.date == body.date, Checkin.slot == slot
            )
        )
        if saved_checkin is None:
            saved_checkin = Checkin(
                user_id=user.id,
                date=body.date,
                slot=slot,
                checked_at=msg.created_at,
                source="ai",
                **fields,
            )
            db.add(saved_checkin)
        else:  # merge: only overwrite what the user confirmed
            for k, v in fields.items():
                setattr(saved_checkin, k, v)

    saved_acts = []
    for a, cat in zip(body.activities, categories, strict=True):
        act = Activity(
            user_id=user.id,
            date=body.date,
            category=cat,
            title=a.title,
            start_time=a.start_time,
            duration_min=a.duration_min if a.completed else None,
            planned_min=a.duration_min if a.planned and not a.completed else None,
            planned=a.planned,
            completed=a.completed,
            source="ai",
        )
        db.add(act)
        saved_acts.append(act)

    saved_decisions = []
    for d in body.decisions:
        dec = Decision(
            user_id=user.id,
            text=d.text,
            options=d.options,
            choice=d.choice,
            reasoning=d.reasoning,
            source="ai",
        )
        db.add(dec)
        saved_decisions.append(dec)

    msg.extraction = body.model_dump(mode="json")
    msg.extraction_status = "confirmed"
    db.commit()
    for row in [msg, saved_checkin, *saved_acts, *saved_decisions]:
        if row is not None:
            db.refresh(row)

    return ConfirmOut(
        message=MessageOut.model_validate(msg),
        checkin=CheckinOut.model_validate(saved_checkin) if saved_checkin else None,
        activities=[ActivityOut.model_validate(a) for a in saved_acts],
        decisions=[DecisionOut.model_validate(d) for d in saved_decisions],
    )


@router.post("/extractions/{message_id}/dismiss", response_model=MessageOut)
def dismiss_extraction(message_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    msg = _pending_message(db, user, message_id)
    msg.extraction_status = "dismissed"
    db.commit()
    db.refresh(msg)
    return msg
