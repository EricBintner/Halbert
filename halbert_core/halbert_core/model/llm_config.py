# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Single owner of the ``llm_config`` section of models.yml.

Every reader and writer of Halbert's model configuration goes through this
module. Nothing else reads ``orchestrator`` / ``specialist`` / ``vision`` or
the SourcePrep-shaped ``small_model`` / ``large_model`` keys — those are
migrated here, once, and removed from the file.

Schema (documentation/design/model-picker-independent-2026-08-26.md §4)::

    llm_config:
      saved_endpoints: [{id, name, provider, url, api_key}]
      chat_model:       {enabled, endpoint_id, model}
      specialist_model: {enabled, endpoint_id, model}
      vision_model:     {enabled, endpoint_id, model}

Callers that change a slot send the whole slot dict (all three keys).
``CHAT_CAPABLE_PROVIDERS`` is imported lazily from :mod:`model.client` so the
two modules do not create a top-level import cycle.
"""
from __future__ import annotations

import copy
import logging
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import yaml

from .config_locator import find_models_config, write_models_config

logger = logging.getLogger("halbert.model.llm_config")

SLOTS = ("chat_model", "specialist_model", "vision_model")
LEGACY_KEYS = ("orchestrator", "specialist", "vision", "saved_endpoints")
DROPPED_KEYS = (
    "embedding", "small_model", "large_model", "code_model", "coordinator_model",
    "assignment_mode", "assignment_blocks", "advanced", "compute_nodes",
    "model_context_cache",
)
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _chat_capable_providers() -> FrozenSet[str]:
    """CHAT_CAPABLE_PROVIDERS from model.client (includes anthropic after E-1).

    Imported lazily to avoid a top-level import cycle: client.py imports this
    module at load time, so importing client.py here at load time would cycle.
    """
    from .client import CHAT_CAPABLE_PROVIDERS
    return CHAT_CAPABLE_PROVIDERS


class SlotProviderError(ValueError):
    """A slot names an endpoint whose provider the chat runtime cannot call."""

    def __init__(self, slot: str, provider: str):
        super().__init__(
            f"{slot} uses provider {provider!r}, which is not yet usable for chat"
        )
        self.slot = slot
        self.provider = provider


@dataclass(frozen=True)
class ResolvedModel:
    model: str
    url: str
    provider: str
    api_key: str = ""


def _empty_slot() -> Dict[str, Any]:
    return {"enabled": False, "endpoint_id": "", "model": ""}


def default_llm_config() -> Dict[str, Any]:
    return {
        "saved_endpoints": [],
        "chat_model": _empty_slot(),
        "specialist_model": _empty_slot(),
        "vision_model": _empty_slot(),
    }


def _new_id() -> str:
    return f"ep_{secrets.token_hex(4)}"


# ── File I/O ──────────────────────────────────────────────────────


def _read_path() -> Optional[Path]:
    return find_models_config(include_repo=False)


def _write_path() -> Path:
    return write_models_config()


def _chmod_600(path: Path) -> None:
    """Tighten permissions on a file that may hold API keys."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_raw() -> Dict[str, Any]:
    path = _read_path()
    if path is None:
        return {}
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:  # unreadable YAML: serve defaults, never rewrite
        logger.error("Could not read %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(data: Dict[str, Any]) -> None:
    """Write via a temp file + atomic rename so a crash never leaves a half file.

    The file is hardened to 0600 because it may contain cloud API keys.
    """
    path = _write_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".models-", suffix=".yml", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
        _chmod_600(path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup_before_rewrite() -> None:
    """Copy models.yml to models.yml.bak when about to rewrite the file that was read."""
    target = _write_path()
    source = _read_path()
    if source is not None and source == target and target.exists():
        bak = target.with_name(target.name + ".bak")
        shutil.copy2(target, bak)
        _chmod_600(bak)


# ── Normalisation ─────────────────────────────────────────────────


def _normalise_url(url: str) -> str:
    """Lowercase and strip trailing slashes so URL comparison is stable."""
    return (url or "").strip().rstrip("/").lower()


def _clean_endpoint(ep: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(ep, dict) or not ep.get("url"):
        return None
    url = str(ep["url"]).strip().rstrip("/")
    return {
        "id": str(ep.get("id") or "").strip() or _new_id(),
        "name": str(ep.get("name") or url),
        "provider": str(ep.get("provider") or "ollama"),
        "url": url,
        "api_key": str(ep.get("api_key") or ""),
    }


def normalise(llm: Any) -> Dict[str, Any]:
    """Coerce any llm_config-shaped dict onto the schema. Pure.

    Unknown keys are dropped. A slot is enabled only when it has a model and
    names an existing, chat-capable endpoint; anything else is disabled with a
    warning (hand-edited files get the same treatment as the UI).
    """
    src = llm if isinstance(llm, dict) else {}
    cfg = default_llm_config()
    endpoints: List[Dict[str, Any]] = []
    seen: set = set()
    for raw_ep in src.get("saved_endpoints") or []:
        ep = _clean_endpoint(raw_ep)
        if ep is None or ep["id"] in seen:
            continue
        seen.add(ep["id"])
        endpoints.append(ep)
    cfg["saved_endpoints"] = endpoints
    by_id = {e["id"]: e for e in endpoints}
    capable = _chat_capable_providers()
    for slot in SLOTS:
        raw = src.get(slot)
        raw = raw if isinstance(raw, dict) else {}
        model = str(raw.get("model") or "").strip()
        endpoint_id = str(raw.get("endpoint_id") or "").strip()
        enabled = bool(raw.get("enabled", bool(model))) and bool(model)
        if enabled and endpoint_id not in by_id:
            logger.warning("%s references unknown endpoint %r; slot disabled", slot, endpoint_id)
            enabled = False
        if enabled and by_id[endpoint_id]["provider"] not in capable:
            logger.warning(
                "%s uses provider %r which is not chat-capable; slot disabled",
                slot, by_id[endpoint_id]["provider"],
            )
            enabled = False
        cfg[slot] = {"enabled": enabled, "endpoint_id": endpoint_id, "model": model}
    return cfg


# ── Legacy migration ──────────────────────────────────────────────


def _match_endpoint(
    endpoints: List[Dict[str, Any]], endpoint_id: Any, url: Any, provider: str
) -> Optional[Dict[str, Any]]:
    if endpoint_id:
        for ep in endpoints:
            if ep["id"] == endpoint_id:
                return ep
    u = str(url or "").strip().rstrip("/")
    if u:
        for ep in endpoints:
            if ep["url"] == u and ep["provider"] == provider:
                return ep
        for ep in endpoints:
            if ep["url"] == u:
                return ep
    return None


def needs_migration(raw: Dict[str, Any]) -> bool:
    if any(k in raw for k in LEGACY_KEYS):
        return True
    llm = raw.get("llm_config")
    return isinstance(llm, dict) and any(k in llm for k in DROPPED_KEYS)


def migrate_legacy(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Fold legacy top-level keys into an llm_config dict. Pure; does not write.

    Precedence: an llm_config slot already enabled with a model wins; legacy
    keys only fill empty slots. Endpoints are the union of both lists,
    de-duplicated by (provider, url); on a duplicate the llm_config entry keeps
    its id and an empty api_key is back-filled from the legacy entry.
    """
    llm = copy.deepcopy(raw.get("llm_config") or {})
    if not isinstance(llm, dict):
        llm = {}
    endpoints: List[Dict[str, Any]] = []

    def _add(raw_ep: Any) -> None:
        ep = _clean_endpoint(raw_ep)
        if ep is None:
            return
        for existing in endpoints:
            if existing["url"] == ep["url"] and existing["provider"] == ep["provider"]:
                if not existing["api_key"] and ep["api_key"]:
                    existing["api_key"] = ep["api_key"]
                return
        endpoints.append(ep)

    for raw_ep in llm.get("saved_endpoints") or []:
        _add(raw_ep)
    for raw_ep in raw.get("saved_endpoints") or []:
        _add(raw_ep)
    llm["saved_endpoints"] = endpoints

    def _fold(target: str, legacy: Any, enabled: bool) -> None:
        legacy = legacy if isinstance(legacy, dict) else {}
        current = llm.get(target) if isinstance(llm.get(target), dict) else {}
        if current.get("enabled") and current.get("model"):
            return
        model = str(legacy.get("model") or "").strip()
        if not model:
            return
        provider = str(legacy.get("provider") or "ollama")
        ep = _match_endpoint(
            endpoints, legacy.get("endpoint_id"), legacy.get("endpoint"), provider
        )
        if ep is None:
            ep = {
                "id": _new_id(),
                "name": "Migrated endpoint",
                "provider": provider,
                "url": str(legacy.get("endpoint") or DEFAULT_OLLAMA_URL).rstrip("/"),
                "api_key": "",
            }
            endpoints.append(ep)
        llm[target] = {"enabled": enabled, "endpoint_id": ep["id"], "model": model}

    specialist = raw.get("specialist") if isinstance(raw.get("specialist"), dict) else {}
    _fold("chat_model", raw.get("orchestrator"), True)
    _fold("specialist_model", specialist, bool(specialist.get("enabled", False)))
    _fold("vision_model", raw.get("vision"), True)
    # SourcePrep-shaped slots: migrate only when they were actually in use.
    for source, target in (("small_model", "chat_model"), ("large_model", "specialist_model")):
        s = llm.get(source)
        if isinstance(s, dict) and s.get("enabled") and s.get("model"):
            _fold(target, {"model": s.get("model"), "endpoint_id": s.get("endpoint_id")}, True)
    for key in DROPPED_KEYS:
        llm.pop(key, None)
    return llm


def normalise_file(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Whole models.yml dict with llm_config migrated + normalised and legacy keys removed. Pure."""
    out = {k: copy.deepcopy(v) for k, v in raw.items() if k not in LEGACY_KEYS}
    out["llm_config"] = normalise(
        migrate_legacy(raw) if needs_migration(raw) else raw.get("llm_config")
    )
    return out


# ── Public API ────────────────────────────────────────────────────


def load_file() -> Dict[str, Any]:
    """The whole models.yml dict, post-migration. Rewrites the file once when legacy keys are found."""
    raw = _read_raw()
    out = normalise_file(raw)
    if needs_migration(raw):
        try:
            _backup_before_rewrite()
            _write_raw(out)
            llm = out["llm_config"]
            logger.info(
                "Migrated legacy model config: chat=%r specialist=%r vision=%r endpoints=%d",
                llm["chat_model"]["model"], llm["specialist_model"]["model"],
                llm["vision_model"]["model"], len(llm["saved_endpoints"]),
            )
        except Exception as e:
            logger.error("Could not rewrite models.yml after migration: %s", e)
    return out


def load() -> Dict[str, Any]:
    """The llm_config section, normalised."""
    return load_file()["llm_config"]


def save(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace llm_config in the file; legacy keys are dropped, every other key is kept."""
    raw = _read_raw()
    for key in LEGACY_KEYS:
        raw.pop(key, None)
    raw["llm_config"] = normalise(llm_config)
    _write_raw(raw)
    return raw["llm_config"]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, val in override.items():
        if isinstance(base.get(key), dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def update(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge ``partial`` into the current config and save.

    Raises :class:`SlotProviderError` when a slot with a model names an endpoint
    whose provider is not chat-capable — the UI must never save such a slot.
    """
    merged = _deep_merge(load(), copy.deepcopy(partial))
    endpoints = {e["id"]: e for e in normalise(merged)["saved_endpoints"]}
    capable = _chat_capable_providers()
    for slot in SLOTS:
        s = merged.get(slot) if isinstance(merged.get(slot), dict) else {}
        ep = endpoints.get(str(s.get("endpoint_id") or ""))
        if s.get("model") and ep is not None and ep["provider"] not in capable:
            raise SlotProviderError(slot, ep["provider"])
    return save(merged)


def set_slot(slot: str, model: str, endpoint_id: str) -> Dict[str, Any]:
    return update({slot: {"enabled": bool(model), "endpoint_id": endpoint_id, "model": model}})


def set_top_level(key: str, value: Any) -> None:
    """Write a non-llm_config key (e.g. ``compression``) without disturbing llm_config."""
    raw = _read_raw()
    llm = normalise(
        migrate_legacy(raw) if needs_migration(raw) else raw.get("llm_config")
    )
    for legacy in LEGACY_KEYS:
        raw.pop(legacy, None)
    raw["llm_config"] = llm
    raw[key] = value
    _write_raw(raw)


def resolve_from(file_cfg: Dict[str, Any], slot: str) -> Optional[ResolvedModel]:
    """Resolve a slot against an already-loaded (normalised) models.yml dict."""
    llm = file_cfg.get("llm_config") or {}
    s = llm.get(slot) or {}
    if not s.get("enabled"):
        return None
    for ep in llm.get("saved_endpoints") or []:
        if ep.get("id") == s.get("endpoint_id"):
            return ResolvedModel(
                model=s["model"], url=ep["url"], provider=ep["provider"],
                api_key=ep.get("api_key") or "",
            )
    return None


def resolve(slot: str) -> Optional[ResolvedModel]:
    """(model, url, provider, api_key) for an enabled slot, else None."""
    return resolve_from(load_file(), slot)


def _endpoints_matching(url: str) -> List[Dict[str, Any]]:
    """Saved endpoints whose URL matches ``url`` (case/trailing-slash insensitive)."""
    target = _normalise_url(url)
    if not target:
        return []
    return [
        ep for ep in (load().get("saved_endpoints") or [])
        if isinstance(ep, dict) and _normalise_url(ep.get("url", "")) == target
    ]


def api_key_for(url: str) -> str:
    """API key of the first saved endpoint whose url matches, else ""."""
    for ep in _endpoints_matching(url):
        key = ep.get("api_key") or ""
        if key:
            return key
    return ""


def provider_for(url: str, default: str = "ollama") -> str:
    """Provider of the first saved endpoint matching ``url``, else ``default``."""
    for ep in _endpoints_matching(url):
        provider = ep.get("provider") or ""
        if provider:
            return provider
    return default


def resolve_endpoint_by_id(endpoint_id: str) -> Optional[Tuple[str, str, str]]:
    """Public (url, provider, api_key) for a saved endpoint id, or None."""
    if not endpoint_id:
        return None
    for ep in load()["saved_endpoints"]:
        if ep.get("id") == endpoint_id:
            return (ep.get("url", DEFAULT_OLLAMA_URL), ep.get("provider", "ollama"), ep.get("api_key") or "")
    return None


def ensure_ollama_endpoint(url: str = DEFAULT_OLLAMA_URL) -> str:
    """Id of the Ollama endpoint at ``url``; creates "Local Ollama" if absent."""
    cfg = load()
    u = url.rstrip("/")
    for ep in cfg["saved_endpoints"]:
        if ep["provider"] == "ollama" and ep["url"] == u:
            return ep["id"]
    ep = {"id": _new_id(), "name": "Local Ollama", "provider": "ollama", "url": u, "api_key": ""}
    cfg["saved_endpoints"].append(ep)
    save(cfg)
    return ep["id"]


def _probe_ollama(url: str, timeout: float) -> bool:
    try:
        import requests
        return requests.get(f"{url}/api/tags", timeout=timeout).status_code == 200
    except Exception:
        return False


def ensure_local_ollama_endpoint(timeout: float = 2.0) -> bool:
    """Fresh install helper: with no endpoints saved, add Local Ollama if :11434 answers."""
    if load()["saved_endpoints"]:
        return False
    if not _probe_ollama(DEFAULT_OLLAMA_URL, timeout):
        return False
    ensure_ollama_endpoint(DEFAULT_OLLAMA_URL)
    return True
