# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""CRAG scoring regression tests (round 2).

Round-1 live run logged, on every evaluation (including a turn where SEARCHING
loaded 5 SourcePrep docs and the LLM answer was correct):

    action=INCORRECT, confidence=0.20, relevance=0.00, completeness=0.00, freshness=1.00

Root causes:
* ``_keyword_similarity`` split on whitespace only, so ``sshd_config`` in the
  query never matched ``file:host/etc/ssh/sshd_config`` / ``sshd_config.`` in
  the docs -> relevance exactly 0.0.
* ``_llm_completeness_check`` grabbed the FIRST digit in the reply, so a reply
  like ``"0.\\n"`` or reasoning text before the score parsed as 0.0 (or
  "1 of 3" as 1.0).
* The retriever score returned by SourcePrep was dropped before CRAG saw it.

The doc contents below are verbatim SourcePrep results for the round-1 query.
"""
import asyncio
import time

import pytest

from halbert_core.eval.crag import CRAGEvaluator, CRAGAction

QUERY = "what does PermitRootLogin accept in sshd_config"

_SP_DOCS = [
    ("file:host/etc/ssh/sshd_config.d/100-macos.conf",
     "File: file:host/etc/ssh/sshd_config.d/100-macos.conf\nRole: config\nSummary: macOS-specific SSH daemon override enabling PAM authentication, environment variable acceptance, and SFTP subsystem support.",
     0.7071697115898132),
    ("file:host/etc/ssh/sshd_config",
     "Context: Architecture: configuration layer. Subsystem: ssh-server. Patterns: modular-include, convention-over-configuration, first-value-wins\nFile: file:host/etc/ssh/sshd_config\nDomain: auth, network-security, ssh",
     0.6713025569915771),
    ("file:host/etc/ssh/sshd_config",
     "File: file:host/etc/ssh/sshd_config\nRole: config\nSummary: Primary OpenSSH server configuration file defining default security policies, port settings, and including modular overrides from sshd_config.d.",
     0.652409553527832),
    ("file:host/etc/ssh/sshd_config.d/100-macos.conf",
     "Context: Architecture: configuration layer. Subsystem: ssh-daemon. Patterns: drop-in-configuration\nFile: file:host/etc/ssh/sshd_config.d/100-macos.conf\nDomain: ssh, authentication, sftp, system-config",
     0.6473889946937561),
    ("file:host/Library/LaunchAgents/com.maxon.mxnotify.agent.plist",
     "File: file:host/Library/LaunchAgents/com.maxon.mxnotify.agent.plist\nRole: config\nSummary: LaunchAgent configuration that starts the Maxon MxNotify application to handle license and notification services.",
     0.603458821773529),
]


def _ctx_docs(with_score: bool = False):
    """Shape produced by AgentContext.add_context in the SEARCHING state."""
    docs = []
    for source, content, score in _SP_DOCS:
        meta = {"section": "catalogue", "source": "knowledge"}
        if with_score:
            meta["score"] = score
        docs.append({"source": source, "content": content,
                     "metadata": meta, "timestamp": time.time()})
    return docs


class _Reply:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        return _Reply(self.reply)


def _run(evaluator, docs=None):
    return asyncio.run(evaluator.evaluate(QUERY, docs or _ctx_docs(), []))


# --- relevance ---------------------------------------------------------------

def test_keyword_similarity_tokenises_on_punctuation():
    ev = CRAGEvaluator()
    assert ev._keyword_similarity(QUERY, _SP_DOCS[2][1]) > 0.0
    # exact-token behaviour still works
    assert ev._keyword_similarity("port settings", "the port settings here") == 1.0


def test_round1_docs_no_llm_relevance_positive():
    r = _run(CRAGEvaluator())
    assert r.relevance_score > 0.0
    assert r.completeness_score > 0.0
    assert r.confidence > 0.3
    assert r.action != CRAGAction.INCORRECT


def test_retriever_score_in_metadata_lifts_relevance():
    ev = CRAGEvaluator()
    plain = _run(ev, _ctx_docs(with_score=False))
    scored = _run(ev, _ctx_docs(with_score=True))
    assert scored.relevance_score >= plain.relevance_score
    assert scored.relevance_score >= 0.5


# --- completeness parsing -----------------------------------------------------

@pytest.mark.parametrize("reply,expected", [
    ("0.8", 0.8),
    ("0.\n", 0.0),                       # the model really said zero
    ("**0.7**", 0.7),
    ("0.8/1.0", 0.8),
    ("80%", 0.8),
    ("Completeness: 0.6", 0.6),
    ("<think>\nThe docs cover 1 of 3 topics, so maybe 0.9? No, 0.3.\n</think>\n0.3", 0.3),
    ("I'd rate this 0.7 because the docs mostly answer it.", 0.7),
    ("The docs mention 2 files. Score: 0.5", 0.5),
    ("Score: 0.5 out of 1.0", 0.5),
    ("3 of 5", 0.6),
    ("0.5 out of 1.0", 0.5),
    ("I'd give it 7 out of 10", 0.7),
    ("1", 1.0),
    ("no idea", 0.5),                    # unparseable -> neutral default
    ("", 0.5),
])
def test_parse_completeness_score(reply, expected):
    assert CRAGEvaluator._parse_completeness(reply) == pytest.approx(expected)


def test_round1_docs_with_llm_08_gives_sane_confidence():
    llm = _FakeLLM("0.8")
    r = _run(CRAGEvaluator(llm_client=llm))
    assert llm.calls == 1
    assert r.completeness_score == pytest.approx(0.8)
    assert r.relevance_score > 0.0
    assert 0.5 <= r.confidence <= 1.0
    assert r.action in (CRAGAction.CORRECT, CRAGAction.AMBIGUOUS)


def test_llm_think_block_reply_not_parsed_as_leading_digit():
    llm = _FakeLLM("<think>Covers 1 of 3 points.</think>\n0.4")
    r = _run(CRAGEvaluator(llm_client=llm))
    assert r.completeness_score == pytest.approx(0.4)


def test_llm_reply_object_without_content_attr_is_handled():
    class L:
        async def chat(self, messages, **kw):
            return "0.6"
    r = _run(CRAGEvaluator(llm_client=L()))
    assert r.completeness_score == pytest.approx(0.6)


def test_llm_failure_falls_back_to_heuristic_not_zero():
    class Boom:
        async def chat(self, messages, **kw):
            raise RuntimeError("down")
    r = _run(CRAGEvaluator(llm_client=Boom()))
    assert r.completeness_score > 0.0


def test_empty_content_docs_still_score_zero_relevance():
    docs = [{"source": "rag", "content": "", "metadata": {}, "timestamp": time.time()}]
    r = _run(CRAGEvaluator(), docs)
    assert r.relevance_score == 0.0
