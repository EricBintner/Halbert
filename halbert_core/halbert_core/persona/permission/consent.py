# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The consent record — axis 4 of five.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5:

    Consent — did the owner say yes, when, shown what?
    Only an authenticated owner on a first-party surface may write it.
    Absence → DENY — absence means *never asked*, not *allowed*.

One event per capability per decision — never a bare boolean. This module
is the **record** and the pure reads over an append-ordered sequence of
them; the append-only ``haloysius.integrity.EventLog`` store, the ``0600``
projection, the copy manifest, and ``consent-verify`` are D3-P2.

Two load-bearing properties, both pure and both pinned by test:

- **``text_shown_sha256`` is the field that turns a record into evidence**
  (§1.5). Without it, "the user consented" is a boolean anyone can assert;
  with it, "the user agreed to X" resolves to a specific wording in a
  specific release. A grant record without it is not a valid grant.
- **The widening asymmetry** (§1.5): *narrowing needs no authority; widening
  needs an owner and a surface.* A ``denied``/``revoked``/``expired`` record
  may be written by an ``owner``, an ``os`` (a revocation we detected) or
  ``system`` (halt, expiry, a new-capability default). A ``granted`` record
  is refused unless the principal is an **owner**, on an authenticated
  **first-party surface**, with a **live OS re-auth**, at the machine. There
  is no argument that makes the agent an owner — it cannot mint a grant; it
  can only ask.

This module does not read the legacy consent flags (``being.yml
senses.*``, ``vision_config.yml``, …). Per the standing no-users directive
those keys stay on disk, unread, never deleted, and are never read as
grants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional, Sequence


class ConsentDecision(Enum):
    """The outcome a record carries. Only GRANTED is affirmative."""

    GRANTED = "granted"    # the owner said yes, shown specific words
    DENIED = "denied"      # the owner said no (or a new capability's default)
    REVOKED = "revoked"    # the OS or the owner took it back
    EXPIRED = "expired"    # a TTL passed (e.g. the voiceprint 400-day default)
    ABSENT = "absent"      # no record exists — never asked, never allowed


#: The fail-closed reading of "no record": absence, as a decision value.
ABSENT_DECISION = ConsentDecision.ABSENT


#: Authenticated first-party surfaces that may show a widening prompt
#: (§1.5). Remote surfaces (``mcp``, ``ha_component``, peers) are
#: deliberately absent: "No dangerous grant may be made from a remote
#: surface" (§3.4). The D3-P2/D3-P4 packets extend this set as real
#: surfaces ship — it never grows implicitly.
FIRST_PARTY_SURFACES = frozenset({
    "desktop-app/first-run",
    "desktop-app/settings/permissions",
})

#: The authn marker prefix that means "a live OS re-auth happened for this
#: decision" — Touch ID / polkit auth_admin / Windows Hello. A session
#: credential ("session") or no re-auth ("none") is not a widening path.
_LIVE_OS_REAUTH_PREFIX = "os_reauth"


#: The ask dispositions a grant may carry (A11-G1). A closed set: an
#: unknown disposition would be a control nobody can enforce.
ASK_OFF = "off"
ASK_EVERY_USE = "every_use"
ASK_DISPOSITIONS = frozenset({ASK_OFF, ASK_EVERY_USE})

#: A11-G10: capabilities whose grant MUST carry a TTL, and how long the
#: design allows. A biometric template is not a preference -- it is a
#: body measurement, and a grant to hold one has to expire whether or not
#: anyone remembers to set an expiry. A grant recorded without one is
#: refused at use rather than silently living forever.
MANDATORY_TTL_DAYS = {
    "sensor.voiceprint": 400,
}


def mandatory_ttl_days(capability: str):
    """The mandatory TTL for a capability in days, or None."""
    return MANDATORY_TTL_DAYS.get(capability)


@dataclass(frozen=True)
class Principal:
    """Who decided — never just a name, always an authentication story."""

    kind: str            # "owner" | "os" | "system" | "agent" | ...
    id: str = ""         # e.g. "local:501"
    name: str = ""       # display only — names never authorize anything
    authn: str = ""      # "os_reauth:touchid" | "session" | "none" | ...
    at_machine: bool = False  # False for anything arriving over a wire


@dataclass(frozen=True)
class ConsentRecord:
    """One event: one capability, one decision, its full provenance.

    Flattened from the design's §1.5 JSON. The chain fields (``seq``,
    ``prev_hash``, ``hash``) belong to the EventLog store (D3-P2) and are
    deliberately not here: a record is the decision, the store is its
    integrity.
    """

    capability: str
    decision: ConsentDecision
    ts: str                                # ISO-8601, when the decision was made
    principal: Principal
    surface: str                           # where the decision was shown
    text_shown_sha256: str = ""            # the words the owner saw — the evidence
    via: str = ""                          # "profile:attentive" | "individual"
    scope: Mapping[str, object] = field(default_factory=dict)
    channel: str = ""                       # e.g. "macos-pro"
    body: str = ""                          # per-body subject (second-machine rule)
    os_grant_at_time: str = ""              # GRANTED/DENIED/UNDETERMINED/UNQUERYABLE
    session_type: str = ""                  # e.g. "aqua"
    other_login_accounts: int = 0           # the household notice's recorded count
    build_version: str = ""
    build_commit: str = ""
    signing_subject: Optional[str] = None
    policy_version: str = "consent-schema/1"
    expires_at: Optional[str] = None        # ISO-8601 TTL bound (voiceprint: 400 days)
    cause: str = ""                         # e.g. "os_declined", "os_revoked"
    prior: Optional[ConsentDecision] = None # the immediately previous decision
    #: A11-G1 + bug 2: the ASK disposition of this grant. ``"off"`` is an
    #: unconditional grant; ``"every_use"`` means the review screen
    #: promised a confirmation before each use, and the ledger has to say
    #: so -- ``accept_profile`` used to drop ``ask_every_use`` on the
    #: floor, so an ask row landed here indistinguishable from an
    #: unconditional one and the promised confirmation existed only as a
    #: Python constant.
    ask: str = ASK_OFF

    def __post_init__(self) -> None:
        if self.ask not in ASK_DISPOSITIONS:
            raise ValueError(
                f"ask must be one of {sorted(ASK_DISPOSITIONS)}, not "
                f"{self.ask!r}: an unknown disposition is a control that "
                f"could lie about when it asks"
            )


def is_affirmative_consent(decision: Optional[ConsentDecision]) -> bool:
    """Only a live GRANTED is yes. Absence is never allowed."""
    return decision is ConsentDecision.GRANTED


def latest_for(
    records: Sequence[ConsentRecord],
    capability: str,
) -> Optional[ConsentRecord]:
    """The most recent record for one capability, in append order.

    The consent log is append-only, so the last record for a capability in
    the sequence is the current decision — the store (D3-P2) guarantees the
    order; this read never re-sorts, because a log whose order can be
    re-derived is a log whose order can be forged.
    """
    latest: Optional[ConsentRecord] = None
    for record in records:
        if record.capability == capability:
            latest = record
    return latest


def _parse_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating the design's ``Z`` suffix.

    ``datetime.fromisoformat`` only understands ``Z`` from Python 3.11;
    the design's records carry ``2026-09-06T14:12:03Z`` verbatim, so the
    ``Z`` is normalized here rather than at every writer.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _expired(record: ConsentRecord, now: str) -> bool:
    if not record.expires_at:
        return False
    try:
        return _parse_ts(record.expires_at) <= _parse_ts(now)
    except (ValueError, TypeError):
        # An unparseable TTL is not a reason to keep a grant alive.
        return True


def consent_state(
    records: Sequence[ConsentRecord],
    capability: str,
    *,
    now: Optional[str] = None,
) -> ConsentDecision:
    """The current consent decision for one capability.

    No record → ABSENT (never asked, not allowed). The latest record wins;
    a grant whose TTL has passed reads EXPIRED — an expired grant is a
    denial with a reason, never a silent extension.
    """
    record = latest_for(records, capability)
    if record is None:
        return ConsentDecision.ABSENT
    if record.decision is ConsentDecision.GRANTED and record.expires_at:
        current = now or datetime.now(timezone.utc).isoformat()
        if _expired(record, current):
            return ConsentDecision.EXPIRED
    return record.decision


def may_record_grant(principal: Principal, surface: str) -> bool:
    """The widening asymmetry, as one pure question (§1.5).

    True only when the principal is an **owner**, on an authenticated
    **first-party surface**, whose ``authn`` records a **live OS re-auth**,
    given **at the machine**. Everything else — the agent, a peer, MCP, HA,
    a session credential, a remote desktop — is refused. Narrowing
    (denied/revoked/expired) has no such bar and never calls this.
    """
    if principal.kind != "owner":
        return False
    if surface not in FIRST_PARTY_SURFACES:
        return False
    if not principal.at_machine:
        return False
    return principal.authn.startswith(_LIVE_OS_REAUTH_PREFIX)


def is_valid_grant_record(record: ConsentRecord) -> bool:
    """Gate 4's evidentiary bar: a grant resolves to specific words.

    A ``granted`` record without the digest of the copy the owner saw is
    not a grant — it is a boolean anyone could have asserted. Non-grant
    decisions carry no such bar (a revocation needs no text shown).
    """
    if record.decision is not ConsentDecision.GRANTED:
        return False
    return bool(record.text_shown_sha256) and bool(record.policy_version)