# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Halbert LLM Router — model picker backend.

Endpoints:
  Config:
    - GET  /llm/config             — the global layer (what an edit writes to)
    - PUT  /llm/config             — merge-update the global layer (whole slots)
    - GET  /llm/config/effective   — read-only merged view + which layer won each slot

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

_ALLOWED_LOCAL_PORTS = {11434, 1234, 1235, 11435}  # Ollama, LM Studio, Apple Intelligence

# Upper bound on per-model /api/show enrichment. Generous enough to cover any
# realistic local library; a bound still exists so a pathological endpoint
# cannot stall the listing.
_OLLAMA_SHOW_LIMIT = 200

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
        if provider in ("ollama", "lm-studio", "apple-foundation"):
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
from ...model.config_layers import GLOBAL_LAYER


class LLMConfigUpdate(BaseModel):
    llm_config: Dict[str, Any]


def _providers() -> List[str]:
    from ...model.client import CHAT_CAPABLE_PROVIDERS
    return sorted(CHAT_CAPABLE_PROVIDERS)


def _redact_api_keys(llm_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """A shallow copy of an llm_config dict with every endpoint's api_key redacted.

    R05-F3: GET (and the PUT response, which re-serves the same payload)
    must never carry a saved secret back to the browser. The real value
    is replaced with "" and ``key_set`` tells the UI whether one is
    configured, so a saved key can still be shown as present without
    ever leaving the server. This is safe for the write side too:
    ``_carry_forward_api_keys`` (llm_config.py) re-attaches the stored
    key to any endpoint a client PUTs back without an ``api_key`` field,
    so the client never needs to see — or echo — the real value to keep
    it. An explicit ``api_key: ""`` in a PUT still clears it, unchanged.
    """
    out = dict(llm_cfg)
    endpoints = out.get("saved_endpoints")
    if isinstance(endpoints, list):
        out["saved_endpoints"] = [
            {**ep, "api_key": "", "key_set": bool(ep.get("api_key"))}
            if isinstance(ep, dict) else ep
            for ep in endpoints
        ]
    return out


def _effective_block(layered: llm_store.LayeredConfig) -> Dict[str, Any]:
    """The read-only half: what is in force, and which layer put it there."""
    return {
        "llm_config": _redact_api_keys(layered.effective),
        "slot_layers": layered.slot_layers,
        "layers": layered.layers,
        "overridden_slots": {
            slot: name for slot, name in layered.slot_layers.items() if name != GLOBAL_LAYER
        },
    }


def _editor_payload(session_id: Optional[str] = None) -> Dict[str, Any]:
    """The global layer to edit, with the effective view attached read-only.

    ``llm_config`` is deliberately the global layer and not the merged one. The
    drawer is a read-modify-write over HTTP, so serving it the merged view
    wrote the workspace layer's endpoints and the session's pins into the
    user's own models.yml the first time anyone opened Settings — the reason
    ``git config`` makes you say ``--global`` or ``--local``.
    """
    layered = llm_store.load_layered(session_id)
    return {
        "llm_config": _redact_api_keys(layered.global_config),
        "chat_capable_providers": _providers(),
        "effective": _effective_block(layered),
    }


@router.get("/llm/config")
def get_llm_config(session_id: Optional[str] = None) -> Dict[str, Any]:
    """The global layer, the layer an edit writes to.

    On a fresh install this registers Local Ollama when it answers, so the
    endpoint list is not empty. It does **not** choose a model: which model
    answers is the operator's decision, and Quick-setup offers a hardware-fitted
    suggestion they can take or ignore. Opting in with
    ``first_run: {auto_select_model: true}`` makes it choose one for them.

    ``ensure_local_ollama_endpoint`` returns True only when the saved list was
    empty and :11434 answered, which is the one moment nobody's choice can be
    overwritten — every later call leaves a cleared slot cleared.

    On Apple Silicon Macs that qualify for Apple Intelligence, the
    ``apple-foundation`` endpoint is registered and assigned to
    ``secure_model`` (and ``chat_model`` on 16-24GB Macs) before the Ollama
    probe runs. This is idempotent and only fills empty slots. Home
    automation variants (home) skip it entirely: secure_model is
    a sysadmin-instance slot they never configure.
    """
    from . import settings as settings_routes

    try:
        # Apple Intelligence provisioning runs first: it is idempotent
        # (checks for an existing apple-foundation endpoint, not whether
        # any endpoints exist) and only fills empty slots, so it cannot
        # overwrite a user's choice or interfere with the Ollama probe.
        #
        # The hardware detection (system_profiler + sysctl + bridge probe)
        # is expensive (~1s), so it is skipped when the apple-foundation
        # endpoint is already registered — the common case after first boot.
        # Gated by CAP_SECURE_MODEL_ALLOWED — "may this variant host a
        # secure model at all" (preset/override, home defaults off, being.yml
        # can override) — never CAP_SECURE_MODEL, which means "one is
        # already configured" and would make this gate circular on a fresh
        # install (U4-18): auto_provision_apple_intelligence itself checks
        # whether the FoundationModels bridge is actually running before
        # assigning anything.
        try:
            from ...capabilities import has_capability, CAP_SECURE_MODEL_ALLOWED
            from ...model.auto_provision import auto_provision_apple_intelligence
            from ...model import llm_config as _cfg
            already_provisioned = any(
                ep.get("provider") == _cfg.APPLE_FOUNDATION_PROVIDER
                for ep in _cfg.load_global(use_cache=False).get("saved_endpoints", [])
            )
            if not already_provisioned and has_capability(CAP_SECURE_MODEL_ALLOWED):
                from ...model.hardware_detector import HardwareDetector
                hw = HardwareDetector().detect()
                auto_provision_apple_intelligence(hw)
        except Exception as e:
            logger.debug(f"Apple Intelligence auto-provisioning skipped: {e}")

        if llm_store.ensure_local_ollama_endpoint() and llm_store.auto_select_enabled():
            settings_routes.configure_first_run_model()
    except llm_store.ConfigUnreadableError as e:
        # Reading still works (the store serves defaults), so show the picker
        # rather than an error page — but say why nothing can be saved.
        logger.error("models.yml is unreadable: %s", e)
        return {"data": {**_editor_payload(session_id), "config_error": str(e)}}
    return {"data": _editor_payload(session_id)}


@router.get("/llm/config/effective")
def get_effective_llm_config(session_id: Optional[str] = None) -> Dict[str, Any]:
    """Read-only: the merged config a model runtime resolves against.

    There is no PUT beside this one on purpose. An editor must name the layer
    it edits, and nothing can write to a merged view without copying somebody
    else's layer into the file it saves.
    """
    layered = llm_store.load_layered(session_id)
    return {"data": {**_effective_block(layered), "chat_capable_providers": _providers()}}


@router.put("/llm/config")
def update_llm_config(body: LLMConfigUpdate, session_id: Optional[str] = None):
    """Deep-merge a partial llm_config into the *global* layer and return it.

    Callers send whole slots. The write rebases on the global layer, and GET
    serves that same layer, so neither end of the round trip can carry a
    workspace endpoint or a session pin into the user's file.
    """
    try:
        llm_store.update(body.llm_config)
    except llm_store.ConfigUnreadableError as e:
        return JSONResponse(
            status_code=409,
            content={"error": {
                "code": "CONFIG_UNREADABLE",
                "path": str(e.path),
                "message": str(e),
            }},
        )
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
    return {"data": _editor_payload(session_id)}


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


def _publish_context_limit(name: str, tokens: Any) -> None:
    """Tell the model runtime a model's real context window.

    ``compute_num_ctx`` has always taken a cap and nothing ever supplied one,
    so every local call was sized against the 32768 fallback — up to ~2GB of KV
    cache for a 7B, against the no-options-block behaviour that shipped before.
    Listing models for the picker already learns the true window, so the fix
    costs no extra request: it is published from here.

    Only ever an architecture maximum, read from /api/show's ``model_info``.
    The runtime refuses to lower a window it already knows, so a wrong small
    number cannot start truncating prompts — but it equally cannot be taken
    back, which is why the weaker number in a model listing goes through
    :func:`_publish_listing_context_limit` instead.
    """
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
        return
    try:
        from ...model.client import remember_model_context_limit
    except Exception:  # pragma: no cover - the picker must still list models
        return
    remember_model_context_limit(name, tokens)


def _publish_listing_context_limit(name: str, tokens: Any) -> None:
    """Tell the model runtime what /api/tags said, on the runtime's terms.

    The listing's ``details.context_length`` is one unlabelled number with no
    way to tell an architecture maximum from a load-time default, so the
    runtime accepts it only where it cannot cap anything (see
    ``client.remember_listing_context_length``). The enrichment pass below
    publishes the corroborated number for every model it covers, so nothing is
    lost for a model the picker actually inspects — while a model past the
    /api/show cap, or a daemon whose /api/show is unavailable, falls back to
    the fallback ceiling rather than to a number nobody checked.
    """
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
        return
    try:
        from ...model.client import remember_listing_context_length
    except Exception:  # pragma: no cover - the picker must still list models
        return
    remember_listing_context_length(name, tokens)


def _architecture_context_length(data: Dict[str, Any]) -> int:
    """The largest window the weights can hold, from /api/show's ``model_info``.

    The key selection lives beside the cap it feeds
    (``model.client.architecture_context_length``) rather than here, because
    the model runtime's own endpoint probe has to apply exactly the same
    discrimination when it confirms a window from /api/show — and a second
    copy of "which of these keys is the model's window" is how the two paths
    would drift apart.
    """
    try:
        from ...model.client import architecture_context_length
    except Exception:  # pragma: no cover - the picker must still list models
        return 0
    return architecture_context_length(data.get("model_info"))


def _modelfile_num_ctx(data: Dict[str, Any]) -> int:
    """The Modelfile's ``num_ctx`` — the window the model is LOADED with by
    default, which is a different number from the architecture maximum and
    routinely a small fraction of it (measured live: 8192 against 262144).

    Reported for display, never used as a cap. Capping num_ctx here would pin
    that model at 8192 and silently truncate the head of every larger prompt —
    the exact failure sizing num_ctx exists to prevent.
    """
    for line in str(data.get("parameters") or "").split("\n"):
        line = line.strip()
        if line.startswith("num_ctx"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return 0
    return 0


def _ollama_show_detail(url: str, name: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Fetch context length, licence text and capabilities from Ollama /api/show."""
    try:
        r = requests.post(
            f"{url}/api/show",
            json={"name": name},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        num_ctx_default = _modelfile_num_ctx(data)
        architecture_tokens = _architecture_context_length(data)
        # The architecture maximum is the real context window. The Modelfile
        # default is the last resort for old daemons that report no model_info
        # at all — better than showing nothing — but it stays out of
        # ``architecture_tokens``, which is the only field allowed to cap
        # num_ctx. Letting it through there is precisely the truncation trap.
        ctx = architecture_tokens or num_ctx_default
        ctx_label = f"{ctx // 1000}k" if ctx >= 1000 else str(ctx) if ctx > 0 else ""
        lic = data.get("license")
        if isinstance(lic, list):
            lic = "\n\n".join(str(x) for x in lic)
        return {
            "context_tokens": ctx,
            "context_window": ctx_label,
            "architecture_tokens": architecture_tokens,
            "num_ctx_default": num_ctx_default,
            "license": lic if isinstance(lic, str) else None,
            "capabilities": data.get("capabilities"),
        }
    except Exception:
        return None


# What a provider genuinely asserts about every model it serves. Authority is
# per-capability, not per-provider: Ollama can say its models call tools, but
# it says nothing about vision until /api/show reports it, and lm-studio /
# openai-compatible are transports that will serve anything, so they assert
# nothing at all.
_PROVIDER_ASSERTS: Dict[str, tuple] = {
    "anthropic": ("vision", "tool_use"),
    "openai": ("tool_use",),
    "openrouter": ("tool_use",),
    "ollama": ("tool_use",),
    "apple-foundation": ("tool_use",),
}


def _add_capabilities(detail: Dict[str, Any], name: str, provider: str, runtime: Optional[Dict[str, Any]] = None) -> None:
    """Set vision/tool_use/reasoning on a model_details entry (D-4).

    Delegates to model.capabilities.ModelCapabilities.detect(), which layers
    generic name tokens, provider-level defaults and (when given) runtime
    metadata such as Ollama's own reported `capabilities` list. No cloud
    model-name table is added here — see the module docstring in
    tests/test_llm_proxy_capabilities.py for why.

    A capability we could not determine is **omitted**, never emitted as
    ``False``. The distinction matters: the picker filters roles on these
    flags, so asserting "no tools" for a provider we simply cannot inspect
    empties the Chat dropdown, and asserting "no vision" for an Ollama daemon
    that does not report capabilities empties the Vision dropdown. Absent
    means unknown, and the picker lets unknown through.
    """
    from ...model.capabilities import ModelCapabilities

    caps = ModelCapabilities.detect(name, provider, runtime=runtime)
    # A runtime capabilities list comes from the model itself; a provider in
    # the set above makes a genuine claim. Otherwise only a positive name-token
    # match is worth reporting.
    from_runtime = bool(runtime and runtime.get("capabilities"))
    asserted = _PROVIDER_ASSERTS.get(provider, ())
    for key, value in (
        ("vision", caps.vision),
        ("tool_use", caps.tool_use),
        ("reasoning", caps.reasoning),
    ):
        if value or from_runtime or key in asserted:
            detail[key] = value
        else:
            detail.pop(key, None)


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
                        # /api/tags already carries a context window for most
                        # models, so the listing the picker does anyway answers
                        # for all of them in one round trip. (Verified live: it
                        # reports the architecture maximum, not the Modelfile
                        # default — 262144 for a model whose Modelfile sets
                        # num_ctx 8192.) It is DISPLAYED as it comes; the
                        # num_ctx cap is a stricter question, so it goes to the
                        # runtime as a listing, not as an architecture maximum,
                        # and the /api/show pass below is what confirms a
                        # window small enough to cap anything.
                        tags_ctx = (m.get("details") or {}).get("context_length")
                        if isinstance(tags_ctx, int) and not isinstance(tags_ctx, bool) and tags_ctx > 0:
                            detail["context_tokens"] = tags_ctx
                            detail["context_window"] = (
                                f"{tags_ctx // 1000}k" if tags_ctx >= 1000 else str(tags_ctx)
                            )
                            _publish_listing_context_limit(name, tags_ctx)
                        _add_capabilities(detail, name, "ollama")
                        model_details.append(detail)

                # Enrich every model with /api/show. Since D-4 this decides
                # whether a model is selectable at all — a cap here silently
                # hid vision models past the cut, in whatever order /api/tags
                # happened to return them. Run them concurrently so covering
                # the whole list costs roughly one round trip.
                shown = model_details[:_OLLAMA_SHOW_LIMIT]
                if len(model_details) > _OLLAMA_SHOW_LIMIT:
                    logger.warning(
                        "Endpoint lists %d models; enriching only the first %d. "
                        "Capabilities for the rest are reported as unknown.",
                        len(model_details), _OLLAMA_SHOW_LIMIT,
                    )
                with ThreadPoolExecutor(max_workers=8) as pool:
                    shows = list(pool.map(
                        lambda md: _ollama_show_detail(url, md["name"]), shown
                    ))
                for md, show in zip(shown, shows):
                    if not show:
                        continue
                    if show["context_tokens"] > 0:
                        md["context_tokens"] = show["context_tokens"]
                        md["context_window"] = show["context_window"]
                    # Only the architecture maximum may cap num_ctx. The
                    # Modelfile default that show falls back to for display is
                    # deliberately not published.
                    _publish_context_limit(md["name"], show.get("architecture_tokens"))
                    if show.get("license"):
                        _annotate_license(md, license_text=show["license"])
                    if show.get("capabilities"):
                        # Live data from the model itself supersedes the
                        # name-only guess above.
                        _add_capabilities(
                            md, md["name"], "ollama",
                            runtime={
                                "capabilities": show["capabilities"],
                                "context_length": show.get("context_tokens"),
                            },
                        )

        elif req.provider in ("openai", "openai-compatible", "lm-studio", "anthropic", "apple-foundation"):
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
                        _add_capabilities(detail, name, req.provider)
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
                _add_capabilities(detail, name, "google")
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

        elif req.provider in ("openai", "openai-compatible", "lm-studio", "apple-foundation"):
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
APPLE_FOUNDATION_DISCOVERY_URL = "http://127.0.0.1:11435"


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


def _probe_apple_foundation(url: str = APPLE_FOUNDATION_DISCOVERY_URL) -> Dict[str, Any]:
    """Probe the Swift FoundationModels bridge. Never raises.

    The bridge is a Tauri sidecar that exposes Apple Intelligence via an
    OpenAI-compatible server on loopback:11435. When it answers, Apple
    Intelligence is fully available; when it does not, the host may still
    be *eligible* (detected separately by the hardware detector) but the
    endpoint is inert.
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
        logger.debug(f"Apple Foundation discovery probe failed: {e}")
    return result


@router.get("/api/llm/discover")
def discover_local_engines() -> Dict[str, Any]:
    """Probe the standard local inference ports.

    The three probes run concurrently, so a dead port never adds its timeout to
    a live one's latency. Deliberately read-only: it reports what is running
    and does not register an endpoint in models.yml, because two
    saved_endpoints lists exist in that file and auto-writing to the wrong one
    creates the duplicates this redesign is removing.
    """
    with ThreadPoolExecutor(max_workers=3) as pool:
        ollama_future = pool.submit(_probe_ollama)
        lm_studio_future = pool.submit(_probe_lm_studio)
        apple_future = pool.submit(_probe_apple_foundation)
        ollama = ollama_future.result()
        lm_studio = lm_studio_future.result()
        apple_foundation = apple_future.result()

    logger.info(
        f"Local engine discovery: ollama={ollama['running']} "
        f"({len(ollama['models'])} models), "
        f"lm_studio={lm_studio['running']} ({len(lm_studio['models'])} models), "
        f"apple_foundation={apple_foundation['running']} ({len(apple_foundation['models'])} models)"
    )
    return {"data": {
        "ollama": ollama,
        "lm_studio": lm_studio,
        "apple_foundation": apple_foundation,
    }}
