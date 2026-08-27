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
  call_llm_chat()          — unified LLM call (Ollama or OpenAI-compatible)
  _score_query_complexity() — query complexity for guide vs specialist routing
  _estimate_tokens()       — rough token count
  _truncate_messages_for_context() — truncate message list to fit context

Config schema:
  Reads the unified LLMConfig schema (shared with SourcePrep) from the
  'llm_config' key in models.yml. Falls back to the legacy
  'orchestrator'/'specialist'/'vision' keys for backward compatibility.

  Unified schema mapping:
    guide (orchestrator)  → llm_config.small_model (or large_model if small disabled)
    specialist            → llm_config.large_model
    vision                → legacy 'vision' key (no unified equivalent yet)
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

logger = logging.getLogger("halbert.model.client")


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


# ── Unified LLMConfig loader ────────────────────────────────────


def _load_models_config() -> Dict[str, Any]:
    """Load the raw models.yml config dict."""
    try:
        from .config_locator import find_models_config
        import yaml

        config_path = find_models_config(include_repo=False)
        if config_path is not None:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug(f"Could not load models.yml: {e}")
    return {}


def _resolve_endpoint(
    llm_config: Dict[str, Any], endpoint_id: Optional[str]
) -> Tuple[str, str]:
    """Resolve an endpoint_id from saved_endpoints to (url, provider).

    Returns ("http://localhost:11434", "ollama") as fallback.
    """
    if not endpoint_id:
        return ("http://localhost:11434", "ollama")

    endpoints = llm_config.get("saved_endpoints") or []
    for ep in endpoints:
        if ep.get("id") == endpoint_id:
            return (ep.get("url", "http://localhost:11434"), ep.get("provider", "ollama"))

    return ("http://localhost:11434", "ollama")


def _get_slot_config(
    config: Dict[str, Any], slot: str
) -> Optional[Dict[str, Any]]:
    """Get a model slot from the unified llm_config schema.

    Args:
        config: The raw models.yml dict.
        slot: One of 'small_model', 'large_model', 'code_model', 'coordinator_model'.

    Returns:
        The slot dict if the slot is enabled and has a model, else None.
    """
    llm_config = config.get("llm_config") or {}
    slot_cfg = llm_config.get(slot) or {}
    if not slot_cfg.get("enabled", False):
        return None
    if not slot_cfg.get("model"):
        return None
    return slot_cfg


def get_ollama_endpoint() -> str:
    """Get the Ollama endpoint URL from config (guide model's endpoint).

    Reads from the unified llm_config.small_model (or large_model) slot,
    falling back to the legacy orchestrator key.
    """
    config = _load_models_config()

    # Try unified schema: small_model first, then large_model
    for slot in ("small_model", "large_model"):
        slot_cfg = _get_slot_config(config, slot)
        if slot_cfg:
            llm_config = config.get("llm_config") or {}
            url, _ = _resolve_endpoint(llm_config, slot_cfg.get("endpoint_id"))
            return url

    # Fall back to legacy orchestrator key
    orch = config.get("orchestrator", {})
    if orch.get("endpoint"):
        return orch["endpoint"]

    return "http://localhost:11434"


def get_configured_model() -> str:
    """Get the configured guide model name from config.

    Reads from the unified llm_config.small_model (or large_model) slot,
    falling back to the legacy orchestrator key.

    Returns "" when no guide model is configured. Callers must treat an
    empty value as "not configured" and surface a clear error (choose a
    model in Settings -> AI Models) instead of posting model="".
    """
    config = _load_models_config()

    # Try unified schema: small_model first, then large_model
    for slot in ("small_model", "large_model"):
        slot_cfg = _get_slot_config(config, slot)
        if slot_cfg:
            return slot_cfg["model"]

    # Fall back to legacy orchestrator key
    orch = config.get("orchestrator", {})
    if orch.get("model"):
        return orch["model"]

    return ""


def get_specialist_model() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Get the configured specialist/executor model name, endpoint, and provider.

    Reads from the unified llm_config.large_model slot, falling back to
    the legacy 'specialist' key.

    Returns:
        Tuple of (model_name, endpoint_url, provider) or (None, None, None)
        if not enabled. Provider is 'ollama' or 'openai'.
    """
    config = _load_models_config()

    # Try unified schema: large_model
    slot_cfg = _get_slot_config(config, "large_model")
    if slot_cfg:
        llm_config = config.get("llm_config") or {}
        url, provider = _resolve_endpoint(llm_config, slot_cfg.get("endpoint_id"))
        model = slot_cfg["model"]
        logger.info(f"Specialist (large_model) enabled: {model} at {url} (provider: {provider})")
        return (model, url, provider)

    # Fall back to legacy specialist key
    specialist = config.get("specialist", {})
    if not specialist.get("enabled", False):
        logger.debug("Specialist not enabled in config")
        return (None, None, None)

    model = specialist.get("model")
    if not model:
        logger.debug("Specialist enabled but no model configured")
        return (None, None, None)
    endpoint = specialist.get("endpoint", get_ollama_endpoint())
    provider = specialist.get("provider", "ollama")
    logger.info(f"Specialist enabled: {model} at {endpoint} (provider: {provider})")
    return (model, endpoint, provider)


def get_vision_model() -> Tuple[Optional[str], str]:
    """Get the configured vision model name and endpoint.

    Reads from the legacy 'vision' key (no unified equivalent yet — the
    unified LLMConfig schema doesn't have a dedicated vision slot).

    Returns:
        Tuple of (model_name, endpoint_url). model_name is None when no
        vision model is configured; callers must fall back to the guide /
        specialist model or report "no vision model configured".
    """
    config = _load_models_config()

    vision = config.get("vision", {})
    model = vision.get("model") or None
    endpoint = vision.get("endpoint", get_ollama_endpoint())
    return (model, endpoint)


def call_llm_chat(
    endpoint: str,
    model: str,
    messages: list,
    provider: str = "ollama",
    stream: bool = False,
    timeout: int = 180,
    options: dict = None,
    tools: list = None,
) -> dict:
    """Call LLM with correct API format based on provider.

    Args:
        endpoint: Base URL (e.g., http://localhost:11434)
        model: Model name
        messages: List of message dicts with 'role' and 'content'
        provider: 'ollama' or 'openai' (for OpenAI-compatible APIs)
        stream: Whether to stream response
        timeout: Request timeout in seconds
        options: Provider-specific options (temperature, max_tokens, etc.)
        tools: Optional OpenAI-style tool schemas
            (``[{"type": "function", "function": {...}}]``). Sent to the model
            when non-empty; models that reject them fall back to a plain call.

    Returns:
        Dict with 'content' (response text), 'tool_calls' (normalised list,
        see :func:`_normalise_tool_calls`) and 'raw' (full response)
    """
    options = options or {}

    total_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"Sending {len(messages)} messages, ~{total_chars} chars to {provider}"
    )

    # Acquire advisory lock to prevent GPU contention with SourcePrep pipeline.
    # Cloud endpoints (openai, anthropic, google) don't need the lock — only
    # local GPU-bound providers (ollama, llamacpp, mlx) do.
    needs_lock = provider in ("ollama", "llamacpp", "mlx")

    if needs_lock:
        with llm_advisory_lock() as acquired:
            if not acquired:
                logger.warning("GPU may be busy — LLM call proceeding without lock")
            return _call_with_tool_fallback(
                endpoint, model, messages, provider, stream, timeout, options, tools
            )
    else:
        return _call_with_tool_fallback(
            endpoint, model, messages, provider, stream, timeout, options, tools
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
) -> dict:
    """Call the model with tools, retrying once without them on rejection.

    Plenty of local models have no tool-calling support; Ollama answers a
    ``tools`` payload for one of those with a 400 rather than ignoring it.
    Losing the whole turn over an unsupported capability is worse than
    answering without tools, so the retry drops them and logs it.
    """
    if not tools:
        return _do_llm_call(endpoint, model, messages, provider, stream, timeout, options)

    try:
        result = _do_llm_call(
            endpoint, model, messages, provider, stream, timeout, options, tools
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
        retried = _do_llm_call(endpoint, model, messages, provider, stream, timeout, options)
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


# ── num_ctx sizing (Plan A, spec §7) ─────────────────────────────
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


def compute_num_ctx(
    prompt_tokens_estimate: int, num_predict: int, model_max: Optional[int]
) -> int:
    """clamp(round_up(prompt + 512 + num_predict, 1024), 4096, model_max or 32768)."""
    need = int(prompt_tokens_estimate) + _NUM_CTX_HEADROOM + int(num_predict)
    rounded = ((need + 1023) // 1024) * 1024
    ceiling = int(model_max) if model_max else _NUM_CTX_DEFAULT_MAX
    return max(_NUM_CTX_MIN, min(rounded, ceiling))


def num_ctx_for_model(
    model: str,
    prompt_tokens_estimate: int,
    num_predict: int,
    model_max: Optional[int] = None,
) -> int:
    """Per-model num_ctx: computed once, grown only when a prompt needs more."""
    wanted = compute_num_ctx(prompt_tokens_estimate, num_predict, model_max)
    cached = _NUM_CTX_CACHE.get(model)
    if cached is not None and cached >= wanted:
        return cached
    if cached is not None:
        logger.info(f"num_ctx for {model} grows {cached} -> {wanted}")
    _NUM_CTX_CACHE[model] = wanted
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
) -> dict:
    """Make the actual LLM API call (separated for lock wrapping)."""
    if provider == "openai":
        url = f"{endpoint}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": options.get("temperature", 0.7),
            "max_tokens": options.get(
                "num_predict", options.get("max_tokens", 2048)
            ),
        }
        if tools:
            payload["tools"] = tools
        logger.info(f"Calling OpenAI-compatible API: {url} model={model}")
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content") or ""
        return {
            "content": content.strip(),
            "tool_calls": _normalise_tool_calls(message.get("tool_calls")),
            "raw": data,
        }
    else:
        url = f"{endpoint}/api/chat"
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
        num_ctx = options.get("num_ctx") or num_ctx_for_model(
            model, prompt_tokens, num_predict, options.get("num_ctx_max"),
        )
        if prompt_tokens + _NUM_CTX_HEADROOM > num_ctx:
            # The clamp (model_max or the 32768 default ceiling) capped
            # num_ctx below what the prompt actually needs. Ollama truncates
            # the HEAD of the prompt silently in this case, so make it loud.
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
