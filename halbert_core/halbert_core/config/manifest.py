# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import os
import re
from pathlib import Path
import yaml
from typing import Dict, List

"""
Manifest loader for config registry.
YAML schema documented in docs/Phase1/config-registry.md
"""

def _segment_regex(segment: str) -> str:
    """One path segment's glob, as a regex that cannot cross a separator."""
    out, i, n = [], 0, len(segment)
    while i < n:
        c = segment[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1
            if j < n and segment[j] in "!^":
                j += 1
            if j < n and segment[j] == "]":
                j += 1
            while j < n and segment[j] != "]":
                j += 1
            if j >= n:
                out.append(r"\[")  # unterminated class: a literal bracket
            else:
                body = segment[i + 1 : j].replace("\\", r"\\")
                if body[:1] in ("!", "^"):
                    body = "^" + body[1:]
                out.append("[" + body + "]")
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _compile(pattern: str) -> "re.Pattern[str]":
    """A manifest glob, with the semantics an operator writing one expects.

    ``fnmatch`` is the obvious tool here and it is the wrong one: its ``*``
    matches ``/``. Over an already-recursive ``os.walk`` that turns every
    include into a recursive one, so ``/etc/*.conf`` -- written to mean the
    handful of files directly in ``/etc`` -- reaches every ``.conf`` at any
    depth. On this machine that was 95 files rather than 14, among them
    ``/etc/racoon/racoon.conf``: the registry's own ``exclude`` list names
    racoon, so the over-match landed on precisely the file its author had
    tried to keep out. An allowlist that admits files nobody listed is not an
    allowlist.

    The same bug ran the other way. ``fnmatch`` requires a literal ``/`` after
    ``**``, so the Linux registry's broadest include, ``/etc/**/*.conf``,
    could not match ``/etc/resolv.conf`` or ``/etc/pf.conf`` at all -- the
    "structurally cannot match" note in ``config/scopes/storage.yml``.

    So: ``*`` and ``?`` stay inside one segment, ``**`` spans zero or more of
    them. A leading ``**`` also has to be able to eat the leading ``/``, since
    the paths it is matched against are absolute.
    """
    segments = pattern.split("/")
    out = []
    for i, segment in enumerate(segments):
        last = i == len(segments) - 1
        if segment == "**":
            if last:
                out.append(".*")
            elif i == 0:
                out.append("(?:.*/)?")
            else:
                out.append("(?:[^/]+/)*")
            continue
        out.append(_segment_regex(segment))
        if not last:
            out.append("/")
    return re.compile("(?s:" + "".join(out) + r")\Z")


_COMPILED: Dict[str, "re.Pattern[str]"] = {}


def path_matches(path: str, pattern: str) -> bool:
    """True when ``path`` is one of the files ``pattern`` names."""
    compiled = _COMPILED.get(pattern)
    if compiled is None:
        compiled = _COMPILED[pattern] = _compile(pattern)
    return compiled.match(path) is not None


class Manifest:
    def __init__(self, include: List[str], exclude: List[str], parsers: Dict[str, List[str]]):
        self.include = include
        self.exclude = exclude
        self.parsers = parsers

    @classmethod
    def from_file(cls, path: str) -> "Manifest":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Role manifests reference per-user paths (~/Library/LaunchAgents,
        # ~/.zshrc). Neither os.path.dirname nor os.walk expands ~, so an
        # unexpanded pattern silently matches nothing.
        include = [os.path.expanduser(p) for p in data.get("include", [])]
        exclude = [os.path.expanduser(p) for p in data.get("exclude", [])]
        parsers = data.get("parsers", {})
        return cls(include, exclude, parsers)

    @staticmethod
    def walk_root(pattern: str) -> str:
        """The deepest real directory a glob can live under.

        ``os.path.dirname`` is the wrong tool: for ``/etc/**/*.conf`` it
        returns the literal ``/etc/**``, which is never a directory, so
        ``os.walk`` yields nothing and the pattern silently matches no files.
        That is not a macOS quirk -- it kills the broadest include in the
        shipped Linux manifest, and the codebase already noticed the symptom
        (``config/scopes/storage.yml`` records that the flat host scope's
        ``/etc/**/*.conf`` "structurally cannot match" what it should).

        Truncating at the first glob metacharacter instead gives ``/etc``,
        which walks. A pattern with no metacharacter keeps its own dirname.
        """
        # Expanded defensively: from_file already does this, but a caller
        # passing a raw manifest line would otherwise get "~" as a root.
        pattern = os.path.expanduser(pattern)
        head = pattern
        for i, ch in enumerate(pattern):
            if ch in "*?[":
                head = pattern[:i]
                break
        else:
            return os.path.dirname(pattern) or "."
        root = os.path.dirname(head) if not head.endswith(os.sep) else head
        return root.rstrip(os.sep) or "/"

    def iter_paths(self) -> List[str]:
        """Every file the registry names, excludes applied.

        Matching is ``path_matches``, not ``fnmatch``: see its docstring for
        why the difference is the whole security property of this list.
        """
        results: List[str] = []
        for root in sorted({self.walk_root(p) for p in self.include}):
            for dirpath, _dirnames, filenames in os.walk(root):
                for f in filenames:
                    full = os.path.join(dirpath, f)
                    if any(path_matches(full, pat) for pat in self.include):
                        if any(path_matches(full, pat) for pat in self.exclude):
                            continue
                        results.append(full)
        return sorted(set(results))


def find_registry():
    """The config registry for THIS body, or None.

    One function, used by both the loader that opens the file and the
    capability probe that asks whether there is one. They used to be two
    functions searching different places, so on a repo checkout the probe
    said "nothing to watch" while the manifest sat where the loader would
    have opened it -- and the watcher stayed off with everything in place.

    Searched in order:

    1. the config directory -- an operator's own list beats the packaged one;
    2. ``/etc/halbert`` -- a system install;
    3. this package's own ``config/`` -- the shipped default.

    **Never the current working directory.** A registry is a list of files to
    read on a schedule; picking one up because a process happened to start
    next to it is not a decision anybody made.

    A platform-specific name wins where one exists: the generic registry globs
    ``/etc/systemd/*.service``, which on a Mac watches nothing at all.
    """
    from ..utils.platform import get_config_dir, is_macos

    names = ["config-registry.macos.yml"] if is_macos() else []
    names.append("config-registry.yml")

    roots = [Path(get_config_dir()), Path("/etc/halbert")]
    for parent in Path(__file__).resolve().parents:
        roots.append(parent / "config")

    for name in names:
        for root in roots:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None
