# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A10: options.num_ctx is set on every Ollama call, sized from the
prompt, computed once per model per process (spec §7)."""

import asyncio
import json
import logging
import time

import pytest
from unittest.mock import MagicMock, patch

import halbert_core.model.client as mc
from halbert_core.model.client import compute_num_ctx, num_ctx_for_model, estimate_prompt_tokens, call_llm_chat


def _reset_caches():
    mc._NUM_CTX_CACHE.clear()
    mc._NUM_CTX_HIGH_WATER_AT.clear()
    mc._MODEL_MAX_CACHE.clear()
    mc._CONTEXT_PROBED_ENDPOINTS.clear()
    mc._CONTEXT_ENDPOINT_MODELS.clear()
    mc._CONTEXT_SHOWN_MODELS.clear()
    mc._CONTEXT_PROBE_THREADS.clear()


def _join_probes(timeout=5.0):
    """Wait for any discovery started on a worker thread.

    The streaming path never waits for the probe — that is the point of it —
    so a test that wants to see what the probe learned has to say so, and a
    test that does not still has to join before the stubs come off, or a
    background thread outlives the patch and reaches a real daemon.
    """
    for thread in list(mc._CONTEXT_PROBE_THREADS.values()):
        thread.join(timeout)
        assert not thread.is_alive(), "context probe thread did not finish"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every per-process num_ctx cache starts and ends empty.

    ``requests.get`` and ``requests.post`` are stubbed out for the whole module
    because the endpoint probe reaches for /api/tags and, for a window small
    enough to cap anything, /api/show; a unit test must not depend on a daemon
    being up. Tests that exercise the probe patch them again, and the inner
    patch wins.
    """
    _reset_caches()
    with patch.object(mc.requests, "get", side_effect=OSError("no network in unit tests")), \
         patch.object(mc.requests, "post", side_effect=OSError("no network in unit tests")):
        try:
            yield
        finally:
            _join_probes()
    _reset_caches()


def _response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_compute_num_ctx_clamps_and_rounds():
    assert compute_num_ctx(10, 100, None) == 4096            # floor
    assert compute_num_ctx(3000, 1024, None) == 5120         # 4536 -> 5120
    assert compute_num_ctx(4096, 1536, None) == 6144         # exact multiple stays
    assert compute_num_ctx(100_000, 1024, None) == 32768     # default ceiling
    assert compute_num_ctx(100_000, 1024, 8192) == 8192      # model_max caps
    assert compute_num_ctx(10, 10, 2048) == 4096             # floor beats a tiny model_max


def test_per_model_cache_grows_and_holds_across_a_turn():
    """Renamed from "...never_shrinks": every assertion below is unchanged, but
    the window is no longer pinned for the life of the process — see
    test_a_one_off_huge_prompt_does_not_pin_the_window_forever."""
    assert num_ctx_for_model("m:7b", 3000, 1024) == 5120
    assert num_ctx_for_model("m:7b", 10, 10) == 5120
    assert num_ctx_for_model("m:7b", 9000, 1024) == 11264
    assert num_ctx_for_model("m:7b", 10, 10) == 11264
    assert num_ctx_for_model("other", 10, 10) == 4096


def test_estimate_counts_messages_and_tools():
    msgs = [{"role": "user", "content": "x" * 400}]
    tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
    assert estimate_prompt_tokens(msgs, None) == 100
    assert estimate_prompt_tokens(msgs, tools) == 100 + len(json.dumps(tools)) // 4
    assert estimate_prompt_tokens([{"role": "user", "content": [{"type": "text", "text": "abcd" * 10}]}], None) > 0


def test_estimate_counts_images_and_tool_calls():
    """Review finding (A10): a text-only estimate ignores the ``images`` a
    vision call attaches to a message and the ``tool_calls`` an assistant
    turn attaches instead of ``content`` — both carry real prompt tokens
    that must not silently estimate to zero."""
    baseline = estimate_prompt_tokens([{"role": "user", "content": "caption this"}], None)
    one_image = estimate_prompt_tokens(
        [{"role": "user", "content": "caption this", "images": ["base64..."]}], None
    )
    two_images = estimate_prompt_tokens(
        [{"role": "user", "content": "caption this", "images": ["a", "b"]}], None
    )
    assert one_image - baseline == mc._NUM_CTX_IMAGE_TOKENS
    assert two_images - baseline == 2 * mc._NUM_CTX_IMAGE_TOKENS

    empty_content = estimate_prompt_tokens([{"role": "assistant", "content": None}], None)
    with_tool_calls = estimate_prompt_tokens(
        [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "1", "function": {"name": "search", "arguments": '{"q": "x" * 200}'}}],
        }],
        None,
    )
    assert with_tool_calls > empty_content


def test_ollama_chat_payload_carries_num_ctx():
    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "hi"}])
    opts = post.call_args.kwargs["json"]["options"]
    assert opts == {"num_predict": 1024, "temperature": 0.7, "num_ctx": 4096}

    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "y" * 40_000}], options={"num_predict": 1024})
    assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 12288   # 10000+512+1024 -> 12288

    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="example-model:latest",
                      messages=[{"role": "user", "content": "hi"}], options={"num_ctx": 8192})
    assert post.call_args.kwargs["json"]["options"]["num_ctx"] == 8192   # explicit override wins


def test_ollama_chat_warns_when_ceiling_clamp_still_leaves_prompt_over_num_ctx(caplog):
    """Review finding (A10): once the prompt is so large that even the 32768
    default ceiling can't hold it, num_ctx_for_model silently returns the
    ceiling instead of what the prompt needs. Ollama then truncates the head
    of the prompt with nothing logged. _do_llm_call must warn in that case."""
    with caplog.at_level(logging.WARNING, logger="halbert.model.client"):
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response({"message": {"content": "hi"}})):
            call_llm_chat(endpoint="http://localhost:11434", model="huge-prompt-model:latest",
                          messages=[{"role": "user", "content": "y" * 200_000}])
    assert any(
        "huge-prompt-model:latest" in r.getMessage() and "num_ctx" in r.getMessage()
        for r in caplog.records
    )


def test_ollama_chat_payload_num_ctx_accounts_for_images():
    """Same review finding, through the real Ollama call path: a vision
    prompt with an image must size num_ctx larger than the identical prompt
    without one, or the image inflates the true prompt with nothing counted
    for it — the exact silent head-truncation A10 exists to prevent."""
    # Enough images to clear the 4096 floor both with and without the fix
    # would otherwise sit under (a single image's 768-token allowance still
    # rounds back down to the floor), so the comparison actually exercises
    # the fix instead of two floored values that happen to be equal.
    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="vision-model:latest",
                      messages=[{"role": "user", "content": "describe", "images": ["x" * 4000] * 6}])
    with_image_ctx = post.call_args.kwargs["json"]["options"]["num_ctx"]

    mc._NUM_CTX_CACHE.clear()
    with patch("halbert_core.model.client.requests.post", return_value=_response({"message": {"content": "hi"}})) as post:
        call_llm_chat(endpoint="http://localhost:11434", model="vision-model:latest",
                      messages=[{"role": "user", "content": "describe"}])
    without_image_ctx = post.call_args.kwargs["json"]["options"]["num_ctx"]

    assert with_image_ctx > without_image_ctx


def test_openai_payload_has_no_options():
    with patch("halbert_core.model.client.requests.post",
               return_value=_response({"choices": [{"message": {"content": "ok"}}]})) as post:
        call_llm_chat(endpoint="https://api.example.test", model="hosted",
                      messages=[{"role": "user", "content": "hi"}], provider="openai")
    assert "options" not in post.call_args.kwargs["json"]


# --- streaming payloads (OllamaClient and the dashboard adapter) -------------

class _Lines:
    def __init__(self, lines):
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _FakeResp:
    status = 200

    def __init__(self):
        # Content and the done flag on separate lines: the dashboard adapter
        # breaks on ``done`` before appending that line's content, so a
        # single done:true line would yield nothing.
        self.content = _Lines([
            b'{"message":{"content":"hi"},"done":false}\n',
            b'{"message":{"content":""},"done":true}\n',
        ])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def text(self):
        return ""

    async def json(self):
        return {"message": {"content": "hi"}}


class _FakeSession:
    captured = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, **k):
        _FakeSession.captured["json"] = json
        return _FakeResp()


@pytest.fixture
def fake_aiohttp(monkeypatch):
    _FakeSession.captured.clear()
    monkeypatch.setattr("aiohttp.ClientSession", _FakeSession)
    return _FakeSession.captured


@pytest.mark.asyncio
async def test_ollama_client_chat_and_stream_carry_num_ctx(fake_aiohttp):
    from halbert_core.agents.llm_client import OllamaClient
    client = OllamaClient(model="example-model:latest")
    assert [c async for c in client.stream([{"role": "user", "content": "hi"}])] == ["hi"]
    assert fake_aiohttp["json"]["options"] == {"temperature": 0.7, "num_predict": 2048, "num_ctx": 4096}
    await client.chat([{"role": "user", "content": "hi"}])
    assert fake_aiohttp["json"]["options"]["num_ctx"] == 4096


fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "example-model:latest")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model", lambda: (None, None, None))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model", lambda: (None, "http://localhost:11434"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_adapter_stream_has_num_ctx_and_bounded_num_predict(adapter, fake_aiohttp):
    adapter.max_tokens = 8192
    assert "".join([c async for c in adapter.stream([{"role": "user", "content": "hi"}])]) == "hi"
    opts = fake_aiohttp["json"]["options"]
    assert opts["num_ctx"] >= 4096 and opts["num_ctx"] % 1024 == 0
    assert opts["num_predict"] <= opts["num_ctx"] - 512 and opts["num_predict"] <= 8192


@pytest.mark.asyncio
async def test_adapter_stream_warns_when_ceiling_clamp_still_leaves_prompt_over_num_ctx(adapter, fake_aiohttp, caplog):
    """Same review finding as above, for the dashboard adapter's stream
    payload, which computes num_ctx independently of _do_llm_call."""
    with caplog.at_level(logging.WARNING, logger="halbert.dashboard.routes.agent"):
        result = "".join([c async for c in adapter.stream([{"role": "user", "content": "y" * 200_000}])])
    assert result == "hi"
    assert any("num_ctx" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_adapter_planning_chat_uses_num_predict_1024(adapter):
    with patch("halbert_core.model.client.call_llm_chat") as chat:
        chat.return_value = {"content": "ok", "tool_calls": []}
        await adapter.chat([{"role": "user", "content": "plan"}], tools=[])
    assert chat.call_args.kwargs["options"]["num_predict"] == 1024


def test_send_message_request_bounds_max_tokens():
    """Review finding (A10): num_ctx_for_model's per-model cache only grows
    and is process-global, so an unbounded max_tokens field would let one
    request pin num_ctx at the ceiling for that model for the rest of the
    process's life. The request boundary must reject that, while still
    allowing every value the frontend's own Performance Tweaks control
    offers (up to 32768 — see Settings.tsx)."""
    import pydantic
    from halbert_core.dashboard.routes.agent import SendMessageRequest

    SendMessageRequest(message="hi", max_tokens=32768)  # the UI's own max: allowed
    SendMessageRequest(message="hi")  # default: allowed
    with pytest.raises(pydantic.ValidationError):
        SendMessageRequest(message="hi", max_tokens=1_000_000)
    with pytest.raises(pydantic.ValidationError):
        SendMessageRequest(message="hi", max_tokens=0)


# ── issue 1: the ceiling now has a producer, and it is the right number ──────
#
# `compute_num_ctx` clamps to `model_max or the default ceiling`, and until now
# nothing in the tree ever supplied `model_max`, so every model got 32768 —
# roughly +2GB of KV cache for a 7B against the no-options-block behaviour that
# shipped before, which is enough to OOM a GPU that was fine before.
#
# The producer is the model's ARCHITECTURE maximum, never the Modelfile's
# `num_ctx` default. See tests/test_llm_show_context_length.py for why, and for
# the live payload that proves the two differ by 32x on a real model.


def _tags(models):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"models": models}
    return resp


def _show(model_info):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"model_info": model_info}
    return resp


def _arch(tokens, arch="archfam"):
    return {"general.architecture": arch, f"{arch}.context_length": tokens}


def _recorder(**kwargs):
    """A stub that RECORDS calls instead of raising on them.

    A ``side_effect=AssertionError(...)`` tripwire cannot fail here: the probe
    ends in ``except Exception``, AssertionError is an Exception, and the
    tripwire is swallowed along with every other network error — so the test
    passes whether or not the thing it forbids happened. Four tests in this
    file were written that way; ``assert probe.call_count == 0`` after the
    fact is what actually holds.
    """
    kwargs.setdefault("side_effect", OSError("this call was not supposed to happen"))
    return MagicMock(**kwargs)


class TestModelContextLimit:

    def test_unknown_until_something_reports_it(self):
        assert mc.model_context_limit("never-seen:7b") is None

    def test_a_remembered_window_caps_num_ctx_below_the_default_ceiling(self):
        """The point of the whole fix: a model whose real window is 8192 must
        not be asked for 32768 of KV cache it cannot use."""
        mc.remember_model_context_limit("small-window:7b", 8192)
        assert num_ctx_for_model("small-window:7b", 100_000, 1024) == 8192

    def test_a_large_window_is_still_bounded_by_the_default_ceiling(self):
        """model_max raises no ceiling on its own: 262144 tokens of KV cache is
        not something to allocate because the architecture would allow it."""
        mc.remember_model_context_limit("big-window:35b", 262144)
        assert num_ctx_for_model("big-window:35b", 100_000, 1024) == 32768

    def test_a_producer_can_only_ever_raise_a_known_window_never_lower_it(self):
        """Structural guard against the trap this issue is about: if some
        producer ever hands us a Modelfile default again, it cannot pull an
        already-known architecture maximum down and start truncating prompts."""
        mc.remember_model_context_limit("m:7b", 262144)
        mc.remember_model_context_limit("m:7b", 8192)
        assert mc.model_context_limit("m:7b") == 262144

    def test_a_nonsense_window_is_ignored(self):
        for bad in (0, -1, None, "8192", 3.5):
            mc.remember_model_context_limit("junk:7b", bad)
        assert mc.model_context_limit("junk:7b") is None

    def test_one_round_trip_settles_every_window_that_cannot_cap_anything(self):
        """A listing answers for every model on the daemon at once, and a
        window at or above the fallback ceiling needs nothing more: it cannot
        make num_ctx smaller than the ceiling would have anyway."""
        with patch.object(mc.requests, "get", return_value=_tags([
            {"name": "a:7b", "details": {"context_length": 131072}},
            {"name": "c:70b", "details": {"context_length": 1048576}},
        ])) as get:
            assert mc.model_context_limit("a:7b", "http://localhost:11434") == 131072
        assert get.call_count == 1
        # c came free with the same round trip, and a second lookup adds none.
        probe = _recorder()
        with patch.object(mc.requests, "get", probe), patch.object(mc.requests, "post", probe):
            assert mc.model_context_limit("c:70b", "http://localhost:11434") == 1048576
        assert probe.call_count == 0

    def test_a_window_small_enough_to_cap_is_confirmed_against_api_show(self):
        """The listing's number is one unlabelled integer: nothing in it says
        whether it is the architecture maximum or the window the model is
        loaded with by default, and those differ by 32x on a real model. A
        producer may only ever RAISE a window, so trusting the small one
        verbatim is not a guess that gets corrected later — it is a permanent
        cap. /api/show says which number it is."""
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "b:1b", "details": {"context_length": 8192}}]
        )), patch.object(mc.requests, "post", return_value=_show(_arch(8192))) as post:
            assert mc.model_context_limit("b:1b", "http://localhost:11434") == 8192
        assert post.call_count == 1
        assert post.call_args.args[0] == "http://localhost:11434/api/show"
        assert post.call_args.kwargs["json"] == {"name": "b:1b"}

    def test_a_listing_that_understates_the_window_cannot_cap_the_model(self):
        """The failure this guards: a daemon build whose listing reports the
        LOADED window (the Modelfile default) rather than the architecture
        maximum. Taken verbatim it would pin a 262144-token model at 8192 for
        the life of the process and truncate the head of every larger prompt —
        the exact bug the num_ctx work exists to prevent."""
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "big:35b", "details": {"context_length": 8192}}]
        )), patch.object(mc.requests, "post", return_value=_show(_arch(262144))):
            assert mc.model_context_limit("big:35b", "http://localhost:11434") == 262144

    def test_a_window_no_listing_reported_is_still_found(self):
        """The safetensors/MLX entries on the live daemon carry no
        details.context_length at all; /api/show has it."""
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "mlx:27b", "details": {}}]
        )), patch.object(mc.requests, "post", return_value=_show(_arch(262144))):
            assert mc.model_context_limit("mlx:27b", "http://localhost:11434") == 262144

    def test_api_show_is_asked_once_per_model_however_many_calls_follow(self):
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "b:1b", "details": {"context_length": 8192}}]
        )), patch.object(mc.requests, "post", return_value=_show({})) as post:
            assert mc.model_context_limit("b:1b", "http://localhost:11434") is None
            assert mc.model_context_limit("b:1b", "http://localhost:11434") is None
        assert post.call_count == 1

    def test_a_show_that_failed_is_asked_again_later(self):
        """Same reason the endpoint is not latched: a daemon restarting when
        the question was put must not silence the answer for the life of the
        process."""
        clock = [1000.0]
        with patch.object(mc.time, "monotonic", lambda: clock[0]), \
             patch.object(mc.requests, "get", return_value=_tags(
                 [{"name": "b:1b", "details": {"context_length": 8192}}]
             )), patch.object(mc.requests, "post", side_effect=ConnectionError("restarting")):
            assert mc.model_context_limit("b:1b", "http://localhost:11434") is None

        clock[0] += mc._CONTEXT_PROBE_RETRY_SECONDS + 1
        with patch.object(mc.time, "monotonic", lambda: clock[0]), \
             patch.object(mc.requests, "get", return_value=_tags(
                 [{"name": "b:1b", "details": {"context_length": 8192}}]
             )), patch.object(mc.requests, "post", return_value=_show(_arch(8192))):
            assert mc.model_context_limit("b:1b", "http://localhost:11434") == 8192

    def test_a_model_the_listing_never_named_costs_no_show(self):
        """An endpoint that is not Ollama at all (this path is also the
        llamacpp/mlx fallback) must cost one failed request, not two."""
        probe = _recorder()
        with patch.object(mc.requests, "get", side_effect=OSError("refused")), \
             patch.object(mc.requests, "post", probe):
            assert mc.model_context_limit("x:7b", "http://nowhere.test") is None
        assert probe.call_count == 0

    def test_an_endpoint_is_probed_once_even_when_it_answers_nothing(self):
        """A daemon that is down, not Ollama at all (this path is also the
        llamacpp/mlx fallback), or serving a model /api/tags does not list, must
        cost one failed round trip per retry window — not one per call."""
        with patch.object(mc.requests, "get", side_effect=OSError("refused")) as get:
            assert mc.model_context_limit("x:7b", "http://nowhere.test") is None
            assert mc.model_context_limit("x:7b", "http://nowhere.test") is None
            assert mc.model_context_limit("y:7b", "http://nowhere.test") is None
        assert get.call_count == 1

    def test_a_daemon_that_comes_up_later_is_still_discovered(self, monkeypatch):
        """The probe latch was permanent: an endpoint was written off before
        the request went out and never retried, so a Halbert started before
        Ollama — or running across an Ollama restart, which is the normal case
        on a real install — never learned any model's window again for the life
        of the process. On a headless install this probe is the only producer
        there is; the picker's listing never runs."""
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])

        with patch.object(mc.requests, "get", side_effect=ConnectionError("refused")):
            assert mc.model_context_limit("m:7b", "http://localhost:11434") is None

        clock[0] += mc._CONTEXT_PROBE_RETRY_SECONDS + 1
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "m:7b", "details": {"context_length": 131072}}]
        )) as get:
            assert mc.model_context_limit("m:7b", "http://localhost:11434") == 131072
        assert get.call_count == 1

    def test_no_endpoint_means_no_probe(self):
        """"Where should I ask?" is not optional-with-a-guess.

        Both production callers name an endpoint now, and a caller that omits
        it must get None rather than a blocking network call against a guessed
        default host.
        """
        probe = _recorder()
        with patch.object(mc.requests, "get", probe), patch.object(mc.requests, "post", probe):
            assert mc.model_context_limit("z:7b") is None
        assert probe.call_count == 0

    def test_a_prompt_that_fits_the_floor_never_probes(self):
        """No architecture window can change the answer below the 4096 floor,
        so the round trip is not taken. This is also what keeps every existing
        short-prompt test in the suite off the network."""
        probe = _recorder()
        with patch.object(mc.requests, "get", probe), patch.object(mc.requests, "post", probe):
            assert num_ctx_for_model("tiny:1b", 10, 10, endpoint="http://localhost:11434") == 4096
        assert probe.call_count == 0

    def test_a_prompt_over_the_floor_probes_and_is_capped(self):
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "capped:7b", "details": {"context_length": 8192}}]
        )), patch.object(mc.requests, "post", return_value=_show(_arch(8192))):
            assert num_ctx_for_model("capped:7b", 40_000, 1024,
                                     endpoint="http://localhost:11434") == 8192


class TestWhichContextLengthKeyIsTheModels:
    """``model_info`` can carry more than one ``*.context_length``. Picking the
    wrong one is not a display bug: it is published as the model's maximum, a
    producer may only ever raise a window, and 77 tokens pins num_ctx at the
    4096 floor for every prompt for the life of the process."""

    def test_the_declared_architectures_own_key_wins(self):
        assert mc.architecture_context_length({
            "general.architecture": "archfam",
            "archfam.context_length": 131072,
            "vistower.vision.context_length": 77,
        }) == 131072

    def test_a_vision_towers_key_is_not_the_models_window(self):
        """The payload that made this a bug: a declared architecture that
        publishes no context_length of its own, beside a projector that does."""
        assert mc.architecture_context_length({
            "general.architecture": "archfam",
            "vistower.vision.context_length": 77,
            "archfam.embedding_length": 4096,
        }) == 0

    def test_the_largest_credible_key_wins_when_no_architecture_is_declared(self):
        assert mc.architecture_context_length({
            "vistower.vision.context_length": 77,
            "archfam2.context_length": 131072,
        }) == 131072

    def test_embedding_length_is_not_a_context_length(self):
        assert mc.architecture_context_length({
            "general.architecture": "archfam2",
            "archfam2.embedding_length": 4096,
            "archfam2.context_length": 32768,
        }) == 32768

    def test_nothing_to_read_is_zero_not_a_guess(self):
        assert mc.architecture_context_length({}) == 0
        assert mc.architecture_context_length(None) == 0
        assert mc.architecture_context_length({"archfam.context_length": True}) == 0
        assert mc.architecture_context_length({"archfam.context_length": "131072"}) == 0

    def test_a_bogus_window_from_a_show_is_never_published_as_a_cap(self):
        """End to end through the probe: the 77 must not reach the cap, where
        nothing could ever raise it again."""
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "vision:4b", "details": {"context_length": 8192}}]
        )), patch.object(mc.requests, "post", return_value=_show({
            "general.architecture": "archfam",
            "vistower.vision.context_length": 77,
            "archfam.embedding_length": 4096,
        })):
            assert mc.model_context_limit("vision:4b", "http://localhost:11434") is None
        # and the prompt gets the window it needs, not the floor a 77 would
        # have pinned it to
        assert num_ctx_for_model("vision:4b", 20_000, 1024) == 22528


class TestNumCtxCeilingIsConfigurable:
    """The fallback ceiling — what we use when the model's real window is
    unknown — is an operator dial. It is not lowered by default: clamping a
    prompt that a 262144-token model could have held is the silent
    head-truncation this module exists to prevent. An operator on a small card
    sets a hard cap and gets the loud warning instead of an OOM."""

    def test_default_is_unchanged(self, monkeypatch):
        monkeypatch.delenv(mc._NUM_CTX_MAX_ENV, raising=False)
        assert compute_num_ctx(100_000, 1024, None) == 32768

    def test_env_lowers_the_ceiling(self, monkeypatch):
        monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, "8192")
        assert compute_num_ctx(100_000, 1024, None) == 8192

    def test_env_raises_the_ceiling(self, monkeypatch):
        monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, "65536")
        assert compute_num_ctx(100_000, 1024, None) == 65536

    def test_a_garbage_value_is_ignored_not_obeyed(self, monkeypatch):
        for bad in ("", "lots", "-1", "0", "3.5"):
            monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, bad)
            assert compute_num_ctx(100_000, 1024, None) == 32768

    def test_the_floor_still_wins_over_a_tiny_ceiling(self, monkeypatch):
        """A dial set below the floor must not produce a 1024-token window."""
        monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, "1024")
        assert compute_num_ctx(10, 10, None) == 4096

    def test_the_dial_is_read_per_call_so_it_can_be_set_at_runtime(self, monkeypatch):
        monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, "8192")
        assert compute_num_ctx(100_000, 1024, None) == 8192
        monkeypatch.setenv(mc._NUM_CTX_MAX_ENV, "16384")
        assert compute_num_ctx(100_000, 1024, None) == 16384


class TestTheWindowIsReleased:
    """The per-model window is a high-water mark so Ollama does not reload the
    model on every message. Left to latch forever, one outlier prompt (a pasted
    log, a big RAG context) pins the model at the ceiling for the life of the
    process, and every one-line question after it allocates 32768 tokens of KV
    cache. It is released after a quiet period — never below what the prompt in
    hand needs, so this can never truncate anything."""

    def test_it_holds_through_a_turn(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])
        assert num_ctx_for_model("m:7b", 30_000, 1024) == 31744
        clock[0] += 30          # the same turn's second call, seconds later
        assert num_ctx_for_model("m:7b", 500, 1024) == 31744
        clock[0] += mc._NUM_CTX_RELEASE_SECONDS - 60
        assert num_ctx_for_model("m:7b", 500, 1024) == 31744

    def test_a_one_off_huge_prompt_does_not_pin_the_window_forever(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])
        assert num_ctx_for_model("m:7b", 30_000, 1024) == 31744
        clock[0] += mc._NUM_CTX_RELEASE_SECONDS + 1
        assert num_ctx_for_model("m:7b", 500, 1024) == 4096

    def test_a_release_never_goes_below_what_the_prompt_needs(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])
        assert num_ctx_for_model("m:7b", 30_000, 1024) == 31744
        clock[0] += mc._NUM_CTX_RELEASE_SECONDS + 1
        assert num_ctx_for_model("m:7b", 9000, 1024) == 11264

    def test_steady_use_of_most_of_the_window_keeps_it(self, monkeypatch):
        """Only a prompt needing less than half the window is a candidate for
        release, so ordinary turn-to-turn variation never reloads the model."""
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])
        assert num_ctx_for_model("m:7b", 20_000, 1024) == 22528
        for _ in range(10):
            clock[0] += mc._NUM_CTX_RELEASE_SECONDS + 1
            assert num_ctx_for_model("m:7b", 15_000, 1024) == 22528

    def test_a_release_grows_again_immediately(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(mc.time, "monotonic", lambda: clock[0])
        num_ctx_for_model("m:7b", 30_000, 1024)
        clock[0] += mc._NUM_CTX_RELEASE_SECONDS + 1
        assert num_ctx_for_model("m:7b", 500, 1024) == 4096
        assert num_ctx_for_model("m:7b", 30_000, 1024) == 31744


class TestALaterDiscoveryCorrectsTheHeldWindow:
    """The high-water mark is there so Ollama does not reload the model between
    messages. It must not outlive the ignorance that set it: turn 1 of a cold
    process is sized before anything knows the model's window, and if the
    32768 it asked for were simply held, discovering the real 8192 a moment
    later would buy nothing for the next quarter of an hour."""

    def test_a_window_learned_after_the_mark_was_set_corrects_it(self):
        assert num_ctx_for_model("m:7b", 100_000, 1024) == 32768
        mc.remember_model_context_limit("m:7b", 8192)
        assert num_ctx_for_model("m:7b", 100_000, 1024) == 8192

    def test_a_correction_never_goes_below_the_floor(self):
        assert num_ctx_for_model("m:7b", 100_000, 1024) == 32768
        mc.remember_model_context_limit("m:7b", 1024)   # nonsense, from somewhere
        assert num_ctx_for_model("m:7b", 5000, 1024) == 4096

    def test_a_bigger_window_still_does_not_inflate_the_mark(self):
        assert num_ctx_for_model("m:7b", 9000, 1024) == 11264
        mc.remember_model_context_limit("m:7b", 262144)
        assert num_ctx_for_model("m:7b", 9000, 1024) == 11264


class TestTheStreamingPathDiscoversTheWindowWithoutStoppingTheLoop:
    """The streaming path is the one the user reads, and on turn 1 of a cold
    process it is often the FIRST call to reach a model. It is also a
    coroutine, and that is what makes discovery here a different problem from
    discovery in ``_call_ollama``.

    ``requests`` is synchronous. A probe taken inline from ``_stream_turn``
    does not merely slow this turn down: it stops the event loop, so every
    other open SSE stream and every other request the process is serving stops
    with it, for up to the probe timeout and longer if name resolution hangs.
    Measured on this tree before the fix: a 3.01s probe and a 3.06s gap between
    event-loop heartbeats, on the first large prompt of a session.

    So the turn is sized from what is already known — the picker's listing, the
    planning call, an earlier turn — and anything still unknown is discovered
    on a worker thread. Turn 1 of a cold process streams at the fallback
    ceiling, exactly as it did before any of this work; every turn after it is
    capped at the model's real window.
    """

    SLOW = 0.5   # what a daemon that is slow to answer costs the loop

    def _slow_tags(self, *models):
        def _get(url, **kwargs):
            time.sleep(self.SLOW)
            return _tags(list(models))
        return _get

    @pytest.mark.asyncio
    async def test_a_cold_stream_neither_waits_for_the_daemon_nor_stops_the_loop(
        self, adapter, fake_aiohttp
    ):
        adapter.max_tokens = 8192
        # A prompt far over the 4096 floor, so the lookup is worth taking, and
        # far over this model's real window, so an uncapped run is visible.
        big = [{"role": "user", "content": "y" * 200_000}]

        gaps = []

        async def heartbeat():
            last = time.monotonic()
            while True:
                await asyncio.sleep(0.01)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        beat = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.05)   # let it settle into its rhythm
        with patch.object(mc.requests, "get", side_effect=self._slow_tags(
            {"name": "example-model:latest", "details": {"context_length": 8192}},
        )), patch.object(mc.requests, "post", return_value=_show(_arch(8192))):
            started = time.monotonic()
            assert "".join([c async for c in adapter.stream(big)]) == "hi"
            turn_took = time.monotonic() - started
            # Let a beat whose timer expired while the loop was blocked
            # actually LAND before the task is cancelled. A cancel delivered
            # in the same pass takes that beat away, the gap is never
            # recorded, and ``max(gaps)`` below sees only the rhythm from
            # before the call -- measured on this tree with the probe put back
            # inline: max(gaps) 0.011s over four beats while the loop was in
            # fact stopped for half a second, so the assertion held with the
            # very thing it exists to catch happening.
            await asyncio.sleep(0.03)
            beat.cancel()
            # The turn is over; the probe it started is still running.
            assert fake_aiohttp["json"]["options"]["num_ctx"] == 32768
            _join_probes()

        assert turn_took < self.SLOW / 2, "the streaming turn waited for the probe"
        assert max(gaps) < self.SLOW / 2, "the probe stopped the event loop"
        # Nothing was lost by not waiting: the window is known now, off the
        # loop, for every turn after this one.
        assert mc.model_context_limit("example-model:latest") == 8192

    @pytest.mark.asyncio
    async def test_the_next_turn_is_capped_at_the_models_real_window(
        self, adapter, fake_aiohttp
    ):
        adapter.max_tokens = 8192
        big = [{"role": "user", "content": "y" * 200_000}]
        with patch.object(mc.requests, "get", return_value=_tags(
            [{"name": "example-model:latest", "details": {"context_length": 8192}}]
        )) as get, patch.object(mc.requests, "post", return_value=_show(_arch(8192))):
            # Turn 1 is sized from what was known when it started; whether
            # the worker thread beat it to the cache is a race, and not one
            # this test has an opinion about (the slow-daemon test above is
            # where turn 1's ceiling is pinned down deterministically).
            assert "".join([c async for c in adapter.stream(big)]) == "hi"
            _join_probes()
            assert "".join([c async for c in adapter.stream(big)]) == "hi"

        # It asked the endpoint the stream is about to post to, not some other.
        assert get.call_count == 1
        assert get.call_args.args[0] == "http://localhost:11434/api/tags"
        # And this turn obeyed the answer instead of falling back to the ceiling.
        assert fake_aiohttp["json"]["options"]["num_ctx"] == 8192

    @pytest.mark.asyncio
    async def test_a_short_prompt_still_costs_no_round_trip(
        self, adapter, fake_aiohttp
    ):
        """Passing the endpoint must not make every stream pay for a probe:
        below the floor no architecture window can change the answer.

        ``num_predict`` counts toward that floor as much as the prompt does, so
        the reply budget is small here too -- a turn that has already asked for
        8192 tokens of answer is over the floor whatever the question was.
        """
        adapter.max_tokens = 256
        probe = _recorder()
        with patch.object(mc.requests, "get", probe), patch.object(mc.requests, "post", probe):
            assert "".join([c async for c in adapter.stream(
                [{"role": "user", "content": "hi"}]
            )]) == "hi"
            _join_probes()
        assert probe.call_count == 0
        assert not mc._CONTEXT_PROBE_THREADS, "a short prompt started a probe thread"
        assert fake_aiohttp["json"]["options"]["num_ctx"] == 4096


def test_call_ollama_never_takes_the_blocking_context_probe():
    """`_call_ollama` is synchronous, but it is reachable from a coroutine.

    routes/agent.py::send_message -> AgentStateMachine.process() ->
    self.intake.analyze() (inline, no thread) -> ComplexityRouter.assess ->
    _call_llm -> call_llm_chat -> _do_llm_call -> _call_ollama. A blocking
    probe on that path stops the event loop and every open SSE stream with it,
    so this call site must take the non-blocking discovery path even though it
    is not itself a coroutine.

    Recorded rather than asserted inside the double: `_probe_context_limits`
    swallows Exception, and AssertionError is an Exception, so a
    `side_effect=AssertionError` tripwire here would be silently eaten and the
    test would pass whether or not the forbidden call happened.
    """
    calls = {"blocking": 0, "nowait": 0}

    def _blocking(model, endpoint=None):
        calls["blocking"] += 1
        return None

    def _nowait(model, endpoint=None):
        calls["nowait"] += 1
        return None

    # A prompt big enough that the discovery lookup is worth taking at all:
    # below the floor num_ctx_for_model short-circuits before either probe.
    big = [{"role": "user", "content": "x" * 80000}]

    with patch.object(mc, "model_context_limit", _blocking), \
         patch.object(mc, "model_context_limit_nowait", _nowait), \
         patch("halbert_core.model.client.requests.post",
               return_value=_response({"message": {"content": "hi"}})):
        mc._call_ollama("http://127.0.0.1:11434", "guide:7b", big, False, 30, {"num_predict": 512}, None)

    assert calls["blocking"] == 0, "took the blocking probe on a coroutine-reachable path"
    assert calls["nowait"] == 1, "did not attempt non-blocking discovery at all"
