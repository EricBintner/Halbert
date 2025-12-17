"""
Knowledge Graph Module

Sprint 2: Graph-based relationship modeling for system components.

Inspired by Mem0's graph-enhanced variant and GraphRAG concepts.
Enables queries like "What depends on Docker?" and "What would break if X fails?"
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .self_knowledge import SelfKnowledge, KnowledgeEntry, get_self_knowledge

logger = logging.getLogger(__name__)


class RelationType(str, Enum):
    """Types of relationships between components."""
    DEPENDS_ON = "depends_on"       # A needs B to function (nginx → docker)
    MANAGES = "manages"             # A controls/orchestrates B (systemd → nginx.service)
    CONTAINS = "contains"           # A includes B (bcachefs_pool → nvme0n1)
    EXPOSES = "exposes"             # A provides B (nginx → port:80)
    BACKS_UP = "backs_up"           # A is backup destination for B
    MOUNTS = "mounts"               # A is mounted at B (/dev/sda1 → /mnt/data)
    USES = "uses"                   # A uses B (app → postgres)
    CONNECTS_TO = "connects_to"     # A connects to B (client → server)
    PART_OF = "part_of"             # A is part of B (disk → raid array)
    PROVIDES = "provides"           # A provides capability B


@dataclass
class KnowledgeRelation:
    """A relationship between two knowledge entries or system components."""
    id: str
    source: str                     # Source node (knowledge ID or component name)
    target: str                     # Target node (knowledge ID or component name)
    relation_type: RelationType     # Type of relationship
    strength: float = 1.0           # Relationship strength (0-1)
    bidirectional: bool = False     # If true, relation goes both ways
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type.value,
            "strength": self.strength,
            "bidirectional": self.bidirectional,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeRelation':
        """Create from dictionary."""
        return cls(
            id=data["id"],
            source=data["source"],
            target=data["target"],
            relation_type=RelationType(data["relation_type"]),
            strength=data.get("strength", 1.0),
            bidirectional=data.get("bidirectional", False),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )


class KnowledgeGraph:
    """
    Graph layer over SelfKnowledge for relationship queries.
    
    Enables:
    - "What depends on Docker?" → find all dependents
    - "What would break if this fails?" → impact analysis
    - "Show me the storage topology" → subgraph extraction
    """
    
    _instance: Optional['KnowledgeGraph'] = None
    
    def __new__(cls) -> 'KnowledgeGraph':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._relations: Dict[str, KnowledgeRelation] = {}
        self._data_path = self._get_data_path()
        
        # Index for fast lookups
        self._outgoing: Dict[str, Set[str]] = {}  # source → relation IDs
        self._incoming: Dict[str, Set[str]] = {}  # target → relation IDs
        
        # Load existing relations
        self._load_from_disk()
        self._rebuild_indices()
        
        logger.info(f"KnowledgeGraph initialized with {len(self._relations)} relations")
    
    def _get_data_path(self) -> Path:
        """Get path to graph store."""
        data_dir = Path.home() / ".local" / "share" / "halbert" / "knowledge"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "knowledge_graph.json"
    
    def _load_from_disk(self):
        """Load relations from JSON file."""
        if not self._data_path.exists():
            return
        
        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)
            
            for rel_data in data.get('relations', []):
                rel = KnowledgeRelation.from_dict(rel_data)
                self._relations[rel.id] = rel
            
            logger.info(f"Loaded {len(self._relations)} relations from disk")
        except Exception as e:
            logger.error(f"Failed to load graph: {e}")
    
    def _save_to_disk(self):
        """Persist relations to JSON file."""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'relations': [r.to_dict() for r in self._relations.values()]
            }
            with open(self._data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save graph: {e}")
    
    def _rebuild_indices(self):
        """Rebuild lookup indices."""
        self._outgoing.clear()
        self._incoming.clear()
        
        for rel_id, rel in self._relations.items():
            # Outgoing index
            if rel.source not in self._outgoing:
                self._outgoing[rel.source] = set()
            self._outgoing[rel.source].add(rel_id)
            
            # Incoming index
            if rel.target not in self._incoming:
                self._incoming[rel.target] = set()
            self._incoming[rel.target].add(rel_id)
            
            # If bidirectional, add reverse
            if rel.bidirectional:
                if rel.target not in self._outgoing:
                    self._outgoing[rel.target] = set()
                self._outgoing[rel.target].add(rel_id)
                
                if rel.source not in self._incoming:
                    self._incoming[rel.source] = set()
                self._incoming[rel.source].add(rel_id)
    
    # ─────────────────────────────────────────────────────────────
    # Relation Management
    # ─────────────────────────────────────────────────────────────
    
    def add_relation(
        self,
        source: str,
        target: str,
        relation_type: RelationType,
        strength: float = 1.0,
        bidirectional: bool = False,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Add a relationship between two nodes.
        
        Args:
            source: Source node identifier
            target: Target node identifier
            relation_type: Type of relationship
            strength: Relationship strength (0-1)
            bidirectional: Whether relation goes both ways
            metadata: Additional metadata
        
        Returns:
            Relation ID
        """
        # Generate ID
        rel_id = f"rel:{source}:{relation_type.value}:{target}"
        
        # Check for existing
        if rel_id in self._relations:
            # Update strength if higher
            existing = self._relations[rel_id]
            if strength > existing.strength:
                existing.strength = strength
                self._save_to_disk()
            logger.debug(f"Relation already exists: {rel_id}")
            return rel_id
        
        relation = KnowledgeRelation(
            id=rel_id,
            source=source,
            target=target,
            relation_type=relation_type,
            strength=strength,
            bidirectional=bidirectional,
            metadata=metadata or {},
        )
        
        self._relations[rel_id] = relation
        
        # Update indices
        if source not in self._outgoing:
            self._outgoing[source] = set()
        self._outgoing[source].add(rel_id)
        
        if target not in self._incoming:
            self._incoming[target] = set()
        self._incoming[target].add(rel_id)
        
        if bidirectional:
            if target not in self._outgoing:
                self._outgoing[target] = set()
            self._outgoing[target].add(rel_id)
            if source not in self._incoming:
                self._incoming[source] = set()
            self._incoming[source].add(rel_id)
        
        self._save_to_disk()
        logger.info(f"Added relation: {source} --[{relation_type.value}]--> {target}")
        return rel_id
    
    def remove_relation(self, rel_id: str) -> bool:
        """Remove a relation by ID."""
        if rel_id not in self._relations:
            return False
        
        rel = self._relations[rel_id]
        
        # Remove from indices
        if rel.source in self._outgoing:
            self._outgoing[rel.source].discard(rel_id)
        if rel.target in self._incoming:
            self._incoming[rel.target].discard(rel_id)
        
        del self._relations[rel_id]
        self._save_to_disk()
        logger.info(f"Removed relation: {rel_id}")
        return True
    
    def get_relation(self, rel_id: str) -> Optional[KnowledgeRelation]:
        """Get a relation by ID."""
        return self._relations.get(rel_id)
    
    # ─────────────────────────────────────────────────────────────
    # Query Methods
    # ─────────────────────────────────────────────────────────────
    
    def get_outgoing(
        self, 
        node: str, 
        relation_type: Optional[RelationType] = None
    ) -> List[KnowledgeRelation]:
        """
        Get all outgoing relations from a node.
        
        Example: get_outgoing("nginx") → relations where nginx is the source
        """
        rel_ids = self._outgoing.get(node, set())
        relations = [self._relations[rid] for rid in rel_ids if rid in self._relations]
        
        if relation_type:
            relations = [r for r in relations if r.relation_type == relation_type]
        
        return relations
    
    def get_incoming(
        self, 
        node: str, 
        relation_type: Optional[RelationType] = None
    ) -> List[KnowledgeRelation]:
        """
        Get all incoming relations to a node.
        
        Example: get_incoming("docker") → relations where docker is the target
        """
        rel_ids = self._incoming.get(node, set())
        relations = [self._relations[rid] for rid in rel_ids if rid in self._relations]
        
        if relation_type:
            relations = [r for r in relations if r.relation_type == relation_type]
        
        return relations
    
    def get_dependencies(self, node: str) -> List[str]:
        """
        Get what this node depends on.
        
        Example: get_dependencies("nginx") → ["docker", "network"]
        """
        relations = self.get_outgoing(node, RelationType.DEPENDS_ON)
        return [r.target for r in relations]
    
    def get_dependents(self, node: str) -> List[str]:
        """
        Get what depends on this node.
        
        Example: get_dependents("docker") → ["nginx", "postgres", "app"]
        """
        relations = self.get_incoming(node, RelationType.DEPENDS_ON)
        return [r.source for r in relations]
    
    def get_related(
        self, 
        node: str, 
        relation_type: Optional[RelationType] = None
    ) -> List[Tuple[str, RelationType, str]]:
        """
        Get all related nodes (both directions).
        
        Returns: List of (related_node, relation_type, direction)
        where direction is 'outgoing' or 'incoming'
        """
        related = []
        
        for rel in self.get_outgoing(node, relation_type):
            related.append((rel.target, rel.relation_type, 'outgoing'))
        
        for rel in self.get_incoming(node, relation_type):
            related.append((rel.source, rel.relation_type, 'incoming'))
        
        return related
    
    # ─────────────────────────────────────────────────────────────
    # Analysis Methods
    # ─────────────────────────────────────────────────────────────
    
    def impact_analysis(self, node: str) -> Dict[str, Any]:
        """
        Analyze what would be affected if this node fails.
        
        Performs transitive closure over DEPENDS_ON relations.
        
        Returns:
            {
                "node": "docker",
                "direct_dependents": ["nginx", "postgres"],
                "transitive_dependents": ["nginx", "postgres", "app", "web"],
                "total_affected": 4
            }
        """
        direct = set(self.get_dependents(node))
        transitive = set()
        
        # BFS to find all transitive dependents
        to_check = list(direct)
        while to_check:
            current = to_check.pop(0)
            if current in transitive:
                continue
            transitive.add(current)
            
            # Find dependents of this node
            for dependent in self.get_dependents(current):
                if dependent not in transitive:
                    to_check.append(dependent)
        
        return {
            "node": node,
            "direct_dependents": list(direct),
            "transitive_dependents": list(transitive),
            "total_affected": len(transitive),
        }
    
    def find_path(
        self, 
        source: str, 
        target: str, 
        max_depth: int = 10
    ) -> Optional[List[str]]:
        """
        Find a path between two nodes.
        
        Returns list of nodes in path, or None if no path exists.
        """
        if source == target:
            return [source]
        
        # BFS
        visited = {source}
        queue = [(source, [source])]
        
        while queue and len(visited) < max_depth * 10:
            current, path = queue.pop(0)
            
            # Check all related nodes
            for rel in self.get_outgoing(current):
                next_node = rel.target
                if next_node == target:
                    return path + [next_node]
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append((next_node, path + [next_node]))
        
        return None
    
    def get_subgraph(
        self, 
        root: str, 
        depth: int = 2, 
        direction: str = "both"
    ) -> Dict[str, Any]:
        """
        Extract a subgraph centered on a node.
        
        Args:
            root: Center node
            depth: How many hops to include
            direction: 'outgoing', 'incoming', or 'both'
        
        Returns:
            {"nodes": [...], "edges": [...]}
        """
        nodes = {root}
        edges = []
        
        current_level = {root}
        for _ in range(depth):
            next_level = set()
            
            for node in current_level:
                if direction in ("outgoing", "both"):
                    for rel in self.get_outgoing(node):
                        edges.append(rel.to_dict())
                        next_level.add(rel.target)
                
                if direction in ("incoming", "both"):
                    for rel in self.get_incoming(node):
                        edges.append(rel.to_dict())
                        next_level.add(rel.source)
            
            nodes.update(next_level)
            current_level = next_level
        
        return {
            "nodes": list(nodes),
            "edges": edges,
            "root": root,
            "depth": depth,
        }
    
    def get_all_nodes(self) -> Set[str]:
        """Get all nodes in the graph."""
        nodes = set()
        for rel in self._relations.values():
            nodes.add(rel.source)
            nodes.add(rel.target)
        return nodes
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        nodes = self.get_all_nodes()
        
        # Count by relation type
        type_counts = {}
        for rel in self._relations.values():
            type_name = rel.relation_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "total_nodes": len(nodes),
            "total_relations": len(self._relations),
            "relation_types": type_counts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_graph_instance: Optional[KnowledgeGraph] = None

def get_knowledge_graph() -> KnowledgeGraph:
    """Get the singleton KnowledgeGraph instance."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = KnowledgeGraph()
    return _graph_instance


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Discovery from System Profile
# ─────────────────────────────────────────────────────────────────────────────

def discover_relations_from_profile(profile: Dict[str, Any]) -> Dict[str, int]:
    """
    Auto-discover relationships from a system profile scan.
    
    Extracts relations like:
    - Docker containers depend on Docker service
    - Services managed by systemd
    - Filesystems mounted on devices
    - Network connections between services
    
    Args:
        profile: System profile dict from SystemProfiler.scan_all()
    
    Returns:
        Dict with counts of relations discovered by type
    """
    graph = get_knowledge_graph()
    counts = {rt.value: 0 for rt in RelationType}
    
    # ─────────────────────────────────────────────────────────────
    # Docker/Container Relations
    # ─────────────────────────────────────────────────────────────
    containers = profile.get("containers", {})
    
    # Running containers depend on Docker
    for container in containers.get("running", []):
        name = container.get("name", container.get("id", "unknown"))
        graph.add_relation(
            source=f"container:{name}",
            target="service:docker",
            relation_type=RelationType.DEPENDS_ON,
            metadata={"container_id": container.get("id")}
        )
        counts["depends_on"] += 1
        
        # Container port exposures
        ports = container.get("ports", "")
        if ports:
            for port_mapping in str(ports).split(","):
                if ":" in port_mapping:
                    port = port_mapping.split(":")[-1].split("/")[0]
                    graph.add_relation(
                        source=f"container:{name}",
                        target=f"port:{port}",
                        relation_type=RelationType.EXPOSES,
                    )
                    counts["exposes"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Service Relations
    # ─────────────────────────────────────────────────────────────
    services = profile.get("services", {})
    
    # Services managed by systemd
    for service in services.get("running", []):
        name = service if isinstance(service, str) else service.get("name", "unknown")
        graph.add_relation(
            source="systemd",
            target=f"service:{name}",
            relation_type=RelationType.MANAGES,
        )
        counts["manages"] += 1
    
    # Failed services also managed by systemd
    for service in services.get("failed", []):
        name = service if isinstance(service, str) else service.get("name", "unknown")
        graph.add_relation(
            source="systemd",
            target=f"service:{name}",
            relation_type=RelationType.MANAGES,
            metadata={"status": "failed"}
        )
        counts["manages"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Storage/Filesystem Relations
    # ─────────────────────────────────────────────────────────────
    storage = profile.get("storage", {})
    
    # Filesystems mount on devices
    for fs in storage.get("filesystems", []):
        device = fs.get("device", fs.get("source"))
        mountpoint = fs.get("mountpoint", fs.get("target"))
        fstype = fs.get("fstype", fs.get("type", "unknown"))
        
        if device and mountpoint:
            graph.add_relation(
                source=device,
                target=mountpoint,
                relation_type=RelationType.MOUNTS,
                metadata={"fstype": fstype}
            )
            counts["mounts"] += 1
    
    # Physical disks contain partitions
    for disk in storage.get("disks", []):
        disk_name = disk.get("name", disk.get("device"))
        if not disk_name:
            continue
            
        for partition in disk.get("partitions", disk.get("children", [])):
            part_name = partition.get("name", partition.get("device"))
            if part_name:
                graph.add_relation(
                    source=disk_name,
                    target=part_name,
                    relation_type=RelationType.CONTAINS,
                )
                counts["contains"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Network Relations
    # ─────────────────────────────────────────────────────────────
    network = profile.get("network", {})
    
    # Listening ports
    for listener in network.get("listening", []):
        port = listener.get("port", listener.get("local_port"))
        process = listener.get("process", listener.get("program"))
        
        if port and process:
            # Extract process name (may be "pid/name" format)
            proc_name = process.split("/")[-1] if "/" in str(process) else process
            graph.add_relation(
                source=f"process:{proc_name}",
                target=f"port:{port}",
                relation_type=RelationType.EXPOSES,
                metadata={"protocol": listener.get("protocol", "tcp")}
            )
            counts["exposes"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # User/Group Relations
    # ─────────────────────────────────────────────────────────────
    users = profile.get("users", {})
    
    # Users part of groups
    for user in users.get("users", []):
        username = user.get("name", user.get("username"))
        groups = user.get("groups", [])
        
        if username and groups:
            for group in groups:
                graph.add_relation(
                    source=f"user:{username}",
                    target=f"group:{group}",
                    relation_type=RelationType.PART_OF,
                )
                counts["part_of"] += 1
    
    # ─────────────────────────────────────────────────────────────
    # Virtualization Relations
    # ─────────────────────────────────────────────────────────────
    virt = profile.get("virtualization", {})
    
    # VMs managed by hypervisor
    for vm in virt.get("vms", []):
        vm_name = vm.get("name", vm.get("id"))
        hypervisor = virt.get("type", "kvm")
        
        if vm_name:
            graph.add_relation(
                source=f"hypervisor:{hypervisor}",
                target=f"vm:{vm_name}",
                relation_type=RelationType.MANAGES,
            )
            counts["manages"] += 1
    
    logger.info(f"Discovered {sum(counts.values())} relations from profile")
    return counts
