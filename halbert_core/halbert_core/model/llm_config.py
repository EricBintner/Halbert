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
      secure_model:     {enabled, endpoint_id, model}  # local-only enforced

Callers that change a slot send the whole slot dict (all three keys).
``CHAT_CAPABLE_PROVIDERS`` is imported lazily from :mod:`model.client` so the
two modules do not create a top-level import cycle.

**Layers.** Readers see the effective config —
``defaults < global file < workspace file < session`` — merged one slot at a
time by :mod:`model.config_layers`. Writers see the global file alone:
:func:`load` is what a model runtime should resolve against, :func:`load_global`
is what an editor must start from, because saving a merged view would copy a
workspace's or a session's pins into the user's own file. :func:`load_layered`
serves both in one read, with the name of the layer each slot came from, for a
picker that has to edit one layer while showing what another put in force.

**Against E-2's per-request overrides.** ``StateContext``'s ``model_override`` /
``tier_override`` pin *one turn* and are never persisted; the session layer is a
*server-side default for a session*. The route applies its override after
resolving against this store, so the full order is::

    request override  >  session layer  >  workspace file  >  global file

Pin a session to one model and a single turn can still be sent elsewhere; pin a
turn to a *tier* and it uses that session's model for the tier.
"""
from __future__ import annotations

import copy
import logging
import os
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from urllib.parse import urlparse
import ipaddress

import yaml

from . import config_layers
from .config_locator import find_models_config, write_models_config

logger = logging.getLogger("halbert.model.llm_config")

SLOTS = ("chat_model", "specialist_model", "vision_model", "secure_model")
LEGACY_KEYS = ("orchestrator", "specialist", "vision", "saved_endpoints")
DROPPED_KEYS = (
    "embedding", "small_model", "large_model", "code_model", "coordinator_model",
    "assignment_mode", "assignment_blocks", "advanced", "compute_nodes",
    "model_context_cache",
)
DEFAULT_OLLAMA_URL = "http://localhost:11434"

# Apple Intelligence (FoundationModels) — on-device LLM via the ANE.
# The Swift bridge (halbert-foundation-bridge) serves OpenAI-compatible
# wire format on loopback port 11435, distinct from Ollama (11434) and
# LM Studio (1234). The model name is a stable identifier for the
# built-in OS foundation model; the bridge maps it to
# SystemLanguageModel.default.
APPLE_FOUNDATION_URL = "http://127.0.0.1:11435"
APPLE_FOUNDATION_MODEL = "apple-foundation-3b"
APPLE_FOUNDATION_PROVIDER = "apple-foundation"


def _chat_capable_providers() -> FrozenSet[str]:
    """CHAT_CAPABLE_PROVIDERS from model.client (includes anthropic after E-1).

    Imported lazily to avoid a top-level import cycle: client.py imports this
    module at load time, so importing client.py here at load time would cycle.
    """
    from .client import CHAT_CAPABLE_PROVIDERS
    return CHAT_CAPABLE_PROVIDERS


class ConfigUnreadableError(RuntimeError):
    """models.yml exists but could not be parsed.

    Readers fall back to defaults for the session; writers raise this instead,
    because an unparsable file is indistinguishable from an empty one and
    writing over it destroys every sibling key — compression, routing, handoff,
    and any saved API keys — with no way back.
    """

    def __init__(self, path: Any, cause: Exception):
        self.path = path
        self.cause = cause
        super().__init__(
            f"{path} could not be parsed ({cause}). Fix or remove the file; "
            f"refusing to overwrite it."
        )


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


def _is_local_url(url: str) -> bool:
    """True when ``url`` points at a loopback or unspecified address.

    Uses standard URL parsing so it handles ``http://[::1]:11434`` and rejects
    ``http://attacker.com/localhost``.  Used by :func:`normalise` to enforce
    that ``secure_model`` never points at a remote endpoint.
    """
    try:
        hostname = urlparse(url).hostname or ""
        if hostname in ("localhost", "0.0.0.0"):
            return True
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return False


def default_llm_config() -> Dict[str, Any]:
    return {
        "saved_endpoints": [],
        "chat_model": _empty_slot(),
        "specialist_model": _empty_slot(),
        "vision_model": _empty_slot(),
        "secure_model": _empty_slot(),
    }


def _new_id() -> str:
    return f"ep_{secrets.token_hex(4)}"


# ── File I/O ──────────────────────────────────────────────────────


def _read_path() -> Optional[Path]:
    return find_models_config(include_repo=False)


def global_config_path() -> Optional[Path]:
    """The file the global layer is read from, or None on a fresh install.

    Lets a reader that was handed a path ask whether it is the store's own file
    — and so whether it should be reading the layers instead of parsing it.
    """
    return _read_path()


def _write_path() -> Path:
    return write_models_config()


def _chmod_600(path: Path) -> None:
    """Tighten permissions on a file that may hold API keys."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ── Parse cache ───────────────────────────────────────────────────
#
# Every model getter resolves against this store per call, on purpose: one
# LLMClientAdapter is shared by every concurrent request, so caching a model
# *decision* anywhere would leak one session's pin into another's turn. The
# cost of that correctness was 12 full parses of models.yml for a single turn
# (a pinned turn costs the same again through ``tools_supported_for``) —
# ~1.3ms each, synchronous, on the event loop, inside the turn lock.
#
# What is cached here is the PARSE, never a decision. Every getter still
# resolves per call and still sees current file contents; it just does not
# re-read and re-parse the same unchanged bytes a dozen times a turn.
#
# Freshness is the file's own identity — path, mtime_ns, size, inode, device —
# so an edit made while Halbert is running is picked up by the next read, which
# is existing, relied-on behaviour. ``_CACHE_TTL_SECONDS`` is a backstop, not the
# mechanism: it bounds staleness on filesystems whose timestamps are coarser
# than a turn (HFS+ and some network mounts round to the second, where a small
# same-second edit that happens to preserve the size would otherwise be missed).
# Locally, mtime_ns was measured to change on every rewrite.
#
# A parse FAILURE is never cached, and it drops any cached success with it.
# "Never overwrite an unreadable models.yml" is the reason _read_raw
# distinguishes {} from None, and a cached failure could outlive the repair —
# including one caused by reading the file mid-write, which is exactly when a
# human is editing it. The mirror image matters just as much: a cached SUCCESS
# must not outlive the file's health, so the moment a read finds the file
# unparsable the earlier parse is dropped rather than served on for a TTL.
#
# NO WRITER READS THROUGH THIS CACHE. The cache is a read-path optimisation
# and only ever that: every writer goes through _read_for_write, which passes
# use_cache=False. "Refuse the write when the file on disk cannot be parsed" is
# a statement about the bytes on disk at the moment of writing, and a cached
# success — however fresh — is not evidence about them. update() in particular
# calls load_global() and then save() microseconds apart, so a write validated
# against the cache would be validated against a snapshot the filesystem's
# timestamp resolution cannot even distinguish from the current file: not a
# narrow race but, on any coarse-timestamp filesystem (NFS/SMB home dirs,
# HFS+, exFAT), the guarantee gone every single time.
_CACHE_TTL_SECONDS = 1.0
_cache: Optional[Tuple[Tuple[Any, ...], float, Dict[str, Any]]] = None


def invalidate_cache() -> None:
    """Drop the cached parse. Called after every write through this module."""
    global _cache
    _cache = None


def _cache_stamp(path: Path) -> Tuple[Any, ...]:
    """The file's identity: any change to it changes this."""
    try:
        st = os.stat(path)
    except OSError:
        return ("missing", str(path))
    return (str(path), st.st_mtime_ns, st.st_size, st.st_ino, st.st_dev)


def _read_raw(use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """The parsed file, ``{}`` when there is none, or ``None`` when it is broken.

    The three cases must stay distinguishable: ``{}`` is a fresh install and is
    safe to write over, ``None`` is a file whose contents we could not
    understand and must not touch.

    ``use_cache=False`` opens and parses the file however fresh the cached
    parse looks. Every writer takes that path — see the note above the cache:
    a write is allowed to rest only on the bytes that are on disk now.

    The result is a deep copy: ``save()`` and the migration path mutate what
    they are handed, and handing out the cached object itself would let one
    writer's in-place edit become every later reader's truth without ever
    reaching disk.
    """
    global _cache
    path = _read_path()
    if path is None:
        return {}

    stamp = _cache_stamp(path)
    now = time.monotonic()
    cached = _cache
    if (
        use_cache
        and cached is not None
        and cached[0] == stamp
        and now - cached[1] < _CACHE_TTL_SECONDS
    ):
        return copy.deepcopy(cached[2])

    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Could not read %s: %s", path, e)
        # This is the file the cache describes, and it has just been found
        # unparsable: a parse taken before the breakage must not go on being
        # served (or, worse, written back) for the rest of the TTL.
        _cache = None
        return None
    if not isinstance(data, dict):
        data = {}
    # Stamp the file as it was BEFORE the read: a write that lands during the
    # read then leaves a stamp that no longer matches, and the next reader
    # parses again rather than trusting a half-written parse.
    _cache = (stamp, now, data)
    return copy.deepcopy(data)


def _read_for_write() -> Dict[str, Any]:
    """Like :func:`_read_raw`, but reads the file itself and refuses to proceed
    on an unparsable one.

    Uncached on purpose, and this is the single site that gives every writer in
    the module (``save``, ``set_top_level``, the migration rewrite) that
    property: a write must be refused against the file as it is now, not
    against a snapshot taken microseconds earlier by the ``load_global()`` that
    built the payload being written.
    """
    raw = _read_raw(use_cache=False)
    if raw is None:
        path = _read_path()
        try:
            with open(path, "r") as f:
                yaml.safe_load(f)
            cause: Exception = ValueError("unknown parse failure")
        except Exception as e:
            cause = e
        raise ConfigUnreadableError(path, cause)
    return raw


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
        # The file this module reads from may be the file it just wrote; drop
        # the parse so the next reader sees the new contents even on a
        # filesystem whose timestamps are too coarse to notice.
        invalidate_cache()
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
        if enabled and slot == "secure_model":
            ep_url = by_id[endpoint_id]["url"]
            if not _is_local_url(ep_url):
                logger.warning(
                    "secure_model endpoint %r is not local; slot disabled", ep_url,
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


def _endpoints_missing_id(raw: Dict[str, Any]) -> bool:
    """True when a saved endpoint has no id of its own."""
    llm = raw.get("llm_config")
    if not isinstance(llm, dict):
        return False
    for ep in llm.get("saved_endpoints") or []:
        if isinstance(ep, dict) and ep.get("url") and not str(ep.get("id") or "").strip():
            return True
    return False


def needs_rewrite(raw: Dict[str, Any]) -> bool:
    """True when reading the file produced something that must be written back.

    Migration is the obvious case. The other is an endpoint with no id:
    ``_clean_endpoint`` mints one on every read, so leaving it unpersisted
    hands out a different id each time and every slot pointing at it is
    disabled on the next load.
    """
    return needs_migration(raw) or _endpoints_missing_id(raw)


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
        # Resolve the URL once, before matching. Passing the raw (often absent)
        # value to _match_endpoint and only defaulting it afterwards meant a
        # legacy slot with no explicit endpoint could never match the local
        # endpoint the user already had, and minted a duplicate beside it.
        url = str(legacy.get("endpoint") or DEFAULT_OLLAMA_URL).strip().rstrip("/")
        ep = _match_endpoint(endpoints, legacy.get("endpoint_id"), url, provider)
        if ep is None:
            ep = {
                "id": _new_id(),
                "name": "Migrated endpoint",
                "provider": provider,
                "url": url,
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


def load_global_file(use_cache: bool = True) -> Dict[str, Any]:
    """The whole models.yml dict, post-migration — the global layer alone.

    Rewrites the file once when migration or id-minting changed something. An
    unparsable file serves defaults for the session and is left untouched.

    ``use_cache=False`` for a read that is about to become a WRITE's payload.
    ``save()`` validates against the file itself, but validating fresh bytes
    and then persisting a stale snapshot loses the same edit just as
    completely — the guard has to cover the payload, not only the check.
    """
    raw = _read_raw(use_cache)
    if raw is None:
        return normalise_file({})
    if needs_rewrite(raw):
        # The migration branch WRITES, so it may not rest on a cached parse
        # either: re-read the file itself and rebuild from that, so a rewrite
        # cannot put a stale snapshot back over someone's edit or over a file
        # that has become unparsable since the cached read.
        try:
            raw = _read_for_write()
        except ConfigUnreadableError as e:
            logger.error("Not migrating models.yml: %s", e)
            return normalise_file({})
        out = normalise_file(raw)
        if needs_rewrite(raw):
            try:
                _backup_before_rewrite()
                _write_raw(out)
                llm = out["llm_config"]
                logger.info(
                    "Migrated legacy model config: chat=%r specialist=%r vision=%r secure=%r endpoints=%d",
                    llm["chat_model"]["model"], llm["specialist_model"]["model"],
                    llm["vision_model"]["model"], llm["secure_model"]["model"],
                    len(llm["saved_endpoints"]),
                )
            except Exception as e:
                logger.error("Could not rewrite models.yml after migration: %s", e)
        return out
    return normalise_file(raw)


def load_global(use_cache: bool = True) -> Dict[str, Any]:
    """The llm_config section of the global file, normalised, unlayered.

    Every writer starts here: rebasing a write on the effective config would
    persist a workspace file's or a session's pins into the user's own file.
    Writers pass ``use_cache=False`` — see :func:`load_global_file`.
    """
    return load_global_file(use_cache)["llm_config"]


@dataclass(frozen=True)
class LayeredConfig:
    """One resolution of the layers: what is in force, and what put it there.

    ``global_config`` is what an editor must edit; ``effective`` is what a
    runtime resolves against. Handing an editor ``effective`` is what let a
    read-modify-write copy a workspace's endpoints and a session's pins into
    the user's own file.
    """

    effective: Dict[str, Any]
    global_config: Dict[str, Any]
    slot_layers: Dict[str, str]
    layers: List[str]


def _layered(global_file: Dict[str, Any], session_id: Optional[str]) -> LayeredConfig:
    """The global llm_config with the overlay and session layers merged over it."""
    base = global_file["llm_config"]
    layers = [config_layers.Layer(config_layers.GLOBAL_LAYER, base)]
    layers.extend(config_layers.file_overlay_layers(global_file))
    session = config_layers.session_layer(session_id)
    if session:
        layers.append(config_layers.Layer(config_layers.SESSION_LAYER, session))
    names = [layer.name for layer in layers]
    if len(layers) == 1:
        return LayeredConfig(base, base, {s: config_layers.GLOBAL_LAYER for s in SLOTS}, names)
    merged = config_layers.merge_layers_with_sources(layers, SLOTS)
    return LayeredConfig(
        effective=normalise(merged.llm),
        global_config=base,
        slot_layers={s: merged.slot_layers.get(s, config_layers.GLOBAL_LAYER) for s in SLOTS},
        layers=names,
    )


def load_layered(session_id: Optional[str] = None) -> LayeredConfig:
    """Both views of the config in one read, plus which layer supplied each slot."""
    return _layered(load_global_file(), session_id)


def load_file(session_id: Optional[str] = None) -> Dict[str, Any]:
    """The whole models.yml dict with every layer applied to ``llm_config``.

    ``session_id`` defaults to the session bound by
    :func:`config_layers.bind_session`.
    """
    out = load_global_file()
    out["llm_config"] = _layered(out, session_id).effective
    return out


def load(session_id: Optional[str] = None) -> Dict[str, Any]:
    """The effective llm_config section, normalised."""
    return load_file(session_id)["llm_config"]


def save(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace llm_config in the file; legacy keys are dropped, every other key is kept.

    Raises :class:`ConfigUnreadableError` rather than overwriting a file that
    could not be parsed.
    """
    raw = _read_for_write()
    if needs_migration(raw):
        _backup_before_rewrite()
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


def _carry_forward_api_keys(
    incoming: Any, current: Dict[str, Any]
) -> None:
    """Re-attach a stored api_key to any incoming endpoint that omitted it.

    ``saved_endpoints`` is a list, so a deep merge replaces it wholesale — an
    endpoint sent without its key would have the stored one erased. A client
    should not have to echo a secret back just to rename an endpoint, and a
    client that never displays the key (a provider with no key field) cannot.
    An explicit ``api_key: ""`` still clears it; only an absent key is carried.
    """
    if not isinstance(incoming, list):
        return
    stored = {
        e["id"]: e.get("api_key", "")
        for e in current.get("saved_endpoints") or []
        if isinstance(e, dict) and e.get("id")
    }
    for ep in incoming:
        if not isinstance(ep, dict) or "api_key" in ep:
            continue
        carried = stored.get(str(ep.get("id") or ""))
        if carried:
            ep["api_key"] = carried


def update(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge ``partial`` into the current config and save.

    Raises :class:`SlotProviderError` when a slot with a model names an endpoint
    whose provider is not chat-capable — the UI must never save such a slot.
    """
    # Uncached: this read becomes the saved payload.
    current = load_global(use_cache=False)
    partial = copy.deepcopy(partial)
    if "saved_endpoints" in partial:
        _carry_forward_api_keys(partial["saved_endpoints"], current)
    merged = _deep_merge(current, partial)
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
    """Write a non-llm_config key (e.g. ``compression``) without disturbing llm_config.

    Takes the same backup as :func:`load_file` when this write is also the one
    that migrates the file, and refuses an unparsable file for the same reason
    :func:`save` does.
    """
    raw = _read_for_write()
    if needs_migration(raw):
        _backup_before_rewrite()
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


def resolve(slot: str, session_id: Optional[str] = None) -> Optional[ResolvedModel]:
    """(model, url, provider, api_key) for an enabled slot, else None.

    An unconfigured ``chat_model`` is filled from the ``HALBERT_MODEL`` env
    var when one is set (see :func:`_env_chat_model_override`) — the
    per-instance deployment dial for a sysadmin box whose operator pinned a
    model without writing models.yml. Every other slot, and any slot the file
    configures, is unaffected.
    """
    resolved = resolve_from(load_file(session_id), slot)
    if resolved is not None or slot != "chat_model":
        return resolved
    return _env_chat_model_override()


def _env_chat_model_override() -> Optional[ResolvedModel]:
    """``HALBERT_MODEL`` as the chat model when models.yml configures none.

    The override only fills an EMPTY chat slot: a models.yml assignment wins,
    so a UI configuration is never silently replaced by a stale environment
    variable. It is also deliberately absent on the home variants — their
    chat/specialist slots resolve to the compute peer (U6/S3) and there is no
    local model for the variable to name. Variant resolution reuses
    ``cognition_wiring._get_variant()`` (being.yml > env > sysadmin) so the
    backend gating and this override agree on which instance they are on;
    the import is lazy because integrations has no place in model's import
    time, and any failure there simply disables the override rather than
    breaking model resolution.
    """
    model = os.environ.get("HALBERT_MODEL", "").strip()
    if not model:
        return None
    try:
        from ..integrations.cognition_wiring import _get_variant

        if _get_variant() in ("home", "home-light"):
            return None
    except Exception:
        return None
    return ResolvedModel(
        model=model,
        url=DEFAULT_OLLAMA_URL,
        provider="ollama",
        api_key=api_key_for(DEFAULT_OLLAMA_URL),
    )


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


def ensure_endpoint(url: str, provider: str = "ollama", name: str = "", api_key: str = "") -> str:
    """Id of the saved endpoint at (``provider``, ``url``); creates it if absent.

    A caller that needs an endpoint id must get it from here rather than
    inventing one: a slot whose ``endpoint_id`` names no saved endpoint is
    disabled by :func:`normalise` on the next read.

    ``api_key`` sets the credential when creating the endpoint, and
    refreshes a stored one that differs (a re-paired peer token). An
    empty ``api_key`` never clears a stored key — a caller that merely
    wants the id must not be able to erase a secret by omission.
    """
    cfg = load_global(use_cache=False)  # becomes a write payload
    u = (url or "").rstrip("/")
    for ep in cfg["saved_endpoints"]:
        if ep["provider"] == provider and ep["url"] == u:
            if api_key and ep.get("api_key", "") != api_key:
                ep["api_key"] = api_key
                save(cfg)
            return ep["id"]
    ep = {"id": _new_id(), "name": name or u, "provider": provider, "url": u, "api_key": api_key}
    cfg["saved_endpoints"].append(ep)
    save(cfg)
    return ep["id"]


def ensure_ollama_endpoint(url: str = DEFAULT_OLLAMA_URL) -> str:
    """Id of the Ollama endpoint at ``url``; creates "Local Ollama" if absent."""
    return ensure_endpoint(url, "ollama", "Local Ollama")


def ensure_apple_foundation_endpoint() -> str:
    """Id of the Apple Intelligence endpoint; creates it if absent.

    The endpoint points at the Swift FoundationModels bridge on loopback
    port 11435. It is registered even when the bridge is not running: the
    host is *eligible* for Apple Intelligence and the endpoint is inert
    until the bridge is bundled and started.
    """
    return ensure_endpoint(
        APPLE_FOUNDATION_URL,
        APPLE_FOUNDATION_PROVIDER,
        "Apple Intelligence (On-Device)",
    )


def _probe_ollama(url: str, timeout: float) -> bool:
    try:
        import requests
        return requests.get(f"{url}/api/tags", timeout=timeout).status_code == 200
    except Exception:
        return False


# Choosing a model for the user is off unless they ask for it. Halbert's
# picker exists to give an operator control over which model answers, and a
# machine that quietly picks one on their behalf — by a VRAM heuristic that
# cannot say anything useful about a hosted model — is the opposite of that.
# Set `first_run: {auto_select_model: true}` in models.yml to opt in.
AUTO_SELECT_KEY = "first_run"


def auto_select_enabled() -> bool:
    """True when the operator has opted into first-run model selection."""
    try:
        block = load_file().get(AUTO_SELECT_KEY) or {}
    except ConfigUnreadableError:
        return False
    return bool(isinstance(block, dict) and block.get("auto_select_model"))


def ensure_local_ollama_endpoint(timeout: float = 2.0) -> bool:
    """Fresh install helper: with no endpoints saved, add Local Ollama if :11434 answers."""
    if load_global(use_cache=False)["saved_endpoints"]:
        return False
    if not _probe_ollama(DEFAULT_OLLAMA_URL, timeout):
        return False
    ensure_ollama_endpoint(DEFAULT_OLLAMA_URL)
    return True
