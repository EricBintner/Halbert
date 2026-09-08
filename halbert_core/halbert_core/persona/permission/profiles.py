# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The three profiles as data — the §2.1 grant table, and its acceptance.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md PART 2:

    A profile is a named set of proposals, not a runtime object. On
    acceptance it writes N individual consent records, each carrying
    ``via: "profile:attentive"``. There is no code path anywhere that
    asks "which profile am I?" — every grant is individually recorded,
    individually shown, individually revocable. The profile name is
    provenance.

The vocabulary discipline this module adds on top of P1/P2:

- **The five bright lines are compiler invariants** (§2.1). A profile
  definition that crosses one fails at import, not at runtime: no
  profile grants any ``egress.*``; none grants ``auto.act``; none
  grants a biometric; ``reach.privileged`` re-authenticates every
  single time in every profile including Present; and no profile
  requests Full Disk Access or Accessibility — the vocabulary cannot
  express either, and no proposal escapes the vocabulary.
- **The shipped-default reversals are data** (§2.1's four): silent
  capture on intent is *denied* (and acceptance writes the denial as a
  record, so the reversal is durable and visible in the ledger);
  redaction is required on the on-demand screen grant; the autonomy
  default is ``suggest`` where the product lives and ``observe`` in
  Reserved — carried as a proposal datum, never a grant; Wyoming binds
  to loopback/UDS in Attentive — carried in ``surface_defaults``,
  because surface ids take no consent records.
- **The Attentive/Present line is one testable sentence** — *it is
  whether anyone asked*. Pinned as data: a profile marked
  ``turn_scoped_only`` grants zero always-on capabilities (the
  continuous sensors, the loop nobody is in, unprompted speech).
  ``auto.scheduler`` is the deliberate §2.1 exception — jobs the owner
  created, each with its own revocable record — so it is not in the
  excluded set, and that exception is stated here rather than smuggled.

Acceptance goes through the D3-P2 store's one writer
(``ConsentStore.record_decision``): every record carries the digest of
the shipped review-screen copy for the profile (Gate 4 — "the user
agreed to X" resolves to specific words), the ``via`` that names the
profile, and the distribution channel the decision was made on. The
review-screen copy itself lives in ``halbert_core/consent/copy.py``
(all consent copy in one module); it is imported lazily here because
``copy.py`` imports this package's ceiling and a module-level import
would cycle.

This module is pure data plus one writer-composing function. It wires
no live surface, starts nothing, and reads no runtime state — the
first-run flow that renders the screens and calls ``accept_profile``
is D3-P5/P6 territory, review-gated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

from .ceiling import VOCABULARY, takes_consent_records
from .channels import channel_for
from .consent import ConsentDecision, ConsentRecord, Principal

__all__ = [
    "ALWAYS_ON_IDS",
    "PRESELECTED_PROFILE",
    "PROFILE_NAMES",
    "PROFILES",
    "ProfileDefinition",
    "ProfileProposal",
    "ProfileRefused",
    "VOICEPRINT_DEFAULT_TTL_DAYS",
    "accept_profile",
    "profile_proposals_for",
]


#: The three profile names, in display order (§2.1's column order).
RESERVED = "reserved"
ATTENTIVE = "attentive"
PRESENT = "present"
PROFILE_NAMES: Tuple[str, ...] = (RESERVED, ATTENTIVE, PRESENT)

#: §2.3: Attentive is preselected. A first-run-UI fact; this packet
#: ships the datum (and the copy digests for the review screen), and
#: the first-run wiring (D3-P5/P6) renders it.
PRESELECTED_PROFILE = ATTENTIVE

#: §2.1 bright line 3: the biometric's default TTL, in days. The
#: profile never grants it; an individual typed-phrase grant carries
#: ``expires_at`` computed by the *caller* (P2's store takes it as a
#: parameter) — the profile compiler only pins the shipped default the
#: caller must use.
VOICEPRINT_DEFAULT_TTL_DAYS = 400

#: Capabilities that run with nobody in the turn — the
#: Attentive/Present line, as data. A ``turn_scoped_only`` profile
#: grants none of these: every grant it makes opens inside a turn a
#: person started, holds for that turn, and closes with it. The
#: continuous sensors are here because on-demand and continuous are
#: two grants, never a switch and a sub-switch (§1.3); ``auto.observe``
#: is "sensor loops running with nobody in the turn"; ``auto.speak``
#: is unprompted speech. ``auto.scheduler`` is deliberately absent —
#: see the module docstring.
ALWAYS_ON_IDS: FrozenSet[str] = frozenset({
    "sensor.screen.continuous",
    "sensor.camera.continuous",
    "sensor.mic.continuous",
    "auto.observe",
    "auto.speak",
})

#: Capabilities no proposal may ever carry, in any profile, under any
#: decision: the bright-line rows where even a denial record would
#: imply the profile governs the thing. Egress is decided per
#: destination at configuration time, never in bulk (§2.5); the
#: biometric is an individual typed-phrase act; ``auto.act`` is an
#: individual typed-phrase grant; the photo library is not implemented
#: and no row ships. Absence already denies all of these — fail-closed
#: needs no record, and a record would imply there was something to
#: decide.
NEVER_PROPOSED_IDS: Tuple[str, ...] = (
    "sensor.voiceprint",
    "sensor.photos",
    "auto.act",
)


class ProfileRefused(Exception):
    """An acceptance or proposal lookup the profile layer refused.

    Fail-closed: nothing is written when this is raised. The reason
    code names which leg failed, in the GrantRefused discipline.
    """

    #: The profile name is not one of the three shipped profiles.
    UNKNOWN_PROFILE = "unknown_profile"
    #: The distribution channel id is not one this build knows.
    UNKNOWN_CHANNEL = "unknown_channel"
    #: §2.4: the channel does not offer this profile (Present is not
    #: displayed on the companion channels; Windows offers nothing).
    NOT_OFFERED_ON_CHANNEL = "not_offered_on_channel"

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(
            f"refused: {reason_code}" + (f" ({detail})" if detail else "")
        )


@dataclass(frozen=True)
class ProfileProposal:
    """One row of the §2.1 grant table.

    ``decision`` is GRANTED (a ``✓`` row) or DENIED (an explicit
    reversal row — only ``auto.capture_on_intent``, the one shipped
    sensor default the table flips). ``ask_every_use`` marks an ``ask``
    row: granted, but every use is confirmed with the literal artefact
    shown — the per-use confirmation is the lease/lattice ask path's
    job (P1/P3), the profile only ships the fact that the row asks.
    A row the table leaves off is simply absent: absence means *never
    asked*, never allowed — fail-closed needs no record.
    """

    capability: str
    decision: ConsentDecision
    ask_every_use: bool = False
    scope: Mapping[str, object] = field(default_factory=dict)


def _granted(capability: str, **scope) -> ProfileProposal:
    return ProfileProposal(
        capability, ConsentDecision.GRANTED, scope=dict(scope)
    )


def _ask(capability: str, **scope) -> ProfileProposal:
    return ProfileProposal(
        capability, ConsentDecision.GRANTED, ask_every_use=True, scope=dict(scope)
    )


#: The one shipped-default reversal that writes a record (§2.1):
#: ``senses.vision.capture_on_intent`` ships ``True`` in the tree today
#: and grabs the active window plus OCR with no tool call, no user
#: turn, no message and no indicator. No profile carries it forward,
#: and acceptance writes the denial so the owner's ledger says so.
_CAPTURE_ON_INTENT_DENIED = ProfileProposal(
    "auto.capture_on_intent", ConsentDecision.DENIED,
    scope={"reversal": "shipped_default_true_to_denied"},
)


@dataclass(frozen=True)
class ProfileDefinition:
    """One profile: its statement, its proposal rows, its defaults.

    ``autonomy_default`` and ``surface_defaults`` are *data the first-run
    wiring reads* — never grants, never consent records. ``auto.act``
    is bright-line barred and ``surface.*`` takes no consent records
    (§1.3), so both live here as shipped defaults instead.
    """

    name: str
    statement: str
    preselected: bool
    #: §2.1's Attentive/Present testable sentence, pinned as data.
    turn_scoped_only: bool
    #: "observe" | "suggest" — the shipped autonomy default (a
    #: reversal: ``observe`` is not the safe default, it is the
    #: useless one). Never "act"; never a grant.
    autonomy_default: str
    #: The §2.1 proposal rows, in table order.
    grants: Tuple[ProfileProposal, ...]
    #: surface id → shipped binding. Surface ids take no consent
    #: records, so these are config facts, not grants.
    surface_defaults: Mapping[str, str] = field(default_factory=dict)


_RESERVED = ProfileDefinition(
    name=RESERVED,
    statement=(
        "I answer questions and read my own state. I don't watch, I "
        "don't listen, and nothing on this machine changes because of "
        "me."
    ),
    preselected=False,
    turn_scoped_only=True,
    autonomy_default="observe",
    grants=(
        _granted("sensor.hardware"),
        _granted("reach.config.read"),
        _granted("reach.fs.read", roots="own_config_data"),
        _granted("reach.fs.write", roots="own_data"),
        _CAPTURE_ON_INTENT_DENIED,
    ),
    surface_defaults={
        "surface.lan_api": "off",
        "surface.mcp": "off",
        "surface.wyoming": "off",
        "surface.ha_component": "off",
    },
)

_ATTENTIVE = ProfileDefinition(
    name=ATTENTIVE,
    statement=(
        "I look after this machine. I read its logs and its "
        "configuration, I change things when you approve the exact "
        "change, I look at your screen when you ask me to, and I hear "
        "you while you hold the talk button. I never watch on my own, "
        "and nothing leaves this computer."
    ),
    preselected=True,
    turn_scoped_only=True,
    autonomy_default="suggest",
    grants=(
        # -- sensor: on-demand only; the continuous rows are absent --
        _granted("sensor.hardware"),
        _granted("sensor.journal"),
        _granted("sensor.config_watch"),
        _granted(
            "sensor.screen",
            redaction="required", named_target=True, receipt="transcript",
        ),
        _granted("sensor.window_titles", bound_to="sensor.screen"),
        _granted("sensor.mic.push_to_talk"),
        # -- reach --
        _granted("reach.config.read"),
        _granted("reach.fs.read", roots="reach_roots_named"),
        _granted("reach.fs.write", roots="own_data_plus_staging"),
        _ask(
            "reach.config.write",
            diff="literal", reason=True, backup=True,
        ),
        _granted(
            "reach.terminal",
            sandboxed=True, classified=True, logged="every_command",
        ),
        _ask(
            "reach.privileged",
            re_auth="every_time", verbs=("read", "diagnostic"),
        ),
        _granted("reach.service", verbs={"query": "granted", "manage": "ask"}),
        _granted("reach.package", verbs={"package.query": "granted",
                                          "package.modify": "ask"}),
        _granted("reach.display_power"),
        # -- auto: the nightly sweep the owner scheduled, nothing else --
        _granted("auto.scheduler", jobs=("nightly_sweep", "morning_summary")),
        # -- the reversal, written so the ledger says so --
        _CAPTURE_ON_INTENT_DENIED,
    ),
    surface_defaults={
        "surface.lan_api": "off",
        "surface.mcp": "off",
        "surface.wyoming": "loopback_or_uds",
        "surface.ha_component": "loopback_or_uds",
    },
)

_PRESENT = ProfileDefinition(
    name=PRESENT,
    statement=(
        "I'm awake in the room. I listen for my name, I keep an eye on "
        "the screen and the cameras you've set up, and I can act on the "
        "house. This is the setting where other people — guests, "
        "family, anyone who walks in — can be recorded. Choose it "
        "deliberately."
    ),
    preselected=False,
    turn_scoped_only=False,
    autonomy_default="suggest",
    grants=(
        # -- sensor: the room, plus everything Attentive holds --
        _granted("sensor.hardware"),
        _granted("sensor.journal"),
        _granted("sensor.config_watch"),
        _granted("sensor.screen", redaction="required"),
        _granted(
            "sensor.screen.continuous",
            named_target=True, max_session_lease="4h", x11_caveat="on_row",
        ),
        _granted("sensor.window_titles"),
        _granted("sensor.camera"),
        _granted("sensor.camera.network", named_cameras=True),
        _granted("sensor.mic.push_to_talk"),
        _granted("sensor.mic.continuous"),
        # -- reach: Attentive's set, wider where the table says wider --
        _granted("reach.config.read"),
        _granted("reach.fs.read", roots="reach_roots_plus_home"),
        _granted("reach.fs.write", roots="own_data_plus_staging"),
        _ask("reach.config.write"),
        _granted("reach.terminal", logged="every_command"),
        _ask(
            "reach.privileged",
            re_auth="every_time",
            verbs=("read", "diagnostic", "write_config", "service_manage"),
        ),
        _granted("reach.service", verbs={"query": "granted", "manage": "ask"}),
        _granted("reach.package", verbs={"package.query": "granted",
                                          "package.modify": "ask"}),
        _ask("reach.network"),
        _granted("reach.display_power"),
        _granted(
            "reach.home",
            tiers={"T0": "granted", "T1": "granted", "T2": "offered",
                   "T3": "out_of_band", "T4": "denied"},
        ),
        # -- auto: the loops run when nobody is there --
        _granted("auto.scheduler"),
        _granted("auto.observe"),
        _granted("auto.speak"),
        _CAPTURE_ON_INTENT_DENIED,
    ),
    surface_defaults={
        "surface.lan_api": "off",
        "surface.mcp": "off",
        "surface.wyoming": "lan_token_pinned_tls",
        "surface.ha_component": "lan_token_pinned_tls",
    },
)


def _compile_profiles(registry: Mapping[str, ProfileDefinition]) -> Dict[str, ProfileDefinition]:
    """The profile compiler — the five bright lines as invariants.

    Runs at import on the shipped registry (and on any registry a test
    hands it): a profile definition that crosses a line raises here,
    before any record could ever be written. "That is the whole GDPR
    Art. 9 / BIPA answer and it costs one line in the profile compiler"
    (§2.1) — this is that compiler.
    """
    for profile in registry.values():
        proposed = [p.capability for p in profile.grants]

        # Bright line 5's structural half: no proposal escapes the
        # vocabulary, and every proposal takes consent records — so no
        # profile can request a thing the ceiling cannot even name
        # (Full Disk Access and Accessibility are not vocabulary ids;
        # surface and sys ids ride the profile's own fields instead).
        for capability in proposed:
            if capability not in VOCABULARY:
                raise ValueError(
                    f"{profile.name}: '{capability}' is not a shipped "
                    f"capability id. A renamed capability is a silently "
                    f"re-granted capability; a profile cannot propose "
                    f"one."
                )
            if not takes_consent_records(capability):
                raise ValueError(
                    f"{profile.name}: '{capability}' does not take "
                    f"consent records; surface and sys facts ride the "
                    f"profile's own fields, never its grants"
                )

        # Bright lines 1–3, and the unimplemented row: no profile may
        # carry these rows at all — not granted, not denied. Absence
        # already denies them; a record would imply there was something
        # to decide, and egress is decided per destination (§2.5),
        # never in bulk.
        for banned in NEVER_PROPOSED_IDS:
            if banned in proposed:
                raise ValueError(
                    f"{profile.name}: '{banned}' may never appear in a "
                    f"profile — it is an individual act with its own "
                    f"record and its own disclosure, or (photos) not "
                    f"implemented at all"
                )
        for capability in proposed:
            if capability.startswith("egress."):
                raise ValueError(
                    f"{profile.name}: '{capability}' — no profile "
                    f"grants any egress. A profile is a statement "
                    f"about this machine's own body; it can never be "
                    f"the reason something left."
                )

        # Bright line 4: re-auth every single time, including in
        # Present. Matching the polkit table: auth_admin_keep appears
        # exactly once, on the read-only diagnostic set.
        for proposal in profile.grants:
            if proposal.capability == "reach.privileged":
                if proposal.decision is not ConsentDecision.GRANTED:
                    raise ValueError(
                        f"{profile.name}: reach.privileged must be an "
                        f"ask row — it is never silently granted and "
                        f"never silently absent"
                    )
                if proposal.scope.get("re_auth") != "every_time" \
                        or not proposal.ask_every_use:
                    raise ValueError(
                        f"{profile.name}: reach.privileged without the "
                        f"every-time re-auth promise. auth_admin_keep "
                        f"appears exactly once, on the read-only "
                        f"diagnostic set; every mutating action "
                        f"re-authenticates."
                    )

        # The shipped autonomy default is a proposal, never an act.
        if profile.autonomy_default not in ("observe", "suggest"):
            raise ValueError(
                f"{profile.name}: autonomy_default "
                f"'{profile.autonomy_default}' — a profile proposes "
                f"observe or suggest. 'act' and 'orchestrate' are "
                f"individual typed-phrase grants."
            )

        # The Attentive/Present line, pinned as data: a profile that
        # holds only turn-scoped capabilities grants nothing that runs
        # with nobody in the turn.
        if profile.turn_scoped_only:
            granted = {
                p.capability for p in profile.grants
                if p.decision is ConsentDecision.GRANTED
            }
            crossed = granted & set(ALWAYS_ON_IDS)
            if crossed:
                raise ValueError(
                    f"{profile.name} is turn-scoped (it is whether "
                    f"anyone asked) but grants {sorted(crossed)}, which "
                    f"run with nobody in the turn"
                )

    return dict(registry)


#: The three shipped profiles — compiled at import. A bright-line
#: violation anywhere in this table fails the import, not a runtime
#: path nobody exercises.
PROFILES: Dict[str, ProfileDefinition] = _compile_profiles({
    RESERVED: _RESERVED,
    ATTENTIVE: _ATTENTIVE,
    PRESENT: _PRESENT,
})


def profile_for(name: str) -> ProfileDefinition:
    """One profile by name. Unknown → ProfileRefused (fail-closed)."""
    try:
        return PROFILES[name]
    except KeyError:
        raise ProfileRefused(
            ProfileRefused.UNKNOWN_PROFILE,
            f"'{name}' is not one of the three shipped profiles "
            f"({list(PROFILE_NAMES)}); there is no fourth posture to "
            f"fall back to",
        ) from None


def profile_proposals_for(profile_name: str, channel_id: str) -> Tuple[ProfileProposal, ...]:
    """The proposal rows acceptance will write, on one channel.

    §2.4's degradation, as a filter: a capability the channel cannot
    deliver is not rendered — so it is not proposed and not recorded,
    on any decision. The row is absent from the batch, never silently
    granted, never written as a grant the ceiling will refuse at every
    future use.
    """
    profile = profile_for(profile_name)
    try:
        channel = channel_for(channel_id)
    except LookupError as exc:
        raise ProfileRefused(ProfileRefused.UNKNOWN_CHANNEL, str(exc)) from exc
    if profile_name not in channel.profiles_offered:
        raise ProfileRefused(
            ProfileRefused.NOT_OFFERED_ON_CHANNEL,
            f"the '{channel_id}' channel does not offer '{profile_name}' "
            f"(§2.4: a profile the channel does not offer is not "
            f"displayed, never shown disabled)",
        )
    return tuple(
        proposal for proposal in profile.grants
        if channel.ceiling.permits(proposal.capability)
    )


def _review_digest(profile_name: str) -> str:
    """The digest of the shipped review-screen copy for one profile.

    Lazy import: ``consent/copy.py`` imports this package's ceiling
    module, so a module-level import here would cycle. Every consent
    copy lives in that one module (Gate 4) — including the review
    screens this packet adds.
    """
    from ...consent.copy import digest_for, review_copy_key

    return digest_for(review_copy_key(profile_name))


def accept_profile(
    profile_name: str,
    store,
    *,
    principal: Principal,
    surface: str,
    channel: str,
    body: str = "",
    os_grant_at_time: str = "",
    session_type: str = "",
    other_login_accounts: int = 0,
    build_version: str = "",
    build_commit: str = "",
    signing_subject: Optional[str] = None,
) -> List[ConsentRecord]:
    """Accept one profile: write its N consent records, individually.

    The one writer is the store's ``record_decision`` (D3-P2) — this
    function composes it, it never appends to the ledger itself. Every
    record carries:

    - ``via: "profile:<name>"`` — the profile name is provenance, the
      only place it ever exists. There is no runtime object to ask
      "which profile am I?"; every grant stays individually revocable;
    - ``text_shown_sha256`` — the digest of the shipped review-screen
      copy for the profile, the words the owner actually read
      (Gate 4: "the user agreed to X" resolves to specific words in a
      specific release);
    - ``channel`` — the distribution channel the decision was made on
      (the record's own field, not the talk channel a turn arrived on);
    - the principal/surface re-auth story, enforced per record by the
      store's widening asymmetry — an agent, a peer, MCP or a remote
      surface cannot accept a profile, and the refusal propagates with
      nothing written.

    Refuses (``ProfileRefused``, nothing written) an unknown profile,
    an unknown channel, or a profile the channel does not offer —
    Present on a companion channel, anything on Windows. Rows the
    channel's ceiling cannot deliver are dropped from the batch
    (§2.4: not rendered), and the count the caller gets back is the
    count actually written.

    All-or-nothing by validation, not by transaction: every record in
    one batch shares the same principal, surface, digest and channel,
    and the compiler has already guaranteed every proposed id is a
    consenting capability no store rule can refuse — so a mid-batch
    refusal is not reachable through profile data, and an I/O failure
    propagates from the store's append with the already-written
    records remaining in the chain (they are true records of grants
    the owner did accept; the first-run commit retries, it never
    back-fills).
    """
    profile = profile_for(profile_name)
    try:
        channel_info = channel_for(channel)
    except LookupError as exc:
        raise ProfileRefused(
            ProfileRefused.UNKNOWN_CHANNEL, str(exc)
        ) from exc
    if profile_name not in channel_info.profiles_offered:
        raise ProfileRefused(
            ProfileRefused.NOT_OFFERED_ON_CHANNEL,
            f"the '{channel}' channel does not offer '{profile_name}'",
        )

    proposals = profile_proposals_for(profile_name, channel)
    digest = _review_digest(profile_name)
    via = f"profile:{profile_name}"

    written: List[ConsentRecord] = []
    for proposal in proposals:
        written.append(
            store.record_decision(
                proposal.capability,
                proposal.decision,
                principal=principal,
                surface=surface,
                text_shown_sha256=digest,
                via=via,
                scope=dict(proposal.scope),
                channel=channel,
                body=body,
                os_grant_at_time=os_grant_at_time,
                session_type=session_type,
                other_login_accounts=other_login_accounts,
                build_version=build_version,
                build_commit=build_commit,
                signing_subject=signing_subject,
            )
        )
    return written