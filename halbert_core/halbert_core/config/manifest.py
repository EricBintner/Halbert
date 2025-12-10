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
        include = data.get("include", [])
        exclude = data.get("exclude", [])
        parsers = data.get("parsers", {})
        return cls(include, exclude, parsers)

    def iter_paths(self) -> List[str]:
        # Simple globbing across include globs; exclude patterns take precedence
        results: List[str] = []
        for root in set(os.path.dirname(p) or "." for p in self.include):
            for dirpath, dirnames, filenames in os.walk(root):
                rel = dirpath
                for f in filenames:
                    full = os.path.join(dirpath, f)
                    if any(fnmatch.fnmatch(full, pat) for pat in self.include):
                        if any(fnmatch.fnmatch(full, pat) for pat in self.exclude):
                            continue
                        results.append(full)
        return sorted(set(results))
