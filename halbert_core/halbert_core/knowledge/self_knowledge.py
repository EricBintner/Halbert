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
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
        self._data_path = self._get_data_path()
        self._chroma_collection = None
        
        # Load existing knowledge
        self._load_from_disk()
        self._init_chromadb()
        
        logger.info(f"SelfKnowledge initialized with {len(self._knowledge)} entries")
    
    def _get_data_path(self) -> Path:
        """Get path to knowledge store."""
        data_dir = Path.home() / ".local" / "share" / "halbert" / "knowledge"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "self_knowledge.json"
    
    def _load_from_disk(self):
        """Load knowledge from JSON file."""
        if not self._data_path.exists():
            return
        
        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)
            
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
            logger.error(f"Failed to load knowledge: {e}")
    
    def _save_to_disk(self):
        """Persist knowledge to JSON file."""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'entries': [asdict(e) for e in self._knowledge.values()]
            }
            with open(self._data_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save knowledge: {e}")
    
    def _init_chromadb(self):
        """Initialize ChromaDB collection for semantic search."""
        try:
            import chromadb
            
            persist_dir = str(Path.home() / ".local" / "share" / "halbert" / "chromadb")
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
        """Add or update a knowledge entry."""
        if entry.id in self._knowledge:
            entry.updated_at = datetime.now().isoformat()
        
        self._knowledge[entry.id] = entry
        self._save_to_disk()
        
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
        """Delete a knowledge entry."""
        if knowledge_id not in self._knowledge:
            return False
        
        del self._knowledge[knowledge_id]
        self._save_to_disk()
        
        if self._chroma_collection:
            try:
                self._chroma_collection.delete(ids=[knowledge_id])
            except Exception:
                pass
        
        return True
    
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
