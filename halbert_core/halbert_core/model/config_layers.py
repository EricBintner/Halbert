# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Layering for llm_config: which layers exist, and how they combine.

    built-in defaults  <  global file  <  workspace file  <  session

:mod:`model.llm_config` stays the only reader and writer of the file; this
module supplies the overlay layers and the merge, and owns the in-memory
session layer. Nothing here writes to disk.

**There is no discovered project layer.** Halbert identifies as the host rather
than being pointed at a checkout, so walking up from a working directory would
scope a user's configuration to *Halbert's own* source tree. The workspace
layer therefore exists only when an operator declares it —
``$HALBERT_WORKSPACE_MODELS_CONFIG`` or the ``workspace_models_config`` key in
the global file — and is otherwise absent.

**How this relates to E-2's per-request overrides.** ``StateContext``'s
``model_override`` / ``tier_override`` describe *one turn* and are never
persisted; the session layer here is a *server-side default for a session*.
They compose rather than compete, in this order:

    request override  >  session layer  >  workspace file  >  global file

A request override is applied by the route after the store has already resolved
the session's effective config, so pinning a model for one turn still wins over
a session pin, and a tier pin for one turn selects *that session's* model for
the tier. Neither layer needs to know about the other.

Slot merging is per slot, never per file: a layer that pins only the specialist
must leave the global chat model alone. Endpoints are scoped the same way — a
layer's redefinition of an endpoint id reaches only the slots that layer
supplies, so an overlay naming one slot cannot redirect the other two through
an id they happen to share.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import (Any, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional,
                    Sequence, Tuple)

import yaml

from .config_locator import GLOBAL_LAYER, resolve_layers

logger = logging.getLogger("halbert.model.config_layers")

WORKSPACE_SETTING_KEY = "workspace_models_config"
SESSION_LAYER = "session"

# A long-lived server pinning a model per session would otherwise grow a dict
# entry for every session it ever saw.
MAX_TRACKED_SESSIONS = 256


class Layer(NamedTuple):
    """One layer's llm_config-shaped dict, however it was sourced."""

    name: str
    llm: Mapping[str, Any]


# ── Overlay files ─────────────────────────────────────────────────


def _read_overlay(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        # An overlay only ever adds pins, so dropping it degrades to the global
        # config rather than to nothing; refusing to read at all would take the
        # whole model configuration down with one bad operator file.
        logger.error("Could not read config layer %s: %s; ignoring it", path, e)
        return None
    return data if isinstance(data, dict) else None


def _warn_about_unreadable_shapes(path: Path, raw: Mapping[str, Any]) -> None:
    """Say so when an overlay is written in a shape the merge cannot read.

    Migration is the global file's privilege — it rewrites what it read, and
    Halbert must never write to a file an operator pointed it at. So a legacy
    or SourcePrep-shaped overlay is simply skipped, and skipping it in silence
    is what makes an operator believe a pin took effect when it never did.
    """
    from .llm_config import DROPPED_KEYS, LEGACY_KEYS

    top = [k for k in LEGACY_KEYS if k != "saved_endpoints" and k in raw]
    if top:
        logger.warning(
            "config layer %s uses the pre-migration top-level keys %s; only the "
            "llm_config section of a layer is read, so these are ignored",
            path, ", ".join(top),
        )
    llm = raw.get("llm_config")
    dropped = [k for k in DROPPED_KEYS if isinstance(llm, dict) and k in llm]
    if dropped:
        logger.warning(
            "config layer %s declares %s inside llm_config; the layer schema is "
            "chat_model / specialist_model / vision_model / secure_model, so these are ignored",
            path, ", ".join(dropped),
        )


def file_overlay_layers(global_file: Mapping[str, Any]) -> List[Layer]:
    """Every file layer above the global one, lowest precedence first.

    Read as-is: legacy top-level keys are not migrated here, because migration
    rewrites the file it read and Halbert must never write to a file an
    operator pointed it at.
    """
    declared = global_file.get(WORKSPACE_SETTING_KEY)
    layers: List[Layer] = []
    for file_layer in resolve_layers(
        declared_workspace=declared if isinstance(declared, str) else None,
        include_repo=False,
    ):
        if file_layer.name == GLOBAL_LAYER:
            continue
        raw = _read_overlay(file_layer.path)
        if raw is None:
            continue
        _warn_about_unreadable_shapes(file_layer.path, raw)
        llm = raw.get("llm_config")
        if isinstance(llm, dict):
            layers.append(Layer(file_layer.name, llm))
        else:
            logger.warning(
                "config layer %s has no llm_config section; ignoring it", file_layer.path
            )
    return layers


# ── Session layer ─────────────────────────────────────────────────

_sessions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_sessions_lock = threading.Lock()

# Bound by whoever is serving a turn, so resolution deep inside the model stack
# picks up the session pin without every call site growing a session_id
# parameter it would have to thread through.
_active_session: ContextVar[Optional[str]] = ContextVar(
    "halbert_active_session", default=None
)


def active_session() -> Optional[str]:
    """The session bound to this context, if any."""
    return _active_session.get()


@contextmanager
def bind_session(session_id: Optional[str]) -> Iterator[None]:
    """Make ``session_id`` the ambient session for the duration of the block."""
    token = _active_session.set(session_id or None)
    try:
        yield
    finally:
        _active_session.reset(token)


def set_session_slot(
    session_id: str,
    slot: str,
    model: str,
    endpoint_id: str = "",
    enabled: bool = True,
) -> Dict[str, Any]:
    """Pin one slot for one session. In memory only — never touches a file.

    An empty ``endpoint_id`` inherits the endpoint of the slot being overridden,
    so pinning a different model on the runtime already configured does not
    need the caller to look the endpoint up.
    """
    if not session_id:
        raise ValueError("session_id is required to pin a session slot")
    # The merge only walks the known slots, so a typo would be accepted here and
    # then quietly never applied. Imported lazily: llm_config imports this module.
    from .llm_config import SLOTS
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot!r}; expected one of {', '.join(SLOTS)}")
    model = str(model or "").strip()
    if not model:
        # A layer contributes a slot only by naming a model, so an empty pin was
        # accepted, stored, and then never applied to anything.
        raise ValueError(
            f"a session pin needs a model; call clear_session_slot to unpin {slot!r}"
        )
    pin = {"enabled": bool(enabled), "endpoint_id": endpoint_id or "", "model": model}
    with _sessions_lock:
        layer = _sessions.pop(session_id, {})
        layer[slot] = pin
        _sessions[session_id] = layer
        while len(_sessions) > MAX_TRACKED_SESSIONS:
            evicted, _ = _sessions.popitem(last=False)
            logger.info("Evicted model pins for session %s (tracking limit)", evicted)
        return {name: dict(p) for name, p in layer.items()}


def clear_session_slot(session_id: str, slot: str) -> None:
    """Drop one slot's pin, falling that slot back to the file layers."""
    with _sessions_lock:
        layer = _sessions.get(session_id)
        if layer is None:
            return
        layer.pop(slot, None)
        if not layer:
            _sessions.pop(session_id, None)


def clear_session(session_id: str) -> None:
    """Drop every pin for a session."""
    with _sessions_lock:
        _sessions.pop(session_id, None)


def reset_sessions() -> None:
    """Drop every session's pins."""
    with _sessions_lock:
        _sessions.clear()


def session_layer(session_id: Optional[str]) -> Dict[str, Any]:
    """A copy of the session's pins, or ``{}``. ``None`` means the bound session."""
    key = session_id if session_id is not None else active_session()
    if not key:
        return {}
    with _sessions_lock:
        layer = _sessions.get(key)
        return {slot: dict(pin) for slot, pin in layer.items()} if layer else {}


# ── Merge ─────────────────────────────────────────────────────────


class MergedConfig(NamedTuple):
    """The collapsed llm_config, plus the layer that supplied each slot."""

    llm: Dict[str, Any]
    slot_layers: Dict[str, str]


class _SlotWin(NamedTuple):
    slot: Dict[str, Any]
    layer: int          # index into ``ordered`` of the layer naming the model
    endpoint_layer: int  # index of the layer the endpoint_id came from


def _layer_endpoints(layer: Layer) -> "OrderedDict[str, Dict[str, Any]]":
    """One layer's usable endpoints, by id, in declaration order."""
    out: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for ep in layer.llm.get("saved_endpoints") or []:
        if not isinstance(ep, dict) or not ep.get("url"):
            continue
        ep_id = str(ep.get("id") or "").strip()
        if not ep_id:
            # Ids are minted on read and persisted by the writer, and no writer
            # touches an overlay — so an id-less overlay endpoint would get a
            # different id on every read and disable every slot pointing at it.
            logger.warning(
                "endpoint %r in the %s layer has no id and was skipped; give it "
                "a stable id", ep.get("name") or ep.get("url"), layer.name,
            )
            continue
        out.setdefault(ep_id, dict(ep))
    return out


def _carry_api_key(ep: Dict[str, Any], lower: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Re-attach the layer below's key when a redeclaration omitted it.

    The overlay an operator actually writes is a copy of models.yml with the
    secret stripped so it can be shared; replacing the record wholesale erased
    the real key for every slot still resolving through that id. An explicit
    ``api_key: ""`` still clears it — only an absent key is carried, the same
    rule the write path applies in ``llm_config._carry_forward_api_keys``.
    """
    if lower is None or "api_key" in ep:
        return ep
    carried = lower.get("api_key") or ""
    if not carried:
        return ep
    logger.debug("endpoint %s redeclared without an api_key; carrying the stored one", ep["id"])
    return dict(ep, api_key=carried)


def _endpoint_identity(ep: Mapping[str, Any]) -> tuple:
    """What makes two definitions of one id behave differently. Name is cosmetic."""
    return (
        str(ep.get("provider") or "ollama"),
        str(ep.get("url") or "").strip().rstrip("/"),
        str(ep.get("api_key") or ""),
    )


def _endpoint_layers(
    ordered: Sequence[Layer],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Dict[str, Any]]]]:
    """The merged endpoint list, and what each layer can see of it.

    ``views[i]`` is layer ``i`` over every layer below it, so a layer redefines
    an endpoint only for the slots it also supplies. One shared list instead let
    an overlay naming a single slot redirect — or, with a provider the chat
    runtime cannot call, blind — every other slot resolving through the same id.
    """
    per_layer = [_layer_endpoints(layer) for layer in ordered]
    views: List[Dict[str, Dict[str, Any]]] = [{} for _ in ordered]
    below: Dict[str, Dict[str, Any]] = {}
    for i in range(len(ordered) - 1, -1, -1):
        view = dict(below)
        for ep_id, ep in per_layer[i].items():
            view[ep_id] = _carry_api_key(ep, below.get(ep_id))
        views[i] = view
        below = view
    top = views[0] if views else {}
    merged: List[Dict[str, Any]] = []
    seen: set = set()
    for eps in per_layer:
        for ep_id in eps:
            if ep_id not in seen:
                seen.add(ep_id)
                merged.append(dict(top[ep_id]))
    return merged, views


def _merge_slot(
    slot: str, ordered: Sequence[Layer], views: Sequence[Mapping[str, Any]]
) -> Optional[_SlotWin]:
    """The winning definition of one slot, or None when no layer defines it."""
    defined = [(i, layer.llm[slot]) for i, layer in enumerate(ordered)
               if isinstance(layer.llm.get(slot), dict)]
    with_model = [(i, c) for i, c in defined if str(c.get("model") or "").strip()]
    if not with_model:
        return None
    chosen_at: Optional[int] = None
    for pos, (i, cand) in enumerate(with_model):
        ep_id = str(cand.get("endpoint_id") or "").strip()
        if not ep_id or ep_id in views[i]:
            chosen_at = pos
            break
        if pos + 1 < len(with_model):
            # An overlay that names an endpoint it never declared would
            # otherwise blind the slot rather than leave the layer below in
            # charge of it.
            logger.warning(
                "%s in the %s layer names unknown endpoint %r; falling back to "
                "the %s layer", slot, ordered[i].name, ep_id,
                ordered[with_model[pos + 1][0]].name,
            )
    if chosen_at is None:
        # Nothing resolvable anywhere: keep the lowest pin so normalise reports
        # it the way it reports a hand-edited global file.
        chosen_at = len(with_model) - 1
    index, chosen = with_model[chosen_at]
    endpoint_id = str(chosen.get("endpoint_id") or "").strip()
    endpoint_layer = index
    if not endpoint_id:
        for j, cand in defined:
            if j <= index:
                continue
            inherited = str(cand.get("endpoint_id") or "").strip()
            if inherited:
                endpoint_id, endpoint_layer = inherited, j
                break
    return _SlotWin(
        slot={
            "enabled": bool(chosen.get("enabled", True)),
            "endpoint_id": endpoint_id,
            "model": str(chosen["model"]).strip(),
        },
        layer=index,
        endpoint_layer=endpoint_layer,
    )


def _alias_id(
    ep_id: str, layer_name: str, taken: Mapping[str, Any], wanted: Mapping[str, Any]
) -> str:
    """A stable id for one layer's own definition of a redeclared endpoint.

    Derived from the id and the layer so it is the same on every read — slots
    are resolved by id, and an id that moved between reads would disable the
    slot pointing at it. Every slot needing the same definition gets the same
    alias, so the endpoint list cannot grow one entry per slot.
    """
    alias = f"{ep_id}@{layer_name}"
    n = 2
    while alias in taken and _endpoint_identity(taken[alias]) != _endpoint_identity(wanted):
        alias = f"{ep_id}@{layer_name}~{n}"
        n += 1
    return alias


def merge_layers_with_sources(
    layers: Iterable[Layer], slots: Sequence[str]
) -> MergedConfig:
    """:func:`merge_layers`, plus the name of the layer each slot came from.

    The provenance is what lets a picker say *which* layer is overriding a slot
    instead of only showing the value that won.
    """
    ordered = list(layers)[::-1]
    endpoints, views = _endpoint_layers(ordered)
    by_id = {ep["id"]: ep for ep in endpoints}
    merged: Dict[str, Any] = {"saved_endpoints": endpoints}
    slot_layers: Dict[str, str] = {}
    for slot in slots:
        win = _merge_slot(slot, ordered, views)
        if win is None:
            continue
        resolved = win.slot
        ep_id = resolved["endpoint_id"]
        wanted = views[win.endpoint_layer].get(ep_id) if ep_id else None
        current = by_id.get(ep_id)
        if (wanted is not None and current is not None
                and _endpoint_identity(wanted) != _endpoint_identity(current)):
            # A higher layer redeclared this id. Give this slot its own layer's
            # definition under an id of its own rather than following the
            # redeclaration into a runtime its layer never named.
            alias = _alias_id(ep_id, ordered[win.endpoint_layer].name, by_id, wanted)
            if alias not in by_id:
                by_id[alias] = dict(wanted, id=alias)
                endpoints.append(by_id[alias])
            resolved = dict(resolved, endpoint_id=alias)
        merged[slot] = resolved
        slot_layers[slot] = ordered[win.layer].name
    return MergedConfig(merged, slot_layers)


def merge_layers(layers: Iterable[Layer], slots: Sequence[str]) -> Dict[str, Any]:
    """Collapse layers (lowest precedence first) into one llm_config-shaped dict.

    Per slot, not per file: a layer contributes a slot only when it names a
    model, so a workspace file that pins the specialist leaves the global chat
    model standing instead of blanking it. The corollary is that no layer can
    turn a lower layer's slot *off* — disabling happens in the layer that set
    it, and a higher layer redirects rather than blinds.

    Endpoints are per slot too: a layer's redefinition of an endpoint id reaches
    only the slots that layer supplies, and a slot whose own layer defined the
    id differently keeps that definition under an id of its own.

    The result is not normalised; the caller runs it through
    ``llm_config.normalise`` so hand-written layers get the same validation as
    the global file.
    """
    return merge_layers_with_sources(layers, slots).llm
