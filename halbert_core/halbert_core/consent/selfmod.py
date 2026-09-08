# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Class-1 fence — what the agent may never write, by path.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §6.1/§6.2/§6.3:

    It may not change what it is permitted to do, what it is told to be,
    or the record of either. It may propose any of those, and apply none.

    Class 1 — Governing artefacts. Never writable by the agent, at any
    autonomy level, with no override, no confirmation dialog, no escape
    hatch.

    A policy that says "the agent must not edit policy.yml" is stored in
    policy.yml. So this is enforced by path, by filesystem, by chain
    and by lint — never by policy.

This module is layer 1 (compiled path denial): ``GOVERNED_PATHS`` is a
**function of the resolved config and data dirs** — never a literal,
never CWD-relative — and ``is_governed_path``/``assert_not_governed``
run on the **resolved path the handler will actually open**, obtained
once, as one string, and used for both the check and the open (the F16
lesson: a raw argument while the handler expands ``~`` is how
``write_file(path="~/.ssh/authorized_keys")`` walked past the gate).

The wiring that refuses is D3-P5's (review-gated): ``write_config``,
``_write_file``, ``routes/editor.py``, the recovery rollback, the
privileged helper, and the PTY's ledger watcher all call
``assert_not_governed`` and refuse. Nothing in this module writes,
reads, or gates anything by itself — it is the list, the resolution
rule, and the refusal exception.

The remaining Class-1 rows of §6.2 — signing keys and the keystore, the
install prefix, the privileged-helper allowlist and its polkit/systemd
files — are governed where they resolve on each platform; rows whose
location a later packet fixes (the keystore's custody ladder) join this
table when they gain a filesystem address, never by loosening it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

__all__ = [
    "GOVERNED_PATHS",
    "GovernedPathError",
    "assert_not_governed",
    "governed_roots",
    "is_governed_path",
]


class GovernedPathError(RuntimeError):
    """A write primitive was pointed at a Class-1 governing artefact.

    Never catchable into a confirmation: Class 1 has no override, no
    dialog, no escape hatch — the caller refuses, and the attempt is
    surfaced.
    """

    def __init__(self, path: str, governed_root: str) -> None:
        self.path = path
        self.governed_root = governed_root
        super().__init__(
            f"'{path}' resolves inside the governed set (under "
            f"'{governed_root}'): governing artefacts are never writable "
            f"by the agent, at any autonomy level, with no override."
        )


def governed_roots(
    *,
    config_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> Tuple[str, ...]:
    """The Class-1 roots, resolved against the dirs this machine runs on.

    Each entry is ``realpath``-resolved (symlinks and ``~`` included),
    absolute, and boundary-safe: a target matches a root either exactly
    or one-or-more directories *inside* it, never by string prefix.
    """
    if config_dir is None or data_dir is None or log_dir is None:
        from ..utils.paths import config_dir as _default_config_dir
        from ..utils.paths import data_dir as _default_data_dir
        from ..utils.paths import log_dir as _default_log_dir
        config_dir = config_dir or _default_config_dir()
        data_dir = data_dir or _default_data_dir()
        log_dir = log_dir or _default_log_dir()

    home = Path.home()
    raw = (
        # The consent ledger, its projection, and the halt state — the
        # record of what the machine is permitted to do (§1.5, §4.1).
        os.path.join(str(data_dir), "consent"),
        os.path.join(str(config_dir), "consent-state.json"),
        os.path.join(str(data_dir), "runtime", "halt.json"),
        # The audit log (the record of what was done).
        os.path.join(str(log_dir), "audit"),
        # Persona, autonomy, and the surviving legacy policy file — what
        # the machine is told to be and how much rope it holds.
        os.path.join(str(config_dir), "being.yml"),
        os.path.join(str(config_dir), "autonomy.yml"),
        os.path.join(str(config_dir), "policy.yml"),
        # Standing directives: the skills and lenses directories (§6.4 —
        # a dropped file must be a notification, never a takeover).
        os.path.join(str(config_dir), "skills"),
        os.path.join(str(config_dir), "lenses"),
        # Persistence locations (§6.2's list, verbatim where they resolve).
        str(home / "Library" / "LaunchAgents"),
        str(home / "Library" / "LaunchDaemons"),
        "/Library/LaunchDaemons",
        str(home / ".config" / "systemd" / "user"),
        str(home / ".config" / "autostart"),
    )
    # Resolve every root the way a write primitive resolves its target,
    # so the governed side of the comparison is the same kind of string
    # as the target — never a lexical guess.
    resolved = []
    for entry in raw:
        try:
            resolved.append(_resolve(entry))
        except OSError:  # pragma: no cover - unresolvable home on odd hosts
            resolved.append(os.path.abspath(os.path.expanduser(entry)))
    return tuple(sorted(set(resolved)))


def GOVERNED_PATHS(
    *,
    config_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> Tuple[str, ...]:
    """The Class-1 governing artefacts for this machine (§6.2).

    A **function** of the resolved config and data dirs — never a
    literal, never CWD-relative — so the governed set follows the
    machine it runs on and cannot drift when the config dir moves.
    """
    return governed_roots(
        config_dir=config_dir, data_dir=data_dir, log_dir=log_dir
    )


def _resolve(path: str) -> str:
    """Resolve once, the way the handler will: ``~`` expanded, symlinks
    followed, one absolute string, used for both check and open (F16)."""
    return os.path.realpath(os.path.expanduser(str(path)))


def is_governed_path(
    path,
    *,
    config_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> bool:
    """Does this path resolve inside the Class-1 set? Fail-closed on
    shape: a non-string is governed rather than crashed on — a refusal
    the caller can explain beats a TypeError they might catch."""
    try:
        resolved = _resolve(path)
    except (TypeError, ValueError):
        return True
    for root in governed_roots(
        config_dir=config_dir, data_dir=data_dir, log_dir=log_dir
    ):
        if resolved == root or resolved.startswith(root + os.sep):
            return True
    return False


def assert_not_governed(
    path,
    *,
    config_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    log_dir: Optional[str] = None,
) -> str:
    """Resolve once, refuse if governed, and return the resolved path.

    This is the call every write primitive makes (D3-P5 wiring):

        resolved = assert_not_governed(raw_argument)
        open(resolved, ...)          # the same string, checked and opened

    The resolution is obtained **once** — the F16 shape — so the path
    that is checked and the path that is opened cannot differ.
    """
    resolved = _resolve(path)
    for root in governed_roots(
        config_dir=config_dir, data_dir=data_dir, log_dir=log_dir
    ):
        if resolved == root or resolved.startswith(root + os.sep):
            raise GovernedPathError(resolved, root)
    return resolved