# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Every word an owner can be shown — all consent copy in one module.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5:

    ``text_shown_sha256`` is the field that turns a record into
    evidence. Without it, "the user consented" is a boolean anyone can
    assert. With it, "the user agreed to X" resolves to a specific
    wording in a specific release. It only works if the wording is
    resolvable, so all consent copy lives in exactly one module,
    ``consent/copy.py``.

Rules this module is built under:

- The copy is **shipped deterministic text** — never generated, never
  paraphrased at display time. The words hashed into a record are the
  words here, byte for byte.
- ``copy_manifest.json`` sits alongside, mapping capability → copy key
  → digest, and ``tests/test_consent_copy_manifest.py`` pins that every
  consenting capability in the vocabulary has copy and that the shipped
  digests match the manifest.
- **Superseded versions ship as versioned assets.** A wording change is
  a *new* version (``v2``), never an edit to ``v1`` — a two-year-old
  ``text_shown_sha256`` must still resolve to the words the owner saw.
  ``sensor.screen`` carries a superseded ``v0`` so that round trip is
  exercised by the shipped data itself.
- **Profile review screens ride the same module and manifest** (D3-P4,
  §3.2 Screen 5/6): a profile acceptance batch carries one digest on
  every record it writes — the review-screen wording — under the
  ``profile:<name>.review`` keys, so a ``via: "profile:attentive"``
  grant resolves to the exact screen the owner accepted.
- The manifest is regenerated from this module
  (``python -c "from halbert_core.consent.copy import write_manifest;
  write_manifest()"``) — the module is the source of truth, the
  manifest is the committed evidence, and the test is the ratchet.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Tuple

from ..persona.permission.ceiling import VOCABULARY, takes_consent_records

#: The copy key a grant record defaults to. Bumping this is a copy
#: change: new records hash the new wording, old records still resolve
#: their own version from ``COPY``.
CURRENT_VERSION = "v1"

#: capability → copy key → the exact wording shown. One entry per
#: consenting capability in the shipped vocabulary, verbatim below.
COPY: Dict[str, Dict[str, str]] = {
    # -- sensor -------------------------------------------------------
    "sensor.screen": {
        "v0": "Look at your screen when you ask me to.",
        "v1": (
            "Read what is on your screen when you ask me to look at it. "
            "I take a screenshot only when a task needs one, and an "
            "indicator shows whenever it is open."
        ),
    },
    "sensor.screen.continuous": {
        "v1": (
            "Watch your screen continuously while this is on, so I can "
            "follow what you are working on. An indicator stays lit the "
            "whole time this is open, and closing it stops the watching."
        ),
    },
    "sensor.window_titles": {
        "v1": (
            "See the titles of your open windows, so I know what you are "
            "working in. Window contents are not included."
        ),
    },
    "sensor.camera": {
        "v1": (
            "Use this machine's camera when you ask me to look with it. "
            "An indicator shows whenever the camera is open."
        ),
    },
    "sensor.camera.continuous": {
        "v1": (
            "Keep this machine's camera open while this is on, for example "
            "to watch a room you have pointed me at. The indicator stays "
            "lit the whole time, and one action stops it."
        ),
    },
    "sensor.camera.network": {
        "v1": (
            "Reach a network camera on your local network — one you own, "
            "such as an RTSP or Frigate camera. Frames stay on this machine."
        ),
    },
    "sensor.mic.push_to_talk": {
        "v1": (
            "Listen while you hold the talk key. I hear audio only while "
            "the key is held, and the same key releases it."
        ),
    },
    "sensor.mic.continuous": {
        "v1": (
            "Keep the microphone open while this is on, so you can just "
            "speak. An indicator shows whenever it is listening, and one "
            "action stops me."
        ),
    },
    "sensor.voiceprint": {
        "v1": (
            "Recognize you by the characteristics of your voice. This is "
            "biometric processing: it is granted only by an individual "
            "typed phrase, it expires after 400 days, and it is never "
            "part of any profile."
        ),
    },
    "sensor.photos": {
        "v1": (
            "Look inside your photo library when you ask me to find or "
            "describe something in it. Nothing leaves this machine."
        ),
    },
    "sensor.journal": {
        "v1": (
            "Read your journal entries when you ask me to search or recall "
            "them."
        ),
    },
    "sensor.hardware": {
        "v1": (
            "Read this machine's own hardware sensors — power, battery, "
            "temperature — to notice the machine's state."
        ),
    },
    "sensor.config_watch": {
        "v1": (
            "Watch this machine's configuration files for changes, so I "
            "can tell you what changed on your system."
        ),
    },
    # -- reach --------------------------------------------------------
    "reach.fs.read": {
        "v1": (
            "Read files in the folders you list on the Reach screen. "
            "Nothing outside them is readable, and a standing deny list "
            "stays closed even when you add a folder that contains it."
        ),
    },
    "reach.fs.write": {
        "v1": (
            "Write files in the folders you list on the Reach screen. "
            "Writes anywhere else are refused."
        ),
    },
    "reach.config.read": {
        "v1": (
            "Read system configuration — /etc and its friends — to answer "
            "questions about this machine's setup."
        ),
    },
    "reach.config.write": {
        "v1": (
            "Change system configuration. Every change is shown to you as "
            "a diff before it happens, and nothing is applied without "
            "that review."
        ),
    },
    "reach.terminal": {
        "v1": (
            "Run commands in a terminal. Commands I run carry this "
            "machine's own permissions, so everything they can do, I can "
            "do — grant this only as wide as you are comfortable with."
        ),
    },
    "reach.privileged": {
        "v1": (
            "Perform privileged actions — things that need root. Every "
            "single one asks for your OS password again, in every profile, "
            "with no exception and no way to turn that off."
        ),
    },
    "reach.service": {
        "v1": (
            "Start, stop, and inspect system services on this machine."
        ),
    },
    "reach.package": {
        "v1": (
            "Install, remove, and update software packages on this "
            "machine. Each change is shown to you before it happens."
        ),
    },
    "reach.network": {
        "v1": (
            "Reach other machines on your local network — ping, port "
            "checks, and requests to hosts on your LAN."
        ),
    },
    "reach.home": {
        "v1": (
            "Control your Home Assistant — only the entities you expose "
            "to me, shown as a list, each individually revocable."
        ),
    },
    "reach.display_power": {
        "v1": (
            "Turn this machine's displays on and off, for example to wake "
            "a screen you are looking for."
        ),
    },
    # -- egress -------------------------------------------------------
    "egress.cloud_model": {
        "v1": (
            "Send your prompts to a cloud model you chose for this. What "
            "leaves is what you typed plus the context I attach; the "
            "destination is shown in Settings, and you can change it "
            "there."
        ),
    },
    "egress.web_search": {
        "v1": (
            "Search the web on your behalf and read the results."
        ),
    },
    "egress.web_fetch": {
        "v1": (
            "Fetch web pages you name and read their contents."
        ),
    },
    "egress.peer": {
        "v1": (
            "Exchange messages and files with the machines you have paired "
            "with me. Each pairing is listed and individually revocable."
        ),
    },
    "egress.acoustid": {
        "v1": (
            "Send a short audio fingerprint of music to the AcoustID "
            "service to identify tracks. The fingerprint cannot be "
            "reversed into audio."
        ),
    },
    "egress.telemetry": {
        "v1": (
            "There is nothing to grant here: I never send telemetry, and "
            "no build of me is capable of it. This entry exists so the "
            "absence itself is provable."
        ),
    },
    # -- auto ---------------------------------------------------------
    "auto.scheduler": {
        "v1": (
            "Run tasks you have scheduled while you are away — only the "
            "ones you created, each with its own record you can revoke."
        ),
    },
    "auto.observe": {
        "v1": (
            "Notice things on my own between turns — watch a camera you "
            "left open, check a feed you named — only within the grants "
            "you made, and always written to the activity log."
        ),
    },
    "auto.capture_on_intent": {
        "v1": (
            "Take a screenshot when I think it would help me understand "
            "what you are asking about. Off by default; it only turns on "
            "individually."
        ),
    },
    "auto.capture_on_error": {
        "v1": (
            "Capture my own state when something errors, so I can show "
            "you what went wrong."
        ),
    },
    "auto.speak": {
        "v1": (
            "Speak answers aloud without you pressing a key."
        ),
    },
    "auto.act": {
        "v1": (
            "Take actions on my own, with no turn you started. No profile "
            "grants this. It exists in the list so that its absence is a "
            "rule, not an oversight."
        ),
    },
    # -- profile review screens (D3-P4) ------------------------------
    # Not capabilities: these are the §3.2 Screen-5 review texts, the
    # words an owner reads before accepting a profile. A profile's
    # acceptance batch carries ONE digest — this text's — on every
    # record it writes ("each with text_shown_sha256 of the Screen-5
    # wording", §3.2 Screen 6), which is why they live in the one copy
    # module and ride the same manifest: a "profile:attentive" grant
    # resolves to the exact review screen the owner accepted.
    "profile:reserved.review": {
        "v1": (
            "Here is everything you're about to allow. I answer your "
            "questions, read this machine's own vitals, and read my own "
            "settings and history. I watch nothing, I listen to nothing, "
            "and nothing on this machine changes because of me: I never "
            "run commands, never read system configuration, and nothing I "
            "do leaves this machine. Silent capture is off and stays off. "
            "What you allow here is written to a record you can read and "
            "I cannot edit, with the date, the surface you granted it "
            "from, and a fingerprint of these exact words — and every "
            "part of it is revocable afterwards on one page."
        ),
    },
    "profile:attentive.review": {
        "v1": (
            "Here is everything you're about to allow. On my own, while "
            "you're away, I read this machine's system logs and hardware "
            "sensors continuously; I read the configuration under /etc "
            "and keep dated copies, so I can tell you what changed; and I "
            "run a nightly check and write you a morning summary. When "
            "you ask me to, I run a command in a terminal under your user "
            "account; change a configuration file after showing you the "
            "exact difference; take one picture of a display or a window "
            "with passwords and keys blanked out first; and hear you "
            "while you hold the talk button. I always stop and ask first "
            "for anything rated high risk — with the exact command "
            "shown, not a summary of it; for anything needing your "
            "administrator password, and I ask for it again every single "
            "time; and for any change to a file the system owns. Never, "
            "under this setup: I do not watch your screen or listen to "
            "the room when you haven't asked; I do not turn on the "
            "camera; I do not learn or match anyone's voice; I do not "
            "send anything you say, see or store off this machine; I do "
            "not do something risky on my own, even if I'm certain; and I "
            "do not read your mail, messages, photos, keys, keychains, "
            "browser profiles or password store. Silent capture is off "
            "and stays off. What you allow here is written to a record "
            "you can read and I cannot edit, with the date, the surface "
            "you granted it from, and a fingerprint of these exact words "
            "— and every part of it is revocable afterwards on one page."
        ),
    },
    "profile:present.review": {
        "v1": (
            "Here is everything you're about to allow. Everything in the "
            "previous setup, plus the room: I keep the microphone open "
            "and listen for my name; I keep an eye on the screen and the "
            "cameras you've set up, continuously and by name; I can act "
            "on the house through Home Assistant at the tiers you "
            "expose; I speak answers aloud without you pressing a key; "
            "and I reach other machines on your local network when you "
            "approve it each time. Privileged actions still ask for your "
            "administrator password again every single time, with no "
            "exception and no way to turn that off. The cost is the one "
            "on the card: the privacy of this room, for you and for "
            "everyone else in it — other people, guests, anyone who "
            "walks in, can be recorded. Choose it deliberately. Nothing "
            "I hold ever leaves this machine, I never learn or match "
            "anyone's voice, and silent capture is off and stays off. "
            "What you allow here is written to a record you can read and "
            "I cannot edit, with the date, the surface you granted it "
            "from, and a fingerprint of these exact words — and every "
            "part of it is revocable afterwards on one page."
        ),
    },
}


def copy_for(capability: str, version: str = CURRENT_VERSION) -> str:
    """The exact wording a ``text_shown_sha256`` resolves to (fail-closed).

    An unknown capability or a version that was never shipped raises
    ``KeyError``: an evidence field that quietly resolves to the *wrong*
    words is worse than one that resolves to nothing.
    """
    return COPY[capability][version]


def digest_for(capability: str, version: str = CURRENT_VERSION) -> str:
    """The SHA-256 of the exact wording — the value a record's
    ``text_shown_sha256`` carries."""
    return hashlib.sha256(copy_for(capability, version).encode("utf-8")).hexdigest()


def available_versions(capability: str) -> Tuple[str, ...]:
    """Every copy version shipped for a capability, oldest first."""
    return tuple(sorted(COPY[capability]))


#: The review-screen copy keys, one per shipped profile (D3-P4). The
#: key space is closed alongside the three profile names; the manifest
#: test cross-checks it against the profiles registry.
PROFILE_REVIEW_KEYS: Tuple[str, ...] = (
    "profile:reserved.review",
    "profile:attentive.review",
    "profile:present.review",
)

#: The prefix that marks a copy key as a profile review screen rather
#: than a capability row.
PROFILE_REVIEW_PREFIX = "profile:"


def review_copy_key(profile_name: str) -> str:
    """The copy key for one profile's review screen."""
    return f"{PROFILE_REVIEW_PREFIX}{profile_name}.review"


def review_copy_for(profile_name: str, version: str = CURRENT_VERSION) -> str:
    """The exact review-screen wording an acceptance of this profile
    hashes into every record it writes (§3.2 Screen 6)."""
    return copy_for(review_copy_key(profile_name), version)


def review_digest_for(profile_name: str, version: str = CURRENT_VERSION) -> str:
    """The SHA-256 of the review-screen wording — the
    ``text_shown_sha256`` a profile acceptance batch carries."""
    return digest_for(review_copy_key(profile_name), version)


def copy_manifest_path() -> Path:
    """The committed manifest beside this module."""
    return Path(__file__).with_name("copy_manifest.json")


def manifest_data() -> Dict[str, Dict[str, str]]:
    """The manifest as data: capability → copy key → digest, for exactly
    the consenting vocabulary — the module cannot drift from the
    vocabulary it serves."""
    return {
        capability: {version: digest_for(capability, version)
                     for version in versions}
        for capability, versions in sorted(COPY.items())
    }


def write_manifest(path: Path = None) -> Path:
    """Regenerate the committed manifest from this module.

    The module is the source of truth; the manifest is the committed
    evidence; ``tests/test_consent_copy_manifest.py`` is the ratchet that
    fails when the two drift. Run after any copy change:
    ``python -c "from halbert_core.consent.copy import write_manifest; write_manifest()"``
    """
    target = path or copy_manifest_path()
    target.write_text(
        json.dumps(manifest_data(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _self_check() -> None:
    """Import-time invariant: every consenting capability in the shipped
    vocabulary has at least one version of copy here. A vocabulary id
    added without copy fails at import — a consent record for it could
    never carry resolvable evidence."""
    missing = sorted(
        cap for cap in VOCABULARY
        if takes_consent_records(cap) and cap not in COPY
    )
    if missing:
        raise ValueError(
            f"consent copy missing for {missing}: every consenting "
            f"capability must have resolvable wording (Gate 4)"
        )


_self_check()