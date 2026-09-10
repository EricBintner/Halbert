# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Lease — one object doing five jobs (§1.6), D3-P3's pure half.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.6:

    The gate does not return a boolean. It returns the thing that does
    the work.

A ``Lease`` is simultaneously:

1. **the gate's return value** — there is no other way to obtain a
   capturer, an exec handle, or an egress client;
2. **the only constructor argument the primitives accept** (the
   Lease-typed constructors on the six primitives are the review-gated
   half, D3-P5) — ``Lease.__init__`` is module-private; the only mint
   is ``require()``;
3. **the live-indicator source** — it registers in an in-process
   registry on open and deregisters on close. **An indicator is
   defined as the set of open leases**, so an indicator that lies is
   structurally impossible rather than merely tested for;
4. **the activity-log row** — it carries the reason: a human utterance
   or a named deterministic rule, never a model-generated rationale;
5. **the in-loop liveness token** — ``lease.check()`` is called every
   iteration, and a revoked or halted lease sets the loop's
   ``threading.Event`` so the thread **exits** rather than merely
   failing its next call (the F38/F99 fix shape).

Fail-closed rules built in:

- **Redaction fails closed on the capability, not the frame** (§1.7): a
  grant whose scope declares ``redaction: "required"`` refuses to open
  on a host with no working backend, and the refusal is the §4.1 halt
  (``REDACTION_UNAVAILABLE``) — it never captures and mislabels.
- **The resolved-path check runs on the path the handler will actually
  open, obtained once, used for both check and open** (F16):
  ``lease.bind_path(raw)`` resolves the target a single time, checks it
  against the grant's resolved Reach roots, and returns the resolved
  path the handler then opens with.
- Every default of ``require()`` denies (the D3-P1 discipline): an
  unwired axis is a closed axis.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ...consent.denials import CLOSED_REASONS, Denied
from .affordance import AffordanceTable, EMPTY_AFFORDANCE, affords
from .ceiling import CapabilityCeiling, EMPTY_CEILING, takes_consent_records
from .consent import (
    ASK_EVERY_USE,
    ConsentDecision,
    ConsentRecord,
    consent_state,
    latest_for,
)
from .effective import (
    _HALT_REQUIRED,
    AXIS_CEILING,
    AXIS_CONSENT,
    AXIS_HALT,
    AXIS_SCOPE,
    EffectiveDecision,
    REASON_HALTED,
    REASON_NO_AFFORDANCE,
    REASON_NO_CEILING,
    REASON_NOT_GRANTED,
    REASON_OS_DENIED,
    REASON_OS_UNKNOWN,
    REASON_NEEDS_APPROVAL,
    REASON_OUT_OF_SCOPE,
    REASON_SCOPE_UNREADABLE,
    effective_capability,
)
from .halt import HaltReason, HaltState
from .os_grant import DEFAULT_OS_GRANTS, OsGrantTable

__all__ = [
    "DEFAULT_REGISTRY",
    "Lease",
    "LeaseRegistry",
    "Scope",
    "require",
]

#: The module-private mint token. ``require()`` is the only holder; a
#: direct ``Lease(...)`` raises ``TypeError`` (§1.6: the only mint).
_MINT = object()

#: The redaction mode a grant's scope may declare.
REDACTION_REQUIRED = "required"

#: Which decisive axis a revoked lease's reason code names.
_AXIS_FOR_REASON = {
    REASON_HALTED: AXIS_HALT,
    REASON_NO_CEILING: AXIS_CEILING,
    REASON_NO_AFFORDANCE: AXIS_CEILING,  # never minted; leases are open by then
    REASON_NOT_GRANTED: AXIS_CONSENT,
    REASON_OS_DENIED: AXIS_CONSENT,      # never minted; leases are open by then
    REASON_OS_UNKNOWN: AXIS_CONSENT,      # never minted; leases are open by then
    REASON_OUT_OF_SCOPE: AXIS_SCOPE,
}


def _resolve(path: str) -> str:
    """Obtained once: ``~`` expanded, symlinks followed, one absolute
    string used for both the check and the open (F16)."""
    return os.path.realpath(os.path.expanduser(str(path)))


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


# ---------------------------------------------------------------------------
# Scope — what a grant covers, and what a request names.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """The named targets a grant covers, or that a request names.

    Used in both directions: the *granted* scope rides on the consent
    record (``{"displays": ["*"], "redaction": "required"}``); the
    *requested* scope is passed to ``require()``. ``admits`` decides
    whether the grant covers the request; ``redaction`` on the grant
    drives the fails-closed backend requirement.
    """

    reach_roots: Tuple[str, ...] = ()
    displays: Tuple[str, ...] = ()
    cameras: Tuple[str, ...] = ()
    redaction: str = ""
    #: The descriptive half of the vocabulary (A11-G2). Recorded on the
    #: scope so the grant's own words survive to the ledger and the
    #: review screen, and read by name where a rule consumes one --
    #: never folded into ``admits``, which is what "not interpreted as
    #: a grant" means.
    provenance: Mapping[str, Any] = field(default_factory=dict)

    #: BINDING facts: the ones ``admits`` actually checks. A grant's
    #: coverage is exactly these.
    _BINDING_KEYS = ("reach_roots", "displays", "cameras", "redaction")

    #: PROVENANCE facts: what the grant SAYS about itself. These are the
    #: keys the shipped profile rows carry (§2.1's table) plus the ones
    #: the design names. They are recorded, shown, and read by name where
    #: a specific rule consumes one (``re_auth`` at profiles.py:429,
    #: ``max_session_lease`` at the lease's expiry) -- but none of them
    #: widens what ``admits`` covers, so recording one can never grant
    #: anything.
    #:
    #: A11-G2 + bug 1: before this split, ``from_mapping`` raised on any
    #: key outside the binding four, and 24 of the 47 shipped rows carry
    #: one. The first ``require()`` after first-run acceptance therefore
    #: raised a bare ValueError out of the permission system and crashed
    #: the turn. The parser lesson still holds for anything in NEITHER
    #: list: a scope the code cannot read is not a grant.
    _PROVENANCE_KEYS = (
        "roots",              # the policy label a profile row names
        "verbs",              # per-verb dispositions (reach.service/package)
        "re_auth",            # "every_time" -- read by the profile compiler
        "diff", "reason", "backup",          # reach.config.write's contract
        "sandboxed", "classified", "logged",  # reach.terminal's contract
        "jobs",               # auto.scheduler's named jobs
        "named_target", "named_cameras",      # what may be pointed at
        "receipt",            # what the use leaves behind
        "bound_to",           # this row rides another capability
        "max_session_lease",  # the ceiling on one open lease
        "x11_caveat",         # a platform truth recorded on the row
        "tiers",              # reach.home's tier list
        "reversal",           # a shipped default written as DENIED
    )

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]]) -> "Scope":
        """Build from a consent record's scope mapping (strict).

        A key in neither vocabulary raises rather than being ignored: a
        scope that silently drops a field would widen what the check
        believes it covered (the parser.py:206 lesson).
        """
        data = dict(mapping or {})
        known = set(cls._BINDING_KEYS) | set(cls._PROVENANCE_KEYS)
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(
                f"unknown scope key(s) {unknown}: a scope the code cannot "
                f"read must never be interpreted as a grant"
            )
        redaction = data.get("redaction", "")
        if redaction not in ("", REDACTION_REQUIRED):
            raise ValueError(
                f"redaction must be '' or 'required', not {redaction!r}: an "
                f"unknown redaction mode is a control that could lie"
            )
        return cls(
            reach_roots=tuple(data.get("reach_roots", ())),
            displays=tuple(data.get("displays", ())),
            cameras=tuple(data.get("cameras", ())),
            redaction=redaction,
            provenance=MappingProxyType({
                k: v for k, v in data.items() if k in cls._PROVENANCE_KEYS
            }),
        )

    @property
    def redaction_required(self) -> bool:
        return self.redaction == REDACTION_REQUIRED

    def admits(self, requested: "Scope") -> bool:
        """Does this granted scope cover that requested one?

        Unknown/absent coverage denies: a request that names anything the
        grant does not cover is out of scope, and a request that names
        nothing specific is vacuously admitted (the binding calls below
        still check every concrete target).
        """
        if requested.reach_roots:
            if not self.reach_roots:
                return False
            granted = [_resolve(root) for root in self.reach_roots]
            for root in requested.reach_roots:
                resolved = _resolve(root)
                if not any(_within(resolved, g) for g in granted):
                    return False
        for named, covered in (
            (requested.displays, self.displays),
            (requested.cameras, self.cameras),
        ):
            if named and not covered:
                return False
            for target in named:
                if target not in covered and "*" not in covered:
                    return False
        return True


# ---------------------------------------------------------------------------
# The registry — an indicator is the set of open leases.
# ---------------------------------------------------------------------------


class LeaseRegistry:
    """The in-process set of open leases — Halbert is single-instance,
    and the registry is deliberately not multi-process machinery.

    The indicator's honesty is structural: leases are added only on open
    (``require()``) and removed only on close, so the set *is* the truth
    an indicator reads — there is no second list to drift from.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: list = []

    def register(self, lease: "Lease") -> None:
        if not isinstance(lease, Lease):
            raise TypeError("only require() mints leases to register")
        with self._lock:
            if lease not in self._open:
                self._open.append(lease)

    def deregister(self, lease: "Lease") -> None:
        if not isinstance(lease, Lease):
            raise TypeError("only an open lease deregisters")
        with self._lock:
            if lease in self._open:
                self._open.remove(lease)

    def open_leases(self) -> Tuple["Lease", ...]:
        """The indicator: a snapshot of the open set, in open order."""
        with self._lock:
            return tuple(self._open)

    def revoke_all(self, reason_code: str, *, by: str = "", surface: str = "") -> int:
        """Mark every open lease revoked and trip its stop event.

        The Stop wiring's one call (D3-P6): every loop that checks its
        lease exits, and every thread blocked on its event wakes.
        """
        count = 0
        for lease in self.open_leases():
            lease.revoke(reason_code, by=by, surface=surface)
            count += 1
        return count

    def __contains__(self, lease: object) -> bool:
        with self._lock:
            return lease in self._open

    def __len__(self) -> int:
        with self._lock:
            return len(self._open)


#: The process's registry. Injectable everywhere; the default exists so
#: the wiring has one honest place to read the indicator from. Tests
#: inject their own and never touch this one (the singleton-probe lesson).
DEFAULT_REGISTRY = LeaseRegistry()


# ---------------------------------------------------------------------------
# The lease.
# ---------------------------------------------------------------------------


class Lease:
    """The gate's return value — the thing that does the work.

    ``__init__`` is module-private (the only mint is :func:`require`);
    a direct construction raises ``TypeError``. The lease is the
    liveness token (``check()``), the indicator row (its presence in a
    registry), the activity row (``activity_row()``), and the scope the
    handler binds targets against (``bind_path``/``bind_display``/
    ``bind_camera``).
    """

    __slots__ = (
        "_closed", "_decision", "_granted_scope", "_halt", "_opened_at",
        "_reason", "_registry", "_requested_scope", "_revoked",
        "_revoked_by", "_revoked_reason", "_stop_event", "_actor",
        "_capability", "_turn_id",
    )

    def __init__(self, *, _mint: object = None, **fields) -> None:
        if _mint is not _MINT:
            raise TypeError(
                "Lease cannot be constructed directly; require() is the only "
                "mint. There is no other way to obtain a capturer, an exec "
                "handle, or an egress client."
            )
        self._capability = fields["capability"]
        self._decision = fields["decision"]
        self._granted_scope = fields["granted_scope"]
        self._requested_scope = fields["requested_scope"]
        self._halt = fields["halt"]
        self._stop_event = fields["stop_event"]
        self._registry = fields["registry"]
        self._actor = fields["actor"]
        self._reason = fields["reason"]
        self._turn_id = fields["turn_id"]
        self._opened_at = datetime.now(timezone.utc).isoformat()
        self._closed = False
        self._revoked = False
        self._revoked_reason = ""
        self._revoked_by = ""

    # -- identity ------------------------------------------------------

    @property
    def capability(self) -> str:
        return self._capability

    @property
    def decision(self) -> EffectiveDecision:
        return self._decision

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def revoked(self) -> bool:
        return self._revoked

    @property
    def revoked_reason(self) -> str:
        return self._revoked_reason

    @property
    def granted_scope(self) -> Optional[Scope]:
        return self._granted_scope

    # -- the activity row (job 4) ---------------------------------------

    def activity_row(self) -> Dict[str, str]:
        """The provenance an activity log writes on open: who asked, why
        (a human utterance or a named deterministic rule — never a
        model-generated rationale), which turn, when."""
        return {
            "capability": self._capability,
            "actor": self._actor,
            "reason": self._reason,
            "turn_id": self._turn_id,
            "opened_at": self._opened_at,
        }

    # -- the liveness token (job 5) --------------------------------------

    def check(self) -> None:
        """Every loop iteration calls this. A revoked or halted lease
        raises the typed ``Denied`` **after** tripping the loop's stop
        event, so the thread exits rather than merely failing its next
        call — F38/F99's lesson: failing the next capture is not enough;
        the loop must end."""
        if self._closed:
            raise RuntimeError(
                f"the {self._capability} lease is closed; a closed lease has "
                f"no loop to check"
            )
        if self._revoked:
            raise Denied(
                self._capability,
                self._revoked_reason,
                decisive_axis=_AXIS_FOR_REASON.get(self._revoked_reason, ""),
                detail=f"revoked by {self._revoked_by or 'the owner'}",
            )
        if self._halt is not None and self._halt.is_halted():
            # Trip the event first, so even a thread blocked elsewhere in
            # the loop (selecting on the event) wakes and ends.
            self._trip()
            raise Denied(
                self._capability,
                REASON_HALTED,
                decisive_axis=AXIS_HALT,
                detail=f"the machine is stopped ({self._halt.reason_code})",
            )

    def revoke(self, reason_code: str, *, by: str = "", surface: str = "") -> None:
        """Mark this lease revoked and trip its stop event. Idempotent;
        a second revocation records the newer reason (the HaltState
        lesson: newer failure is newer information)."""
        if reason_code not in CLOSED_REASONS:
            raise ValueError(
                f"'{reason_code}' is not a typed denial outcome; a lease "
                f"cannot be revoked with an invented reason"
            )
        self._revoked = True
        self._revoked_reason = reason_code
        self._revoked_by = by
        self._trip()

    def _trip(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    # -- scope binding (the F16 shape) ------------------------------------

    def bind_path(self, raw_path: str) -> str:
        """Resolve the handler's path **once**, check it against the
        grant's resolved Reach roots, and return the resolved path to
        open with — the same string used for both the check and the open.

        A grant with no Reach roots binds nothing (fail-closed), and a
        path that resolves outside the roots raises the typed
        ``OUT_OF_SCOPE`` denial.
        """
        resolved = _resolve(raw_path)
        if self._granted_scope is None or not self._granted_scope.reach_roots:
            raise self._out_of_scope(
                resolved, "the grant names no Reach roots, so no path is in it"
            )
        for root in self._granted_scope.reach_roots:
            if _within(resolved, _resolve(root)):
                return resolved
        raise self._out_of_scope(
            resolved, "the resolved path is outside the granted Reach roots"
        )

    def bind_display(self, name: str) -> str:
        """Check a named display against the grant; return it to open with."""
        return self._bind_named(name, "displays", "display")

    def bind_camera(self, name: str) -> str:
        """Check a named camera against the grant; return it to open with."""
        return self._bind_named(name, "cameras", "camera")

    def _bind_named(self, name: str, field: str, noun: str) -> str:
        covered = getattr(self._granted_scope, field) if self._granted_scope else ()
        if name in covered or "*" in covered:
            return name
        raise self._out_of_scope(
            name, f"the grant covers no {noun} named '{name}'"
        )

    def _out_of_scope(self, target: str, detail: str) -> Denied:
        return Denied(
            self._capability,
            REASON_OUT_OF_SCOPE,
            decisive_axis=AXIS_SCOPE,
            detail=detail,
        )

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Deregister the lease — the indicator row goes when the work
        ends. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._registry is not None:
            self._registry.deregister(self)

    def __enter__(self) -> "Lease":
        self.check()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# require() — the only mint.
# ---------------------------------------------------------------------------


def require(
    capability: str,
    *,
    scope: Optional[Scope] = None,
    actor: str = "",
    reason: str = "",
    turn_id: str = "",
    stop_event: Optional[threading.Event] = None,
    registry: Optional[LeaseRegistry] = None,
    # Axis evidence — the D3-P1 defaults: an unwired axis is a closed axis.
    ceiling: CapabilityCeiling = EMPTY_CEILING,
    affordance: AffordanceTable = EMPTY_AFFORDANCE,
    os_grants: OsGrantTable = DEFAULT_OS_GRANTS,
    consent_records: Sequence[ConsentRecord] = (),
    halt: Any = _HALT_REQUIRED,
    capabilities_registry: Optional[object] = None,
    redaction_backend_available: bool = False,
    now: Optional[str] = None,
    approval_token: Optional[str] = None,
    approval_receipts: Optional[object] = None,
    artefact_sha256: str = "",
) -> Lease:
    """Evaluate the five axes and mint the lease that does the work.

    Every refusal raises the D3-P2 typed ``Denied`` (never a bare
    ``False``, no default return path); an allow mints a ``Lease``
    registered in its registry on open. The wiring (D3-P5) supplies the
    axis evidence from the live tables; unwired axes deny, so this is
    importable and testable with zero effect on a running app.

    Args:
        scope: the targets this use names (a display, a camera, Reach
            roots). Admitted only if the grant's own scope covers them.
        actor / reason / turn_id: the activity row's provenance. The
            reason is a human utterance or a named deterministic rule —
            the caller passes what was actually said; a generated
            rationale is not a reason and must never be passed here.
        stop_event: the loop's event. Revocation and halt trip it so the
            thread exits rather than merely failing its next call.
        approval_token / approval_receipts / artefact_sha256: the
            answered confirmation this use redeems (A11-G1/G9, FD-6). A
            grant recorded ``ask: every_use`` is a standing permission,
            not a standing authorisation: the use itself needs a receipt
            minted by the confirmation flow and bound to the artefact
            that was shown. Omitting them on such a grant denies with
            ``NEEDS_APPROVAL`` -- which is not NOT_GRANTED, because the
            remedy is different: answer the confirmation, do not grant
            again.
        redaction_backend_available: whether a working redaction backend
            exists on this host. Defaults to **False** — a grant whose
            scope declares ``redaction: "required"`` refuses to open
            until a backend is affirmatively wired (§1.7: fail closed on
            the capability, not the frame), and the refusal is §4.1's
            halt (``REDACTION_UNAVAILABLE``), never a capture mislabelled
            as redacted.
    """
    if not takes_consent_records(capability):
        # Not a capability that gates through consent at all (sys.* is
        # affordance-only; an unknown id is not a capability). Refuse
        # with the ceiling's own answer: nothing carries it.
        raise Denied(
            capability,
            REASON_NO_CEILING,
            decisive_axis=AXIS_CEILING,
            detail="not a consenting capability; the lease gates "
                   "sensor/reach/egress/auto ids only",
        )

    # The granted scope, from the live grant (only meaningful when the
    # folded state is GRANTED — everything else denies first).
    records = list(consent_records)
    granted_record = latest_for(records, capability)
    granted_scope: Optional[Scope] = None
    if (
        granted_record is not None
        and consent_state(records, capability, now=now) is ConsentDecision.GRANTED
    ):
        # A11-G2 + bug 1: a scope the code cannot read is a DENIAL, not
        # an exception escaping the permission system. It used to raise a
        # bare ValueError out of require() and crash the turn -- and 24
        # of the 47 shipped profile rows took that path on the first
        # require() after first-run acceptance.
        try:
            granted_scope = Scope.from_mapping(granted_record.scope)
        except ValueError as e:
            raise Denied(
                capability,
                REASON_SCOPE_UNREADABLE,
                decisive_axis=AXIS_SCOPE,
                detail=str(e),
            ) from None

    # Scope admission feeds the evaluator's scope axis (§1.7 order);
    # no requested scope is vacuously affirmative.
    scope_ok: Optional[bool] = None
    if scope is not None:
        scope_ok = granted_scope.admits(scope) if granted_scope is not None else False

    decision = effective_capability(
        capability,
        ceiling=ceiling,
        affordance=affordance,
        os_grants=os_grants,
        consent_records=records,
        halt=halt,
        scope_ok=scope_ok,
        registry=capabilities_registry,
        # A11 bug 3: the same clock the scope resolution above used.
        now=now,
    )
    if not decision.allowed:
        raise Denied.from_decision(decision)

    # A11-G1 + G9 (FD-6): an ask-every-use grant needs THIS use approved.
    # The grant says the owner is willing to be asked; the receipt says
    # they were asked and said yes, about this artefact, once.
    if decision.ask == ASK_EVERY_USE:
        receipts = approval_receipts
        if receipts is None:
            from .approval import get_approval_receipts
            receipts = get_approval_receipts()
        redeemed = receipts.redeem(
            approval_token, capability, artefact_sha256=artefact_sha256)
        if redeemed is None:
            raise Denied(
                capability,
                REASON_NEEDS_APPROVAL,
                decisive_axis=AXIS_CONSENT,
                detail="this grant asks before every use, and this use "
                       "carries no answered confirmation for what it is "
                       "about to do",
            )

    # Redaction fails closed on the capability, not the frame — checked
    # only on an otherwise-allowed lease (a refused capability has
    # nothing to mislabel).
    if granted_scope is not None and granted_scope.redaction_required:
        if not redaction_backend_available:
            if isinstance(halt, HaltState):
                halt.halt(
                    HaltReason.REDACTION_UNAVAILABLE,
                    by="require",
                    surface="lease",
                )
            raise Denied(
                capability,
                REASON_HALTED,
                decisive_axis=AXIS_HALT,
                detail="this grant requires redaction and no working "
                       "redaction backend exists on this host; it never "
                       "captures and mislabels",
            )

    target_registry = registry if registry is not None else DEFAULT_REGISTRY
    lease = Lease(
        _mint=_MINT,
        capability=capability,
        decision=decision,
        granted_scope=granted_scope,
        requested_scope=scope,
        halt=halt,
        stop_event=stop_event,
        registry=target_registry,
        actor=actor,
        reason=reason,
        turn_id=turn_id,
    )
    target_registry.register(lease)
    return lease