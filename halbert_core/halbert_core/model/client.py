# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Model Client — shared LLM routing and calling logic.

Extracted from dashboard/routes/chat.py to break the circular dependency
between the agent state machine (agent.py) and the chat routes (chat.py).

Both chat.py and agent.py import from this module instead of from each other.

Functions:
  get_ollama_endpoint()    — guide model endpoint from models.yml
  get_configured_model()   — guide model name from models.yml
  get_specialist_model()   — specialist model tuple from models.yml
  get_vision_model()       — vision model tuple from models.yml
  api_key_for()            — API key for a saved endpoint URL
  call_llm_chat()          — unified LLM call (Ollama, OpenAI-compatible, Anthropic)
  _score_query_complexity() — query complexity for guide vs specialist routing
  _estimate_tokens()       — rough token count
  _truncate_messages_for_context() — truncate message list to fit context

Config schema:
  All model resolution goes through model.llm_config (the single owner of
  the 'llm_config' section of models.yml):
    guide (chat)   → llm_config.chat_model
    specialist     → llm_config.specialist_model
    vision         → llm_config.vision_model
  Legacy 'orchestrator'/'specialist'/'vision' keys are migrated by that
  module on first load; nothing here reads them.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

logger = logging.getLogger("halbert.model.client")


class UnsupportedProviderError(RuntimeError):
    """Raised when a saved endpoint's provider has no chat adapter.

    The picker lets a user save an endpoint for any provider so they can list
    and test its models, but only the providers below can actually carry a
    chat turn. Raising here — rather than silently posting to the Ollama
    route and 404-ing — is what stops "tests green in Settings, fails in
    chat".
    """

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"{provider} endpoints can list and test models but are not yet "
            f"usable for chat"
        )


# Providers whose wire format is OpenAI's /v1/chat/completions.
# apple-foundation: the Swift FoundationModels bridge speaks OpenAI-compatible
# on loopback:11435, so _call_openai_compatible handles it with no new adapter.
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "openai-compatible", "lm-studio", "apple-foundation"})

# Providers that can carry a chat turn. Anything saved under another provider
# is listable and testable but rejected by call_llm_chat.
# peer: a paired Halbert node's compute endpoint (peer:// in models.yml).
# It speaks OpenAI's wire format but under /api/compute/v1 rather than /v1,
# so it gets its own adapter (_call_peer) instead of joining the set above.
CHAT_CAPABLE_PROVIDERS = frozenset(
    {"ollama", "llamacpp", "mlx", "anthropic", "peer"} | OPENAI_COMPATIBLE_PROVIDERS
)

# Providers that contend for the local GPU and therefore need the advisory
# lock. lm-studio serves models from the same VRAM Ollama does.
LOCAL_GPU_PROVIDERS = frozenset({"ollama", "llamacpp", "mlx", "lm-studio"})

_ANTHROPIC_VERSION = "2023-06-01"


# ── Advisory lock for GPU contention ────────────────────────────
#
# Prevents Halbert chat and SourcePrep pipeline from simultaneously
# slamming the same local GPU. Uses a file lock with a short timeout
# — if the lock can't be acquired, the call proceeds anyway (fail-open)
# but logs a warning. This is NOT full AIMD concurrency arbitration;
# it's cheap insurance against the worst UX failure.
#
# The lock file lives in the config directory and is shared with
# SourcePrep (both apps agree on the path via get_config_dir()).

_LOCK_TIMEOUT_S = 30.0  # Max wait before failing open


def _lock_path() -> "Any":
    """Path to the advisory lock file."""
    from ..utils.platform import get_config_dir
    return get_config_dir() / "llm.lock"


@contextmanager
def llm_advisory_lock(timeout_s: float = _LOCK_TIMEOUT_S) -> Iterator[bool]:
    """Acquire an advisory file lock before an LLM call.

    Uses fcntl.flock (POSIX) or a simple file-existence check (Windows).
    Returns True if the lock was acquired, False if it timed out (fail-open).

    Usage:
        with llm_advisory_lock() as acquired:
            if not acquired:
                logger.warning("LLM lock timed out — proceeding anyway")
            # ... make the LLM call ...
    """
    import platform as _platform

    if _platform.system() == "Windows":
        # Windows doesn't have fcntl — use a simple file-existence lock
        lock_file = _lock_path()
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        acquired = False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                # Check if the lock is stale (older than 5 minutes)
                try:
                    age = time.time() - lock_file.stat().st_mtime
                    if age > 300:
                        lock_file.unlink(missing_ok=True)
                        continue
                except Exception:
                    pass
                time.sleep(0.5)
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    lock_file.unlink(missing_ok=True)
                except Exception:
                    pass
        return

    # POSIX — use fcntl.flock (shared lock, so multiple readers are OK)
    import fcntl

    lock_file = _lock_path()
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    acquired = False
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_WRONLY)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                time.sleep(0.5)

        if not acquired:
            logger.warning(
                "LLM advisory lock timed out after %.1fs — proceeding (fail-open)",
                timeout_s,
            )

        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
        try:
            os.close(fd)
        except Exception:
            pass


# ── Model resolution (single source: model.llm_config) ──────────

from . import llm_config as _store


def get_ollama_endpoint() -> str:
    """URL of the chat model's endpoint (local Ollama when nothing is configured)."""
    chat = _store.resolve("chat_model")
    return chat.url if chat else _store.DEFAULT_OLLAMA_URL


def get_configured_model() -> str:
    """Chat model name, or "" when none is configured.

    Callers must treat "" as "not configured" and surface a clear error
    (choose a model in Settings -> AI Models) instead of posting model="".
    """
    chat = _store.resolve("chat_model")
    return chat.model if chat else ""


def get_specialist_model() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(model, endpoint_url, provider) for the specialist slot, or (None, None, None)."""
    spec = _store.resolve("specialist_model")
    if spec is None:
        logger.debug("Specialist not configured")
        return (None, None, None)
    logger.info(f"Specialist enabled: {spec.model} at {spec.url} (provider: {spec.provider})")
    return (spec.model, spec.url, spec.provider)


def get_vision_model() -> Tuple[Optional[str], str, str]:
    """(model, endpoint_url, provider) for the vision slot; model is None when unset.

    Callers fall back to the chat model for images when model is None. The
    provider is carried because a vision slot may point at a cloud endpoint,
    and posting that to Ollama's /api/chat 404s.
    """
    vis = _store.resolve("vision_model")
    if vis is None:
        chat = _store.resolve("chat_model")
        fallback_url = chat.url if chat else _store.DEFAULT_OLLAMA_URL
        fallback_provider = chat.provider if chat else "ollama"
        return (None, fallback_url, fallback_provider)
    logger.info(f"Vision enabled: {vis.model} at {vis.url} (provider: {vis.provider})")
    return (vis.model, vis.url, vis.provider)


def get_secure_model() -> Tuple[Optional[str], str, str]:
    """(model, endpoint_url, provider) for the secure-data slot, or (None, "", "").

    The secure_model is guaranteed local-only (enforced by llm_config.normalise).
    Used for processing sensitive data — system configs, secrets, persona memory,
    cognitive tick internal monologue — that must never leave the machine.

    Callers fall back to the chat model when secure_model is not configured,
    but ONLY when the chat model's endpoint is also local. Otherwise the caller
    must degrade gracefully (e.g. template thoughts instead of LLM thoughts).
    """
    sec = _store.resolve("secure_model")
    if sec is None:
        return (None, "", "")
    logger.info(f"Secure model enabled: {sec.model} at {sec.url} (provider: {sec.provider})")
    return (sec.model, sec.url, sec.provider)


# ── Endpoint helpers (one implementation, in the store) ──────────


def api_key_for(url: str) -> str:
    """API key for the first saved endpoint matching ``url``, else "".

    Delegates to :func:`model.llm_config.api_key_for` so there is one
    implementation. Lets ``call_llm_chat`` recover a key when a caller
    passes only the URL — which is every one of the 30+ existing call
    sites of the model getters.
    """
    return _store.api_key_for(url)


def provider_for(url: str, default: str = "ollama") -> str:
    """Provider of the first saved endpoint matching ``url``, else ``default``."""
    return _store.provider_for(url, default)


def resolve_endpoint_by_id(endpoint_id: str) -> Optional[Tuple[str, str, str]]:
    """Public (url, provider, api_key) for a saved endpoint id, or None."""
    return _store.resolve_endpoint_by_id(endpoint_id)


def call_llm_chat(
    endpoint: str,
    model: str,
    messages: list,
    provider: str = "ollama",
    stream: bool = False,
    timeout: int = 180,
    options: dict = None,
    tools: list = None,
    api_key: Optional[str] = None,
) -> dict:
    """Call LLM with correct API format based on provider.

    Args:
        endpoint: Base URL (e.g., http://localhost:11434)
        model: Model name
        messages: List of message dicts with 'role' and 'content'
        provider: One of :data:`CHAT_CAPABLE_PROVIDERS`
        stream: Whether to stream response
        timeout: Request timeout in seconds
        options: Provider-specific options (temperature, max_tokens, etc.)
        tools: Optional OpenAI-style tool schemas
            (``[{"type": "function", "function": {...}}]``). Sent to the model
            when non-empty; models that reject them fall back to a plain call.
        api_key: Bearer / x-api-key credential. When None it is looked up from
            models.yml with :func:`api_key_for` so the 30+ callers that pass
            only a URL still authenticate. Pass "" to force an unauthenticated
            call.

    Returns:
        Dict with 'content' (response text), 'tool_calls' (normalised list,
        see :func:`_normalise_tool_calls`) and 'raw' (full response)

    Raises:
        UnsupportedProviderError: the provider has no chat adapter.
    """
    options = options or {}

    if provider not in CHAT_CAPABLE_PROVIDERS:
        raise UnsupportedProviderError(provider)

    # None means "look it up"; "" means "deliberately unauthenticated".
    if api_key is None:
        api_key = api_key_for(endpoint)

    total_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"Sending {len(messages)} messages, ~{total_chars} chars to {provider}"
    )

    # Acquire advisory lock to prevent GPU contention with SourcePrep pipeline.
    # Cloud endpoints (openai, anthropic, google) don't need the lock — only
    # local GPU-bound providers do. lm-studio serves from the same VRAM as
    # Ollama, so it belongs in that set even though it speaks OpenAI's wire
    # format.
    needs_lock = provider in LOCAL_GPU_PROVIDERS

    if needs_lock:
        with llm_advisory_lock() as acquired:
            if not acquired:
                logger.warning("GPU may be busy — LLM call proceeding without lock")
            return _call_with_tool_fallback(
                endpoint, model, messages, provider, stream, timeout, options,
                tools, api_key,
            )
    else:
        return _call_with_tool_fallback(
            endpoint, model, messages, provider, stream, timeout, options,
            tools, api_key,
        )


# ── Tool-schema rejection registry (Plan A, spec §7) ─────────────
#
# Models without tool calling answer a ``tools`` payload with a 4xx. The
# fallback below retries without tools and, once that retry has actually
# answered, records the model here, so the warning is logged once per model
# per process and the clients can expose tools_supported=False: the prompt
# layer then drops the "call recall_thread / new_thread" instruction from
# the continuity preamble (AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS)
# for a model that cannot call anything.
#
# The entry is keyed by model and is evidence, not a latch: a later call
# whose schemas the model accepts clears it again.

_TOOLS_REJECTED: Dict[str, bool] = {}


def model_supports_tools(model: str) -> Optional[bool]:
    """False once ``model`` rejected tool schemas this process; None
    otherwise (unknown: nothing has proven it either way)."""
    return False if _TOOLS_REJECTED.get(model) else None


def _call_with_tool_fallback(
    endpoint: str,
    model: str,
    messages: list,
    provider: str,
    stream: bool,
    timeout: int,
    options: dict,
    tools: list,
    api_key: str = "",
) -> dict:
    """Call the model with tools, retrying once without them on rejection.

    Plenty of local models have no tool-calling support; Ollama answers a
    ``tools`` payload for one of those with a 400 rather than ignoring it.
    Losing the whole turn over an unsupported capability is worse than
    answering without tools, so the retry drops them and logs it.

    A 401/403 is deliberately *not* retried — a bad credential will fail the
    same way without tools, and retrying doubles the latency of every
    misconfigured key.
    """
    if not tools:
        return _do_llm_call(
            endpoint, model, messages, provider, stream, timeout, options,
            None, api_key,
        )

    try:
        result = _do_llm_call(
            endpoint, model, messages, provider, stream, timeout, options,
            tools, api_key,
        )
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status not in (400, 404, 422, 501):
            raise
        already_known = bool(_TOOLS_REJECTED.get(model))
        # Retry before recording anything. These statuses cover plenty of
        # causes that have nothing to do with tool schemas — Ollama answers
        # 404 for a model that simply is not pulled, 400 for an oversized
        # payload — and only a retry that succeeds *without* the schemas
        # proves the schemas were the problem. A retry that fails too raises
        # from here and leaves the registry untouched, so an unpulled model
        # is not durably remembered as tool-blind (review: Plan A / A9d).
        retried = _do_llm_call(
            endpoint, model, messages, provider, stream, timeout, options,
            None, api_key,
        )
        if not already_known:
            # Once per model per process (spec §7); later fallbacks are silent.
            logger.warning(
                f"Model {model} rejected tool schemas (HTTP {status}); "
                "retried without tools"
            )
        _TOOLS_REJECTED[model] = True
        return retried

    # The schemas were accepted: forget any earlier rejection, so a 4xx that
    # came from an unrelated cause cannot mute the tool instruction for the
    # rest of the process once the model is answering tool calls again.
    _TOOLS_REJECTED.pop(model, None)
    return result


def _normalise_tool_calls(raw_calls: list) -> list:
    """Flatten provider tool-call shapes into ``{id, name, arguments}`` dicts.

    Ollama returns ``arguments`` already decoded; OpenAI-compatible APIs send
    a JSON string. Both arrive here; callers downstream expect a dict, since
    that is what the tool executor takes.
    """
    normalised = []
    for i, call in enumerate(raw_calls or []):
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name")
        if not name:
            continue
        args = fn.get("arguments", call.get("arguments", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except (ValueError, TypeError):
                logger.warning(f"Tool call {name} had unparseable arguments: {args!r}")
                args = {}
        if not isinstance(args, dict):
            args = {}
        normalised.append({
            "id": call.get("id") or f"call_{i}",
            "name": name,
            "arguments": args,
        })
    return normalised


def _api_url(endpoint: str, suffix: str) -> str:
    """Join a base endpoint to an API suffix without doubling ``/v1``.

    Users paste both ``https://api.example.com`` and
    ``https://api.example.com/v1``; the second form used to produce
    ``/v1/v1/chat/completions`` and a 404.
    """
    base = (endpoint or "").rstrip("/")
    if base.endswith("/v1") and suffix.startswith("/v1/"):
        suffix = suffix[3:]
    return f"{base}{suffix}"


def _call_peer(
    endpoint: str,
    model: str,
    messages: list,
    stream: bool,
    timeout: int,
    options: dict,
    tools: Optional[list],
    api_key: str,
) -> dict:
    """Peer compute endpoint — OpenAI's wire format under /api/compute/v1.

    The ``peer://`` scheme is the saved form in models.yml; the HTTP call
    goes to the same host over http. Auth is the peer bearer token issued
    at pairing, stored as the endpoint's api_key (routes/peers.py
    ``/api/peers/compute-peer``), so the usual api_key_for() lookup in
    call_llm_chat recovers it from a bare URL like every other provider.
    """
    if stream:
        # The workstation has no SSE path yet — redaction across chunk
        # boundaries is unsolved there (federation/compute_endpoint.py,
        # TODO(federation-9.4)). Fail loudly rather than returning a
        # non-streaming body to a caller expecting chunks.
        raise NotImplementedError(
            "peer compute streaming is not supported yet — TODO(federation-9.4)"
        )

    base = endpoint.replace("peer://", "http://", 1).rstrip("/")
    url = f"{base}/api/compute/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": options.get("temperature", 0.7),
        "max_tokens": options.get("num_predict", options.get("max_tokens", 2048)),
    }
    if tools:
        payload["tools"] = tools

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        f"Calling peer compute endpoint: {url} model={model} "
        f"(auth: {'yes' if api_key else 'no'})"
    )
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("choices", [{}])[0].get("message", {}) or {}
    return {
        "content": (message.get("content") or "").strip(),
        "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
        "raw": data,
    }


def _call_openai_compatible(
    endpoint: str,
    model: str,
    messages: list,
    stream: bool,
    timeout: int,
    options: dict,
    tools: Optional[list],
    api_key: str,
) -> dict:
    """OpenAI /v1/chat/completions — also LM Studio and any compatible gateway."""
    url = _api_url(endpoint, "/v1/chat/completions")
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": options.get("temperature", 0.7),
        "max_tokens": options.get("num_predict", options.get("max_tokens", 2048)),
    }
    if tools:
        payload["tools"] = tools

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        f"Calling OpenAI-compatible API: {url} model={model} "
        f"(auth: {'yes' if api_key else 'no'})"
    )
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("choices", [{}])[0].get("message", {}) or {}
    content = message.get("content") or ""
    return {
        "content": content.strip(),
        "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
        "raw": data,
    }


def _anthropic_payload(
    model: str, messages: list, options: dict, tools: Optional[list]
) -> dict:
    """Build an Anthropic Messages payload from OpenAI-shaped messages.

    Anthropic takes the system prompt as a top-level field rather than a
    message, rejects empty content, and names tool schemas ``input_schema``.
    """
    system_parts = []
    api_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if not content:
            continue  # Anthropic 400s on an empty content block
        api_messages.append({
            "role": "assistant" if role == "assistant" else "user",
            "content": content,
        })

    payload = {
        "model": model,
        # max_tokens is mandatory on the Messages API, unlike OpenAI's.
        "max_tokens": options.get("num_predict", options.get("max_tokens", 2048)),
        "messages": api_messages,
        "temperature": options.get("temperature", 0.7),
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if tools:
        converted = [
            {
                "name": (t.get("function") or {}).get("name"),
                "description": (t.get("function") or {}).get("description", ""),
                "input_schema": (t.get("function") or {}).get("parameters", {}),
            }
            for t in tools
            if t.get("type") == "function" and (t.get("function") or {}).get("name")
        ]
        if converted:
            payload["tools"] = converted
    return payload


def _call_anthropic(
    endpoint: str,
    model: str,
    messages: list,
    timeout: int,
    options: dict,
    tools: Optional[list],
    api_key: str,
) -> dict:
    """Anthropic Messages API.

    Deliberately synchronous ``requests`` rather than delegating to
    ``agents.llm_client.AnthropicClient``: that client is async/aiohttp, and
    this function is called synchronously from inside an already-running event
    loop, where awaiting it is impossible and ``asyncio.run`` raises. Keeping
    one transport also means ``_call_with_tool_fallback``'s HTTPError retry
    covers this branch unchanged.
    """
    if not api_key:
        raise ValueError(
            "No API key configured for this endpoint — add one in "
            "Settings → AI Models"
        )

    url = _api_url(endpoint or "https://api.anthropic.com", "/v1/messages")
    payload = _anthropic_payload(model, messages, options, tools)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    logger.info(f"Calling Anthropic Messages API: {url} model={model}")
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    content = ""
    raw_calls = []
    for block in data.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            content += block.get("text", "")
        elif block.get("type") == "tool_use":
            # Anthropic names the arguments "input"; _normalise_tool_calls
            # expects "arguments".
            raw_calls.append({
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "arguments": block.get("input", {}),
            })

    return {
        "content": content.strip(),
        "tool_calls": _normalise_tool_calls(raw_calls),
        "raw": data,
    }


def _call_ollama(
    endpoint: str,
    model: str,
    messages: list,
    stream: bool,
    timeout: int,
    options: dict,
    tools: Optional[list],
) -> dict:
    """Ollama /api/chat — also the fallback for llamacpp and mlx."""
    url = f"{(endpoint or '').rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        # Ollama only returns tool_calls on a non-streamed response.
        "stream": False if tools else stream,
    }
    if tools:
        payload["tools"] = tools
    options = options or {}
    num_predict = options.get("num_predict", options.get("max_tokens", 1024))
    prompt_tokens = estimate_prompt_tokens(messages, tools)
    # Always present (spec §7): without it Ollama truncates the head.
    #
    # `on_event_loop` even though this function is synchronous: being
    # synchronous is not the same as being off the loop. This call site is
    # reachable from a coroutine with no thread anywhere in between —
    # routes/agent.py::send_message -> AgentStateMachine.process() ->
    # self.intake.analyze() (inline) -> ComplexityRouter.assess -> _call_llm ->
    # call_llm_chat -> _do_llm_call -> here — so a blocking probe taken here
    # stops the event loop and every open SSE stream with it, for up to the
    # probe timeout and longer if name resolution hangs. Whether the chat
    # request below is itself off the loop is the caller's problem and is
    # covered elsewhere (tests/test_agent_chat_off_the_event_loop.py); this
    # probe is a stall we can simply not take, so we don't. Discovery goes to
    # a worker thread, and the window it learns caps the turns after this one.
    num_ctx = options.get("num_ctx") or num_ctx_for_model(
        model, prompt_tokens, num_predict, options.get("num_ctx_max"),
        endpoint=endpoint, on_event_loop=True,
    )
    if prompt_tokens + _NUM_CTX_HEADROOM > num_ctx:
        # The clamp (model_max or the 32768 default ceiling) capped num_ctx
        # below what the prompt actually needs. Ollama truncates the HEAD of
        # the prompt silently in this case, and the head of the array is
        # messages[0] — the instruction sheet plus the thread receipt — so
        # make it loud. (The continuity hint itself no longer rides the head:
        # it is appended to the *last* user message by
        # AgentStateMachine._build_messages, so array position, not prose
        # position, is what keeps it out of the truncated region.)
        logger.warning(
            f"Prompt for {model} is ~{prompt_tokens} tokens but num_ctx="
            f"{num_ctx}; Ollama will truncate the head of the prompt."
        )
    payload["options"] = {
        "num_predict": num_predict,
        "temperature": options.get("temperature", 0.7),
        "num_ctx": num_ctx,
    }
    logger.info(
        f"Calling Ollama API: {url} model={model} num_ctx={num_ctx} "
        f"prompt_tokens={prompt_tokens}"
    )
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("message", {}) or {}
    content = message.get("content") or ""
    return {
        "content": content.strip(),
        "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
        "raw": data,
    }


# ── num_ctx sizing (Plan A, spec §7) ─────────────────────────
#
# Ollama's default context window is small and silently truncates the HEAD
# of the prompt. Every local call now sets options.num_ctx from the prompt
# size. The value is cached per model and only ever grows: Ollama reloads a
# model whenever num_ctx changes, so recomputing it per turn would thrash
# the GPU on every message.

_NUM_CTX_MIN = 4096
_NUM_CTX_DEFAULT_MAX = 32768
_NUM_CTX_HEADROOM = 512
_NUM_CTX_CACHE: Dict[str, int] = {}
# Vision models spend several hundred tokens encoding each image; a
# text-only estimate over a captioning message (short text, one big
# image) undercounts to near zero, which pins num_ctx at the floor and
# reproduces exactly the silent head-truncation this module exists to
# prevent. This is a rough per-image budget, not a model-specific one.
_NUM_CTX_IMAGE_TOKENS = 768

# The fallback ceiling is an operator dial. It is NOT lowered by default:
# num_ctx is already sized to the prompt and never speculatively larger, so
# every token the ceiling removes is a token of the *prompt* that Ollama
# silently drops off the head. A smaller default would buy GPU memory by
# reintroducing exactly the truncation this module exists to prevent. An
# operator whose card cannot hold 32768 tokens of KV cache sets this and gets
# the loud "will truncate the head of the prompt" warning instead of an OOM.
_NUM_CTX_MAX_ENV = "HALBERT_NUM_CTX_MAX"

# The window is a high-water mark so Ollama does not reload the model on every
# message — but a mark that latches forever means one outlier prompt (a pasted
# log, an unusually large retrieval) pins the model at the ceiling for the rest
# of the process, and every one-line question after it allocates the full
# window. It is released once no prompt has needed more than half of it for
# this long. Long enough that no realistic turn sequence trips it (the planning
# call and the response call of one turn are seconds apart); short enough that
# a session recovers the memory on its own.
_NUM_CTX_RELEASE_SECONDS = 900.0
_NUM_CTX_HIGH_WATER_AT: Dict[str, float] = {}


# ── The model's real context window: the producer for the cap above ──────────
#
# `compute_num_ctx` has always taken a `model_max`, and until this fix nothing
# in the tree ever supplied one, so every model got the 32768 fallback. The
# right producer is the model's ARCHITECTURE maximum — the largest window the
# weights can hold.
#
# It is emphatically NOT Ollama's `parameters` block `num_ctx`, which is the
# Modelfile's *default* load window and is routinely a small fraction of it.
# Measured against a live daemon: one installed model reports an architecture
# context length of 262144 alongside a Modelfile
# `num_ctx 8192`. Capping at the Modelfile default would pin that model at
# 8192 and truncate the head of every larger prompt — the bug A10 exists to
# prevent, reproduced by construction. See tests/test_llm_show_context_length.py.
#
# Two producers, both cheap:
#   * `routes/llm.py::proxy_models` publishes what it already learned while
#     listing models for the picker (/api/tags carries `details.context_length`
#     for most models; /api/show's `model_info` covers the rest). Free.
#   * failing that, a lazy probe of the endpoint, taken only when the prompt
#     needs more than the 4096 floor — below it no architecture window can
#     change the answer. One GET of `{endpoint}/api/tags` names every model on
#     the daemon; a window small enough to actually cap something is then
#     confirmed with one POST to `{endpoint}/api/show` for the model being
#     called, because /api/tags reports a single unlabelled number and this
#     path has no other chance to tell an architecture maximum from a
#     load-time default.
#
# Unknown stays unknown: on a machine where the endpoint is down, is not Ollama
# at all (this path is also the llamacpp/mlx fallback), or does not list the
# model, the result is None and behaviour is exactly what it is today.
#
# NONE OF IT MAY HAPPEN ON AN EVENT LOOP. These are ordinary blocking requests,
# so a caller that can reach a loop asks `model_context_limit_nowait`, which
# answers from what is already known and puts discovery on a worker thread.
# That is both production callers: the async streaming path, and `_call_ollama`
# — synchronous, but reachable from a coroutine with no thread in between
# (send_message -> the state machine -> intake -> call_llm_chat -> here), so
# "synchronous" says nothing about whether a loop is underneath. The blocking
# `model_context_limit` is for callers that are genuinely off any loop: a CLI
# run, or the worker thread this module starts itself.
_MODEL_MAX_CACHE: Dict[str, int] = {}
# endpoint -> monotonic time before which /api/tags will not be asked again.
# A retry time, never a permanent latch: Ollama being started, or restarted,
# under a long-lived Halbert is the normal case on a real install, and an
# endpoint that was down at first probe must not be written off for the life
# of the process — on a headless install this probe is the only producer there
# is. A dead endpoint still costs one failed request per retry window, not one
# per LLM call, which is what the latch was there for.
_CONTEXT_PROBED_ENDPOINTS: Dict[str, float] = {}
# endpoint -> the model names its /api/tags listing actually returned. Nothing
# is asked of /api/show for a name (or an endpoint) that no successful listing
# ever mentioned, so a non-Ollama endpoint costs one failed request, not two.
_CONTEXT_ENDPOINT_MODELS: Dict[str, set] = {}
# (endpoint, model) -> monotonic time before which /api/show will not be asked
# about it again. A retry time for the same reason as above: a daemon that was
# restarting when the question was put must not silence the answer for the life
# of the process. Once the window is known nothing asks again anyway.
_CONTEXT_SHOWN_MODELS: Dict[Tuple[str, str], float] = {}
_CONTEXT_PROBE_TIMEOUT = 3.0
_CONTEXT_PROBE_RETRY_SECONDS = 60.0
# Background discovery started on behalf of an event loop, one live thread per
# endpoint. Kept so a caller (and a test) can tell whether discovery is running.
_CONTEXT_PROBE_THREADS: Dict[str, threading.Thread] = {}
_CONTEXT_PROBE_LOCK = threading.Lock()
# A "maximum" below the num_ctx floor cannot describe a language model's
# window: compute_num_ctx never returns less than _NUM_CTX_MIN, so such a
# number can only ever cap a prompt and never allow one. Keys like
# `<projector>.vision.context_length: 77` are the reason — they belong to a
# projector, not to the model being called.
_MIN_CREDIBLE_CONTEXT_LENGTH = _NUM_CTX_MIN


def _num_ctx_ceiling() -> int:
    """The fallback ceiling, read per call so the dial works at runtime."""
    raw = os.environ.get(_NUM_CTX_MAX_ENV)
    if raw:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring %s=%r: not an integer number of tokens", _NUM_CTX_MAX_ENV, raw
            )
        else:
            if value > 0:
                return value
            logger.warning("Ignoring %s=%r: must be positive", _NUM_CTX_MAX_ENV, raw)
    return _NUM_CTX_DEFAULT_MAX


def remember_model_context_limit(model: str, limit: Any) -> None:
    """Record a model's architecture context window, learned from anywhere.

    A producer can only ever RAISE a known window, never lower it. That is a
    structural guard, not an optimisation: if some future producer hands us a
    Modelfile default again, it cannot pull an already-known architecture
    maximum down and start silently truncating prompts. Over-stating a window
    only ever removes the cap, leaving the ceiling in charge — which is exactly
    today's behaviour — while under-stating it truncates.
    """
    if not model or not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return
    if limit > _MODEL_MAX_CACHE.get(model, 0):
        _MODEL_MAX_CACHE[model] = limit


def remember_listing_context_length(model: str, limit: Any) -> None:
    """A window read from a model LISTING (/api/tags), which is weaker evidence
    than /api/show's ``model_info``.

    A listing gives one unlabelled number per model. On the daemon this was
    written against it is the architecture maximum, but the field's meaning is
    version-dependent — it is missing entirely from that same daemon's
    safetensors entries — and a listing carries nothing that distinguishes an
    architecture maximum from the window a model is loaded with by default.
    That is the exact distinction /api/show is read so carefully for, because
    on a real model the two differ by 32x. Since a producer may only ever RAISE
    a window, a wrong small number here is not a bad guess that gets corrected:
    it is a permanent cap, and permanent silent head-truncation with it.

    So a listing may only confirm what cannot bind. At or above the fallback
    ceiling the number changes nothing about the num_ctx we would have asked
    for anyway; anything smaller has to come from /api/show — the picker's
    enrichment pass, or this module's own :func:`_probe_model_architecture`.
    """
    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= _num_ctx_ceiling():
        remember_model_context_limit(model, limit)


def architecture_context_length(model_info: Any) -> int:
    """The largest window the weights can hold, from an /api/show ``model_info``.

    GGUF spells the key ``<general.architecture>.context_length``, so the prefix
    varies per model family and is never hardcoded — it is read from
    ``general.architecture``. The two fixed keys an earlier fallback looked for,
    ``llm.context_length`` and ``general.context_length``, are emitted by no
    model: checked against every model on a live daemon, that fallback never
    once fired, so the window came back as 0 for models advertising 262144.
    Any ``*.context_length`` key is therefore accepted, with the declared
    architecture preferred; ``embedding_length`` and friends are excluded by
    the suffix.

    Which of several such keys matters. A payload can carry a projector or
    vision tower alongside the language model — a
    ``<projector>.vision.context_length: 77`` beside a declared architecture
    that publishes no context_length of its own — and taking whichever came
    first published 77 as the model's
    "maximum". 77 pins num_ctx at the 4096 floor for every prompt, for the life
    of the process (a producer may only ever raise a known window), which is
    exactly the silent head-truncation this whole path exists to prevent. So:
    the declared architecture's own key wins outright; failing that the LARGEST
    candidate wins, and only if it is a credible window for a language model at
    all. Over-stating merely leaves the ceiling in charge; under-stating
    truncates.
    """
    if not isinstance(model_info, dict):
        return 0
    arch = str(model_info.get("general.architecture") or "").strip()
    best = 0
    for key, value in model_info.items():
        if not isinstance(key, str) or not key.endswith(".context_length"):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            continue
        if arch and key == f"{arch}.context_length":
            return int(value)
        if value < _MIN_CREDIBLE_CONTEXT_LENGTH:
            continue
        best = max(best, int(value))
    return best


def _probe_context_limits(endpoint: str) -> None:
    """One GET of {endpoint}/api/tags per endpoint per retry window, best effort.

    /api/tags names every model on the daemon and carries each one's
    ``details.context_length``, so a single round trip answers for all of them.
    The retry time is stamped before the request goes out, so a daemon that is
    down, or is not Ollama, costs one failed request per window rather than one
    per LLM call — and unlike the latch this replaces, a daemon that comes up
    afterwards is still discovered.

    What /api/tags reports is a candidate, not a cap. The /api/show path is
    careful to publish only the architecture maximum and never the Modelfile's
    load-time default — they differ by 32x on a real model — while /api/tags
    hands over one unlabelled number whose meaning is version-dependent
    (verified as the architecture maximum on this machine's daemon; absent
    entirely on its safetensors/MLX entries). A value at or above the fallback
    ceiling cannot cap anything below what we would have used anyway, so it is
    published free. Anything smaller would bind, and is left to
    :func:`_probe_model_architecture` to confirm.
    """
    key = (endpoint or "").rstrip("/")
    if not key:
        return
    now = time.monotonic()
    if now < _CONTEXT_PROBED_ENDPOINTS.get(key, 0.0):
        return
    _CONTEXT_PROBED_ENDPOINTS[key] = now + _CONTEXT_PROBE_RETRY_SECONDS
    try:
        response = requests.get(f"{key}/api/tags", timeout=_CONTEXT_PROBE_TIMEOUT)
        if response.status_code != 200:
            return
        listed = set()
        for entry in (response.json() or {}).get("models") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or ""
            if not name:
                continue
            listed.add(name)
            remember_listing_context_length(
                name, (entry.get("details") or {}).get("context_length")
            )
        _CONTEXT_ENDPOINT_MODELS[key] = listed
    except Exception as e:
        logger.debug("Could not read context windows from %s: %s", key, e)


def _probe_model_architecture(endpoint: str, model: str) -> None:
    """One POST to {endpoint}/api/show for one model, per retry window.

    This is the discrimination the picker's listing already applies and that
    /api/tags cannot: ``model_info`` labels the architecture maximum, so a
    Modelfile default (or a vision tower's 77) can be told apart from the real
    window instead of being trusted verbatim as a permanent cap.

    Only asked for a model a successful /api/tags listing actually named, so an
    endpoint that is not Ollama costs one failed request rather than two, and
    only when the window is still unknown — which is also the mlx/safetensors
    case, where /api/tags carries no context_length at all.
    """
    key = (endpoint or "").rstrip("/")
    if not model or model not in _CONTEXT_ENDPOINT_MODELS.get(key, ()):
        return
    now = time.monotonic()
    if now < _CONTEXT_SHOWN_MODELS.get((key, model), 0.0):
        return
    _CONTEXT_SHOWN_MODELS[(key, model)] = now + _CONTEXT_PROBE_RETRY_SECONDS
    try:
        response = requests.post(
            f"{key}/api/show", json={"name": model}, timeout=_CONTEXT_PROBE_TIMEOUT
        )
        if response.status_code != 200:
            return
        remember_model_context_limit(
            model, architecture_context_length((response.json() or {}).get("model_info"))
        )
    except Exception as e:
        logger.debug("Could not read %s's context window from %s: %s", model, key, e)


def model_context_limit(model: str, endpoint: Optional[str] = None) -> Optional[int]:
    """The model's architecture context window, or None when nothing knows it.

    Blocking: up to two short requests on a cold endpoint. Never call it from a
    coroutine — see :func:`model_context_limit_nowait`.
    """
    known = _MODEL_MAX_CACHE.get(model)
    if known:
        return known
    if not endpoint:
        return None
    _probe_context_limits(endpoint)
    known = _MODEL_MAX_CACHE.get(model)
    if known:
        return known
    _probe_model_architecture(endpoint, model)
    return _MODEL_MAX_CACHE.get(model)


def _background_probe(model: str, endpoint: str) -> None:
    try:
        model_context_limit(model, endpoint)
    except Exception as e:  # pragma: no cover - the probe swallows its own
        logger.debug("Background context probe for %s failed: %s", model, e)


def model_context_limit_nowait(model: str, endpoint: Optional[str] = None) -> Optional[int]:
    """What is already known about the model's window. Never a round trip.

    For callers that can reach an asyncio event loop — the coroutines, and the
    synchronous functions a coroutine calls without a thread in between.
    ``requests`` is synchronous, so a probe taken with a loop underneath stalls
    every other request the process is serving — every open SSE stream
    included — for as long as the daemon takes to answer, which is up to the
    timeout and longer if name resolution hangs. Measured on this tree, the
    inline version blocked the loop for 3.01s.

    So this answers from the cache, and when the answer is not there yet it
    starts discovery on a worker thread whose result lands in that same cache.
    A cold process therefore sizes its first big turn against the fallback
    ceiling — exactly the behaviour that shipped before any of this —
    and every turn after it against the model's real window. One live thread
    per endpoint: a turn that arrives while discovery is running does not start
    a second one.
    """
    known = _MODEL_MAX_CACHE.get(model)
    if known:
        return known
    key = (endpoint or "").rstrip("/")
    if not key or not model:
        return None
    now = time.monotonic()
    if now < _CONTEXT_PROBED_ENDPOINTS.get(key, 0.0) and (
        now < _CONTEXT_SHOWN_MODELS.get((key, model), 0.0)
        or model not in _CONTEXT_ENDPOINT_MODELS.get(key, ())
    ):
        # Everything this probe could learn about this model has been asked
        # already; there is nothing for a thread to do.
        return None
    with _CONTEXT_PROBE_LOCK:
        running = _CONTEXT_PROBE_THREADS.get(key)
        if running is not None and running.is_alive():
            return None
        thread = threading.Thread(
            target=_background_probe, args=(model, key),
            name="halbert-context-probe", daemon=True,
        )
        _CONTEXT_PROBE_THREADS[key] = thread
    thread.start()
    return None


def compute_num_ctx(
    prompt_tokens_estimate: int, num_predict: int, model_max: Optional[int]
) -> int:
    """clamp(round_up(prompt + 512 + num_predict, 1024), 4096, model_max or the ceiling)."""
    need = int(prompt_tokens_estimate) + _NUM_CTX_HEADROOM + int(num_predict)
    rounded = ((need + 1023) // 1024) * 1024
    ceiling = min(int(model_max), _num_ctx_ceiling()) if model_max else _num_ctx_ceiling()
    return max(_NUM_CTX_MIN, min(rounded, ceiling))


def num_ctx_for_model(
    model: str,
    prompt_tokens_estimate: int,
    num_predict: int,
    model_max: Optional[int] = None,
    endpoint: Optional[str] = None,
    on_event_loop: bool = False,
) -> int:
    """Per-model num_ctx: sized from the prompt, held across a turn, released
    when it has gone unneeded.

    ``model_max`` overrides discovery; ``endpoint`` allows it. Neither is
    required — with both absent this behaves exactly as it did before, so a
    caller that has no endpoint to give is never worse off than it was.

    ``on_event_loop`` says the caller can reach an event loop, and it is not a
    hint: discovery is synchronous ``requests``, so a probe taken with a loop
    underneath stops it and with it every other request the process is
    serving. Every caller in this tree that can reach a loop sets it — the
    dashboard adapter's ``_stream_turn``, which is a coroutine, and
    ``_call_ollama``, which is synchronous but sits at the end of an
    all-inline chain from ``routes/agent.py::send_message`` with no thread
    anywhere in between. "Synchronous" is not "off the loop", and a caller
    that cannot prove it is off one has to assume it is not. Such a caller
    gets what is known now, plus discovery on a worker thread for the turns
    after this one; only a caller that is genuinely off any loop (a CLI run, a
    worker thread) leaves it False and waits for the answer.
    """
    if model_max is None:
        # Only worth a lookup when the prompt needs more than the floor: below
        # it no architecture window can change the answer, so the common short
        # prompt never pays for one — not even the cost of starting a thread.
        if compute_num_ctx(prompt_tokens_estimate, num_predict, None) > _NUM_CTX_MIN:
            model_max = (
                model_context_limit_nowait(model, endpoint) if on_event_loop
                else model_context_limit(model, endpoint)
            )
    wanted = compute_num_ctx(prompt_tokens_estimate, num_predict, model_max)
    now = time.monotonic()
    cached = _NUM_CTX_CACHE.get(model)

    if cached is not None and model_max:
        # A window learned since the high-water mark was set corrects the mark
        # rather than growing it. The mark exists so Ollama does not reload the
        # model between messages, but holding 32768 for a model whose weights
        # top out at 8192 asks for KV cache the model cannot use, and the mark
        # would hold it for the whole release period — a quarter of an hour of
        # a session, after one big first turn on a cold process that had not
        # discovered the window yet. Never below what the prompt in hand
        # needs, so this cannot truncate anything.
        cap = max(_NUM_CTX_MIN, min(int(model_max), _num_ctx_ceiling()))
        if cached > cap:
            logger.info(
                f"num_ctx for {model} corrected {cached} -> {cap}: the model's "
                f"window is {model_max}"
            )
            cached = cap
            _NUM_CTX_CACHE[model] = cap

    if cached is None or wanted > cached:
        if cached is not None:
            logger.info(f"num_ctx for {model} grows {cached} -> {wanted}")
        _NUM_CTX_CACHE[model] = wanted
        _NUM_CTX_HIGH_WATER_AT[model] = now
        return wanted

    if wanted > cached // 2:
        # Still using most of the window: hold it, and keep the clock warm.
        _NUM_CTX_HIGH_WATER_AT[model] = now
        return cached

    if now - _NUM_CTX_HIGH_WATER_AT.get(model, now) < _NUM_CTX_RELEASE_SECONDS:
        return cached

    # Nothing has needed more than half this window for a long time. Drop to
    # what the prompt in hand needs — never below it, so this cannot truncate.
    logger.info(
        f"num_ctx for {model} released {cached} -> {wanted} after "
        f"{_NUM_CTX_RELEASE_SECONDS:.0f}s below half the window"
    )
    _NUM_CTX_CACHE[model] = wanted
    _NUM_CTX_HIGH_WATER_AT[model] = now
    return wanted


def estimate_prompt_tokens(messages: list, tools: Optional[list]) -> int:
    """~4 chars/token over every message's content, plus the tool schemas,
    an allowance for any ``images`` payload, and any ``tool_calls`` a prior
    assistant turn attached (those carry real prompt tokens even when
    ``content`` is empty/None, as in the agentic tool-calling loop)."""
    total = 0
    for m in messages or []:
        if isinstance(m, dict):
            content = m.get("content", "")
            images = m.get("images")
            if images:
                total += len(images) * _NUM_CTX_IMAGE_TOKENS
            tool_calls = m.get("tool_calls")
            if tool_calls:
                total += len(json.dumps(tool_calls, default=str)) // 4
        else:
            content = m
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        total += len(content) // 4
    if tools:
        total += len(json.dumps(tools, default=str)) // 4
    return total


def _do_llm_call(
    endpoint: str,
    model: str,
    messages: list,
    provider: str,
    stream: bool,
    timeout: int,
    options: dict,
    tools: list = None,
    api_key: str = "",
) -> dict:
    """Dispatch to the provider's adapter (separated for lock wrapping).

    Unknown providers fall through to the Ollama wire format, which is the
    behaviour every local runtime has relied on. Providers with no adapter at
    all are rejected earlier, in :func:`call_llm_chat`.
    """
    if provider == "peer":
        return _call_peer(
            endpoint, model, messages, stream, timeout, options, tools, api_key
        )
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return _call_openai_compatible(
            endpoint, model, messages, stream, timeout, options, tools, api_key
        )
    if provider == "anthropic":
        return _call_anthropic(
            endpoint, model, messages, timeout, options, tools, api_key
        )
    return _call_ollama(endpoint, model, messages, stream, timeout, options, tools)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (avg 4 chars per token)."""
    return len(text) // 4


def _truncate_messages_for_context(
    messages: list, max_tokens: int = 12000
) -> list:
    """Truncate messages to fit within context limit.

    Preserves system message (truncated if needed) and recent conversation.
    """
    total_tokens = sum(
        _estimate_tokens(m.get("content", "")) for m in messages
    )

    if total_tokens <= max_tokens:
        return messages

    logger.warning(
        f"Messages exceed {max_tokens} tokens ({total_tokens}), truncating..."
    )
    result = []

    for m in messages:
        if m.get("role") == "system":
            content = m["content"]
            max_system_chars = 32000
            if len(content) > max_system_chars:
                content = (
                    content[:max_system_chars]
                    + "\n\n[Context truncated for length]"
                )
                logger.info(
                    f"Truncated system message from {len(m['content'])} to {len(content)} chars"
                )
            result.append({"role": "system", "content": content})
            break

    non_system = [m for m in messages if m.get("role") != "system"]
    remaining_tokens = (
        max_tokens - _estimate_tokens(result[0]["content"]) if result else max_tokens
    )
    kept = []
    for m in reversed(non_system):
        msg_tokens = _estimate_tokens(m.get("content", ""))
        if remaining_tokens - msg_tokens > 500:
            kept.insert(0, m)
            remaining_tokens -= msg_tokens
        else:
            break

    result.extend(kept)
    logger.info(
        f"Truncated to {len(result)} messages, ~{sum(_estimate_tokens(m.get('content', '')) for m in result)} tokens"
    )
    return result


def _score_query_complexity(prompt: str) -> float:
    """Score query complexity to decide guide vs specialist routing.

    Returns:
        Float from 0.0 (simple -> guide tier) to 1.0 (complex -> specialist tier)
    """
    score = 0.0
    prompt_lower = prompt.lower()
    word_count = len(prompt.split())

    if word_count > 50:
        score += 0.2
    elif word_count > 20:
        score += 0.1

    diagnostic_keywords = [
        "why",
        "failed",
        "fail",
        "error",
        "broken",
        "not working",
        "troubleshoot",
        "diagnose",
        "investigate",
        "debug",
        "fix",
        "issue",
        "problem",
    ]
    diagnostic_hits = sum(1 for kw in diagnostic_keywords if kw in prompt_lower)
    if diagnostic_hits >= 2:
        score += 0.5
    elif diagnostic_hits >= 1:
        score += 0.4

    code_keywords = [
        "write",
        "create",
        "script",
        "function",
        "code",
        "implement",
        "optimize",
        "refactor",
    ]
    if any(kw in prompt_lower for kw in code_keywords):
        score += 0.3

    multi_step_keywords = [
        "step by step",
        "first",
        "then",
        "after",
        "compare",
        "analyze",
        "explain why",
        "how does",
    ]
    if any(kw in prompt_lower for kw in multi_step_keywords):
        score += 0.2

    analysis_keywords = [
        "analyze",
        "recommend",
        "suggest",
        "identify",
        "find",
        "bottleneck",
        "performance",
        "optimize",
        "improve",
        "best",
        "based on",
        "according to",
        "evaluate",
        "assess",
    ]
    analysis_hits = sum(1 for kw in analysis_keywords if kw in prompt_lower)
    if analysis_hits >= 2:
        score += 0.4
    elif analysis_hits >= 1:
        score += 0.2

    simple_indicators = [
        "what is",
        "show me",
        "list",
        "status",
        "how many",
        "which",
        "where is",
        "hi",
        "hello",
        "thanks",
        "help",
    ]
    if any(prompt_lower.startswith(kw) for kw in simple_indicators) and word_count < 10:
        score -= 0.3

    return max(0.0, min(1.0, score))


# Public aliases (underscore-prefixed names kept for backward compat)
score_query_complexity = _score_query_complexity
estimate_tokens = _estimate_tokens
truncate_messages_for_context = _truncate_messages_for_context


def get_loaded_models(endpoint: str = None, provider: str = "ollama") -> List[dict]:
    """List models currently loaded/available on the LLM server.

    For Ollama: GET /api/ps (models resident in VRAM).
    For OpenAI-compatible: GET /v1/models (available models).

    Moved here from dashboard/routes/chat.py (retired in T4b.1) — this is
    the canonical home for model-management helpers.
    """
    if endpoint is None:
        endpoint = get_ollama_endpoint()

    try:
        if provider == "openai":
            # OpenAI-compatible API (LM Studio, vLLM, etc.)
            response = requests.get(f"{endpoint}/v1/models", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [
                    {"name": m.get("id", ""), "id": m.get("id", "")}
                    for m in data.get("data", [])
                ]
            return []

        # Ollama API
        response = requests.get(f"{endpoint}/api/ps", timeout=5)
        if response.status_code == 200:
            return response.json().get("models", [])
        return []
    except Exception as e:
        logger.debug(f"Could not get loaded models: {e}")
        return []


def is_model_loaded(
    model_name: str, endpoint: str = None, provider: str = "ollama"
) -> bool:
    """Check if a specific model is currently loaded/available."""
    for m in get_loaded_models(endpoint, provider):
        loaded_name = m.get("name", m.get("id", ""))
        if loaded_name == model_name or loaded_name.startswith(model_name + ":"):
            return True
        # Provided name may be a family prefix without the size tag
        if model_name.startswith(loaded_name.split(":")[0]):
            return True
    return False
