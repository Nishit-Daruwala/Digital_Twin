"""Turn template insight sentences into friendlier wording, without trusting the LLM.

The plan: "the LLM turns the evidence JSON into one plain sentence; the numbers come only
from the evidence". We enforce that: every number in the LLM's sentence must appear in the
template (which is built from the evidence), the key numbers must all survive, and causal
language is rejected. Anything that fails falls back to the template.
"""

from __future__ import annotations

import logging
import re

from app.core.config import settings
from app.services.llm import LLMError, LLMNotConfigured, get_llm

log = logging.getLogger("twin.insights")

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_CAUSAL = re.compile(r"\b(causes?|caused|because|leads? to|results? in|makes you)\b", re.I)
_WORD_NUMBERS = {"one": "1", "two": "2", "three": "3"}


def numbers(text: str) -> list[str]:
    out = []
    for m in _NUM.findall(text):
        s = m.rstrip("0").rstrip(".") if "." in m else m
        out.append(s)
    return out


# Timing must survive rewording: "The day after X" reworded as "On days when X" turns a
# next-day pattern into a same-day one, with every number still correct.
_TIMING = [
    (re.compile(r"\btwo days after\b", re.I), re.compile(r"\b(two|2) days (after|later)\b", re.I)),
    (
        re.compile(r"\bthe day after\b", re.I),
        re.compile(r"\b(day after|next day|following day)\b", re.I),
    ),
]
_ANY_DELAY = re.compile(r"\b(day after|next day|following day|days later|days after)\b", re.I)


def same_timing(template: str, candidate: str) -> bool:
    for in_tpl, required in _TIMING:
        if in_tpl.search(template):
            return bool(required.search(candidate))
    # same-day template: the candidate must not invent a delay
    return not _ANY_DELAY.search(candidate)


def verified(template: str, candidate: str) -> bool:
    if not candidate or len(candidate) > 280 or _CAUSAL.search(candidate):
        return False
    if not same_timing(template, candidate):
        return False
    allowed = set(numbers(template))
    # "Two days after" may legitimately become "2 days after" and vice versa
    for w, d in _WORD_NUMBERS.items():
        if re.search(rf"\b{w}\b", template, re.I):
            allowed.add(d)
    got = numbers(candidate)
    if any(n not in allowed for n in got):
        return False  # invented or altered a number
    required = set(numbers(template)) - set(_WORD_NUMBERS.values())
    return required <= set(got)  # and kept every number the finding is about


def reword(templates: dict[str, str]) -> dict[str, tuple[str, str]]:
    """{id: template} -> {id: (text, source)} where source is 'llm' or 'template'."""
    out = {k: (v, "template") for k, v in templates.items()}
    if not templates or not settings.insight_llm_wording:
        return out
    try:
        llm = get_llm()
        result = llm.reword_insights([{"id": k, "sentence": v} for k, v in templates.items()])
    except (LLMNotConfigured, LLMError) as exc:
        log.info("insight wording: using templates (%s)", exc)
        return out
    except Exception:  # noqa: BLE001
        log.exception("insight wording failed")
        return out
    for k, tpl in templates.items():
        cand = (result.get(k) or "").strip()
        if cand and cand != tpl and verified(tpl, cand):
            out[k] = (cand, "llm")
        elif cand and cand != tpl:
            log.warning("insight wording rejected (numbers/causality check): %r", cand)
    return out
