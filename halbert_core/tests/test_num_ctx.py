# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A10: options.num_ctx is set on every Ollama call, sized from the
prompt, computed once per model per process (spec §7)."""

import json
import pytest
from unittest.mock import MagicMock, patch

import halbert_core.model.client as mc
from halbert_core.model.client import compute_num_ctx, num_ctx_for_model, estimate_prompt_tokens, call_llm_chat


@pytest.fixture(autouse=True)
def _clear_cache():
    mc._NUM_CTX_CACHE.clear()
    yield
    mc._NUM_CTX_CACHE.clear()


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


def test_per_model_cache_grows_but_never_shrinks():
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
async def test_adapter_planning_chat_uses_num_predict_1024(adapter):
    with patch("halbert_core.model.client.call_llm_chat") as chat:
        chat.return_value = {"content": "ok", "tool_calls": []}
        await adapter.chat([{"role": "user", "content": "plan"}], tools=[])
    assert chat.call_args.kwargs["options"]["num_predict"] == 1024
