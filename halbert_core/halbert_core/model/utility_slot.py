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
import re
from enum import Enum
from time import monotonic as _monotonic
from typing import Any, Dict, List, Optional, Tuple

import yaml

from . import llm_config
from .capabilities import _VISION_TOKEN_RE
from .llm_config import ResolvedModel, is_cloud_tagged, is_local_model
from .config_locator import find_models_config
from ..utils.reasoning import is_reasoning_model

logger = logging.getLogger("halbert.model.utility_slot")

__all__ = ["AuxSource", "resolve_aux_model"]


class AuxSource(str, Enum):
    """Which ladder rung produced the answer."""

    NONE = "none"          # unset and nothing to fall back to
    DECLARED = "declared"  # the utility_model slot itself
    CATALOG = "catalog"    # live-catalog family match (prefer_fast only)
    LEGACY = "legacy"      # pre-migration small_model entry
    CHAT = "chat"          # the chat slot — the name-neutral curated floor
    SECURE = "secure"      # require_local floor: secure_model, not chat_model


# Probes are attempted only for providers whose catalogs are cheap GETs of a
# stable shape. Others (anthropic, peer) are a deliberate miss — fail-soft —
# until a caller profile justifies their probe shape.
_OLLAMA_PROVIDERS = frozenset({"ollama"})
_GENERIC_MODELS_PATH_PROVIDERS = frozenset(
    {"openai", "openai-compatible", "lm-studio", "apple-foundation", "llamacpp", "mlx"}
)

_CATALOG_TIMEOUT = 2.0
_MIN_FAMILY_TOKEN = 3

# G2: prefer_fast can fire on every side-task dispatch, sometimes many times
# a minute. A short cache keyed by (url, provider) avoids re-dialing the
# same endpoint on every call; a shorter TTL on a failed probe (a dead
# endpoint, a timeout) keeps a revived endpoint from being shut out for
# long, while still sparing it a fresh probe on every miss.
_CATALOG_CACHE_TTL_S = 60.0
_CATALOG_NEGATIVE_TTL_S = 15.0
_catalog_cache: Dict[Tuple[str, str], Tuple[float, List[Dict[str, Any]]]] = {}


def reset_catalog_cache() -> None:
    """Drop every cached catalog probe result (tests; a config/endpoint change)."""
    _catalog_cache.clear()


def _cached_fetch_catalog(url: str, provider: str, api_key: str = "") -> List[Dict[str, Any]]:
    """``_fetch_catalog``, memoized per (url, provider) with a negative cache.

    An exception from the underlying probe is cached too (so a dead endpoint
    isn't re-dialed on every call) and then re-raised, unchanged, so callers
    keep seeing the same fail-soft contract as an uncached probe.
    """
    key = (url, provider)
    now = _monotonic()
    cached = _catalog_cache.get(key)
    if cached is not None and now < cached[0]:
        return cached[1]
    try:
        entries = _fetch_catalog(url, provider, api_key)
    except Exception:
        _catalog_cache[key] = (now + _CATALOG_NEGATIVE_TTL_S, [])
        raise
    ttl = _CATALOG_CACHE_TTL_S if entries else _CATALOG_NEGATIVE_TTL_S
    _catalog_cache[key] = (now + ttl, entries)
    return entries


# ── Ladder ────────────────────────────────────────────────────────


def resolve_aux_model(
    session_id: Optional[str] = None,
    task: str = "utility",
    prefer_fast: bool = False,
    require_local: bool = False,
) -> Optional[ResolvedModel]:
    """A model for an internal side task, or None when nothing can serve one.

    ``task`` is provenance only (it names the log line, never the model).
    ``prefer_fast`` is the per-task opt-in to the catalog rung — the only
    rung that may return something cheaper than what the operator runs;
    without it the ladder costs no round-trip. ``require_local`` is the
    secure-turn gate: every rung's candidate must pass
    :func:`llm_config.is_local_model`, and the floor becomes ``secure_model``
    (already guaranteed local, SEC-21) instead of ``chat_model``, which
    carries no such guarantee.
    """
    resolved, source = _resolve_aux(
        session_id=session_id, task=task, prefer_fast=prefer_fast,
        require_local=require_local,
    )
    logger.debug("utility ladder: task=%s rung=%s", task, source.value)
    return resolved


def _is_local(resolved: ResolvedModel) -> bool:
    return is_local_model(resolved.model, resolved.url, resolved.provider)


def _resolve_aux(
    session_id: Optional[str] = None,
    task: str = "utility",
    prefer_fast: bool = False,
    require_local: bool = False,
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
    if declared is not None and (not require_local or _is_local(declared)):
        return declared, AuxSource.DECLARED

    anchor: Optional[ResolvedModel] = None
    if prefer_fast:
        anchor = _anchor(session_id)
        if anchor is not None:
            picked = _catalog_pick(anchor, require_local=require_local)
            if picked is not None:
                return picked, AuxSource.CATALOG

    if legacy:
        resolved = _resolve_legacy(legacy, anchor or _anchor(session_id))
        if resolved is not None and (not require_local or _is_local(resolved)):
            return resolved, AuxSource.LEGACY

    if require_local:
        # chat_model carries no locality guarantee; secure_model already
        # does (SEC-21 enforces it at normalise), so it is the floor here
        # instead — never fall back further to an unproven chat slot.
        try:
            secure = llm_config.resolve("secure_model", session_id)
        except Exception as e:
            logger.debug("utility ladder: secure floor failed (%s)", e)
            secure = None
        if secure is not None:
            return secure, AuxSource.SECURE
        return None, AuxSource.NONE

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


def _catalog_pick(anchor: ResolvedModel, require_local: bool = False) -> Optional[ResolvedModel]:
    """The smallest strictly-cheaper same-family model the provider lists.

    One probe, short timeout, best effort. Anything odd — no listing, no size
    signal, no family match, an endpoint that will not answer — is a miss and
    the ladder falls through; it is never an error. ``require_local`` drops a
    ``:cloud``-tagged (or otherwise non-local) entry from consideration
    entirely, so the next-smallest local sibling can still win — the same
    endpoint's catalog can list both.
    """
    try:
        entries = _cached_fetch_catalog(anchor.url, anchor.provider, anchor.api_key)
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
        if not name or _is_excluded_sibling(name):
            continue
        candidate_token = _family_token(name)
        if not _same_family(candidate_token, token):
            continue
        if require_local and not is_local_model(name, anchor.url, anchor.provider):
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


#: A size tag anywhere in a model id — ':7b', '-70b', '_14b', ':8b-instruct'.
#: The same shape capabilities.py's own detector uses, so the family-token
#: split and the fallback size parse below are not Ollama's colon-only
#: convention: OpenAI-wire/LM-Studio catalogs are hyphen-styled instead
#: ('family-a-3b-instruct').
_SIZE_TAG_RE = re.compile(r"[:\-_](\d+(?:\.\d+)?)b\b", re.IGNORECASE)


def _is_excluded_sibling(name: str) -> bool:
    """Generic, name-neutral disqualifiers: a catalog entry that is not a
    plain chat-capable sibling at all is never a utility-model candidate,
    regardless of family or size — a reasoning/vision/embedding/audio
    variant or a ':cloud' tag is a different task or a different locality,
    not a cheaper copy of the same one."""
    lower = name.lower()
    if any(tag in lower for tag in ("embed", "tts", "transcribe", "audio")):
        return True
    if is_cloud_tagged(name):
        return True
    if is_reasoning_model(lower):
        return True
    if _VISION_TOKEN_RE.search(lower):
        return True
    return False


def _family_token(model_name: str) -> Optional[str]:
    """The family part of a model name — generic parsing, no names of its own.

    Strips an optional org/namespace prefix (``org/family-a-3b`` →
    ``family-a-3b``) and an optional size tag, from either convention:
    ``family-a:3b-instruct`` and ``family-a-3b-instruct`` both → ``family-a``.
    A colon-less, size-less id is its own family token. None when nothing
    parseable remains.
    """
    name = (model_name or "").strip().lower()
    if not name:
        return None
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    match = _SIZE_TAG_RE.search(name)
    token = name[:match.start()] if match else name.split(":", 1)[0]
    token = token.strip("-_: ")
    return token or None


def _same_family(candidate: Optional[str], reference: str) -> bool:
    """True when two family tokens name the same base family.

    Equal, or one a dash-delimited prefix of the other's segments
    (``family-a`` ↔ ``family-a-coder``) — not a raw character prefix, which
    would fuse any two names sharing a long-enough common substring
    (``abc`` ↔ ``abcd``, ``abcx-coder``). A length floor on the shorter
    token guards against a stray one- or two-character segment matching
    everything.
    """
    if not candidate or len(candidate) < _MIN_FAMILY_TOKEN or len(reference) < _MIN_FAMILY_TOKEN:
        return False
    if candidate == reference:
        return True
    c_parts = candidate.split("-")
    r_parts = reference.split("-")
    shorter, longer = (c_parts, r_parts) if len(c_parts) <= len(r_parts) else (r_parts, c_parts)
    return longer[:len(shorter)] == shorter


def _params_b(entry: Dict[str, Any]) -> Optional[float]:
    """A parameter-count estimate for a catalog entry, or None.

    hardware_detector's estimator — the same generic parsing the first-run
    picker uses — prefers runtime metadata, then a size tag in the name, then
    the weight file size. Imported lazily: hardware_detector pulls psutil,
    which nothing on this import path otherwise needs. Its own name-tag
    parser is colon-only (Ollama's tag shape); when it comes up empty, a
    local fallback tries the same size tag both conventions can carry, so
    an OpenAI-wire/LM-Studio catalog with no runtime metadata still ranks.
    """
    try:
        from .hardware_detector import estimate_model_params_b
        estimate = estimate_model_params_b(entry)
    except Exception as e:
        logger.debug("utility ladder: size estimate failed (%s)", e)
        estimate = None
    if estimate is not None:
        return estimate
    name = str(entry.get("name") or entry.get("model") or "")
    match = _SIZE_TAG_RE.search(name)
    return float(match.group(1)) if match else None


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