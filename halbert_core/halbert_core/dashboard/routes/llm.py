# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert LLM Router — model picker backend.

Endpoints:
  Config:
    - GET  /llm/config             — Halbert's llm_config + chat-capable provider list
    - PUT  /llm/config             — merge-update (whole slots)

  LLM Proxy (model listing & testing, all providers):
    - POST /api/llm/proxy/models       — list models from an endpoint
    - POST /api/llm/proxy/test         — test endpoint connectivity
    - POST /api/llm/proxy/test-model   — test a specific model
    - GET  /api/llm/discover           — probe local Ollama / LM Studio
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("halbert.dashboard")

router = APIRouter(tags=["llm"])


def _annotate_license(detail: Dict[str, Any], license_text: Optional[str] = None, provider: str = "") -> None:
    """Attach licence metadata to a model_details entry (LEG-MOD-04).

    Ollama ships each model's licence text (``/api/show`` → ``license``); the
    notice, if any, is read from that text. Other providers only get their
    provider-level terms. No model names are involved.
    """
    try:
        from ...model.attribution import classify_license_text, provider_terms

        info = classify_license_text(license_text) if license_text else provider_terms(provider)
    except Exception:
        return
    if info is None:
        return
    detail["license"] = info.name
    detail["license_id"] = info.license_id
    if info.license_url:
        detail["license_url"] = info.license_url
    if info.notice:
        detail["attribution"] = info.notice
    if info.non_commercial:
        detail["non_commercial"] = True

# ── SSRF Protection ──────────────────────────────────────────────

_ALLOWED_LOCAL_PORTS = {11434, 1234, 1235}  # Ollama, LM Studio

_ANTHROPIC_VERSION = "2023-06-01"


def _cloud_auth_headers(provider: str, api_key: Optional[str]) -> Dict[str, str]:
    """Auth headers for a cloud provider's list/test calls.

    Anthropic authenticates with ``x-api-key`` and requires a version header;
    sending it a Bearer token — as every branch in this file used to — is a
    guaranteed 401, which is what made "Test Key" fail for Anthropic while
    reporting only an opaque HTTP status.
    """
    if not api_key:
        return {}
    if provider == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }
    return {"Authorization": f"Bearer {api_key}"}


def _openai_style_base(url: str) -> str:
    """``{url}/v1`` unless the user already pasted a /v1 suffix."""
    base = (url or "").rstrip("/")
    return base if "v1" in base else f"{base}/v1"


def is_safe_url(url: str, provider: str) -> bool:
    """SSRF protection: ensure URL is HTTP/HTTPS and not targeting private networks."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname or ""
        port = parsed.port

        # Always block cloud metadata endpoints
        if hostname in ("169.254.169.254", "metadata.google.internal"):
            return False

        # Local providers need loopback access
        if provider in ("ollama", "lm-studio"):
            return True

        # For cloud providers, block private/reserved IP ranges
        try:
            resolved = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            for _, _, _, _, sockaddr in resolved:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    if ip.is_loopback and port in _ALLOWED_LOCAL_PORTS:
                        return True
                    return False
        except (socket.gaierror, ValueError, OSError):
            pass

        return True
    except Exception:
        return False


# ── Config (single owner: halbert_core.model.llm_config) ─────────

from ...model import llm_config as llm_store


class LLMConfigUpdate(BaseModel):
    llm_config: Dict[str, Any]


def _config_payload() -> Dict[str, Any]:
    from ...model.client import CHAT_CAPABLE_PROVIDERS
    return {
        "llm_config": llm_store.load(),
        "chat_capable_providers": sorted(CHAT_CAPABLE_PROVIDERS),
    }


@router.get("/llm/config")
def get_llm_config() -> Dict[str, Any]:
    """Halbert's model configuration. On a fresh install, adds Local Ollama when it answers."""
    llm_store.ensure_local_ollama_endpoint()
    return {"data": _config_payload()}


@router.put("/llm/config")
def update_llm_config(body: LLMConfigUpdate):
    """Deep-merge a partial llm_config (callers send whole slots) and return the saved result."""
    try:
        llm_store.update(body.llm_config)
    except llm_store.SlotProviderError as e:
        return JSONResponse(
            status_code=422,
            content={"error": {
                "code": "PROVIDER_NOT_CHAT_CAPABLE",
                "slot": e.slot,
                "provider": e.provider,
                "message": str(e),
            }},
        )
    return {"data": _config_payload()}


# ── Pydantic Request Models ──────────────────────────────────────


class LLMProxyRequest(BaseModel):
    provider: str = "ollama"
    url: str
    api_key: Optional[str] = None
    slot: Optional[str] = None


class LLMModelTestRequest(BaseModel):
    provider: str = "ollama"
    url: str
    model: str
    api_key: Optional[str] = None
    slot: Optional[str] = None


# ── LLM Proxy Endpoints ──────────────────────────────────────────


def _ollama_show_detail(url: str, name: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Fetch context length and licence text from Ollama /api/show for a single model."""
    try:
        r = requests.post(
            f"{url}/api/show",
            json={"name": name},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        params = data.get("parameters") or ""
        ctx = 0
        for line in params.split("\n"):
            line = line.strip()
            if line.startswith("num_ctx"):
                try:
                    ctx = int(line.split()[1])
                except (IndexError, ValueError):
                    pass
                break
        if not ctx:
            # Fall back to model_info
            model_info = data.get("model_info") or {}
            for key in ("llm.context_length", "general.context_length"):
                if key in model_info:
                    try:
                        ctx = int(model_info[key])
                    except (ValueError, TypeError):
                        pass
                    break
        ctx_label = f"{ctx // 1000}k" if ctx >= 1000 else str(ctx) if ctx > 0 else ""
        lic = data.get("license")
        if isinstance(lic, list):
            lic = "\n\n".join(str(x) for x in lic)
        return {"context_tokens": ctx, "context_window": ctx_label, "license": lic if isinstance(lic, str) else None}
    except Exception:
        return None


@router.post("/api/llm/proxy/models")
def proxy_models(req: LLMProxyRequest) -> Dict[str, Any]:
    """List models from an endpoint."""
    url = req.url.rstrip("/")
    if not is_safe_url(url, req.provider):
        return {"data": {"models": [], "error": "Invalid or unsafe URL"}}

    models: List[str] = []
    model_details: List[Dict[str, Any]] = []

    try:
        if req.provider == "ollama":
            r = requests.get(f"{url}/api/tags", timeout=5)
            if r.status_code == 200:
                data = r.json()
                for m in data.get("models", []):
                    if isinstance(m, dict) and "name" in m:
                        name = m["name"]
                        models.append(name)
                        size_bytes = m.get("size", 0)
                        size_label = f"{size_bytes / 1e9:.1f}GB" if size_bytes > 0 else ""
                        param_size = (m.get("details") or {}).get("parameter_size", "")
                        quant = (m.get("details") or {}).get("quantization_level", "")
                        family = (m.get("details") or {}).get("family", "")
                        parts: list = []
                        if param_size:
                            parts.append(param_size)
                        if quant:
                            parts.append(quant)
                        if size_label:
                            parts.append(size_label)
                        detail: Dict[str, Any] = {
                            "name": name,
                            "cost_tier": " · ".join(parts) if parts else "Local",
                        }
                        if family:
                            detail["family"] = family
                        model_details.append(detail)

                # Fetch context_length via /api/show (batched, max 20)
                for md in model_details[:20]:
                    show = _ollama_show_detail(url, md["name"])
                    if not show:
                        continue
                    if show["context_tokens"] > 0:
                        md["context_tokens"] = show["context_tokens"]
                        md["context_window"] = show["context_window"]
                    if show.get("license"):
                        _annotate_license(md, license_text=show["license"])

        elif req.provider in ("openai", "openai-compatible", "lm-studio", "anthropic"):
            headers = _cloud_auth_headers(req.provider, req.api_key)
            target = f"{_openai_style_base(url)}/models"

            r = requests.get(target, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                for m in data.get("data", []):
                    if isinstance(m, dict) and "id" in m:
                        name = m["id"]
                        models.append(name)
                        detail: Dict[str, Any] = {"name": name}
                        ctx = m.get("context_window") or m.get("context_length") or 0
                        if isinstance(ctx, (int, float)) and ctx > 0:
                            ctx = int(ctx)
                            detail["context_tokens"] = ctx
                            detail["context_window"] = f"{ctx // 1000}k" if ctx >= 1000 else str(ctx)
                        arch = m.get("architecture") or ""
                        quant = m.get("quantization") or ""
                        if not isinstance(arch, str):
                            arch = ""
                        if not isinstance(quant, str):
                            quant = ""
                        if arch or quant:
                            parts = [p for p in [arch, quant] if p]
                            detail["cost_tier"] = " · ".join(parts)
                        elif req.provider == "openai":
                            detail["cost_tier"] = "OpenAI"
                        elif req.provider == "anthropic":
                            detail["cost_tier"] = "Anthropic"
                        model_details.append(detail)

        elif req.provider == "google":
            if not req.api_key:
                return {"error": {"code": "MISSING_API_KEY", "message": "Google Gemini requires an API key."}}
            params = {"key": req.api_key}
            target = f"{url}/v1beta/models"
            r = requests.get(target, params=params, timeout=10)
            if r.status_code != 200:
                err_text = r.text[:200] if r.text else f"HTTP {r.status_code}"
                return {"error": {"code": "GOOGLE_API_ERROR", "message": f"Google API error: {err_text}"}}
            data = r.json()
            for m in data.get("models", []):
                if not isinstance(m, dict) or "name" not in m:
                    continue
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                lower_name = m["name"].lower()
                if any(x in lower_name for x in [
                    "embedding", "imagen", "veo", "audio", "vision",
                    "aqa", "tts", "-image", "image-generation", "computer-use",
                ]):
                    continue
                name = m["name"].replace("models/", "") if m["name"].startswith("models/") else m["name"]
                models.append(name)
                ctx = m.get("inputTokenLimit", 0)
                ctx_label = f"{ctx // 1000}k" if ctx >= 1000 else str(ctx)
                detail: Dict[str, Any] = {
                    "name": name,
                    "context_window": ctx_label,
                    "context_tokens": ctx,
                    "cost_tier": "Google Gemini",
                }
                model_details.append(detail)

    except Exception as e:
        return {"error": {"code": "CONNECTION_FAILED", "message": str(e)}}

    if req.provider != "ollama":
        for md in model_details:
            _annotate_license(md, provider=req.provider)

    return {"data": {"models": models, "model_details": model_details}}


@router.post("/api/llm/proxy/test")
def proxy_test(req: LLMProxyRequest) -> Dict[str, Any]:
    """Test endpoint connectivity."""
    url = req.url.rstrip("/")
    if not is_safe_url(url, req.provider):
        return {"data": {"success": False, "message": "Invalid or unsafe URL scheme", "models": []}}

    success = False
    message = ""
    models: List[str] = []

    try:
        if req.provider == "ollama":
            r = requests.get(f"{url}/api/tags", timeout=5)
            if r.status_code == 200:
                success = True
                data = r.json()
                models = [m["name"] for m in data.get("models", []) if "name" in m]
                message = f"Connected to Ollama v{r.headers.get('version', 'unknown')}"
            else:
                message = f"HTTP {r.status_code}: {r.text[:100]}"

        elif req.provider == "google":
            params = {"key": req.api_key} if req.api_key else {}
            target = f"{url}/v1beta/models"
            r = requests.get(target, params=params, timeout=5)
            if r.status_code == 200:
                success = True
                data = r.json()
                models = [
                    m["name"].replace("models/", "") if m["name"].startswith("models/") else m["name"]
                    for m in data.get("models", [])
                    if isinstance(m, dict) and "name" in m
                    and "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                message = "Connected successfully to Google Gemini"
            else:
                message = f"HTTP {r.status_code}: {r.text[:100]}"

        else:
            headers = _cloud_auth_headers(req.provider, req.api_key)
            target = f"{_openai_style_base(url)}/models"

            r = requests.get(target, headers=headers, timeout=5)
            if r.status_code == 200:
                success = True
                data = r.json()
                models = [m.get("id") for m in data.get("data", []) if "id" in m]
                message = "Connected successfully"
            else:
                message = f"HTTP {r.status_code}: {r.text[:100]}"

    except Exception as e:
        message = str(e)

    return {"data": {"success": success, "message": message, "models": models}}


@router.post("/api/llm/proxy/test-model")
def proxy_test_model(req: LLMModelTestRequest) -> Dict[str, Any]:
    """Test a specific model with a lightweight request."""
    url = req.url.rstrip("/")
    if not is_safe_url(url, req.provider):
        return {"data": {"success": False, "message": "Invalid or unsafe URL scheme", "model_status": "unknown"}}

    success = False
    message = ""
    model_status_str = "unknown"

    try:
        if req.provider == "ollama":
            if True:
                # Check if model is loaded
                try:
                    ps = requests.get(f"{url}/api/ps", timeout=5)
                    loaded_models = set()
                    if ps.status_code == 200:
                        for m in ps.json().get("models", []):
                            if "name" in m:
                                loaded_models.add(m["name"])
                except Exception:
                    loaded_models = set()

                if req.model not in loaded_models:
                    # Try to preload via /api/generate (Ollama auto-loads)
                    pass

                try:
                    r = requests.post(
                        f"{url}/api/generate",
                        json={"model": req.model, "prompt": "Hi", "stream": False},
                        timeout=30,
                    )
                    if r.status_code == 200:
                        success = True
                        load_info = ""
                        try:
                            resp_data = r.json()
                            load_ns = resp_data.get("load_duration", 0)
                            if load_ns > 0:
                                load_info = f" (load: {load_ns / 1e9:.1f}s)"
                        except Exception:
                            pass
                        message = f"Model responded successfully{load_info}"
                        model_status_str = "ready"
                    else:
                        try:
                            err_data = r.json()
                            ollama_err = err_data.get("error", "")
                        except Exception:
                            ollama_err = ""
                        if ollama_err:
                            message = f"Ollama error: {ollama_err}"
                        else:
                            message = f"HTTP {r.status_code}: {r.text[:200]}"
                except requests.Timeout:
                    message = f"Model '{req.model}' timed out (may still be loading)"
                    model_status_str = "loading"

        elif req.provider == "google":
            params = {"key": req.api_key} if req.api_key else {}
            target = f"{url}/v1beta/models/{req.model}:generateContent"
            try:
                r = requests.post(
                    target,
                    params=params,
                    json={
                        "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                        "generationConfig": {"maxOutputTokens": 5},
                    },
                    timeout=30,
                )
                if r.status_code == 200:
                    success = True
                    message = "Model responded successfully"
                    model_status_str = "ready"
                else:
                    message = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.Timeout:
                message = f"Model '{req.model}' timed out"

        elif req.provider == "anthropic":
            # Previously unhandled: an anthropic test-model request matched no
            # branch and fell through to `success: false` with an empty message.
            headers = _cloud_auth_headers(req.provider, req.api_key)
            headers["content-type"] = "application/json"
            r = requests.post(
                f"{_openai_style_base(url)}/messages",
                headers=headers,
                json={
                    "model": req.model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                timeout=30,
            )
            if r.status_code == 200:
                success = True
                message = "Model responded successfully"
                model_status_str = "ready"
            else:
                message = f"HTTP {r.status_code}: {r.text[:100]}"

        elif req.provider in ("openai", "openai-compatible", "lm-studio"):
            headers = _cloud_auth_headers(req.provider, req.api_key)
            base = _openai_style_base(url)

            if True:
                r = requests.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json={
                        "model": req.model,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5,
                    },
                    timeout=30,
                )

            if r.status_code == 200:
                success = True
                message = "Model responded successfully"
                model_status_str = "ready"
            else:
                message = f"HTTP {r.status_code}: {r.text[:100]}"

    except requests.Timeout:
        message = "Request timed out — model may still be loading."
        model_status_str = "loading"
    except Exception as e:
        message = str(e)

    return {"data": {
        "success": success,
        "message": message,
        "model_status": model_status_str,
    }}


# ── Local engine discovery (E-4) ─────────────────────────────────────────
#
# The frontend cannot probe localhost itself: served from
# http://localhost:8000 in a browser, a fetch to :11434 is cross-origin and
# fails whenever OLLAMA_ORIGINS is restricted. Probing from the server's own
# loopback interface sidesteps CORS entirely and works identically in the
# Tauri shell and the browser dashboard.

# Connect and read budgets. `requests` applies a scalar timeout to BOTH
# phases, so the tuple form is what actually bounds a probe. The connect
# budget is the one that matters for "is anything listening" — a closed port
# refuses immediately, so a slow connect means nothing is there. The read
# budget is looser because a *running* daemon with many models can take
# longer than half a second to enumerate them, and reporting a live engine as
# offline is the worse failure.
_DISCOVER_TIMEOUT = (0.5, 2.0)

# Ports are fixed on purpose: no user-supplied host reaches this route, so
# is_safe_url's early-return for local providers cannot be turned into an
# SSRF primitive here.
OLLAMA_DISCOVERY_URL = "http://localhost:11434"
LM_STUDIO_DISCOVERY_URL = "http://localhost:1234"


def _probe_ollama(url: str = OLLAMA_DISCOVERY_URL) -> Dict[str, Any]:
    """Probe a local Ollama daemon. Never raises."""
    result: Dict[str, Any] = {
        "running": False, "url": url, "version": None, "models": [],
    }
    try:
        r = requests.get(f"{url}/api/version", timeout=_DISCOVER_TIMEOUT)
        if r.status_code != 200:
            return result
        result["running"] = True
        result["version"] = (r.json() or {}).get("version")
    except Exception as e:
        logger.debug(f"Ollama discovery probe failed: {e}")
        return result

    try:
        r = requests.get(f"{url}/api/tags", timeout=_DISCOVER_TIMEOUT)
        if r.status_code == 200:
            result["models"] = [
                m["name"] for m in (r.json() or {}).get("models", [])
                if isinstance(m, dict) and m.get("name")
            ]
    except Exception as e:
        # Reachable but slow to enumerate: still running, just no list.
        logger.debug(f"Ollama tag listing failed: {e}")

    return result


def _probe_lm_studio(url: str = LM_STUDIO_DISCOVERY_URL) -> Dict[str, Any]:
    """Probe a local LM Studio server. Never raises.

    LM Studio has no version endpoint, so the model list doubles as the
    liveness check.
    """
    result: Dict[str, Any] = {"running": False, "url": url, "models": []}
    try:
        r = requests.get(f"{url}/v1/models", timeout=_DISCOVER_TIMEOUT)
        if r.status_code != 200:
            return result
        result["running"] = True
        result["models"] = [
            m["id"] for m in (r.json() or {}).get("data", [])
            if isinstance(m, dict) and m.get("id")
        ]
    except Exception as e:
        logger.debug(f"LM Studio discovery probe failed: {e}")
    return result


@router.get("/api/llm/discover")
def discover_local_engines() -> Dict[str, Any]:
    """Probe the standard local inference ports.

    The two probes run concurrently, so a dead port never adds its timeout to
    a live one's latency. Deliberately read-only: it reports what is running
    and does not register an endpoint in models.yml, because two
    saved_endpoints lists exist in that file and auto-writing to the wrong one
    creates the duplicates this redesign is removing.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        ollama_future = pool.submit(_probe_ollama)
        lm_studio_future = pool.submit(_probe_lm_studio)
        ollama = ollama_future.result()
        lm_studio = lm_studio_future.result()

    logger.info(
        f"Local engine discovery: ollama={ollama['running']} "
        f"({len(ollama['models'])} models), "
        f"lm_studio={lm_studio['running']} ({len(lm_studio['models'])} models)"
    )
    return {"data": {"ollama": ollama, "lm_studio": lm_studio}}
