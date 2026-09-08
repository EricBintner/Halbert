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


def make_speech_summarizer(session_id: str = "") -> Callable[[str], str]:
    """A ``summarizer`` callable for :func:`.tts_quality.adapt_for_speech`.

    Args:
        session_id: The turn's session id, carried to the utility-slot
            ladder so a session-scoped utility_model pin resolves.

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
        try:
            from ..model import utility_slot
            resolved = utility_slot.resolve_aux_model(
                session_id=session_id,
                task=SUMMARY_TASK,
                prefer_fast=True,
            )
        except Exception as e:
            logger.debug("speech summarizer: model resolution failed (%s)", e)
            return text
        if resolved is None:
            logger.debug(
                "speech summarizer: no utility model available — "
                "original spoken copy kept"
            )
            return text
        try:
            from ..model import client
            result = client.call_llm_chat(
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
        except Exception as e:
            logger.debug("speech summarizer: request failed (%s)", e)
            return text
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