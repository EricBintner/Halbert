"""
Halbert LLM Router — unified model picker backend.

Provides the API endpoints consumed by the vendored @prep/ui AIModelsSettings
component. The config is stored in models.yml using the unified LLMConfig
schema (shared with SourcePrep).

Endpoints:
  Global Config:
    - GET  /global/config          — read the full UI config (llm_config key)
    - PUT  /global/config          — merge-update global config

  LLM Proxy (model fetching & testing):
    - POST /api/llm/proxy/models       — list models from an endpoint
    - POST /api/llm/proxy/test         — test endpoint connectivity
    - POST /api/llm/proxy/test-model   — test a specific model
    - GET  /llm/plan-limits            — plan limits table (stub)

  Embedding:
    - GET  /embedding/status       — embedding model status
    - POST /embedding/download     — download HF embedding model

  LLM Status:
    - GET  /llm/slots/status       — per-slot connectivity (stub)
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
from typing import Any, Dict, List, Optional

import requests
import yaml
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...utils.platform import get_config_dir

logger = logging.getLogger("halbert.dashboard")

router = APIRouter(tags=["llm"])

# ── SSRF Protection ──────────────────────────────────────────────

_ALLOWED_LOCAL_PORTS = {11434, 1234, 1235}  # Ollama, LM Studio


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


# ── ConfigStore (YAML-based) ─────────────────────────────────────


def _config_path() -> "Any":
    """Path to models.yml — the unified LLM config store."""
    return get_config_dir() / "models.yml"


def _default_llm_config() -> Dict[str, Any]:
    """Default LLMConfig schema (matches @prep/ui types)."""
    return {
        "assignment_mode": "structured",
        "embedding": {
            "source": "endpoint",
        },
        "small_model": {"enabled": False},
        "large_model": {"enabled": False},
        "code_model": {"enabled": False},
        "coordinator_model": {"enabled": False, "inherit_from_large": True},
        "advanced": {
            "enforce_cloud_token_safety": True,
            "max_thinking_budget": 24576,
        },
        "saved_endpoints": [],
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into base (in-place on base)."""
    for key, val in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(val, dict)
        ):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def load_llm_config() -> Dict[str, Any]:
    """Load the LLM config from models.yml, merged with defaults."""
    cfg = _default_llm_config()
    path = _config_path()
    if path.exists():
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            # The llm_config may be stored at top level or under 'llm_config' key
            llm_data = data.get("llm_config", data)
            if isinstance(llm_data, dict):
                _deep_merge(cfg, llm_data)
        except Exception as e:
            logger.warning("Failed to load models.yml: %s", e)
    return cfg


def save_llm_config(llm_cfg: Dict[str, Any]) -> None:
    """Save the LLM config to models.yml.

    Preserves any non-LLM keys (orchestrator, specialist, routing, etc.)
    that Halbert's legacy settings.py wrote to the same file.
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing file to preserve non-LLM keys
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    existing["llm_config"] = llm_cfg
    with open(path, "w") as f:
        yaml.dump(existing, f, default_flow_style=False)


def load_full_ui_config() -> Dict[str, Any]:
    """Load the full UI config (for GET /global/config compatibility).

    Returns the entire models.yml content plus a computed llm_config key.
    """
    path = _config_path()
    cfg: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

    # Ensure llm_config is present and merged with defaults
    if "llm_config" not in cfg or not isinstance(cfg["llm_config"], dict):
        cfg["llm_config"] = _default_llm_config()
    else:
        merged = _default_llm_config()
        _deep_merge(merged, cfg["llm_config"])
        cfg["llm_config"] = merged

    return cfg


def save_full_ui_config(updates: Dict[str, Any]) -> List[str]:
    """Merge-update the full UI config (for PUT /global/config).

    Returns a list of warnings (currently always empty — no plan-tier
    validation in Halbert).
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    current = load_full_ui_config()

    # Deep merge the incoming updates
    _deep_merge(current, updates)

    # If llm_config was in the update, ensure it has defaults
    if "llm_config" in current and isinstance(current["llm_config"], dict):
        merged = _default_llm_config()
        _deep_merge(merged, current["llm_config"])
        current["llm_config"] = merged

    with open(path, "w") as f:
        yaml.dump(current, f, default_flow_style=False)

    return []


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
    kind: str = "completion"
    slot: Optional[str] = None


# ── Global Config Endpoints ──────────────────────────────────────


@router.get("/global/config")
def get_global_config() -> Dict[str, Any]:
    """Get global UI configuration (includes llm_config)."""
    return {"data": load_full_ui_config()}


@router.put("/global/config")
async def update_global_config(req: Request) -> Dict[str, Any]:
    """Update global UI configuration (merge update)."""
    try:
        data = await req.json()
    except Exception:
        return {"error": {"code": "INVALID_JSON", "message": "Invalid JSON body"}}

    if not isinstance(data, dict):
        return {"error": {"code": "VALIDATION_ERROR", "message": "Config must be a JSON object"}}

    warnings = save_full_ui_config(data)
    return {"data": load_full_ui_config(), "warnings": warnings}


# ── LLM Proxy Endpoints ──────────────────────────────────────────


def _ollama_show_detail(url: str, name: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Fetch context length from Ollama /api/show for a single model."""
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
        return {"context_tokens": ctx, "context_window": ctx_label}
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
                    if show and show["context_tokens"] > 0:
                        md["context_tokens"] = show["context_tokens"]
                        md["context_window"] = show["context_window"]

        elif req.provider in ("openai", "openai-compatible", "lm-studio", "anthropic"):
            headers = {}
            if req.api_key:
                headers["Authorization"] = f"Bearer {req.api_key}"

            target = f"{url}/models"
            if "v1" not in url and req.provider != "anthropic":
                target = f"{url}/v1/models"

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
            headers = {}
            if req.api_key:
                headers["Authorization"] = f"Bearer {req.api_key}"

            target = f"{url}/models"
            if "v1" not in url and req.provider != "anthropic":
                target = f"{url}/v1/models"

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
            if req.kind == "embedding":
                try:
                    r = requests.post(
                        f"{url}/api/embeddings",
                        json={"model": req.model, "prompt": "Test embedding"},
                        timeout=120,
                    )
                    if r.status_code == 200:
                        success = True
                        message = "Model responded successfully"
                        model_status_str = "ready"
                    else:
                        message = f"HTTP {r.status_code}: {r.text[:100]}"
                except requests.Timeout:
                    message = f"Model '{req.model}' timed out (may still be loading)"
                    model_status_str = "loading"
            else:
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

        elif req.provider in ("openai", "openai-compatible", "lm-studio"):
            headers = {}
            if req.api_key:
                headers["Authorization"] = f"Bearer {req.api_key}"

            base = url if "v1" in url else f"{url}/v1"

            if req.kind == "embedding":
                r = requests.post(
                    f"{base}/embeddings",
                    headers=headers,
                    json={"model": req.model, "input": "Test"},
                    timeout=30,
                )
            else:
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


# ── Plan Limits (stub — Halbert doesn't have concurrency_limits.json) ──


@router.get("/llm/plan-limits")
def get_plan_limits() -> Dict[str, Any]:
    """Plan limits table — stub for Halbert (no cloud concurrency management)."""
    return {"data": {"version": 1, "providers": {}}}


# ── Embedding Status ─────────────────────────────────────────────


@router.get("/embedding/status")
def embedding_status() -> Dict[str, Any]:
    """Embedding model status."""
    cfg = load_llm_config()
    emb = cfg.get("embedding", {})
    return {"data": {
        "source": emb.get("source", "endpoint"),
        "endpoint_id": emb.get("endpoint_id"),
        "model": emb.get("model"),
        "hf_repo_id": emb.get("hf_repo_id"),
        "hf_downloaded": emb.get("hf_downloaded", False),
        "hf_download_progress": emb.get("hf_download_progress"),
    }}


@router.post("/embedding/download")
def embedding_download() -> Dict[str, Any]:
    """Download HF embedding model — stub (Halbert uses endpoint-based embeddings)."""
    return {"data": {"status": "not_implemented", "message": "Use endpoint-based embeddings in Halbert."}}


# ── LLM Slots Status (stub — Halbert has no pipeline scheduler) ──


@router.get("/llm/slots/status")
def get_llm_slots_status() -> Dict[str, Any]:
    """Per-slot connectivity status — stub for Halbert."""
    cfg = load_llm_config()
    return {"data": {
        "assignment_mode": cfg.get("assignment_mode", "structured"),
        "embedding": {"status": "unknown"},
        "small_model": {"status": "unknown"},
        "large_model": {"status": "unknown"},
        "code_model": {"status": "unknown"},
    }}
