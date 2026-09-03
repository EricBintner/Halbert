# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vault: the change ledger projected into Markdown a person can read.

A **projection with no authority** (`MEM-03`). Nothing reads it back as truth,
``rebuild()`` overwrites hand edits without asking, and deleting the whole
directory loses nothing. That is the property everything else here serves: the
moment a note becomes the only copy of something, erasure cannot reach it and
"forget that" stops being true.

Two invariants make that real, and both are easy to lose:

**A rebuild is byte-identical.** So no wall-clock value may reach a note. That
rules out an epistemic ``composite`` (its freshness term reads ``time.time()``
and drifts every few minutes), naive local timestamps, and any iteration over
a ``set`` — ``str.__hash__`` is randomised per process, and a rebuild is a
different process. Everything that reaches a file is sorted, and every
timestamp is UTC at fixed precision.

**A rebuild reconciles, it does not just write.** Orphans are unlinked. A
projector that only writes leaves a forgotten fact's note on disk forever
while the delete-then-rebuild test stays green.

What is deliberately *not* here: the human-edit watcher from OQ1. A write-back
path is exactly what makes a projection look authoritative to the next reader,
and this step does not have the doubt queue that would arbitrate the conflict.

Known limit, worth stating because it is an accident rather than a guarantee:
the projector enumerates via ``StateStore.current_state()``, which returns only
*open* triples. A key whose rows are all closed is invisible. That is harmless
today because ``invalidate_state`` has no production callers — the first one
silently makes those facts unprojectable.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore

from .provenance import FILE_CONTENT_PREDICATE, FILE_MODE_PREDICATE
from .state_store import (
    ACTOR_USER,
    UNRECORDED,
    StateStore,
    StateTriple,
    default_state_db_path,
)

logger = logging.getLogger("halbert.continuity.vault")

__all__ = ["VaultProjector", "ProjectionResult", "vault_root", "PROJECTABLE"]

#: (subject namespace, predicate) -> category. An explicit allowlist, so an
#: unknown predicate defaults to *rejected* rather than to a note nobody
#: designed. ``is_re_observable`` is not the gate: it would admit
#: ``thread_count``, which churns a new value on every consolidation run.
PROJECTABLE: Dict[Tuple[str, str], str] = {
    ("file", FILE_CONTENT_PREDICATE): "provenance",
    ("file", FILE_MODE_PREDICATE): "permission",
}

#: Admitted in principle, withheld until its writer is fixed.
#:
#: ``("domain", "preferred_entity")`` belongs in the vault -- a durable
#: preference is exactly the non-re-observable kind of fact §4d wants kept.
#: But ``Consolidator._consolidate_domain`` writes every entity in a loop
#: against ONE ``(subject, predicate)`` pair, so each iteration supersedes the
#: last and the key holds whichever entity happened to come last. Projecting
#: it would put a confident note on disk asserting a preference the ledger
#: never really recorded -- the "beautiful empty vault" failure wearing
#: content. Restore this once the writer indexes the key.
_WITHHELD: Dict[Tuple[str, str], str] = {
    ("domain", "preferred_entity"): "preference",
}

_CATEGORY_ABBREV = {"provenance": "prov", "permission": "perm", "preference": "pref"}

#: ISO-8601 UTC at fixed precision. ``valid_from`` is a raw ``time.time()``
#: float, so bare ``isoformat()`` would emit microseconds only when they
#: happen to be non-zero — two formats in one file.
def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return (
        datetime.fromtimestamp(float(ts), timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def vault_root(persona_id: Optional[str] = None) -> Path:
    """``<data dir>/vault/<persona_id>``, resolved at call time.

    Pass ``persona_id`` to reuse one already resolved. A projector that let
    this resolve independently would read being.yml a second time, and a
    change between the two reads would split one rebuild across two
    directories -- writing notes into one and unlinking orphans from the other.

    Through ``data_subdir`` rather than ``state_subdir``: the latter reads only
    ``XDG_STATE_HOME`` and would make two instances share one vault — the same
    ``CFG-1`` bug the ledger path had. And not under ``sourceprep/``, which is
    staged for indexing: a vault in the RAG corpus is a projection being read
    back as truth.
    """
    from ..identity import resolve_persona_id
    from ..utils.paths import data_subdir

    return Path(data_subdir("vault", persona_id or resolve_persona_id()))


@dataclass
class ProjectionResult:
    written: int = 0
    unchanged: int = 0
    unlinked: int = 0
    rejected: int = 0
    root: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "written": self.written, "unchanged": self.unchanged,
            "unlinked": self.unlinked, "rejected": self.rejected,
            "root": self.root, "notes": len(self.notes),
        }


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return (s or "note")[:60]


def _note_id(persona_id: str, subject: str, predicate: str, category: str) -> str:
    """NUL-separated, so no two different key tuples can collide by
    concatenation (``a\\x00b`` and ``ab`` are different inputs)."""
    digest = hashlib.sha256(
        f"{persona_id}\x00{subject}\x00{predicate}".encode("utf-8")
    ).hexdigest()[:8]
    return f"mem_{_CATEGORY_ABBREV.get(category, 'note')}_{digest}"


class VaultProjector:
    """Projects the ledger into Markdown. Never reads it back."""

    def __init__(self, store: Optional[StateStore] = None,
                 root: Optional[Path] = None,
                 persona_id: Optional[str] = None):
        self._store = store
        self._owns_store = store is None
        self._root = root
        # Resolved ONCE per run: _get_persona_id reads being.yml under a file
        # lock on every call, and a mid-run change would split the vault
        # across two directories.
        self._persona_id = persona_id
        self._audit_index: Optional[Dict[str, int]] = None

    # -- setup ---------------------------------------------------------

    def _open(self) -> StateStore:
        if self._store is None:
            self._store = StateStore(db_path=str(default_state_db_path()))
        return self._store

    def _close(self) -> None:
        if self._owns_store and self._store is not None:
            self._store.close()
            self._store = None

    @property
    def persona_id(self) -> str:
        if self._persona_id is None:
            from ..identity import resolve_persona_id

            self._persona_id = resolve_persona_id()
        return self._persona_id

    @property
    def root(self) -> Path:
        if self._root is None:
            # Reuse the persona this projector already resolved, so one
            # rebuild cannot straddle two vault directories.
            self._root = vault_root(self.persona_id)
        return self._root

    def _audited_requests(self) -> Dict[str, int]:
        """``{request_id: seq}``, built once. ``read_all`` is O(N) over the
        whole log, so per-note lookups would make projection quadratic."""
        if self._audit_index is not None:
            return self._audit_index
        index: Dict[str, int] = {}
        try:
            from ..obs.audit import audit_log

            for event in audit_log().read_all():
                rid = (event.payload or {}).get("request_id")
                if rid and rid not in index:
                    index[rid] = event.seq
        except Exception as e:
            # A machine without haloysius.integrity must still get a vault;
            # the notes just say so rather than claiming corroboration.
            logger.info("audit log unavailable; notes will say ledger_only (%s)", e)
        self._audit_index = index
        return index

    # -- rendering -----------------------------------------------------

    def _category(self, triple: StateTriple) -> Optional[str]:
        namespace = triple.subject.split(":", 1)[0]
        return PROJECTABLE.get((namespace, triple.predicate))

    def _frontmatter(self, triple: StateTriple, *, category: str,
                     version: int, validated: bool) -> Dict[str, Any]:
        """§4f field order. No ``composite``: it is a function of wall-clock
        time and would break byte-identity between two rebuilds."""
        return {
            "id": _note_id(self.persona_id, triple.subject, triple.predicate, category),
            "persona_id": self.persona_id,
            "subject": triple.subject,
            "predicate": triple.predicate,
            "category": category,
            "confidence": triple.confidence,
            "validation_status": "corroborated_by_audit" if validated else "ledger_only",
            "version": version,
            "reason": triple.reason,
            "actor": triple.actor,
            "request_id": triple.request_id,
            "temporal_validity": {
                "valid_from": _iso(triple.valid_from),
                "valid_to": _iso(triple.valid_to),
            },
            "links": sorted({f"[[{triple.subject}]]"}),
        }

    def _body(self, triple: StateTriple, category: str) -> str:
        title = f"{triple.subject} — {triple.predicate}"
        lines = [f"# {title}", ""]
        lines.append(f"Current value: `{triple.object}`")
        lines.append(f"Recorded by **{triple.actor}** via `{triple.source}`.")
        lines.append("")
        if triple.reason == UNRECORDED:
            lines.append(
                "> **Provenance:** no reason was recorded at the time of this "
                "change. It has deliberately not been filled in since."
            )
        elif triple.actor == ACTOR_USER:
            # Only a person's words are a quotation. A deterministic rule's
            # self-naming string is not, and presenting it as one would put
            # quotation marks around something nobody said.
            lines.append(f'> **Provenance:** *"{triple.reason}"*')
        else:
            lines.append(f"> **Provenance:** {triple.reason}")
        return "\n".join(lines) + "\n"

    def _render(self, triple: StateTriple, frontmatter: Dict[str, Any],
                category: str) -> str:
        head = yaml.safe_dump(
            frontmatter,
            sort_keys=False,            # pyyaml sorts by default; §4f order is meaningful
            default_flow_style=False,
            allow_unicode=True,         # otherwise non-ASCII becomes \uXXXX
            width=10 ** 9,              # otherwise a long reason folds across lines
        )
        return f"---\n{head}---\n\n{self._body(triple, category)}"

    # -- projection ----------------------------------------------------

    def plan(self) -> Tuple[Dict[str, str], int]:
        """``({relpath: text}, rejected_count)`` — the whole vault, in memory."""
        store = self._open()
        try:
            # strict: an empty plan from a FAILED read would make
            # rebuild() unlink every note and report success.
            triples = store.current_state(strict=True)
            index = self._audited_requests()
            out: Dict[str, str] = {}
            rejected = 0
            for triple in triples:      # already ORDER BY subject, predicate
                category = self._category(triple)
                if category is None:
                    rejected += 1
                    continue
                version = len(store.state_history(
                    triple.subject, triple.predicate, strict=True))
                note_id = _note_id(self.persona_id, triple.subject,
                                   triple.predicate, category)
                validated = bool(triple.request_id and triple.request_id in index)
                fm = self._frontmatter(triple, category=category,
                                       version=version, validated=validated)
                # The 8-hex id is in the filename so two subjects that
                # slugify the same cannot silently overwrite each other --
                # which a byte-compare would never catch.
                rel = f"notes/{_slug(triple.subject)}-{_slug(triple.predicate)}-{note_id[-8:]}.md"
                out[rel] = self._render(triple, fm, category)
            return out, rejected
        finally:
            self._close()

    def rebuild(self) -> ProjectionResult:
        """Reconcile the vault against the ledger.

        Writes what differs, leaves what matches (no mtime churn), and
        **unlinks what the ledger no longer produces**. The unlink pass is
        what makes forgetting real on a live tree; a delete-then-rebuild test
        cannot exercise it.

        Raises rather than reconciling if the ledger cannot be read: an empty
        plan from a failed read is indistinguishable from an empty ledger, and
        acting on it would delete every note and call that a success.
        """
        planned, rejected = self.plan()
        root = self.root
        root.mkdir(parents=True, exist_ok=True)
        result = ProjectionResult(rejected=rejected, root=str(root),
                                  notes=sorted(planned))

        # Reconciled like every other file: an unconditional write would
        # churn its mtime on every rebuild, which is the same "writes but
        # does not reconcile" flaw the unlink pass exists to prevent.
        readme = root / "README.md"
        if not readme.exists() or readme.read_text(encoding="utf-8") != _README:
            readme.write_text(_README, encoding="utf-8")

        notes_dir = root / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        for rel in sorted(planned):
            path = root / rel
            text = planned[rel]
            existing = None
            if path.exists():
                try:
                    existing = path.read_text(encoding="utf-8")
                except OSError:
                    existing = None
            if existing == text:
                result.unchanged += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            result.written += 1

        for path in sorted(notes_dir.glob("*.md")):
            if str(path.relative_to(root)) not in planned:
                path.unlink()
                result.unlinked += 1
        return result

    def forget(self, request_id: str) -> ProjectionResult:
        """Remove one request's words from the ledger and reproject.

        Reproject rather than blind-unlink: a key may already hold a newer
        value under a different request, and that note must survive.

        This removes the *words*. The facts and their timeline stay, because
        what was true and when is not the thing being forgotten — see
        ``StateStore.redact_request``.
        """
        store = self._open()
        try:
            store.redact_request(request_id, actor="forget")
        except Exception as e:
            logger.warning(f"vault forget({request_id}): ledger redaction failed: {e}")
        finally:
            self._close()
        return self.rebuild()


_README = """# Halbert's memory vault

These notes are a **projection** of the change ledger. They are generated, and
nothing reads them back as truth.

- Editing a note changes nothing. The next rebuild overwrites it.
- Deleting the whole directory loses nothing. Rebuild recreates it exactly.
- A note exists because the ledger holds an open fact for that subject. When
  the ledger stops holding it, the note is removed on the next rebuild.

Rebuild with `halbert vault-rebuild`.

What a note does *not* prove: that the value on disk still matches. It records
what was recorded, when, by whom, and the reason captured at the time. Where
that reason reads `unrecorded`, none was captured — and it is never filled in
afterwards, because a plausible invented reason is worse than a blank one.
"""
