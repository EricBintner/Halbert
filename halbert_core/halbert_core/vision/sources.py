# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Naming what Halbert can look through.

`.handoff/DESIGN-VISION-SOURCE-REGISTRY-2026-09-06.md` (VIS-1). Before this
module there were four unrelated notions of "a camera" — two bare integers in
``vision/config.py``, the string literals ``"webcam"``/``"screen"`` in the CV
tools, Frigate's real camera names, and an anonymous ``frame_source`` callable
in ``ZoneWatcher`` — and no way at all to say "the patio camera only".

A source has a **stable id** and a **volatile native**. The id is what a
persona file, a private-source assignment (``persona/private_sources.py``) and
an audit line hold; the native is the index or camera name the driver needs
this week. Separating them is the whole point: replug a webcam and the native
moves, but ``webcam:desk`` still means the desk webcam and stops resolving
rather than silently pointing at the bedroom.

**Declared, not probed — and this is a correction to the design.** §5 D1
recommended "probe to offer, persist a declared id". Offering turns out not to
be available:

- ``mss`` reports no display identity on macOS. Its ``MSSImplDarwin.monitors()``
  fills only left/top/width/height, and on a single-display machine entry 0 (the
  union of all monitors) and entry 1 (the one display) are byte-identical — so
  geometry cannot even tell them apart, let alone name them.
- OpenCV has no device enumeration. ``cv2.videoio_registry`` exposes backend
  introspection only; the sole way to discover a camera is to trial-open indices
  and watch what succeeds, which is slow and lights the camera LED once per
  probe. Doing that to populate a settings page is not acceptable behaviour for
  a machine that is trying to earn trust about its camera.

So the registry is **declared** — sources live in ``vision_config.yml`` with an
id, a label the user chose, and the native to drive — and probing is reduced to
what it can honestly do: ``availability()`` says whether a declared source
resolves *right now*, without claiming to have found it.

Migration is silent and lossless: an install with the old scalar
``screen_capture.monitor_index`` / ``webcam.camera_index`` and no ``sources:``
section gets exactly two auto-declared sources built from those integers, so
nothing a user configured is lost and nothing they did not configure appears.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.vision.sources")

#: The shape ``persona/private_sources.py`` validates. Kept in step with it
#: deliberately: an id this module mints must be assignable to a guest.
_SOURCE_ID = re.compile(r"^[a-z][a-z0-9_]*:[A-Za-z0-9_.:-]{1,120}$")

KIND_SCREEN = "screen"
KIND_WEBCAM = "webcam"
KIND_FRIGATE = "frigate"
KINDS = (KIND_SCREEN, KIND_WEBCAM, KIND_FRIGATE)


class BadSourceId(ValueError):
    """Not a registry-shaped source id."""


class UnknownSource(LookupError):
    """No source with that id is declared."""


class SourceUnavailable(RuntimeError):
    """A declared source did not resolve. Never silently substituted."""


class SourceDenied(PermissionError):
    """The caller may not look through this source."""


def slug(text: str) -> str:
    """A native name reduced to something an id may contain.

    Frigate lets a camera be called ``"Front Door"``, and the id grammar does
    not allow a space — so the id carries ``front_door`` while the source keeps
    ``"Front Door"`` as its native and its label. Without this, assigning a
    Frigate camera with a space in its name raises ``BadSourceId`` and the
    camera simply cannot be handed over.
    """
    # ``str(text or "")`` would turn monitor 0 and camera 0 into "" — 0 is
    # falsy, and index 0 is the commonest camera there is.
    raw = "" if text is None else str(text)
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.:-")
    return cleaned.lower() or "unnamed"


def source_id(kind: str, native: Any) -> str:
    """``kind:native`` with the native slugged into the grammar."""
    if kind not in KINDS:
        raise BadSourceId(f"unknown source kind {kind!r}")
    return f"{kind}:{slug(native)}"


def frigate_source_id(camera: str) -> str:
    """The id for a Frigate camera.

    ``integrations/frigate/frigate_event_mapper._route`` and the registry must
    agree on this or a handed-over camera routes under one id and is looked up
    under another — so both call here rather than each building an f-string.
    """
    camera = str(camera or "").strip()
    return source_id(KIND_FRIGATE, camera) if camera else ""


#: The active window is a source Halbert can watch but cannot name a display
#: for: the frontmost window may be on any monitor, and ``VisualWatcher``
#: captures it by window id, never by monitor index. Emitting
#: ``screen:<monitor_index>`` there would be a *claim*, not a fact — the same
#: honesty the audio adapters keep about per-satellite ids. So it gets its own
#: id, which means "whatever display the user is looking at".
ACTIVE_WINDOW_SOURCE_ID = "screen:active_window"


def id_for_native(kind: str, native: Any) -> str:
    """The declared id for a driver-level index, or a minted one.

    A background watcher knows its OpenCV index, not its id. If the user has
    declared that camera it gets the name they gave it (so handing over
    ``webcam:desk`` covers this watcher); if they have not, it still gets a
    routable id rather than an empty string, which ``route_observation``
    would read as "cannot say where it looked" and keep for Halbert.
    """
    wanted = str(native).strip()
    try:
        for src in list_sources():
            if src.kind == kind and src.native == wanted:
                return src.id
    except Exception:
        pass
    return source_id(kind, wanted)


def is_source_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_SOURCE_ID.match(value))


@dataclass(frozen=True)
class VisionSource:
    """One thing Halbert can look through.

    ``id`` is stable and is what everything else holds. ``native`` is what the
    driver needs and may change under the same id — a monitor index, an OpenCV
    camera index, a Frigate camera name.
    """
    id: str
    label: str
    kind: str
    native: str
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "native": self.native,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisionSource":
        kind = str(data.get("kind") or "").strip().lower()
        if kind not in KINDS:
            raise BadSourceId(f"unknown source kind {kind!r}")
        native = str(data.get("native", "")).strip()
        if kind in (KIND_SCREEN, KIND_WEBCAM):
            # Every consumer does int(src.native) to drive its device, outside
            # the try that catches capture errors, so a free-text native is a
            # crash rather than a bad picture. Checked here, where the value
            # enters, and not at each of the five call sites.
            try:
                int(native)
            except (TypeError, ValueError):
                raise BadSourceId(
                    f"a {kind} source's device must be an index, got {native!r}"
                )
        sid = str(data.get("id") or "").strip() or source_id(kind, native)
        if not is_source_id(sid):
            raise BadSourceId(f"not a source id: {sid!r}")
        label = str(data.get("label") or "").strip() or sid
        return cls(
            id=sid,
            label=label,
            kind=kind,
            native=native,
            enabled=bool(data.get("enabled", True)),
        )


# ---------------------------------------------------------------------------
# Migration — the two scalars become two declared sources
# ---------------------------------------------------------------------------

def _migrated(config: Any) -> List[VisionSource]:
    """The sources an install with no ``sources:`` section implies.

    Exactly the two the old scalars described, no more: a machine with three
    monitors still gets one declared screen, because one is all the old config
    could express and inventing the other two would be claiming a probe we did
    not run.
    """
    screen = getattr(config, "screen_capture", None)
    webcam = getattr(config, "webcam", None)
    out: List[VisionSource] = []
    if screen is not None:
        idx = getattr(screen, "monitor_index", 1)
        out.append(VisionSource(
            id=source_id(KIND_SCREEN, idx),
            label=f"Screen {idx}" if idx else "All screens",
            kind=KIND_SCREEN,
            native=str(idx),
            enabled=bool(getattr(screen, "enabled", False)),
        ))
    if webcam is not None:
        idx = getattr(webcam, "camera_index", 0)
        out.append(VisionSource(
            id=source_id(KIND_WEBCAM, idx),
            label=f"Webcam {idx}",
            kind=KIND_WEBCAM,
            native=str(idx),
            enabled=bool(getattr(webcam, "enabled", False)),
        ))
    return out


def sources_from_config(config: Any) -> List[VisionSource]:
    """Declared sources, migrating the scalars when none are declared."""
    declared = list(getattr(config, "sources", None) or [])
    if not declared:
        return _migrated(config)
    out: List[VisionSource] = []
    seen = set()
    for entry in declared:
        try:
            src = entry if isinstance(entry, VisionSource) else VisionSource.from_dict(entry)
        except (BadSourceId, AttributeError, TypeError) as e:
            logger.warning("Dropping malformed vision source %r: %s", entry, e)
            continue
        if src.id in seen:
            logger.warning("Duplicate vision source id %r ignored", src.id)
            continue
        seen.add(src.id)
        out.append(src)
    return out


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def list_sources(*, include_frigate: bool = True) -> List[VisionSource]:
    """Every source this machine has been told about.

    Local sources come from ``vision_config.yml``; Frigate cameras come from
    its ``enabled_cameras`` list, which is configuration and not a network
    call — listing sources must not depend on Frigate being up.
    """
    from .config import load_config

    out = sources_from_config(load_config())
    if include_frigate:
        # Declared wins. ``_frigate_sources`` marks everything enabled (it is
        # reading Frigate's own config, which has no per-camera off switch of
        # ours), so without this a camera the user switched off here would be
        # shadowed by a second, always-enabled copy of itself.
        have = {s.id for s in out}
        out.extend(s for s in _frigate_sources() if s.id not in have)
    return out


def _frigate_sources() -> List[VisionSource]:
    try:
        from ..integrations.frigate.frigate_config import load_frigate_config
        cfg = load_frigate_config()
    except Exception:
        return []
    if not cfg.is_configured():
        return []
    out: List[VisionSource] = []
    for camera in list(getattr(cfg, "enabled_cameras", None) or []):
        sid = frigate_source_id(camera)
        if not sid:
            continue
        out.append(VisionSource(
            id=sid, label=str(camera), kind=KIND_FRIGATE, native=str(camera), enabled=True,
        ))
    return out


def get_source(sid: str) -> VisionSource:
    """The declared source with this id, or ``UnknownSource``."""
    for src in list_sources():
        if src.id == sid:
            return src
    raise UnknownSource(sid)


def enabled_source_ids() -> List[str]:
    """The ids the system has switched on. The ceiling a persona narrows from.

    Two switches have to agree, and this is where they are ANDed: the global
    ``screen_capture.enabled`` / ``webcam.enabled`` in ``vision_config.yml``
    and the per-source flag. They are written by different controls and drift
    the moment either is edited alone, so neither is treated as the whole
    answer — the stricter one wins, which is the only direction that cannot
    turn a switched-off camera back on.
    """
    try:
        from .config import load_config
        cfg = load_config()
        globals_on = {
            KIND_SCREEN: bool(cfg.screen_capture.enabled),
            KIND_WEBCAM: bool(cfg.webcam.enabled),
            KIND_FRIGATE: True,   # Frigate's switch is Frigate's own config
        }
    except Exception:
        globals_on = {}
    return [
        s.id for s in list_sources()
        if s.enabled and globals_on.get(s.kind, True)
    ]


def availability(src: VisionSource) -> bool:
    """Whether ``src`` resolves right now — cheaply, and without opening a camera.

    Screens can be counted (``mss`` reports how many it sees). Cameras cannot
    be checked without opening them, which lights the LED, so a declared webcam
    reports available and fails loudly at capture instead. Frigate cameras are
    configuration; whether the NVR answers is a question for the capture.
    """
    if src.kind != KIND_SCREEN:
        return True
    try:
        from .screen_capture import ScreenCapture  # noqa: F401
        import mss as _mss
        with _mss.mss() as sct:
            return 0 <= int(src.native) < len(sct.monitors)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Who may look through what
# ---------------------------------------------------------------------------

def persona_scope() -> List[str]:
    """The ids the active persona may look through.

    Its declared narrowing (``being.yml senses.vision.sources``) intersected
    with what the system has enabled. An empty narrowing means *every* enabled
    source, not none — that is what every persona file written before VIS-1
    means, and reading it as "none" would blind the machine on upgrade.

    Intersection, never union: naming a source the system has switched off
    does not switch it on (V1).
    """
    enabled = enabled_source_ids()
    wanted = _explicit_narrowing()   # raises SourceDenied if unreadable
    if not wanted:
        return enabled
    allowed = set(wanted)
    return [sid for sid in enabled if sid in allowed]


def permit_source(requested_id: str, *, scope: Optional[List[str]] = None) -> VisionSource:
    """The source ``requested_id`` names, if this caller may look through it.

    Raises rather than substituting. A denied request that quietly returned an
    allowed source would be a lie about what was looked at, and the caller —
    a model, a route, a watcher — would report the wrong room.
    """
    allowed = persona_scope() if scope is None else list(scope)
    src = get_source(requested_id)   # UnknownSource if it is not declared
    if src.id not in allowed:
        raise SourceDenied(
            f"{src.id} is not one of this persona's sources "
            f"({', '.join(allowed) or 'none'})"
        )
    return src


def _explicit_narrowing() -> List[str]:
    """What the persona actually wrote, before intersection.

    ``persona_scope`` cannot answer this: it returns every enabled source when
    a persona has not narrowed, so "narrowed to nothing in particular" and
    "narrowed to exactly these" come back looking the same.

    Reads the file directly rather than through ``load_being_config``, and the
    reason matters. That loader validates the whole config and raises on any
    bad field — including the id-shape check on this very list — so catching
    its exception and calling the result "no narrowing" would mean **a
    malformed narrowing widens the scope instead of narrowing it**. A
    narrowing that cannot be read at all raises, and every caller treats that
    as a refusal rather than as permission.
    """
    import yaml  # local: this must work even when being_config cannot load

    from ..utils.platform import get_config_dir

    path = get_config_dir() / "being.yml"
    try:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        raise SourceDenied(f"cannot read this persona's vision scope: {e}") from e

    senses = (data.get("senses") or {}) if isinstance(data, dict) else {}
    vision = (senses.get("vision") or {}) if isinstance(senses, dict) else {}
    wanted = vision.get("sources") or [] if isinstance(vision, dict) else []
    if not isinstance(wanted, list):
        raise SourceDenied("this persona's vision scope is not a list")
    return [w for w in wanted if isinstance(w, str) and is_source_id(w)]


def permit_frigate_camera(camera: str) -> str:
    """The source id for a Frigate camera this caller may look at.

    Frigate is the one kind that cannot be bounded by enumeration offline.
    ``enabled_cameras`` empty means "every camera" (its own config comment says
    so), and listing the real set needs the NVR to answer — which listing
    sources must never depend on. So the bound is whatever the caller can
    actually be held to:

    - a persona that narrowed explicitly is held to its list;
    - otherwise, if some cameras are declared, the request must name one;
    - otherwise there is no list to check against, and refusing every camera
      would break a working install to enforce a bound we cannot express.

    That last branch is a real gap and is named as one rather than papered
    over: an install with no ``enabled_cameras`` gets no Frigate narrowing
    until either the user lists their cameras or the persona names the ones it
    may see.
    """
    sid = frigate_source_id(camera)
    if not sid:
        raise SourceDenied("no camera named")

    # Enabled, not merely declared: the per-source off switch is part of the
    # system-enabled set every other kind is intersected with, and reading
    # only ``declared`` here made the Vision tab's toggle decorative for
    # Frigate.
    enabled = set(enabled_source_ids())
    declared = {s.id for s in list_sources() if s.kind == KIND_FRIGATE}
    if declared and sid in declared and sid not in enabled:
        raise SourceDenied(f"{sid} is switched off")
    narrowing = _explicit_narrowing()

    if narrowing and sid not in set(narrowing):
        raise SourceDenied(
            f"{sid} is not one of this persona's sources ({', '.join(narrowing)})"
        )
    # Intersection, never override. A persona naming a camera the machine has
    # not declared must not thereby declare it — that is V1, and reading the
    # narrowing first and returning early would have made a persona file able
    # to widen past the machine's own list.
    if declared and sid not in declared:
        raise SourceDenied(
            f"{sid} is not one of this machine's cameras ({', '.join(sorted(declared))})"
        )
    return sid


def default_source_for_kind(kind: str, *, scope: Optional[List[str]] = None) -> Optional[VisionSource]:
    """The source a caller means by a bare ``"webcam"`` or ``"screen"``.

    The first enabled, in-scope source of that kind. This is what keeps the
    old two-value CV argument working: it now means "my webcam", resolved
    against the persona's scope, rather than "camera index 0" regardless.
    """
    allowed = set(persona_scope() if scope is None else scope)
    for src in list_sources():
        if src.kind == kind and src.enabled and src.id in allowed:
            return src
    return None


def resolve_request(value: Any, kind: str, *, scope: Optional[List[str]] = None) -> VisionSource:
    """Turn what a caller asked for into a permitted source.

    Accepts three spellings, because three already exist in the tree:

    - a registry id (``"frigate:patio"``) — the way forward;
    - a bare kind (``"webcam"``, ``"screen"``) — what the CV tools pass, now
      meaning *this persona's* webcam rather than index 0;
    - a native index (``2``, ``"2"``) — what ``capture_screenshot``'s
      ``monitor`` argument and the HTTP query params pass. This is the case
      that closes the hole: the index is no longer a free choice the model
      makes, it is a *request* for ``screen:2``, which must be declared,
      enabled and in scope like any other.
    """
    if isinstance(value, str) and is_source_id(value):
        src = permit_source(value, scope=scope)
        _require_kind(src, kind)
        return src
    if value is None or (isinstance(value, str) and value.strip().lower() == kind):
        src = default_source_for_kind(kind, scope=scope)
        if src is None:
            raise SourceDenied(f"this persona has no {kind} source")
        return src
    if isinstance(value, str) and value.strip().lower() in KINDS:
        # A bare kind name other than the one asked for. Refused rather than
        # honoured: the caller is about to do ``int(src.native)`` and drive
        # its OWN device with that number, so answering "screen" with a
        # screen source would open camera 1 when the persona was permitted
        # monitor 1.
        raise SourceDenied(
            f"asked for a {kind} source and given {value.strip().lower()!r}"
        )

    # A native index. Look it up in the registry rather than minting an id
    # from it: the whole point of the id/native split is that ``webcam:desk``
    # may have native "1", so ``camera=1`` means *that* source, not a source
    # called ``webcam:1``. Minting would raise UnknownSource for a camera that
    # is declared, and the caller would read that as "no such camera" when the
    # real answer is "not yours".
    native = str(value).strip()
    for src in list_sources():
        if src.kind == kind and src.native == native:
            return permit_source(src.id, scope=scope)
    raise UnknownSource(f"{kind} {native!r} is not a declared source")


def _require_kind(src: VisionSource, kind: str) -> None:
    """A permission for one kind of device must not open another.

    ``resolve_request`` used to accept any registry id and hand it back, and
    every caller then coerced ``src.native`` into its own driver index —
    ``camera_index = int(src.native)``, ``monitor_index = int(src.native)``.
    So an id the persona *was* allowed became an index into a device class it
    was not: ``capture_webcam(source="screen:1")`` opened camera 1.
    """
    if src.kind != kind:
        raise SourceDenied(
            f"{src.id} is a {src.kind} source; this asked for a {kind}"
        )


def kind_of(sid: str) -> str:
    """The kind a registry id names, from the id alone."""
    head = str(sid or "").split(":", 1)[0].strip().lower()
    return head if head in KINDS else ""


# ---------------------------------------------------------------------------
# Resolving one frame
# ---------------------------------------------------------------------------

def resolve_source(sid: str, *, quality: Optional[int] = None,
                   max_dimension: Optional[int] = None) -> bytes:
    """One JPEG from the named source.

    Replaces the two-value ``"webcam" | "screen"`` enum the CV tools used, so
    ``detect_objects`` can run against a Frigate camera for the first time.
    Raises ``UnknownSource`` or ``SourceUnavailable`` — never a frame from a
    different source than the one asked for.
    """
    from .config import load_config

    src = get_source(sid)
    cfg = load_config()

    if src.kind == KIND_SCREEN:
        from .screen_capture import ScreenCapture
        cap = ScreenCapture(
            quality=quality or cfg.screen_capture.quality,
            max_dim=max_dimension or cfg.screen_capture.max_dimension,
            grayscale=cfg.screen_capture.grayscale,
        )
        try:
            return cap.capture_full(monitor_index=int(src.native))
        except Exception as e:
            raise SourceUnavailable(f"{sid} did not resolve: {e}") from e

    if src.kind == KIND_WEBCAM:
        from .webcam_capture import WebcamCapture
        cap = WebcamCapture(
            camera_index=int(src.native),
            quality=quality or cfg.webcam.quality,
            max_dim=max_dimension or cfg.webcam.max_dimension,
            grayscale=cfg.webcam.grayscale,
        )
        try:
            return cap.grab_frame()
        except Exception as e:
            raise SourceUnavailable(f"{sid} did not resolve: {e}") from e

    if src.kind == KIND_FRIGATE:
        return _resolve_frigate(src)

    raise UnknownSource(sid)


def _resolve_frigate(src: VisionSource) -> bytes:
    """A latest frame from Frigate, pulled on demand and never continuously.

    D2 answered yes: a Frigate camera is a real CV source, so ``detect_objects``
    on the patio is a thing Halbert can do. On demand only — a continuous pull
    would be a second recorder beside the one the house already has.
    """
    import asyncio

    from ..integrations.frigate.frigate_client import FrigateClient
    from ..integrations.frigate.frigate_config import load_frigate_config

    async def _pull() -> bytes:
        # Deliberately NOT the module singleton the Frigate tools share.
        # FrigateClient caches its aiohttp.ClientSession and only rebuilds it
        # when the session reports itself closed — which closing the loop does
        # not do. Running a pull on a private loop against the shared client
        # would leave it holding a session bound to a dead loop, and every
        # later Frigate call in the process would fail.
        client = FrigateClient(load_frigate_config())
        try:
            return await client.get_latest_frame(src.native)
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    pass

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_pull())
        # Called from inside a loop: run the pull on its own so a sync caller
        # on an async thread does not deadlock waiting on itself.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_pull())).result()
    except Exception as e:
        raise SourceUnavailable(f"{src.id} did not resolve: {e}") from e
