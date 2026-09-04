# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from __future__ import annotations
import fnmatch
import os
import yaml
from typing import Dict, List

"""
Manifest loader for config registry.
YAML schema documented in docs/Phase1/config-registry.md
"""

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
        # Simple globbing across include globs; exclude patterns take precedence
        results: List[str] = []
        for root in sorted({self.walk_root(p) for p in self.include}):
            for dirpath, dirnames, filenames in os.walk(root):
                rel = dirpath
                for f in filenames:
                    full = os.path.join(dirpath, f)
                    if any(fnmatch.fnmatch(full, pat) for pat in self.include):
                        if any(fnmatch.fnmatch(full, pat) for pat in self.exclude):
                            continue
                        results.append(full)
        return sorted(set(results))
