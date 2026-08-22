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
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import requests

logger = logging.getLogger("halbert.model.client")


def get_ollama_endpoint() -> str:
    """Get the Ollama endpoint URL from config (guide model's endpoint)."""
    try:
        from ..utils.platform import get_config_dir
        import yaml

        config_path = get_config_dir() / "models.yml"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            orch = config.get("orchestrator", {})
            if orch.get("endpoint"):
                return orch["endpoint"]

        return "http://localhost:11434"
    except Exception:
        return "http://localhost:11434"


def get_configured_model() -> str:
    """Get the configured guide model name from config."""
    try:
        from ..utils.platform import get_config_dir
        import yaml

        config_path = get_config_dir() / "models.yml"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            orch = config.get("orchestrator", {})
            if orch.get("model"):
                return orch["model"]

        return "llama3.1:8b"
    except Exception:
        return "llama3.1:8b"


def get_specialist_model() -> Tuple[str, str, str]:
    """Get the configured specialist/executor model name, endpoint, and provider.

    Returns:
        Tuple of (model_name, endpoint_url, provider) or (None, None, None)
        if not enabled. Provider is 'ollama' or 'openai'.
    """
    try:
        from ..utils.platform import get_config_dir
        import yaml

        config_path = get_config_dir() / "models.yml"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            specialist = config.get("specialist", {})
            if not specialist.get("enabled", False):
                logger.debug("Specialist not enabled in config")
                return (None, None, None)

            model = specialist.get("model", "llama3.1:70b")
            endpoint = specialist.get("endpoint", get_ollama_endpoint())
            provider = specialist.get("provider", "ollama")
            logger.info(
                f"Specialist enabled: {model} at {endpoint} (provider: {provider})"
            )
            return (model, endpoint, provider)

        return (None, None, None)
    except Exception as e:
        logger.warning(f"Error loading specialist config: {e}")
        return (None, None, None)


def get_vision_model() -> Tuple[str, str]:
    """Get the configured vision model name and endpoint.

    Returns:
        Tuple of (model_name, endpoint_url)
    """
    try:
        from ..utils.platform import get_config_dir
        import yaml

        config_path = get_config_dir() / "models.yml"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            vision = config.get("vision", {})
            model = vision.get("model", "llava:34b")
            endpoint = vision.get("endpoint", get_ollama_endpoint())
            return (model, endpoint)

        return ("llava:34b", get_ollama_endpoint())
    except Exception:
        return ("llava:34b", get_ollama_endpoint())


def call_llm_chat(
    endpoint: str,
    model: str,
    messages: list,
    provider: str = "ollama",
    stream: bool = False,
    timeout: int = 180,
    options: dict = None,
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

    Returns:
        Dict with 'content' (response text) and 'raw' (full response)
    """
    options = options or {}

    total_chars = sum(len(m.get("content", "")) for m in messages)
    logger.info(
        f"Sending {len(messages)} messages, ~{total_chars} chars to {provider}"
    )

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
        logger.info(f"Calling OpenAI-compatible API: {url} model={model}")
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return {"content": content.strip(), "raw": data}
    else:
        url = f"{endpoint}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = {
                "num_predict": options.get(
                    "num_predict", options.get("max_tokens", 1024)
                ),
                "temperature": options.get("temperature", 0.7),
            }
        logger.info(f"Calling Ollama API: {url} model={model}")
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return {"content": content.strip(), "raw": data}


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
        Float from 0.0 (simple -> use 8b guide) to 1.0 (complex -> use 70b specialist)
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
