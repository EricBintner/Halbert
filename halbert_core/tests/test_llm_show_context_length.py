# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ollama's /api/show carries TWO different context numbers and they must not
be confused (post-merge follow-up, issue 1).

Verified against a live daemon while writing this file:

  one installed model:  architecture context length (model_info)  = 262144
                        parameters block                num_ctx =   8192

The ``parameters`` block is the *Modelfile default* — the window the model is
loaded with unless the caller says otherwise. ``model_info["<arch>.context_length"]``
is the *architecture maximum* — the largest window the weights can hold.

Only the second is a legitimate cap for ``compute_num_ctx``. Capping num_ctx at
the first reproduces, by construction, the silent head-truncation that setting
num_ctx exists to prevent: a 262144-token model would be pinned at 8192.

Also verified live: ``llm.context_length`` and ``general.context_length`` — the
two keys the previous fallback looked for — are emitted by no model. Every real
payload spells it ``<general.architecture>.context_length``.
"""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import llm


def _show(payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    return r


ARCH_MAX = {
    "model_info": {
        "general.architecture": "archfam",
        "archfam.context_length": 262144,
        "archfam.embedding_length": 4096,
    },
    # The same payload also carries the Modelfile's much smaller default.
    "parameters": "num_ctx                        8192\ntemperature 1",
}


def test_context_tokens_is_the_architecture_maximum_not_the_modelfile_default():
    with patch.object(llm.requests, "post", return_value=_show(ARCH_MAX)):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["context_tokens"] == 262144
    assert detail["context_window"] == "262k"
    # The Modelfile default is still reported — separately, and never as the max.
    assert detail["num_ctx_default"] == 8192


def test_architecture_key_is_found_even_when_general_architecture_is_missing():
    """Some payloads omit general.architecture; the '<something>.context_length'
    key is still the architecture maximum."""
    with patch.object(llm.requests, "post", return_value=_show({
        "model_info": {"archfam2.context_length": 131072},
    })):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["context_tokens"] == 131072


def test_embedding_length_is_not_mistaken_for_a_context_length():
    with patch.object(llm.requests, "post", return_value=_show({
        "model_info": {
            "general.architecture": "archfam2",
            "archfam2.embedding_length": 4096,
            "archfam2.context_length": 32768,
        },
    })):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["context_tokens"] == 32768


def test_modelfile_num_ctx_is_the_last_resort_when_model_info_says_nothing():
    """Older daemons return no model_info at all. The Modelfile default is then
    the only number there is — better than reporting nothing — but it is used
    for display only, never as a cap (see test_num_ctx.py)."""
    with patch.object(llm.requests, "post", return_value=_show({
        "parameters": "num_ctx 4096",
    })):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["context_tokens"] == 4096
    assert detail["num_ctx_default"] == 4096


def test_a_show_that_says_nothing_reports_nothing():
    with patch.object(llm.requests, "post", return_value=_show({})):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["context_tokens"] == 0
    assert detail["num_ctx_default"] == 0
    assert detail["context_window"] == ""


def test_proxy_models_publishes_the_window_to_the_num_ctx_cap():
    """/api/tags already carries details.context_length for most models, so the
    listing the picker does anyway is a free producer for compute_num_ctx's cap.
    Nothing else in the tree ever set it (issue 1: 'a ceiling with no producer').

    A listing is weaker evidence than /api/show, though: it is one unlabelled
    number with nothing to say whether it is the architecture maximum or the
    window the model is loaded with, and a producer may only ever RAISE a
    window. So a listing settles what cannot cap anything, and here — with
    /api/show unavailable — that is all it settles. The small model falls back
    to the fallback ceiling, which is what it had before any of this work,
    rather than to a number nobody corroborated.
    """
    import halbert_core.model.client as mc

    def _get(url, **kwargs):
        assert url.endswith("/api/tags")
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"models": [
            {"name": "big:35b", "details": {"context_length": 262144}},
            {"name": "small:1b", "details": {"context_length": 8192}},
        ]}
        return r

    with patch.object(llm.requests, "get", side_effect=_get), \
         patch.object(llm.requests, "post", side_effect=OSError("no /api/show")):
        mc._MODEL_MAX_CACHE.clear()
        out = llm.proxy_models(llm.LLMProxyRequest(provider="ollama", url="http://localhost:11434"))

    try:
        assert mc.model_context_limit("big:35b") == 262144
        assert mc.model_context_limit("small:1b") is None
        # Both are still DISPLAYED as the daemon reported them.
        shown = {d["name"]: d["context_tokens"] for d in out["data"]["model_details"]}
        assert shown == {"big:35b": 262144, "small:1b": 8192}
    finally:
        mc._MODEL_MAX_CACHE.clear()


def test_show_corroborates_a_window_small_enough_to_cap():
    """The enrichment pass the picker runs anyway is what turns the listing's
    small number into a cap: /api/show labels it as the architecture maximum."""
    import halbert_core.model.client as mc

    def _get(url, **kwargs):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"models": [{"name": "small:1b", "details": {"context_length": 8192}}]}
        return r

    with patch.object(llm.requests, "get", side_effect=_get), \
         patch.object(llm.requests, "post", return_value=_show({
             "model_info": {"general.architecture": "archfam", "archfam.context_length": 8192},
         })):
        mc._MODEL_MAX_CACHE.clear()
        llm.proxy_models(llm.LLMProxyRequest(provider="ollama", url="http://localhost:11434"))

    try:
        assert mc.model_context_limit("small:1b") == 8192
    finally:
        mc._MODEL_MAX_CACHE.clear()


def test_a_vision_towers_context_length_is_not_the_models_window():
    """A payload can carry a projector beside the language model. Reading
    whichever ``*.context_length`` came first published the vision tower's 77 as
    the model's maximum — and since a producer may only ever raise a window,
    that pinned num_ctx at the 4096 floor for the life of the process."""
    with patch.object(llm.requests, "post", return_value=_show({
        "model_info": {
            "general.architecture": "archfam",
            "vistower.vision.context_length": 77,
            "archfam.embedding_length": 4096,
        },
        "parameters": "num_ctx 8192",
    })):
        detail = llm._ollama_show_detail("http://localhost:11434", "m")
    assert detail["architecture_tokens"] == 0        # nothing may cap on this
    assert detail["context_tokens"] == 8192          # the Modelfile default, for display


def test_show_upgrades_a_window_tags_understated():
    """The mlx-format models on the live daemon carry no details.context_length
    in /api/tags but do report the architecture length in /api/show."""
    import halbert_core.model.client as mc

    def _get(url, **kwargs):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"models": [{"name": "mlx:27b", "details": {}}]}
        return r

    with patch.object(llm.requests, "get", side_effect=_get), \
         patch.object(llm.requests, "post", return_value=_show(ARCH_MAX)):
        mc._MODEL_MAX_CACHE.clear()
        llm.proxy_models(llm.LLMProxyRequest(provider="ollama", url="http://localhost:11434"))

    try:
        assert mc.model_context_limit("mlx:27b") == 262144
    finally:
        mc._MODEL_MAX_CACHE.clear()


def test_a_modelfile_default_is_never_published_as_the_cap():
    """The trap, guarded at the boundary: an old daemon that reports only the
    Modelfile's num_ctx still gets that number DISPLAYED, but it must never
    reach the num_ctx cap. Publishing 4096 there would pin the model at 4096
    and silently truncate the head of every larger prompt."""
    import halbert_core.model.client as mc

    def _get(url, **kwargs):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"models": [{"name": "old-daemon:7b", "details": {}}]}
        return r

    with patch.object(llm.requests, "get", side_effect=_get), \
         patch.object(llm.requests, "post", return_value=_show({"parameters": "num_ctx 4096"})):
        mc._MODEL_MAX_CACHE.clear()
        out = llm.proxy_models(llm.LLMProxyRequest(provider="ollama", url="http://localhost:11434"))

    try:
        assert out["data"]["model_details"][0]["context_tokens"] == 4096   # shown
        assert mc.model_context_limit("old-daemon:7b") is None             # never capped
    finally:
        mc._MODEL_MAX_CACHE.clear()
