# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The utility slot — a per-provider-resolved cheap model for internal side tasks.

Internal side work (summarization, titling, future TTS summarization) should
not burn the chat slot. But a hardcoded cheap-model ID rots: catalogs change
under a long-lived install, and a baked-in name is also a model Halbert would
be naming, which a standing founder directive forbids. So the utility model
is never hardcoded. It is *resolved*, per call, through a fail-soft ladder
whose every rung draws on the operator's own runtime or config.

The ladder (:func:`_resolve_aux`), first rung that yields wins:

1. **Declared** — the ``utility_model`` slot in models.yml, the operator's own
   pin on a provider endpoint (D-7's new fifth slot). Explicit configuration
   is never overridden by a heuristic, so this rung is first whatever
   ``prefer_fast`` says.
2. **Live catalog** — attempted only on a per-task ``prefer_fast`` opt-in:
   probe the anchor model's provider catalog once (short timeout), match the
   anchor's own family, and take the strictly smallest same-family model
   actually listed. This is Hermes's "resolves from the provider's own
   catalog" rung — the only rung that can find a *cheaper* model than the
   operator already runs, and the only one that costs a round-trip, which is
   why the opt-in gates it. No family match, no size signal, or a dead
   endpoint is a miss, never an error.
3. **Legacy dict** — a pre-migration ``llm_config.small_model`` entry (the
   SourcePrep shape: dict or bare string). It is read from the raw file
   BEFORE the ladder's first load, because migrating the file removes the
   key; the read is what keeps the rung reachable on the first resolution of
   an old file. It sits before the chat floor, not after (the blueprint's
   "curated default → legacy dict" is reordered here) because the curated
   rung, name-neutrally, *is* the chat slot — see below — and the floor must
   stay last.
4. **Chat floor** — the operator's chat model: the curated default, adapted.
   The blueprint's curated rung would bake a known-good ID into source, which
   the no-names directive forbids; the nearest neutral equivalent is the
   model the operator already runs and trusts. When chat is unset too, the
   ladder returns None and the caller falls back however it must — the
   fail-soft the lift packet requires (unset → callers fall back to the chat
   slot).

Every rung is individually fail-soft: an exception inside one falls through
to the next, and the module raises nothing for a broken world (unparsable
models.yml, no file, unreachable endpoint all resolve to None or the floor).

**No model names in source.** The family match is generic string arithmetic
over the operator's own configured model and the provider's own listing; the
one size parser used is hardware_detector's, which parses whatever the
catalog reports. Nothing here names, recommends, or prefers any model family.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml

from . import llm_config
from .llm_config import ResolvedModel
from .config_locator import find_models_config

logger = logging.getLogger("halbert.model.utility_slot")

__all__ = ["AuxSource", "resolve_aux_model"]


class AuxSource(str, Enum):
    """Which ladder rung produced the answer."""

    NONE = "none"          # unset and nothing to fall back to
    DECLARED = "declared"  # the utility_model slot itself
    CATALOG = "catalog"    # live-catalog family match (prefer_fast only)
    LEGACY = "legacy"      # pre-migration small_model entry
    CHAT = "chat"          # the chat slot — the name-neutral curated floor


# Probes are attempted only for providers whose catalogs are cheap GETs of a
# stable shape. Others (anthropic, peer) are a deliberate miss — fail-soft —
# until a caller profile justifies their probe shape.
_OLLAMA_PROVIDERS = frozenset({"ollama"})
_GENERIC_MODELS_PATH_PROVIDERS = frozenset(
    {"openai", "openai-compatible", "lm-studio", "apple-foundation", "llamacpp", "mlx"}
)

_CATALOG_TIMEOUT = 2.0
_MIN_FAMILY_TOKEN = 3


# ── Ladder ────────────────────────────────────────────────────────


def resolve_aux_model(
    session_id: Optional[str] = None,
    task: str = "utility",
    prefer_fast: bool = False,
) -> Optional[ResolvedModel]:
    """A model for an internal side task, or None when nothing can serve one.

    ``task`` is provenance only (it names the log line, never the model).
    ``prefer_fast`` is the per-task opt-in to the catalog rung — the only
    rung that may return something cheaper than what the operator runs;
    without it the ladder costs no round-trip.
    """
    resolved, _source = _resolve_aux(session_id=session_id, task=task, prefer_fast=prefer_fast)
    return resolved


def _resolve_aux(
    session_id: Optional[str] = None,
    task: str = "utility",
    prefer_fast: bool = False,
) -> Tuple[Optional[ResolvedModel], AuxSource]:
    """The ladder proper: (model, rung). Private; tests drive this directly."""
    # Captured before any load: migrating the file on first read removes the
    # legacy key, so the rung below reads the raw bytes up front.
    legacy = _legacy_aux_entry()

    try:
        declared = llm_config.resolve("utility_model", session_id)
    except Exception as e:
        logger.debug("utility ladder: declared rung failed (%s)", e)
        declared = None
    if declared is not None:
        return declared, AuxSource.DECLARED

    anchor: Optional[ResolvedModel] = None
    if prefer_fast:
        anchor = _anchor(session_id)
        if anchor is not None:
            picked = _catalog_pick(anchor)
            if picked is not None:
                return picked, AuxSource.CATALOG

    if legacy:
        resolved = _resolve_legacy(legacy, anchor or _anchor(session_id))
        if resolved is not None:
            return resolved, AuxSource.LEGACY

    try:
        chat = llm_config.resolve("chat_model", session_id)
    except Exception as e:
        logger.debug("utility ladder: chat floor failed (%s)", e)
        chat = None
    if chat is not None:
        return chat, AuxSource.CHAT
    return None, AuxSource.NONE


def _anchor(session_id: Optional[str]) -> Optional[ResolvedModel]:
    """The model whose family and endpoint the catalog rung matches against.

    The chat slot, falling back to the specialist and then the secure slot —
    whichever the operator actually runs. All unset: no anchor, no rung.
    """
    for slot in ("chat_model", "specialist_model", "secure_model"):
        try:
            resolved = llm_config.resolve(slot, session_id)
        except Exception as e:
            logger.debug("utility ladder: anchor %s failed (%s)", slot, e)
            resolved = None
        if resolved is not None:
            return resolved
    return None


# ── Rung 2: live-catalog family match ─────────────────────────────


def _catalog_pick(anchor: ResolvedModel) -> Optional[ResolvedModel]:
    """The smallest strictly-cheaper same-family model the provider lists.

    One probe, short timeout, best effort. Anything odd — no listing, no size
    signal, no family match, an endpoint that will not answer — is a miss and
    the ladder falls through; it is never an error.
    """
    try:
        entries = _fetch_catalog(anchor.url, anchor.provider, anchor.api_key)
    except Exception as e:
        logger.debug("utility ladder: catalog probe of %s failed (%s)", anchor.url, e)
        return None
    token = _family_token(anchor.model)
    if token is None:
        return None
    anchor_b = _params_b({"name": anchor.model})
    if anchor_b is None:
        return None  # no size signal for the anchor: nothing can be called smaller
    best_name: Optional[str] = None
    best_b = anchor_b
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or entry.get("model") or "").strip()
        if not name or "embed" in name.lower():
            continue
        candidate_token = _family_token(name)
        if not _same_family(candidate_token, token):
            continue
        b = _params_b(entry)
        if b is None or b >= best_b:
            continue
        best_name, best_b = name, b
    if best_name is None:
        return None
    return ResolvedModel(
        model=best_name, url=anchor.url, provider=anchor.provider, api_key=anchor.api_key
    )


def _fetch_catalog(url: str, provider: str, api_key: str = "") -> List[Dict[str, Any]]:
    """The provider's live model listing, best effort. Injectable in tests.

    Ollama answers ``GET /api/tags`` with ``{models: [...]}``. Providers
    speaking OpenAI's wire format answer ``GET /models`` (or ``/v1/models``,
    for endpoints whose URL does not already carry the version) with
    ``{data: [{id: ...}]}`` — reshaped here to the ``name``-keyed entries the
    ladder ranks. Any other provider, or any failure at all, is an empty
    answer: a miss the ladder falls through, never an exception.
    """
    import requests

    base = (url or "").rstrip("/")
    if not base:
        return []
    if provider in _OLLAMA_PROVIDERS:
        response = requests.get(f"{base}/api/tags", timeout=_CATALOG_TIMEOUT)
        if response.status_code != 200:
            return []
        return [e for e in (response.json() or {}).get("models") or [] if isinstance(e, dict)]
    if provider in _GENERIC_MODELS_PATH_PROVIDERS:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        for path in ("/models", "/v1/models"):
            try:
                response = requests.get(f"{base}{path}", headers=headers, timeout=_CATALOG_TIMEOUT)
            except Exception:
                continue
            if response.status_code != 200:
                continue
            data = (response.json() or {}).get("data") or []
            return [
                {"name": str(entry.get("id") or "")}
                for entry in data if isinstance(entry, dict) and entry.get("id")
            ]
    return []


def _family_token(model_name: str) -> Optional[str]:
    """The family part of a model name — generic parsing, no names of its own.

    ``family-a:3b-instruct`` → ``family-a``; a colon-less id is its own family
    token. None when nothing parseable remains.
    """
    token = (model_name or "").strip().lower().split(":", 1)[0].strip()
    return token or None


def _same_family(candidate: Optional[str], reference: str) -> bool:
    """True when two family tokens name the same base family.

    Equal, or one a prefix of the other (``family`` ↔ ``family-coder``), with
    a floor on length so a stray common prefix cannot fuse unrelated names.
    """
    if not candidate or len(candidate) < _MIN_FAMILY_TOKEN or len(reference) < _MIN_FAMILY_TOKEN:
        return False
    return candidate == reference or candidate.startswith(reference) or reference.startswith(candidate)


def _params_b(entry: Dict[str, Any]) -> Optional[float]:
    """A parameter-count estimate for a catalog entry, or None.

    hardware_detector's estimator — the same generic parsing the first-run
    picker uses — prefers runtime metadata, then a size tag in the name, then
    the weight file size. Imported lazily: hardware_detector pulls psutil,
    which nothing on this import path otherwise needs.
    """
    try:
        from .hardware_detector import estimate_model_params_b
        return estimate_model_params_b(entry)
    except Exception as e:
        logger.debug("utility ladder: size estimate failed (%s)", e)
        return None


# ── Rung 3: legacy dict ───────────────────────────────────────────


def _legacy_aux_entry() -> Optional[Dict[str, Any]]:
    """A pre-migration ``llm_config.small_model`` entry, or None.

    Read from the raw file, uncached and fail-soft, BEFORE the ladder's first
    store read: migrating the file folds an enabled small_model into the chat
    slot (or drops it) and rewrites, so a rung that read after that first load
    would find only files that migration declined to touch. Both shapes the
    old config used are accepted — a dict with ``model`` (and optionally
    ``endpoint_id``/``enabled``), or a bare model-name string.
    """
    path = find_models_config(include_repo=False)
    if path is None:
        return None
    try:
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        logger.debug("utility ladder: legacy read of %s failed (%s)", path, e)
        return None
    if not isinstance(raw, dict):
        return None
    llm = raw.get("llm_config")
    if not isinstance(llm, dict):
        return None
    entry = llm.get("small_model")
    if isinstance(entry, str):
        model = entry.strip()
        return {"model": model, "endpoint_id": ""} if model else None
    if not isinstance(entry, dict):
        return None
    model = str(entry.get("model") or "").strip()
    if not model or entry.get("enabled") is False:
        return None
    return {"model": model, "endpoint_id": str(entry.get("endpoint_id") or "").strip()}


def _resolve_legacy(
    entry: Dict[str, Any], anchor: Optional[ResolvedModel]
) -> Optional[ResolvedModel]:
    """Endpoint for a legacy entry: its own id, else the anchor's, else the only one."""
    try:
        endpoints = llm_config.load().get("saved_endpoints") or []
    except Exception as e:
        logger.debug("utility ladder: legacy endpoint resolution failed (%s)", e)
        return None
    endpoint: Optional[Dict[str, Any]] = None
    wanted = entry.get("endpoint_id") or ""
    if wanted:
        endpoint = next((e for e in endpoints if e.get("id") == wanted), None)
    if endpoint is None and anchor is not None:
        endpoint = next(
            (e for e in endpoints if e.get("url") == anchor.url and e.get("provider") == anchor.provider),
            None,
        )
    if endpoint is None and len(endpoints) == 1:
        endpoint = endpoints[0]
    if endpoint is None:
        return None
    return ResolvedModel(
        model=entry["model"],
        url=endpoint.get("url", ""),
        provider=endpoint.get("provider", "ollama"),
        api_key=endpoint.get("api_key") or "",
    )