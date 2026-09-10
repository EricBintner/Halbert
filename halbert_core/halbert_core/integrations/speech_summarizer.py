# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 C2: the speech summarizer seam (Hermes TTS-pipeline pattern).

A long reply read aloud in full is a monologue the listener has to hold
in their head: Piper reads roughly fifteen characters a second, so a
1200-character reply is eighty seconds of unstructured speech. Screen
readers of the same reply can re-read and skim; a listener cannot. So
the spoken copy of a long prose reply is summarized to one or two
sentences by a cheap model before synthesis — while the on-screen text
keeps every word.

The seam is :func:`make_speech_summarizer`: it returns a callable with
the ``summarizer`` signature :func:`.tts_quality.adapt_for_speech`
reserves (packet 04 C1's recorded hook). The callable is fail-soft by
construction — the model is *summarizing*, never gatekeeping:

  * the length gate is deterministic and runs first (the model never
    sees short text; see the threshold constant below);
  * the model is resolved per attempt through the utility-slot ladder
    (:func:`.utility_slot.resolve_aux_model`, ``task="tts_summarization"``,
    ``prefer_fast=True``) — an unset utility slot falls back to the
    operator's chat slot or to nothing, per the ladder's own contract;
  * a resolution miss, a request error, an empty response, or a summary
    that is not strictly shorter than the input all return the ORIGINAL
    text. Nothing here raises, so nothing can break speech.

The model call goes through the one existing client path
(:func:`.client.call_llm_chat`) — no new provider path, and the GPU
advisory lock that path takes keeps the summarization from contending
with a concurrent local generation.

**Dormant, and known to be** (A10 refuter finding, FD-4). This seam's
600-character gate sits BEHIND the engine's VoiceRiskPolicy word cap,
which is 12–35 words — a few hundred characters at most. So no real
voice turn ever reaches the gate, and this module has never summarized
anything in production. FD-4's ruling is to keep the engine's cap as the
ceiling, wire the budget hint into the prompt instead (A10-G7), and keep
this correct but dormant rather than deleting it or raising the cap to
give it work. It is correct here so that if the cap ever moves, what
wakes up is right: off the event loop, local-only on a secure turn, and
retried once through the ladder rather than silently giving up.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("halbert.integrations.speech_summarizer")

__all__ = [
    "SPOKEN_SUMMARY_THRESHOLD_CHARS",
    "SUMMARY_TASK",
    "make_speech_summarizer",
]

#: A spoken reply at or below this many characters (after the C1
#: code-noise strip) is spoken in full; above it, the voice summarizes.
#: Piper reads ~15 chars/s, so 600 chars is ~40 s of speech — about the
#: longest unstructured monologue a listener follows without effort, and
#: comfortably past the point where "I'll give you the short version"
#: beats the full read. The same constant is both gates the packet
#: requires: short text is never summarized, and text already within
#: the spoken budget is never summarized. Deterministic on purpose —
#: the model only summarizes, it never decides whether to.
SPOKEN_SUMMARY_THRESHOLD_CHARS = 600

#: The provenance tag recorded on the utility-slot ladder run (it names
#: the log line, never the model).
SUMMARY_TASK = "tts_summarization"

#: Side-task budget: a 1-2 sentence summary needs seconds, not minutes,
#: and speech must not wait on a stuck endpoint.
_SUMMARY_TIMEOUT_S = 12

#: Ceiling on the generated summary, in tokens — a 1-2 sentence spoken
#: summary is well under this; the cap keeps a runaway completion from
#: out-living the turn it serves.
_SUMMARY_NUM_PREDICT = 160

_SUMMARY_SYSTEM_PROMPT = (
    "You condense a spoken reply. Reply with ONLY a spoken-form summary "
    "of the text: one or two short sentences, plain conversational prose, "
    "no markdown, no lists, no quotes, no preamble. Keep the key outcome "
    "and any single most important detail; drop everything else."
)


def _resolve_aux(**kwargs):
    """The utility-slot ladder, behind one name (a seam for the tests).

    ``require_local`` and ``exclude`` are passed through when the slot
    accepts them. R-13 adds both to ``resolve_aux_model``; until it
    lands this degrades rather than raising, so the two packets do not
    have to land in the same commit to both be correct.
    """
    from ..model import utility_slot

    try:
        return utility_slot.resolve_aux_model(**kwargs)
    except TypeError:
        pruned = {
            k: v for k, v in kwargs.items()
            if k not in ("require_local", "exclude")
        }
        if pruned.keys() == kwargs.keys():
            raise
        logger.debug(
            "utility slot does not accept require_local/exclude yet; "
            "resolving without them"
        )
        return utility_slot.resolve_aux_model(**pruned)


def _call_llm(**kwargs):
    """The one model client path, behind one name (a seam for the tests)."""
    from ..model import client

    return client.call_llm_chat(**kwargs)


def make_speech_summarizer(
    session_id: str = "", secure: bool = False,
) -> Callable[[str], str]:
    """A ``summarizer`` callable for :func:`.tts_quality.adapt_for_speech`.

    Args:
        session_id: The turn's session id, carried to the utility-slot
            ladder so a session-scoped utility_model pin resolves.
        secure: Whether this turn's context was latched secure. A14-G4
            (summarizer half): the spoken copy of a secure turn is the
            same material the turn was restricted to local models for,
            and handing it to a cloud utility slot to be shortened would
            undo that in one line. ``require_local`` on every rung.

    Returns:
        A callable ``summarize(text) -> str`` that returns the summary
        for long spoken text and the ORIGINAL text for everything else —
        short input, unset utility slot, request error, empty response,
        or a summary not strictly shorter than the input. It never
        raises: summarization must never break speech.
    """

    def summarize(text: str) -> str:
        if not text:
            return text
        # Deterministic gate, first and always: short text is spoken in
        # full, and the model is never consulted for it.
        if len(text) <= SPOKEN_SUMMARY_THRESHOLD_CHARS:
            return text
        # A14-G7 (summarizer half): a pick that ERRORS is excluded and
        # the ladder is asked once more. One retry, not a loop: a second
        # failure is a fact about the host, not about the pick, and a
        # summarizer that keeps trying is a summarizer that keeps the
        # listener waiting.
        result = None
        excluded: tuple = ()
        for attempt in (1, 2):
            try:
                resolved = _resolve_aux(
                    session_id=session_id,
                    task=SUMMARY_TASK,
                    prefer_fast=True,
                    require_local=bool(secure),
                    exclude=excluded,
                )
            except Exception as e:
                logger.debug(
                    "speech summarizer: model resolution failed (%s)", e)
                return text
            if resolved is None:
                logger.debug(
                    "speech summarizer: no utility model available — "
                    "original spoken copy kept"
                )
                return text
            try:
                result = _call_llm(
                    endpoint=resolved.url,
                    model=resolved.model,
                    messages=[
                        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    provider=resolved.provider,
                    stream=False,
                    timeout=_SUMMARY_TIMEOUT_S,
                    options={
                        "temperature": 0.2,
                        "num_predict": _SUMMARY_NUM_PREDICT,
                    },
                    api_key=resolved.api_key or "",
                )
                break
            except Exception as e:
                logger.debug(
                    "speech summarizer: request failed on %s (%s)",
                    resolved.model, e)
                if attempt == 2:
                    return text
                excluded = tuple(excluded) + (resolved.model,)
        summary = " ".join(((result or {}).get("content") or "").split())
        # Compared against the collapsed input: whitespace normalization
        # alone is not a summary, so it must not count as "shorter".
        compact = " ".join(text.split())
        if not summary or len(summary) >= len(compact):
            logger.debug(
                "speech summarizer: unusable summary — original spoken copy kept"
            )
            return text
        return summary

    return summarize


async def make_async_speech_summarizer(
    session_id: str = "", secure: bool = False,
):
    """The summarizer as an awaitable, run off the event loop (A14 bug 3).

    The sync callable does a blocking HTTP request and, one layer down,
    a catalog probe — both INLINE on the loop, so a slow or hung utility
    model froze every other session's turn as well as its own. Callers
    on the loop take this; the sync form stays for callers that are not.
    """
    import asyncio

    summarize = make_speech_summarizer(session_id, secure=secure)

    async def _summarize(text: str) -> str:
        return await asyncio.to_thread(summarize, text)

    return _summarize
