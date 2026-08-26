# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Corpus licensing policy engine.

Decides, per distribution channel, which slices of the RAG corpus may ship —
and proves it against a real build tree.

Three inputs:

* ``config/licensing.yml``   — licence terms + per-channel policy (the rules)
* ``data/manifest.json``     — per-source licence tags and paths (the facts)
* a corpus tree              — what a build is actually about to package

Two questions it answers:

* **Planning**: ``evaluate(channel)`` → which source paths are includable, and
  why each excluded one was excluded.
* **Enforcement**: ``audit_tree(root, channel)`` → does this tree contain
  anything that must not ship? Path-level *and* record-level, because some
  JSONL files historically mixed licences inside a single file.

Why record-level matters: ``data/macos/support/macos_support.jsonl`` used to
hold 87 CC BY-NC 4.0 SS64 pages next to 17 Halbert-authored guides. A path
allowlist alone would have shipped the lot. See LEG-CRIT-01.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml

logger = logging.getLogger("halbert.corpus.license")


# Ordering used to compare a channel's `max_copyleft` against a licence.
COPYLEFT_RANK = {"none": 0, "weak": 1, "strong": 2}

# Record fields searched, in order, for a per-record SPDX tag.
_RECORD_LICENSE_KEYS = ("license_spdx", "license")


class LicenseViolation(Exception):
    """Raised when a corpus tree contains content a channel may not ship."""

    def __init__(self, channel: str, violations: Sequence["Violation"]):
        self.channel = channel
        self.violations = list(violations)
        detail = "\n".join(f"  - {v}" for v in self.violations[:20])
        more = "" if len(self.violations) <= 20 else f"\n  ... and {len(self.violations) - 20} more"
        super().__init__(
            f"{len(self.violations)} licence violation(s) for channel '{channel}':\n{detail}{more}"
        )


@dataclass(frozen=True)
class LicenseTerms:
    """Machine-readable terms for one licence."""

    spdx: str
    name: str = ""
    commercial_use: str = "allowed"      # allowed | prohibited
    copyleft: str = "none"               # none | weak | strong
    share_alike: bool = False
    attribution: bool = True
    drm_conflict: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, spdx: str, data: Dict[str, Any]) -> "LicenseTerms":
        return cls(
            spdx=spdx,
            name=data.get("name", spdx),
            commercial_use=data.get("commercial_use", "allowed"),
            copyleft=data.get("copyleft", "none"),
            share_alike=bool(data.get("share_alike", False)),
            attribution=bool(data.get("attribution", True)),
            drm_conflict=bool(data.get("drm_conflict", False)),
            notes=(data.get("notes") or "").strip(),
        )

    @property
    def copyleft_rank(self) -> int:
        return COPYLEFT_RANK.get(self.copyleft, 2)


@dataclass(frozen=True)
class Channel:
    """A distribution channel and the licence terms it can carry."""

    name: str
    description: str = ""
    commercial: bool = False
    drm: bool = False
    data_roots: Sequence[str] = field(default_factory=tuple)
    require_commercial_use: str = "any"   # any | allowed
    max_copyleft: str = "strong"
    allow_drm_conflict: bool = True
    deny_paths: Sequence[str] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "Channel":
        require = data.get("require", {}) or {}
        return cls(
            name=name,
            description=data.get("description", ""),
            commercial=bool(data.get("commercial", False)),
            drm=bool(data.get("drm", False)),
            data_roots=tuple(data.get("data_roots", ())),
            require_commercial_use=require.get("commercial_use", "any"),
            max_copyleft=require.get("max_copyleft", "strong"),
            allow_drm_conflict=bool(require.get("allow_drm_conflict", True)),
            deny_paths=tuple(data.get("deny_paths", ())),
        )

    @property
    def max_copyleft_rank(self) -> int:
        return COPYLEFT_RANK.get(self.max_copyleft, 2)


@dataclass
class SourceDecision:
    """Why one manifest source path is in or out for a channel."""

    source: str
    path: str
    included: bool
    license_spdx: str
    reasons: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        verdict = "INCLUDE" if self.included else "EXCLUDE"
        why = "; ".join(self.reasons) if self.reasons else "policy satisfied"
        return f"[{verdict}] {self.path} ({self.source}, {self.license_spdx}): {why}"


@dataclass
class Violation:
    """Something present in a build tree that the channel may not ship."""

    path: str
    kind: str                 # denied_path | platform_root | license | quarantined_record | untagged
    detail: str
    source: str = ""
    license_spdx: str = ""
    record_id: str = ""
    line_no: int = 0

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line_no}" if self.line_no else self.path
        rec = f" record={self.record_id}" if self.record_id else ""
        return f"{loc} [{self.kind}]{rec} {self.detail}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "detail": self.detail,
            "source": self.source,
            "license_spdx": self.license_spdx,
            "record_id": self.record_id,
            "line_no": self.line_no,
        }


@dataclass
class PolicyReport:
    """Result of planning a channel's corpus."""

    channel: str
    decisions: List[SourceDecision] = field(default_factory=list)
    advisories: List[str] = field(default_factory=list)

    @property
    def included(self) -> List[SourceDecision]:
        return [d for d in self.decisions if d.included]

    @property
    def excluded(self) -> List[SourceDecision]:
        return [d for d in self.decisions if not d.included]

    @property
    def included_paths(self) -> List[str]:
        return [d.path for d in self.included]

    @property
    def excluded_paths(self) -> List[str]:
        return [d.path for d in self.excluded]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "included": [
                {"source": d.source, "path": d.path, "license_spdx": d.license_spdx}
                for d in self.included
            ],
            "excluded": [
                {
                    "source": d.source,
                    "path": d.path,
                    "license_spdx": d.license_spdx,
                    "reasons": d.reasons,
                }
                for d in self.excluded
            ],
            "advisories": self.advisories,
        }


def _normalize_path(p: str) -> str:
    """`data/macos/support/` -> `macos/support/`, always trailing-slashed dirs."""
    p = str(p).strip().replace("\\", "/").lstrip("./")
    if p.startswith("data/"):
        p = p[len("data/"):]
    return p


def _dig(record: Dict[str, Any], dotted: str) -> Any:
    """Fetch `metadata.command` style keys out of a record."""
    node: Any = record
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


class LicensePolicy:
    """Loads the policy + manifest and answers include/exclude questions."""

    def __init__(
        self,
        policy: Dict[str, Any],
        manifest: Dict[str, Any],
        repo_root: Optional[Path] = None,
    ):
        self.repo_root = Path(repo_root) if repo_root else None
        self._raw_policy = policy
        self.manifest = manifest
        self.licenses: Dict[str, LicenseTerms] = {
            spdx: LicenseTerms.from_dict(spdx, data)
            for spdx, data in (policy.get("licenses") or {}).items()
        }
        self.channels: Dict[str, Channel] = {
            name: Channel.from_dict(name, data)
            for name, data in (policy.get("channels") or {}).items()
        }
        self.record_quarantine: Dict[str, Dict[str, Any]] = policy.get("record_quarantine") or {}
        self.coverage_contracts: List[Dict[str, Any]] = policy.get("coverage_contracts") or []

    # ------------------------------------------------------------------ load

    @classmethod
    def load(
        cls,
        repo_root: Optional[Path] = None,
        policy_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ) -> "LicensePolicy":
        root = Path(repo_root) if repo_root else find_repo_root()
        policy_path = Path(policy_path) if policy_path else root / "config" / "licensing.yml"
        manifest_path = Path(manifest_path) if manifest_path else root / "data" / "manifest.json"

        if not policy_path.exists():
            raise FileNotFoundError(f"Licensing policy not found: {policy_path}")
        if not manifest_path.exists():
            raise FileNotFoundError(f"Corpus manifest not found: {manifest_path}")

        with open(policy_path) as fh:
            policy = yaml.safe_load(fh) or {}
        with open(manifest_path) as fh:
            manifest = json.load(fh)

        return cls(policy=policy, manifest=manifest, repo_root=root)

    # -------------------------------------------------------------- lookups

    def channel(self, name: str) -> Channel:
        try:
            return self.channels[name]
        except KeyError:
            known = ", ".join(sorted(self.channels))
            raise KeyError(f"Unknown distribution channel '{name}'. Known: {known}") from None

    def terms(self, spdx: str) -> Optional[LicenseTerms]:
        return self.licenses.get(spdx)

    def source_for_path(self, path: str) -> Optional[str]:
        """Which manifest source owns this corpus path (longest prefix wins)."""
        norm = _normalize_path(path)
        best: Optional[str] = None
        best_len = -1
        for name, meta in (self.manifest.get("sources") or {}).items():
            for src_path in meta.get("paths", []):
                sp = _normalize_path(src_path)
                if norm == sp.rstrip("/") or norm.startswith(sp):
                    if len(sp) > best_len:
                        best, best_len = name, len(sp)
        return best

    def license_for_path(self, path: str) -> str:
        source = self.source_for_path(path)
        if not source:
            return ""
        return (self.manifest.get("sources", {}).get(source, {}) or {}).get("license_spdx", "")

    # ------------------------------------------------------------ evaluation

    def _license_reasons(self, channel: Channel, terms: Optional[LicenseTerms], spdx: str) -> List[str]:
        """Reasons this licence cannot ship through this channel ([] = it can)."""
        if terms is None:
            return [
                f"licence '{spdx or '(untagged)'}' is not in the licence registry "
                f"(config/licensing.yml) — classify it before shipping"
            ]

        reasons: List[str] = []
        if channel.require_commercial_use == "allowed" and terms.commercial_use != "allowed":
            reasons.append(
                f"{terms.spdx} forbids commercial use and '{channel.name}' is a commercial channel"
            )
        if terms.copyleft_rank > channel.max_copyleft_rank:
            reasons.append(
                f"{terms.spdx} is {terms.copyleft} copyleft; '{channel.name}' tolerates at most "
                f"{channel.max_copyleft}"
            )
        if terms.drm_conflict and not channel.allow_drm_conflict:
            reasons.append(
                f"{terms.spdx} forbids technical restrictions on redistribution and "
                f"'{channel.name}' ships behind DRM"
            )
        return reasons

    def evaluate(self, channel_name: str) -> PolicyReport:
        """Plan the corpus for a channel: what ships, what doesn't, and why."""
        channel = self.channel(channel_name)
        report = PolicyReport(channel=channel_name)
        roots = set(channel.data_roots)

        for source, meta in sorted((self.manifest.get("sources") or {}).items()):
            spdx = (meta or {}).get("license_spdx", "")
            terms = self.terms(spdx)
            license_reasons = self._license_reasons(channel, terms, spdx)

            for raw_path in (meta or {}).get("paths", []):
                path = _normalize_path(raw_path)
                reasons: List[str] = []

                denied = next((d for d in channel.deny_paths if path.startswith(_normalize_path(d))), None)
                if denied:
                    reasons.append(f"path is on '{channel.name}' deny list ({denied})")

                root = path.split("/", 1)[0]
                if root not in roots:
                    reasons.append(
                        f"data root '{root}' not shipped by '{channel.name}' "
                        f"(allowed: {', '.join(sorted(roots))})"
                    )

                reasons.extend(license_reasons)

                report.decisions.append(
                    SourceDecision(
                        source=source,
                        path=path,
                        included=not reasons,
                        license_spdx=spdx or "(untagged)",
                        reasons=reasons,
                    )
                )

            report.advisories.extend(self._source_advisories(channel, source, meta))

        return report

    def _source_advisories(self, channel: Channel, source: str, meta: Dict[str, Any]) -> List[str]:
        """Non-fatal inconsistencies worth a human's attention."""
        out: List[str] = []
        meta = meta or {}
        paths = [_normalize_path(p) for p in meta.get("paths", [])]
        roots = set(channel.data_roots)

        flag = "mac_build" if channel.name.startswith("macos") or channel.name == "oss-macos" else "linux_build"
        declared = meta.get(flag)
        contributes = any(p.split("/", 1)[0] in roots for p in paths)
        if declared is True and not contributes:
            out.append(
                f"{source}: manifest says {flag}=true but none of its paths live under "
                f"{sorted(roots)} — it contributes nothing to '{channel.name}'"
            )
        if declared is False and contributes:
            spdx = meta.get("license_spdx", "")
            if not self._license_reasons(channel, self.terms(spdx), spdx):
                out.append(
                    f"{source}: manifest says {flag}=false but its licence ({spdx or 'untagged'}) "
                    f"is acceptable for '{channel.name}' — exclusion is a product decision, not a legal one"
                )
        return out

    def included_paths(self, channel_name: str) -> List[str]:
        return self.evaluate(channel_name).included_paths

    def excluded_paths(self, channel_name: str) -> List[str]:
        return self.evaluate(channel_name).excluded_paths

    # ----------------------------------------------------------- enforcement

    def audit_tree(
        self,
        root: Path,
        channel_name: str,
        scan_records: bool = True,
        max_records_per_file: int = 0,
    ) -> List[Violation]:
        """Audit a real corpus tree about to be packaged for `channel_name`.

        `root` is the directory that will become `data/` inside the bundle.
        Returns every violation found (empty list == clean).
        """
        channel = self.channel(channel_name)
        root = Path(root)
        violations: List[Violation] = []

        if not root.exists():
            return violations

        allowed_roots = set(channel.data_roots)
        deny = [_normalize_path(d) for d in channel.deny_paths]

        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(root).as_posix()
            if rel.startswith(".") or "/." in rel:
                continue

            top = rel.split("/", 1)[0]
            hit = next((d for d in deny if rel.startswith(d)), None)
            if hit:
                violations.append(
                    Violation(
                        path=rel,
                        kind="denied_path",
                        detail=f"matches '{channel_name}' deny list entry '{hit}'",
                        source=self.source_for_path(rel) or "",
                        license_spdx=self.license_for_path(rel),
                    )
                )
                continue

            if top not in allowed_roots:
                violations.append(
                    Violation(
                        path=rel,
                        kind="platform_root",
                        detail=(
                            f"data root '{top}' is not shipped by '{channel_name}' "
                            f"(allowed: {', '.join(sorted(allowed_roots))})"
                        ),
                        source=self.source_for_path(rel) or "",
                        license_spdx=self.license_for_path(rel),
                    )
                )
                continue

            if file_path.suffix not in (".jsonl", ".json"):
                continue

            source = self.source_for_path(rel)
            if source:
                spdx = (self.manifest.get("sources", {}).get(source, {}) or {}).get("license_spdx", "")
                for reason in self._license_reasons(channel, self.terms(spdx), spdx):
                    violations.append(
                        Violation(
                            path=rel,
                            kind="license",
                            detail=reason,
                            source=source,
                            license_spdx=spdx or "(untagged)",
                        )
                    )

            if scan_records and file_path.suffix == ".jsonl":
                violations.extend(
                    self._audit_records(file_path, rel, channel, max_records_per_file)
                )

        return violations

    def _audit_records(
        self,
        file_path: Path,
        rel: str,
        channel: Channel,
        max_records: int = 0,
    ) -> List[Violation]:
        """Record-level scan: quarantined sources and per-record licence tags."""
        violations: List[Violation] = []
        seen_bad_source: set = set()
        seen_bad_license: set = set()

        try:
            handle = open(file_path, "r", encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file in a build tree
            logger.warning("Cannot read %s for licence audit: %s", rel, exc)
            return violations

        with handle:
            for line_no, line in enumerate(handle, start=1):
                if max_records and line_no > max_records:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue

                rec_source = record.get("source", "")
                quarantined = self.record_quarantine.get(rec_source)
                if quarantined and rec_source not in seen_bad_source:
                    spdx = quarantined.get("license_spdx", "")
                    reasons = self._license_reasons(channel, self.terms(spdx), spdx)
                    if reasons:
                        seen_bad_source.add(rec_source)
                        violations.append(
                            Violation(
                                path=rel,
                                kind="quarantined_record",
                                detail=(
                                    f"record source '{rec_source}' is quarantined ({spdx}): "
                                    f"{reasons[0]}. Canonical home: "
                                    f"data/{quarantined.get('canonical_path', '?')}"
                                ),
                                source=rec_source,
                                license_spdx=spdx,
                                record_id=str(record.get("id", "")),
                                line_no=line_no,
                            )
                        )

                spdx = ""
                for key in _RECORD_LICENSE_KEYS:
                    value = record.get(key) or (record.get("metadata") or {}).get(key)
                    if value:
                        spdx = str(value)
                        break
                if spdx and spdx not in seen_bad_license:
                    reasons = self._license_reasons(channel, self.terms(spdx), spdx)
                    if reasons:
                        seen_bad_license.add(spdx)
                        violations.append(
                            Violation(
                                path=rel,
                                kind="license",
                                detail=f"record-level licence tag: {reasons[0]}",
                                source=rec_source,
                                license_spdx=spdx,
                                record_id=str(record.get("id", "")),
                                line_no=line_no,
                            )
                        )

        return violations

    def assert_tree_clean(self, root: Path, channel_name: str, **kwargs) -> None:
        """audit_tree(), but raise LicenseViolation instead of returning."""
        violations = self.audit_tree(root, channel_name, **kwargs)
        if violations:
            raise LicenseViolation(channel_name, violations)

    # ------------------------------------------------- replacement coverage

    def coverage_gaps(self, data_dir: Optional[Path] = None) -> Dict[str, List[str]]:
        """Check each coverage contract: quarantined keys with no replacement.

        Returns ``{contract_id: [missing keys]}``. Empty lists mean the
        Halbert-authored replacement fully covers what was quarantined, so a
        commercial build loses no coverage by dropping the quarantined slice.
        """
        base = Path(data_dir) if data_dir else (self.repo_root or find_repo_root()) / "data"
        gaps: Dict[str, List[str]] = {}

        for contract in self.coverage_contracts:
            cid = contract.get("id", "unnamed")
            key = contract.get("key", "id")
            quarantined = base / _normalize_path(contract.get("quarantined", ""))
            replacement = base / _normalize_path(contract.get("replacement", ""))
            need = _collect_keys(quarantined, key)
            have = _collect_keys(replacement, key)
            gaps[cid] = sorted(need - have)

        return gaps


def _collect_keys(path: Path, key: str) -> set:
    """Collect one dotted field from every record in a JSONL file."""
    out: set = set()
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = _dig(record, key) if isinstance(record, dict) else None
            if value:
                out.add(str(value))
    return out


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up from `start` looking for the repo markers (config/ + data/)."""
    here = Path(start) if start else Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "config" / "licensing.yml").exists() and (candidate / "data").is_dir():
            return candidate
    # Fall back to the checkout layout: halbert_core/halbert_core/corpus/ -> repo
    return Path(__file__).resolve().parents[3]


def iter_channel_names(policy: LicensePolicy) -> Iterable[str]:
    return sorted(policy.channels)
