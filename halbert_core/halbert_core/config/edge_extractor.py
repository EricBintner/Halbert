"""
Config Dependency Edge Extractor (Phase 3)

Extracts dependency edges from parsed config files and pushes them to
SourcePrep's trace graph via the external-edges API endpoint.

Edge types extracted:
  - systemd unit dependencies (Requires, Wants, After, Before, ExecStart, EnvironmentFile, ...)
  - Include directives (nginx, apache, generic include/.include)
  - fstab -> mount unit correspondence
  - File-reference co-occurrence (absolute paths in config content)
  - Drop-in directory semantics (.d/ directories)

Works from Halbert's config snapshot system (canonical JSON in data/config/canon/).
No file content is sent to SourcePrep — only edge relationships.
"""
from __future__ import annotations

import fnmatch
import glob
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .snapshot import CANON_DIR
from ..utils.paths import data_subdir

logger = logging.getLogger(__name__)

SYSTEMD_PATHS = [
    "/etc/systemd/system/",
    "/lib/systemd/system/",
    "/usr/lib/systemd/system/",
    "/run/systemd/system/",
]

SYSTEMD_DEPENDENCY_DIRECTIVES: Dict[str, str] = {
    "Requires": "requires",
    "Wants": "wants",
    "After": "after",
    "Before": "before",
    "RequiresMountsFor": "requires_mount",
    "BindsTo": "binds_to",
    "PartOf": "part_of",
    "Requisite": "requisite",
}

SYSTEMD_FILE_DIRECTIVES: Dict[str, str] = {
    "EnvironmentFile": "configures",
    "PIDFile": "references",
    "WorkingDirectory": "references",
    "ExecStart": "executes",
    "ExecStartPre": "executes",
    "ExecStartPost": "executes",
    "ExecStop": "executes",
    "ExecStopPost": "executes",
    "ExecReload": "executes",
    "BindPaths": "references",
    "ReadWritePaths": "references",
    "ReadOnlyPaths": "references",
    "ReadWriteOnly": "references",
    "StateDirectory": "references",
    "CacheDirectory": "references",
    "LogsDirectory": "references",
    "ConfigurationDirectory": "references",
    "RuntimeDirectory": "references",
}

INCLUDE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*include\s+(\S+);", re.IGNORECASE), "nginx"),
    (re.compile(r"^\s*Include\s+(\S+)", re.IGNORECASE), "apache"),
    (re.compile(r"^\s*\.include\s+(\S+)", re.IGNORECASE), "generic"),
    (re.compile(r"^\s*@include\s+(\S+)", re.IGNORECASE), "sudoers"),
    (re.compile(r"^\s*include\s+(\S+)", re.IGNORECASE), "generic"),
]

ABS_PATH_RE = re.compile(r"(?<![\w/])/[a-zA-Z0-9_][a-zA-Z0-9_/.@-]+")

FSTAB_PATH = "/etc/fstab"


@dataclass
class ConfigEdge:
    source: str
    target: str
    kind: str
    origin: str = "config"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "origin": self.origin,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d


def _file_node_id(path: str) -> str:
    return f"file:{path}"


def _resolve_unit_path(unit_name: str, known_paths: Optional[set] = None) -> Optional[str]:
    if known_paths:
        for base in SYSTEMD_PATHS:
            path = f"{base}{unit_name}"
            if path in known_paths:
                return path
        return None
    for base in SYSTEMD_PATHS:
        path = f"{base}{unit_name}"
        if os.path.exists(path):
            return path
    return None


def _load_canon_files() -> List[Dict[str, Any]]:
    canon_files: List[Dict[str, Any]] = []
    if not os.path.isdir(CANON_DIR):
        return canon_files
    for fname in os.listdir(CANON_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(CANON_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                canon_files.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return canon_files


def _known_config_paths(canon_files: List[Dict[str, Any]]) -> set:
    return {c["path"] for c in canon_files if "path" in c}


class ConfigEdgeExtractor:
    """Extract dependency edges from parsed config files.

    Reads canonical JSON from the config snapshot system (data/config/canon/).
    Produces edges in SourcePrep node ID format ready for the external-edges API.
    """

    def __init__(self, canon_dir: Optional[str] = None) -> None:
        self.canon_dir = canon_dir or CANON_DIR
        self._canon_files: List[Dict[str, Any]] = []
        self._known_paths: set = set()

    def _load(self) -> None:
        self._canon_files = []
        self._known_paths = set()
        if not os.path.isdir(self.canon_dir):
            return
        for fname in os.listdir(self.canon_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(self.canon_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    self._canon_files.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        self._known_paths = {c["path"] for c in self._canon_files if "path" in c}

    def extract_all(self) -> List[ConfigEdge]:
        self._load()
        edges: List[ConfigEdge] = []
        for canon in self._canon_files:
            path = canon.get("path", "")
            if not path:
                continue
            kind = canon.get("kind", "text")
            if kind == "ini":
                edges.extend(self._extract_systemd_edges(path, canon))
                edges.extend(self._extract_ini_file_refs(path, canon))
            edges.extend(self._extract_include_edges(path, canon))
            if path == FSTAB_PATH or path.endswith("fstab"):
                edges.extend(self._extract_fstab_edges(path, canon))
            edges.extend(self._extract_reference_edges(path, canon))
            edges.extend(self._extract_dropin_edges(path, canon))
        return self._dedup_edges(edges)

    def _extract_systemd_edges(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        sections = canon.get("sections", {})
        src_id = _file_node_id(path)

        is_systemd = path.endswith((".service", ".timer", ".socket", ".target", ".mount"))

        for section_name, items in sections.items():
            for key, value in items.items():
                value_str = str(value)

                if key in SYSTEMD_DEPENDENCY_DIRECTIVES:
                    edge_kind = SYSTEMD_DEPENDENCY_DIRECTIVES[key]
                    for unit_name in value_str.split():
                        unit_name = unit_name.strip()
                        if not unit_name:
                            continue
                        target_path = _resolve_unit_path(unit_name, self._known_paths)
                        if target_path and target_path in self._known_paths:
                            edges.append(ConfigEdge(
                                source=src_id,
                                target=_file_node_id(target_path),
                                kind=edge_kind,
                                metadata={
                                    "directive": key,
                                    "section": section_name,
                                    "unit": unit_name,
                                    "extractor": "systemd",
                                },
                            ))

                if key in SYSTEMD_FILE_DIRECTIVES:
                    edge_kind = SYSTEMD_FILE_DIRECTIVES[key]
                    parts = value_str.split()
                    for part in parts:
                        part = part.strip().strip("'\"")
                        if not part or not part.startswith("/"):
                            continue
                        if part.startswith("-"):
                            part = part[1:]
                        if part in self._known_paths:
                            edges.append(ConfigEdge(
                                source=src_id,
                                target=_file_node_id(part),
                                kind=edge_kind,
                                metadata={
                                    "directive": key,
                                    "section": section_name,
                                    "extractor": "systemd",
                                },
                            ))

        return edges

    def _extract_ini_file_refs(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        sections = canon.get("sections", {})
        src_id = _file_node_id(path)

        for section_name, items in sections.items():
            for key, value in items.items():
                value_str = str(value)
                if not value_str.startswith("/"):
                    continue
                ref_path = value_str.split()[0].strip("'\"")
                if ref_path in self._known_paths:
                    edges.append(ConfigEdge(
                        source=src_id,
                        target=_file_node_id(ref_path),
                        kind="references",
                        metadata={
                            "directive": key,
                            "section": section_name,
                            "extractor": "ini_file_ref",
                        },
                    ))

        return edges

    def _extract_include_edges(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        lines = canon.get("lines", [])
        src_id = _file_node_id(path)

        for line_obj in lines:
            line_text = line_obj.get("text", "")
            line_num = line_obj.get("n", 0)
            for pattern, source_type in INCLUDE_PATTERNS:
                m = pattern.match(line_text)
                if m:
                    inc_path = m.group(1).strip("'\"")
                    if "*" in inc_path or "?" in inc_path:
                        matched = glob.glob(inc_path)
                        for mp in matched:
                            if mp in self._known_paths:
                                edges.append(ConfigEdge(
                                    source=src_id,
                                    target=_file_node_id(mp),
                                    kind="includes",
                                    metadata={
                                        "line": line_num,
                                        "pattern": inc_path,
                                        "source_type": source_type,
                                        "extractor": "include",
                                    },
                                ))
                        for kp in self._known_paths:
                            if fnmatch.fnmatch(kp, inc_path) and kp not in matched:
                                edges.append(ConfigEdge(
                                    source=src_id,
                                    target=_file_node_id(kp),
                                    kind="includes",
                                    metadata={
                                        "line": line_num,
                                        "pattern": inc_path,
                                        "source_type": source_type,
                                        "extractor": "include",
                                    },
                                ))
                    elif inc_path in self._known_paths:
                        edges.append(ConfigEdge(
                            source=src_id,
                            target=_file_node_id(inc_path),
                            kind="includes",
                            metadata={
                                "line": line_num,
                                "source_type": source_type,
                                "extractor": "include",
                            },
                        ))
                    break

        return edges

    def _extract_fstab_edges(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        lines = canon.get("lines", [])
        src_id = _file_node_id(path)

        for line_obj in lines:
            line_text = line_obj.get("text", "").strip()
            if not line_text or line_text.startswith("#"):
                continue
            parts = line_text.split()
            if len(parts) < 2:
                continue
            device = parts[0]
            mount_point = parts[1]

            mount_unit_name = self._mount_point_to_unit(mount_point)
            if mount_unit_name:
                target_path = _resolve_unit_path(mount_unit_name, self._known_paths)
                if target_path and target_path in self._known_paths:
                    edges.append(ConfigEdge(
                        source=src_id,
                        target=_file_node_id(target_path),
                        kind="corresponds_to",
                        metadata={
                            "mount_point": mount_point,
                            "device": device,
                            "unit": mount_unit_name,
                            "extractor": "fstab",
                        },
                    ))

        return edges

    @staticmethod
    def _mount_point_to_unit(mount_point: str) -> str:
        if mount_point == "/":
            return "-.mount"
        encoded = mount_point.lstrip("/").replace("/", "-")
        return f"{encoded}.mount"

    def _extract_reference_edges(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        lines = canon.get("lines", [])
        src_id = _file_node_id(path)

        for line_obj in lines:
            line_text = line_obj.get("text", "")
            line_num = line_obj.get("n", 0)
            for m in ABS_PATH_RE.finditer(line_text):
                ref_path = m.group(0).rstrip(".,;")
                if ref_path == path:
                    continue
                if ref_path in self._known_paths:
                    edges.append(ConfigEdge(
                        source=src_id,
                        target=_file_node_id(ref_path),
                        kind="references",
                        metadata={
                            "line": line_num,
                            "extractor": "file_reference",
                        },
                    ))

        return edges

    def _extract_dropin_edges(
        self, path: str, canon: Dict[str, Any]
    ) -> List[ConfigEdge]:
        edges: List[ConfigEdge] = []
        src_id = _file_node_id(path)

        dropin_dir = f"{path}.d"
        if not os.path.isdir(dropin_dir):
            return edges

        for fname in os.listdir(dropin_dir):
            fpath = os.path.join(dropin_dir, fname)
            if os.path.isfile(fpath) and fpath in self._known_paths:
                edges.append(ConfigEdge(
                    source=src_id,
                    target=_file_node_id(fpath),
                    kind="includes",
                    metadata={
                        "extractor": "dropin",
                        "dropin_dir": dropin_dir,
                    },
                ))

        return edges

    @staticmethod
    def _dedup_edges(edges: List[ConfigEdge]) -> List[ConfigEdge]:
        seen: set = set()
        result: List[ConfigEdge] = []
        for e in edges:
            key = (e.source, e.target, e.kind)
            if key in seen:
                continue
            seen.add(key)
            result.append(e)
        return result

    def to_sourceprep_format(self, edges: List[ConfigEdge]) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in edges]

    def sync(self, client: Any) -> Dict[str, Any]:
        edges = self.extract_all()
        edge_dicts = self.to_sourceprep_format(edges)
        if not edge_dicts:
            logger.info("ConfigEdgeExtractor: no edges extracted")
            return {"accepted": 0, "extracted": 0}
        result = client.push_external_edges(edge_dicts, replace_origin="config")
        result["extracted"] = len(edge_dicts)
        return result
