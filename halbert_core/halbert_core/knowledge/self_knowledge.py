# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Self-Knowledge System

Persistent storage of the system's understanding of itself:
- Core system facts (hardware, OS, hostname, etc.)
- Configuration rationale (WHY things are set up a certain way)
- User-taught knowledge (things the user tells the system)
- Relationships between components (ontology)

This is the system's long-term memory about ITSELF, not ephemeral discoveries.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.paths import data_dir, data_subdir

logger = logging.getLogger(__name__)


class KnowledgeUnavailable(Exception):
    """The knowledge store could not be read, or could not be written.

    Distinct from "nothing recorded" on purpose, and mirrors
    :class:`continuity.recall.LedgerUnavailable`. A caller that renders a
    store failure as an empty result turns "I could not look" into "there is
    nothing"; a caller that renders a *write* failure as success tells the
    operator their rationale was kept when nothing reached the disk. Both are
    the same lie in different directions, and both are worse than an error.
    """


class MemoryOperation(str, Enum):
    """
    Memory operations for intelligent knowledge management.
    
    Inspired by Mem0's approach to preventing duplicates and contradictions.
    """
    ADD = "add"           # New knowledge added
    UPDATE = "update"     # Existing knowledge updated (same subject, new content)
    DELETE = "delete"     # Knowledge removed (contradiction resolved)
    NOOP = "noop"         # No operation (duplicate detected)


class KnowledgeType(str, Enum):
    """Types of self-knowledge."""
    # Core identity
    IDENTITY = "identity"           # hostname, OS, primary purpose
    HARDWARE = "hardware"           # CPU, RAM, GPUs, disks
    
    # Configuration knowledge
    CONFIG_RATIONALE = "config_rationale"   # WHY something is configured
    CONFIG_HISTORY = "config_history"       # History of config changes
    
    # Relationships / Ontology
    RELATIONSHIP = "relationship"   # Component A depends on B
    ROLE = "role"                   # "This disk is for backups"
    
    # User-taught
    USER_TAUGHT = "user_taught"     # Explicit knowledge from user
    PREFERENCE = "preference"       # User preferences
    
    # Observations
    OBSERVATION = "observation"     # Patterns the system noticed
    ANOMALY = "anomaly"            # Unusual things worth remembering


@dataclass
class KnowledgeEntry:
    """A single piece of self-knowledge."""
    id: str
    type: KnowledgeType
    subject: str                    # What this knowledge is about
    content: str                    # The knowledge itself
    rationale: Optional[str] = None # WHY (for config_rationale)
    source: str = "system"          # Who/what created this: system, user, inference
    confidence: float = 1.0         # How confident (1.0 = certain)
    created_at: str = ""
    updated_at: str = ""
    related_to: List[str] = field(default_factory=list)  # Related knowledge IDs
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_embedding_text(self) -> str:
        """Generate text for embedding."""
        parts = [f"{self.type.value}: {self.subject}"]
        parts.append(self.content)
        if self.rationale:
            parts.append(f"Rationale: {self.rationale}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        return "\n".join(parts)


class SelfKnowledge:
    """
    Persistent self-knowledge store.
    
    Uses ChromaDB for semantic search + JSON for full data.
    """
    
    _instance: Optional['SelfKnowledge'] = None
    
    def __new__(cls) -> 'SelfKnowledge':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._knowledge: Dict[str, KnowledgeEntry] = {}
        #: Set when the store exists on disk but could not be read. It gates
        #: every write: an unreadable file may hold the operator's whole
        #: recorded rationale, and overwriting it with the empty dict we
        #: failed to fill would destroy the only recoverable copy.
        self._load_error: Optional[str] = None
        self._data_path = self._get_data_path()
        self._chroma_collection = None
        
        # Memory operation statistics (Sprint 1: Mem0-style tracking)
        self._memory_stats: Dict[str, int] = {
            MemoryOperation.ADD.value: 0,
            MemoryOperation.UPDATE.value: 0,
            MemoryOperation.DELETE.value: 0,
            MemoryOperation.NOOP.value: 0,
        }
        
        # Load existing knowledge
        self._load_from_disk()
        self._init_chromadb()
        
        logger.info(f"SelfKnowledge initialized with {len(self._knowledge)} entries")
    
    @property
    def readable(self) -> bool:
        """False when the store exists but could not be read.

        A caller must check this before treating an empty result as "nothing
        recorded". The two are not the same answer.
        """
        return self._load_error is None

    def retry_load(self) -> bool:
        """Read the store again after a failure, and report whether it worked.

        The singleton loads once per process, so without this a read failure
        outlives whatever caused it: an operator repairs a truncated file,
        retries as the error told them to, and gets the same error until the
        backend restarts. That makes the remediation we print a lie.

        A no-op when the last load succeeded, so callers may guard with it
        freely. On a repeat failure the error is refreshed rather than
        cleared, and any half-parsed entries are dropped as on first load.
        """
        if self._load_error is None:
            return True
        self._load_error = None
        self._knowledge.clear()
        self._load_from_disk()
        return self._load_error is None

    @property
    def load_error(self) -> Optional[str]:
        """Why the store could not be read, or None when it was read."""
        return self._load_error

    def _get_data_path(self) -> Path:
        """Where the store lives. Resolves, and writes nothing.

        Routed through ``utils.paths`` rather than ``Path.home()``: that
        resolver is the one place ``HALBERT_DATA_DIR`` is honoured, and
        hardcoding home meant a test — or any run with the data dir
        redirected — wrote the operator's real knowledge file.

        The directory is created by :meth:`_save_to_disk` (via
        ``data_subdir``), not here. Constructing a ``SelfKnowledge`` is a
        read, and a read must not leave a directory behind on a machine that
        has never recorded anything.
        """
        return Path(data_dir()) / "knowledge" / "self_knowledge.json"

    def _load_from_disk(self):
        """Load knowledge from JSON file.

        A failure to read is recorded on the instance, not just logged.
        Swallowing it meant a corrupt or unreadable store answered every
        later question with "nothing recorded" — and the next save then
        replaced the recoverable file with an empty one.
        """
        try:
            # Opened directly rather than guarded by .exists(). Path.exists()
            # swallows OSError and answers False, so a directory this uid can
            # no longer search — root-owned after one sudo run, a stale mount —
            # was indistinguishable from a first run: the store reported
            # "nothing recorded" and the next save wrote an empty file over
            # notes that were still there. Only a genuine absence is silent.
            try:
                with open(self._data_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                return
            
            for entry_data in data.get('entries', []):
                entry = KnowledgeEntry(
                    id=entry_data['id'],
                    type=KnowledgeType(entry_data['type']),
                    subject=entry_data['subject'],
                    content=entry_data['content'],
                    rationale=entry_data.get('rationale'),
                    source=entry_data.get('source', 'system'),
                    confidence=entry_data.get('confidence', 1.0),
                    created_at=entry_data.get('created_at', ''),
                    updated_at=entry_data.get('updated_at', ''),
                    related_to=entry_data.get('related_to', []),
                    tags=entry_data.get('tags', []),
                    metadata=entry_data.get('metadata', {}),
                )
                self._knowledge[entry.id] = entry
            
            logger.info(f"Loaded {len(self._knowledge)} knowledge entries from disk")
        except Exception as e:
            # Half a file may already be in ``self._knowledge``. Drop it:
            # a partial load presented as the whole store is the same
            # conflation as an empty one, one degree quieter.
            self._knowledge.clear()
            self._load_error = str(e)
            logger.error(f"Failed to load knowledge from {self._data_path}: {e}")

    def _save_to_disk(self):
        """Persist knowledge to JSON, atomically, or raise.

        Two changes from the version that logged and returned:

        *Atomic.* Serialize first, write a temp file in the same directory,
        flush and fsync it, then ``os.replace``. The truncate-then-write it
        replaces left a half-written store on any crash mid-write — of a file
        whose entire job is to be the durable record. This is the house
        pattern; ``mcp/config.py::_atomic_write_yaml`` is the reference.

        *Loud.* A failed write raises :class:`KnowledgeUnavailable` instead of
        logging, because every caller above returns an id or a success flag
        and had no way to tell that nothing reached the disk.

        A store we failed to READ is never written. See ``_load_error``.
        """
        if self._load_error is not None:
            raise KnowledgeUnavailable(
                f"the knowledge store at {self._data_path} could not be read "
                f"({self._load_error}), so it will not be overwritten. Writing "
                f"now would replace records that are still recoverable with an "
                f"empty file. Move or repair that file, then try again"
            )

        data = {
            'version': 1,
            'updated_at': datetime.now().isoformat(),
            'entries': [asdict(e) for e in self._knowledge.values()]
        }
        try:
            text = json.dumps(data, indent=2, default=str)
        except Exception as e:
            raise KnowledgeUnavailable(
                f"the knowledge could not be serialized ({e}), so nothing was "
                f"written and the store on disk is unchanged"
            ) from e

        temp_name = None
        try:
            # ``data_subdir`` is the choke point that both resolves the data
            # dir and creates it -- called here, at the write, rather than in
            # the path getter.
            directory = Path(data_subdir("knowledge"))
            fd, temp_name = tempfile.mkstemp(
                prefix=self._data_path.name + ".", suffix=".tmp",
                dir=str(directory))
            with os.fdopen(fd, "w") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self._data_path)
        except Exception as e:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            raise KnowledgeUnavailable(
                f"the knowledge store at {self._data_path} could not be "
                f"written ({e}), so this was not recorded. The previous "
                f"contents are intact. Check that the directory exists and is "
                f"writable, then try again"
            ) from e

    def _init_chromadb(self):
        """Initialize ChromaDB collection for semantic search."""
        try:
            import chromadb

            # Same treatment as _get_data_path: through utils.paths, so a run
            # with HALBERT_DATA_DIR set does not index into the operator's
            # real collection. ``data_subdir`` creates the directory, which
            # is right here -- chromadb's PersistentClient creates and writes
            # its own store regardless, so this branch was never side-effect
            # free and pretending otherwise would only hide where it writes.
            persist_dir = data_subdir("chromadb")
            client = chromadb.PersistentClient(path=persist_dir)
            
            self._chroma_collection = client.get_or_create_collection(
                name="self_knowledge",
                metadata={"description": "System's knowledge about itself"}
            )
            
            # Index existing knowledge
            if self._knowledge:
                ids = []
                docs = []
                metas = []
                for entry in self._knowledge.values():
                    ids.append(entry.id)
                    docs.append(entry.to_embedding_text())
                    metas.append({
                        'type': entry.type.value,
                        'subject': entry.subject,
                        'source': entry.source,
                    })
                
                self._chroma_collection.upsert(ids=ids, documents=docs, metadatas=metas)
                logger.debug(f"Indexed {len(ids)} knowledge entries in ChromaDB")
                
        except Exception as e:
            logger.warning(f"ChromaDB init failed for self_knowledge: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # Knowledge Management
    # ─────────────────────────────────────────────────────────────
    
    def add(self, entry: KnowledgeEntry) -> str:
        """Add or update a knowledge entry, or raise.

        Raises :class:`KnowledgeUnavailable` when the entry did not reach the
        disk. In-memory state is rolled back first, so a failed write leaves
        no entry that this process would report as recorded and that a later
        successful write would persist without anyone having asked.
        """
        if entry.id in self._knowledge:
            entry.updated_at = datetime.now().isoformat()

        previous = self._knowledge.get(entry.id)
        self._knowledge[entry.id] = entry
        try:
            self._save_to_disk()
        except KnowledgeUnavailable:
            if previous is None:
                self._knowledge.pop(entry.id, None)
            else:
                self._knowledge[entry.id] = previous
            raise

        # Update ChromaDB
        if self._chroma_collection:
            try:
                self._chroma_collection.upsert(
                    ids=[entry.id],
                    documents=[entry.to_embedding_text()],
                    metadatas=[{
                        'type': entry.type.value,
                        'subject': entry.subject,
                        'source': entry.source,
                    }]
                )
            except Exception as e:
                logger.warning(f"Failed to index knowledge: {e}")
        
        logger.info(f"Added knowledge: {entry.type.value}/{entry.subject}")
        return entry.id
    
    def smart_add(
        self, 
        entry: KnowledgeEntry,
        similarity_threshold: float = 0.85
    ) -> tuple[MemoryOperation, str, Optional[str]]:
        """
        Intelligently add knowledge with duplicate/contradiction detection.
        
        Inspired by Mem0's memory management approach:
        1. Check for semantic duplicates → NOOP
        2. Check for same-subject updates → UPDATE  
        3. Otherwise → ADD
        
        Args:
            entry: The knowledge entry to add
            similarity_threshold: Threshold for considering entries as duplicates (0-1)
        
        Returns:
            Tuple of (operation, reason, affected_id)
            - operation: MemoryOperation that was performed
            - reason: Human-readable explanation
            - affected_id: ID of entry that was added/updated/kept, or None for NOOP
        """
        # Step 1: Check for exact ID match (direct update)
        if entry.id in self._knowledge:
            existing = self._knowledge[entry.id]
            if self._content_matches(entry, existing):
                self._memory_stats[MemoryOperation.NOOP.value] += 1
                logger.info(f"Memory NOOP: {entry.id} - content unchanged")
                return (MemoryOperation.NOOP, "Content unchanged", entry.id)
            else:
                self.add(entry)
                self._memory_stats[MemoryOperation.UPDATE.value] += 1
                logger.info(f"Memory UPDATE: {entry.id} - same ID, new content")
                return (MemoryOperation.UPDATE, "Updated existing entry", entry.id)
        
        # Step 2: Search for semantically similar entries
        similar_entries = self._find_similar(entry, k=5)
        
        for existing, similarity in similar_entries:
            # Check for near-duplicate (same meaning)
            if similarity >= similarity_threshold:
                if self._content_matches(entry, existing):
                    self._memory_stats[MemoryOperation.NOOP.value] += 1
                    logger.info(f"Memory NOOP: Duplicate of {existing.id} (similarity: {similarity:.2f})")
                    return (MemoryOperation.NOOP, f"Duplicate of existing: {existing.subject}", existing.id)
            
            # Check for contradiction (same subject + type, different content)
            if self._is_contradiction(entry, existing):
                # Update the existing entry with new information
                self._memory_stats[MemoryOperation.UPDATE.value] += 1
                logger.info(f"Memory UPDATE: {existing.id} - contradiction resolved")
                entry.id = existing.id  # Keep the same ID
                entry.created_at = existing.created_at  # Preserve creation time
                self.add(entry)
                return (MemoryOperation.UPDATE, f"Updated contradicting entry: {existing.subject}", entry.id)
        
        # Step 3: Truly new knowledge
        self.add(entry)
        self._memory_stats[MemoryOperation.ADD.value] += 1
        logger.info(f"Memory ADD: {entry.id} - new knowledge")
        return (MemoryOperation.ADD, "New knowledge added", entry.id)
    
    def _content_matches(self, a: KnowledgeEntry, b: KnowledgeEntry) -> bool:
        """Check if two entries have essentially the same content."""
        # Normalize and compare
        content_a = a.content.lower().strip()
        content_b = b.content.lower().strip()
        
        # Exact match
        if content_a == content_b:
            return True
        
        # Very similar (allowing for minor differences)
        if len(content_a) > 0 and len(content_b) > 0:
            # Simple similarity: ratio of common characters
            shorter = min(len(content_a), len(content_b))
            longer = max(len(content_a), len(content_b))
            if shorter / longer > 0.95:
                common = sum(1 for c1, c2 in zip(content_a, content_b) if c1 == c2)
                if common / longer > 0.95:
                    return True
        
        return False
    
    def _is_contradiction(self, new: KnowledgeEntry, existing: KnowledgeEntry) -> bool:
        """
        Check if new entry contradicts existing entry.
        
        Contradiction = same subject AND same type AND different content
        """
        # Must be same type
        if new.type != existing.type:
            return False
        
        # Must be same subject (case-insensitive)
        if new.subject.lower().strip() != existing.subject.lower().strip():
            return False
        
        # Content must be different
        if self._content_matches(new, existing):
            return False
        
        # Same subject + type + different content = contradiction
        return True
    
    def _find_similar(
        self, 
        entry: KnowledgeEntry, 
        k: int = 5
    ) -> List[tuple[KnowledgeEntry, float]]:
        """
        Find semantically similar entries using ChromaDB.
        
        Returns list of (entry, similarity_score) tuples.
        """
        if not self._chroma_collection or not self._knowledge:
            return []
        
        try:
            results = self._chroma_collection.query(
                query_texts=[entry.to_embedding_text()],
                n_results=min(k, len(self._knowledge)),
                include=['distances']
            )
            
            ids = results.get('ids', [[]])[0]
            distances = results.get('distances', [[]])[0]
            
            similar = []
            for id_, distance in zip(ids, distances):
                if id_ in self._knowledge and id_ != entry.id:
                    # Convert distance to similarity (ChromaDB uses L2 distance)
                    # Lower distance = more similar
                    similarity = max(0, 1 - (distance / 2))  # Normalize to 0-1
                    similar.append((self._knowledge[id_], similarity))
            
            return similar
        except Exception as e:
            logger.warning(f"Similarity search failed: {e}")
            return []
    
    def get(self, knowledge_id: str) -> Optional[KnowledgeEntry]:
        """Get a knowledge entry by ID."""
        return self._knowledge.get(knowledge_id)
    
    def get_by_type(self, ktype: KnowledgeType) -> List[KnowledgeEntry]:
        """Get all knowledge of a specific type."""
        return [e for e in self._knowledge.values() if e.type == ktype]
    
    def get_by_subject(self, subject: str) -> List[KnowledgeEntry]:
        """Get all knowledge about a subject."""
        subject_lower = subject.lower()
        return [
            e for e in self._knowledge.values()
            if subject_lower in e.subject.lower()
        ]
    
    def search(self, query: str, k: int = 5) -> List[KnowledgeEntry]:
        """Semantic search over knowledge."""
        if not self._chroma_collection:
            # Fallback to text search
            query_lower = query.lower()
            matches = []
            for entry in self._knowledge.values():
                if (query_lower in entry.subject.lower() or
                    query_lower in entry.content.lower()):
                    matches.append(entry)
            return matches[:k]
        
        try:
            results = self._chroma_collection.query(
                query_texts=[query],
                n_results=k
            )
            
            ids = results.get('ids', [[]])[0]
            return [self._knowledge[id_] for id_ in ids if id_ in self._knowledge]
        except Exception as e:
            logger.warning(f"Knowledge search failed: {e}")
            return []
    
    def delete(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry.

        Returns False when there was nothing to delete — that is not a
        failure, and a second delete of the same id is a no-op. Raises
        :class:`KnowledgeUnavailable` when the removal could not be
        persisted, with the entry put back so memory still matches disk.
        """
        if knowledge_id not in self._knowledge:
            return False

        removed = self._knowledge.pop(knowledge_id)
        try:
            self._save_to_disk()
        except KnowledgeUnavailable:
            self._knowledge[knowledge_id] = removed
            raise
        self._memory_stats[MemoryOperation.DELETE.value] += 1
        logger.info(f"Memory DELETE: {knowledge_id}")
        
        if self._chroma_collection:
            try:
                self._chroma_collection.delete(ids=[knowledge_id])
            except Exception:
                pass
        
        return True
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get memory operation statistics.
        
        Returns dict with:
        - operations: counts of ADD/UPDATE/DELETE/NOOP
        - total_entries: current number of knowledge entries
        - types: breakdown by KnowledgeType
        """
        type_counts = {}
        for entry in self._knowledge.values():
            type_name = entry.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "operations": dict(self._memory_stats),
            "total_entries": len(self._knowledge),
            "types": type_counts,
            "total_operations": sum(self._memory_stats.values()),
        }
    
    def reset_memory_stats(self):
        """Reset memory operation counters."""
        for key in self._memory_stats:
            self._memory_stats[key] = 0
    
    # ─────────────────────────────────────────────────────────────
    # Convenience Methods
    # ─────────────────────────────────────────────────────────────
    
    def teach(
        self,
        subject: str,
        content: str,
        rationale: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        User teaches the system something.
        
        Example:
            teach("bcachefs pool", 
                  "The bcachefs pool uses nvme0n1 and nvme1n1",
                  rationale="For redundancy and speed on critical data")
        """
        entry = KnowledgeEntry(
            id=f"taught:{subject.lower().replace(' ', '_')}:{int(datetime.now().timestamp())}",
            type=KnowledgeType.USER_TAUGHT,
            subject=subject,
            content=content,
            rationale=rationale,
            source="user",
            confidence=1.0,
            tags=tags or [],
        )
        return self.add(entry)
    
    def explain_config(
        self,
        config_name: str,
        description: str,
        rationale: str,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Record WHY something is configured a certain way.
        
        Example:
            explain_config("kernel version",
                          "Using kernel 6.8.12",
                          rationale="bcachefs requires kernel 6.8 or earlier")
        """
        entry = KnowledgeEntry(
            id=f"config:{config_name.lower().replace(' ', '_')}",
            type=KnowledgeType.CONFIG_RATIONALE,
            subject=config_name,
            content=description,
            rationale=rationale,
            source="user",
            confidence=1.0,
            tags=tags or ['config'],
        )
        return self.add(entry)
    
    def note_relationship(
        self,
        subject: str,
        relationship: str,
        target: str,
        rationale: Optional[str] = None
    ) -> str:
        """
        Record a relationship between components.
        
        Example:
            note_relationship("nginx service", "depends on", "docker network",
                             rationale="Nginx reverse proxies to Docker containers")
        """
        entry = KnowledgeEntry(
            id=f"rel:{subject.lower().replace(' ', '_')}:{target.lower().replace(' ', '_')}",
            type=KnowledgeType.RELATIONSHIP,
            subject=subject,
            content=f"{subject} {relationship} {target}",
            rationale=rationale,
            source="user",
            tags=['relationship'],
        )
        return self.add(entry)
    
    def assign_role(
        self,
        component: str,
        role: str,
        rationale: Optional[str] = None
    ) -> str:
        """
        Assign a role/purpose to a component.
        
        Example:
            assign_role("sda", "backup disk", 
                       rationale="Dedicated to Borg backup repository")
        """
        entry = KnowledgeEntry(
            id=f"role:{component.lower().replace(' ', '_')}",
            type=KnowledgeType.ROLE,
            subject=component,
            content=f"{component} serves as {role}",
            rationale=rationale,
            source="user",
            tags=['role'],
        )
        return self.add(entry)
    
    # ─────────────────────────────────────────────────────────────
    # System Identity
    # ─────────────────────────────────────────────────────────────
    
    def set_identity(self, key: str, value: str) -> str:
        """Set a core identity fact."""
        entry = KnowledgeEntry(
            id=f"identity:{key.lower().replace(' ', '_')}",
            type=KnowledgeType.IDENTITY,
            subject=key,
            content=value,
            source="system",
            confidence=1.0,
            tags=['identity', 'core'],
        )
        return self.add(entry)
    
    def get_identity(self) -> Dict[str, str]:
        """Get all identity facts as a dict."""
        identity_entries = self.get_by_type(KnowledgeType.IDENTITY)
        return {e.subject: e.content for e in identity_entries}
    
    def record_hardware(self, component: str, details: str) -> str:
        """Record hardware information."""
        entry = KnowledgeEntry(
            id=f"hardware:{component.lower().replace(' ', '_')}",
            type=KnowledgeType.HARDWARE,
            subject=component,
            content=details,
            source="system",
            confidence=1.0,
            tags=['hardware'],
        )
        return self.add(entry)
    
    # ─────────────────────────────────────────────────────────────
    # Context for Chat
    # ─────────────────────────────────────────────────────────────
    
    def get_context_for_query(self, query: str, max_entries: int = 5) -> str:
        """
        Get relevant self-knowledge as context for a chat query.
        """
        # Always include core identity
        identity = self.get_identity()
        
        # Search for relevant knowledge
        relevant = self.search(query, k=max_entries)
        
        parts = []
        
        # Core identity summary
        if identity:
            parts.append("**System Identity:**")
            for key, value in list(identity.items())[:5]:
                parts.append(f"- {key}: {value}")
        
        # Relevant knowledge
        if relevant:
            parts.append("\n**Relevant System Knowledge:**")
            for entry in relevant:
                line = f"- [{entry.type.value}] {entry.subject}: {entry.content}"
                if entry.rationale:
                    line += f" (Reason: {entry.rationale})"
                parts.append(line)
        
        return "\n".join(parts) if parts else ""
    
    def stats(self) -> Dict[str, Any]:
        """Get knowledge statistics."""
        by_type = {}
        for entry in self._knowledge.values():
            t = entry.type.value
            by_type[t] = by_type.get(t, 0) + 1
        
        return {
            "total_entries": len(self._knowledge),
            "by_type": by_type,
            "data_path": str(self._data_path),
        }


def get_self_knowledge() -> SelfKnowledge:
    """Get the singleton SelfKnowledge instance."""
    return SelfKnowledge()


def reset_self_knowledge() -> None:
    """Drop the process-wide instance so the next call builds a fresh one.

    ``SelfKnowledge`` caches itself on the class and loads from disk exactly
    once, which is right for a long-lived process and impossible for a test
    suite: whichever test constructed it first owned the data path, the
    loaded entries and the read-failure flag for every test after it. The
    autouse fixture in ``halbert_core/tests/conftest.py`` calls this.
    """
    SelfKnowledge._instance = None


# ─────────────────────────────────────────────────────────────
# System Identity Bootstrap
# ─────────────────────────────────────────────────────────────

def bootstrap_identity():
    """
    Bootstrap core system identity from current system state.
    
    Call this once on first run or when system changes significantly.
    """
    import socket
    import platform
    
    sk = get_self_knowledge()
    
    # Hostname
    hostname = socket.gethostname()
    sk.set_identity("hostname", hostname)
    
    # OS
    sk.set_identity("os", platform.system())
    sk.set_identity("os_release", platform.release())
    
    # Distribution (Linux)
    try:
        import distro
        sk.set_identity("distribution", f"{distro.name()} {distro.version()}")
    except ImportError:
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        sk.set_identity("distribution", line.split("=")[1].strip().strip('"'))
                        break
        except Exception:
            pass
    
    # CPU
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    cpu_model = line.split(":")[1].strip()
                    sk.record_hardware("cpu", cpu_model)
                    break
    except Exception:
        pass
    
    # Memory
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_kb = int(line.split()[1])
                    mem_gb = round(mem_kb / 1024 / 1024, 1)
                    sk.record_hardware("memory", f"{mem_gb} GB")
                    break
    except Exception:
        pass
    
    logger.info(f"Bootstrapped system identity: {hostname}")
    return sk.get_identity()


def bootstrap_from_profile(profile: Dict[str, Any]) -> Dict[str, int]:
    """
    Bootstrap comprehensive self-knowledge from a deep scan profile.
    
    This implements the Genesis vision: "The system's data is its biography,
    its configuration is its physiology."
    
    Args:
        profile: The system profile from SystemProfiler.scan_all()
    
    Returns:
        Dict with counts of knowledge entries added by category
    """
    sk = get_self_knowledge()
    counts = {"identity": 0, "hardware": 0, "config": 0, "role": 0, "observation": 0}
    
    # ─────────────────────────────────────────────────────────────
    # Core Identity - "Who am I?"
    # ─────────────────────────────────────────────────────────────
    
    if "hostname" in profile:
        sk.set_identity("hostname", profile["hostname"])
        counts["identity"] += 1
    
    os_info = profile.get("os", {})
    if os_info:
        if os_info.get("distribution"):
            sk.set_identity("distribution", os_info["distribution"])
            counts["identity"] += 1
        if os_info.get("kernel"):
            sk.set_identity("kernel", os_info["kernel"])
            counts["identity"] += 1
        if os_info.get("uptime"):
            sk.set_identity("uptime", os_info["uptime"])
            counts["identity"] += 1
        if os_info.get("boot_time"):
            sk.set_identity("last_boot", os_info["boot_time"])
            counts["identity"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Hardware - "What is my body?"
    # ─────────────────────────────────────────────────────────────
    
    hw = profile.get("hardware", {})
    if hw:
        cpu = hw.get("cpu", {})
        if cpu:
            cpu_desc = f"{cpu.get('model', 'Unknown')} ({cpu.get('cores', '?')} cores)"
            sk.record_hardware("cpu", cpu_desc)
            counts["hardware"] += 1
        
        mem = hw.get("memory", {})
        if mem:
            mem_desc = f"{mem.get('total_gb', '?')} GB total"
            sk.record_hardware("memory", mem_desc)
            counts["hardware"] += 1
        
        gpus = hw.get("gpus", [])
        for i, gpu in enumerate(gpus):
            gpu_name = gpu.get("name", f"GPU {i}")
            gpu_mem = gpu.get("memory_mb", "?")
            sk.record_hardware(f"gpu_{i}", f"{gpu_name} ({gpu_mem} MB)")
            counts["hardware"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Storage - "What are my organs?" (with roles)
    # ─────────────────────────────────────────────────────────────
    
    storage = profile.get("storage", {})
    if storage:
        filesystems = storage.get("filesystems", [])
        for fs in filesystems:
            device = fs.get("device", "")
            fstype = fs.get("fstype", "")
            mountpoint = fs.get("mountpoint", "")
            size = fs.get("size", "")
            
            if device and mountpoint:
                # Create a role for significant mountpoints
                if mountpoint == "/":
                    sk.assign_role(device, "root filesystem",
                                  rationale=f"{fstype} filesystem, {size} capacity")
                    counts["role"] += 1
                elif mountpoint == "/home":
                    sk.assign_role(device, "user data storage",
                                  rationale=f"{fstype} filesystem for user home directories")
                    counts["role"] += 1
                elif "backup" in mountpoint.lower():
                    sk.assign_role(device, "backup storage",
                                  rationale=f"Mounted at {mountpoint}")
                    counts["role"] += 1
                elif mountpoint.startswith("/mnt") or mountpoint.startswith("/media"):
                    sk.assign_role(device, f"mounted storage at {mountpoint}",
                                  rationale=f"{fstype} filesystem, {size}")
                    counts["role"] += 1
        
        # Note special filesystem capabilities
        if storage.get("has_bcachefs"):
            sk.add(KnowledgeEntry(
                id="config:filesystem_bcachefs",
                type=KnowledgeType.CONFIG_RATIONALE,
                subject="bcachefs usage",
                content="This system uses bcachefs, an advanced copy-on-write filesystem",
                rationale="bcachefs provides snapshots, checksums, compression, and multi-device support",
                source="system",
                tags=["storage", "filesystem", "bcachefs"]
            ))
            counts["config"] += 1
        
        if storage.get("has_zfs"):
            sk.add(KnowledgeEntry(
                id="config:filesystem_zfs",
                type=KnowledgeType.CONFIG_RATIONALE,
                subject="ZFS usage",
                content="This system uses ZFS for storage management",
                rationale="ZFS provides data integrity, snapshots, and RAID-like features",
                source="system",
                tags=["storage", "filesystem", "zfs"]
            ))
            counts["config"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Services - "What processes keep me alive?"
    # ─────────────────────────────────────────────────────────────
    
    services = profile.get("services", {})
    if services:
        notable = services.get("notable_services", [])
        for svc in notable:
            name = svc.get("name", "")
            state = svc.get("state", "")
            
            if name and state == "running":
                # Assign roles to key services
                if "docker" in name.lower():
                    sk.assign_role(name, "container runtime",
                                  rationale="Manages Docker containers for application isolation")
                    counts["role"] += 1
                elif "ssh" in name.lower():
                    sk.assign_role(name, "remote access service",
                                  rationale="Enables secure remote shell connections")
                    counts["role"] += 1
                elif any(db in name.lower() for db in ["postgres", "mysql", "mariadb", "mongodb", "redis"]):
                    sk.assign_role(name, "database service",
                                  rationale="Provides data persistence for applications")
                    counts["role"] += 1
                elif any(web in name.lower() for web in ["nginx", "apache", "caddy"]):
                    sk.assign_role(name, "web server",
                                  rationale="Serves web content and/or reverse proxy")
                    counts["role"] += 1
        
        # Record service health observations
        failed = services.get("failed_count", 0)
        if failed > 0:
            sk.add(KnowledgeEntry(
                id=f"observation:failed_services:{datetime.now().strftime('%Y%m%d')}",
                type=KnowledgeType.OBSERVATION,
                subject="service health",
                content=f"{failed} systemd services are in failed state",
                source="system",
                tags=["services", "health", "warning"]
            ))
            counts["observation"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Security - "How am I protected?"
    # ─────────────────────────────────────────────────────────────
    
    security = profile.get("security", {})
    if security:
        firewall = security.get("firewall", {})
        if firewall:
            fw_type = firewall.get("type", "unknown")
            fw_status = firewall.get("status", "unknown")
            sk.add(KnowledgeEntry(
                id="config:firewall",
                type=KnowledgeType.CONFIG_RATIONALE,
                subject="firewall",
                content=f"Using {fw_type} firewall, status: {fw_status}",
                rationale="Network security boundary protection",
                source="system",
                tags=["security", "firewall"]
            ))
            counts["config"] += 1
        
        ssh_config = security.get("ssh_config", {})
        if ssh_config:
            password_auth = ssh_config.get("password_auth", True)
            root_login = ssh_config.get("root_login", "prohibit-password")
            
            if not password_auth:
                sk.add(KnowledgeEntry(
                    id="config:ssh_key_only",
                    type=KnowledgeType.CONFIG_RATIONALE,
                    subject="SSH authentication",
                    content="SSH is configured for key-based authentication only",
                    rationale="Password authentication is disabled for improved security",
                    source="system",
                    tags=["security", "ssh"]
                ))
                counts["config"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Network - "How do I connect to the world?"
    # ─────────────────────────────────────────────────────────────
    
    network = profile.get("network", {})
    if network:
        interfaces = network.get("interfaces", [])
        for iface in interfaces:
            name = iface.get("name", "")
            ip = iface.get("ip", "")
            if name and ip and not name.startswith("lo"):
                sk.add(KnowledgeEntry(
                    id=f"identity:network_{name}",
                    type=KnowledgeType.IDENTITY,
                    subject=f"network interface {name}",
                    content=f"IP address: {ip}",
                    source="system",
                    tags=["network", "identity"]
                ))
                counts["identity"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Users - "Who uses me?"
    # ─────────────────────────────────────────────────────────────
    
    users = profile.get("users", {})
    if users:
        current = users.get("current_user", "")
        if current:
            sk.set_identity("primary_user", current)
            counts["identity"] += 1
        
        sudo_users = users.get("sudo_users", [])
        if sudo_users:
            sk.add(KnowledgeEntry(
                id="identity:administrators",
                type=KnowledgeType.IDENTITY,
                subject="administrators",
                content=f"Users with sudo access: {', '.join(sudo_users)}",
                source="system",
                tags=["users", "security"]
            ))
            counts["identity"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Packages - "What software defines me?"
    # ─────────────────────────────────────────────────────────────
    
    packages = profile.get("packages", {})
    if packages:
        pkg_manager = packages.get("package_manager", "")
        total = packages.get("total_count", 0)
        notable = packages.get("notable_packages", [])
        
        if pkg_manager and total:
            sk.add(KnowledgeEntry(
                id="identity:package_manager",
                type=KnowledgeType.IDENTITY,
                subject="package management",
                content=f"Using {pkg_manager} with {total} packages installed",
                source="system",
                tags=["packages", "identity"]
            ))
            counts["identity"] += 1
        
        # Record notable development tools
        dev_tools = [p for p in notable if any(t in p for t in ['python', 'node', 'go', 'rust', 'gcc', 'git'])]
        if dev_tools:
            sk.add(KnowledgeEntry(
                id="observation:development_environment",
                type=KnowledgeType.OBSERVATION,
                subject="development environment",
                content=f"Development tools installed: {', '.join(dev_tools[:10])}",
                source="system",
                tags=["development", "packages"]
            ))
            counts["observation"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Containers - "What applications live inside me?"
    # ─────────────────────────────────────────────────────────────
    
    containers = profile.get("containers", {})
    if containers:
        docker_running = containers.get("docker_running", 0)
        if docker_running > 0:
            sk.add(KnowledgeEntry(
                id="observation:docker_containers",
                type=KnowledgeType.OBSERVATION,
                subject="Docker containers",
                content=f"{docker_running} Docker containers currently running",
                source="system",
                tags=["containers", "docker"]
            ))
            counts["observation"] += 1
    
    logger.info(f"Bootstrapped self-knowledge from profile: {sum(counts.values())} entries added")
    logger.info(f"  Identity: {counts['identity']}, Hardware: {counts['hardware']}, "
                f"Config: {counts['config']}, Roles: {counts['role']}, Observations: {counts['observation']}")
    
    return counts


def parse_config_comments(config_path: str) -> List[Dict[str, str]]:
    """
    Parse a config file and extract settings with their comments as rationale.
    
    This implements the Genesis vision: comments in config files are the WHY.
    
    Args:
        config_path: Path to config file (e.g., /etc/fstab, /etc/ssh/sshd_config)
    
    Returns:
        List of {setting, value, comment} dicts
    """
    from pathlib import Path

    results = []
    path = Path(config_path)
    
    if not path.exists():
        return results
    
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        
        pending_comment = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                pending_comment = []
                continue
            
            # Collect comments (potential rationale for next setting)
            if line.startswith('#'):
                comment_text = line.lstrip('#').strip()
                if comment_text and not comment_text.startswith('!'):  # Skip shebang-like
                    pending_comment.append(comment_text)
                continue
            
            # This is a setting line
            # Handle inline comments
            inline_comment = ""
            if '#' in line:
                parts = line.split('#', 1)
                line = parts[0].strip()
                inline_comment = parts[1].strip()
            
            # Parse the setting (handle different formats)
            setting = None
            value = None
            
            # Key=Value format
            if '=' in line:
                parts = line.split('=', 1)
                setting = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""
            # Key Value format (space separated)
            elif ' ' in line or '\t' in line:
                parts = line.split(None, 1)
                setting = parts[0]
                value = parts[1] if len(parts) > 1 else ""
            else:
                setting = line
                value = ""
            
            if setting:
                # Combine pending comments and inline comment as rationale
                rationale_parts = pending_comment + ([inline_comment] if inline_comment else [])
                rationale = " ".join(rationale_parts) if rationale_parts else None
                
                results.append({
                    "setting": setting,
                    "value": value,
                    "comment": rationale,
                    "source": config_path
                })
            
            pending_comment = []
    
    except Exception as e:
        logger.warning(f"Failed to parse config {config_path}: {e}")
    
    return results


def learn_from_config(config_path: str, config_name: Optional[str] = None) -> int:
    """
    Learn self-knowledge from a config file, including comments as rationale.
    
    Args:
        config_path: Path to config file
        config_name: Human-readable name for the config (default: filename)
    
    Returns:
        Number of knowledge entries added
    """
    from pathlib import Path
    
    sk = get_self_knowledge()
    path = Path(config_path)
    name = config_name or path.name
    
    entries = parse_config_comments(config_path)
    count = 0
    
    for entry in entries:
        setting = entry["setting"]
        value = entry["value"]
        comment = entry.get("comment")
        
        # Skip common/uninteresting settings
        if not value or setting.startswith('_'):
            continue
        
        knowledge = KnowledgeEntry(
            id=f"config:{name}:{setting.lower().replace(' ', '_')}",
            type=KnowledgeType.CONFIG_RATIONALE,
            subject=f"{name}: {setting}",
            content=f"{setting} = {value}",
            rationale=comment,
            source="config_file",
            metadata={"config_path": config_path},
            tags=["config", name.lower().replace('.', '_')]
        )
        
        sk.add(knowledge)
        count += 1
    
    logger.info(f"Learned {count} settings from {config_path}")
    return count
