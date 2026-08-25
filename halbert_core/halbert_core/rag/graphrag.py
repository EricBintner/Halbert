"""
GraphRAG: Graph-enhanced Retrieval Augmented Generation

Implementation inspired by Microsoft Research GraphRAG (2024):
- GitHub: https://github.com/microsoft/graphrag
- Uses LLM-derived knowledge graphs instead of flat vectors
- Extracts entities, relationships, and builds community hierarchies
- Excels at complex, multi-hop reasoning

Linux-specific entity types:
- Commands (systemctl, pacman, etc.)
- Services (nginx, docker, postgresql)
- Config files (/etc/nginx/nginx.conf)
- Packages (nginx, docker, python)
- Concepts (systemd units, cgroups, namespaces)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class LinuxEntityType:
    """Entity types specific to Linux documentation."""
    COMMAND = "command"           # CLI commands (systemctl, pacman)
    SERVICE = "service"           # System services (nginx, docker)
    CONFIG_FILE = "config_file"   # Config files (/etc/...)
    PACKAGE = "package"           # Software packages
    CONCEPT = "concept"           # Technical concepts (cgroups, namespaces)
    DIRECTORY = "directory"       # Important directories
    USER = "user"                 # Users/groups (root, www-data)
    PORT = "port"                 # Network ports
    PROTOCOL = "protocol"         # Protocols (TCP, HTTP, SSH)
    FILESYSTEM = "filesystem"     # Filesystems (ext4, btrfs)
    KERNEL_MODULE = "kernel_module"  # Kernel modules


class LinuxRelationType:
    """Relationship types for Linux entities."""
    CONFIGURES = "configures"         # command configures service
    MANAGES = "manages"               # systemd manages service
    REQUIRES = "requires"             # service requires another
    PROVIDES = "provides"             # package provides command
    USES = "uses"                     # service uses config_file
    LISTENS_ON = "listens_on"         # service listens on port
    MOUNTS = "mounts"                 # command mounts filesystem
    CONTAINS = "contains"             # directory contains file
    DEPENDS_ON = "depends_on"         # package depends on package
    RELATED_TO = "related_to"         # general relationship
    ALTERNATIVE_TO = "alternative_to"  # alternatives (apt vs pacman)


@dataclass
class GraphEntity:
    """An entity extracted from documentation."""
    id: str
    name: str
    entity_type: str
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    source_docs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "aliases": self.aliases,
            "source_docs": self.source_docs,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GraphEntity':
        return cls(**data)


@dataclass
class GraphRelation:
    """A relationship between entities."""
    id: str
    source: str           # Source entity ID
    target: str           # Target entity ID
    relation_type: str
    description: str = ""
    strength: float = 1.0
    source_docs: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "description": self.description,
            "strength": self.strength,
            "source_docs": self.source_docs,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GraphRelation':
        return cls(**data)


class LinuxGraphRAG:
    """
    GraphRAG implementation for Linux documentation.
    
    Extracts entities and relationships from docs to enable:
    - "What commands configure nginx?" → traverse graph
    - "What depends on systemd?" → dependency analysis
    - "How are docker and containerd related?" → path finding
    
    Example:
        graph = LinuxGraphRAG()
        graph.extract_from_text(doc_text, doc_id="arch-wiki-nginx")
        
        # Query relationships
        results = graph.query_related("nginx", relation_type="configures")
        
        # Get context for RAG
        context = graph.get_graph_context("how to configure nginx")
    """
    
    def __init__(self, llm_model: str = "llama3.1:8b"):
        """Initialize GraphRAG."""
        self.llm_model = llm_model
        
        self._entities: Dict[str, GraphEntity] = {}
        self._relations: Dict[str, GraphRelation] = {}
        
        # Indices
        self._entity_by_name: Dict[str, str] = {}  # name -> entity ID
        self._entity_by_type: Dict[str, Set[str]] = {}  # type -> entity IDs
        self._outgoing: Dict[str, Set[str]] = {}  # entity -> relation IDs
        self._incoming: Dict[str, Set[str]] = {}  # entity -> relation IDs
        
        self._data_path = self._get_data_path()
        self._load_from_disk()
        
        logger.info(f"LinuxGraphRAG initialized: {len(self._entities)} entities, {len(self._relations)} relations")
    
    def _get_data_path(self) -> Path:
        """Get path to GraphRAG store."""
        data_dir = Path.home() / ".local" / "share" / "halbert" / "graphrag"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "linux_graph.json"
    
    def _load_from_disk(self):
        """Load graph from disk."""
        if not self._data_path.exists():
            return
        
        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)
            
            for ent_data in data.get('entities', []):
                ent = GraphEntity.from_dict(ent_data)
                self._entities[ent.id] = ent
                self._entity_by_name[ent.name.lower()] = ent.id
                
                if ent.entity_type not in self._entity_by_type:
                    self._entity_by_type[ent.entity_type] = set()
                self._entity_by_type[ent.entity_type].add(ent.id)
            
            for rel_data in data.get('relations', []):
                rel = GraphRelation.from_dict(rel_data)
                self._relations[rel.id] = rel
                
                if rel.source not in self._outgoing:
                    self._outgoing[rel.source] = set()
                self._outgoing[rel.source].add(rel.id)
                
                if rel.target not in self._incoming:
                    self._incoming[rel.target] = set()
                self._incoming[rel.target].add(rel.id)
            
            logger.info(f"Loaded {len(self._entities)} entities, {len(self._relations)} relations")
        except Exception as e:
            logger.error(f"Failed to load GraphRAG: {e}")
    
    def _save_to_disk(self):
        """Persist graph to disk."""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'entities': [e.to_dict() for e in self._entities.values()],
                'relations': [r.to_dict() for r in self._relations.values()],
            }
            with open(self._data_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save GraphRAG: {e}")
    
    def _generate_entity_id(self, name: str, entity_type: str) -> str:
        """Generate unique entity ID."""
        content = f"{entity_type}:{name.lower()}"
        return f"ent:{hashlib.md5(content.encode()).hexdigest()[:10]}"
    
    def _generate_relation_id(self, source: str, target: str, rel_type: str) -> str:
        """Generate unique relation ID."""
        content = f"{source}:{rel_type}:{target}"
        return f"rel:{hashlib.md5(content.encode()).hexdigest()[:10]}"
    
    def _extract_with_llm(self, text: str) -> Tuple[List[Dict], List[Dict]]:
        """Use LLM to extract entities and relationships from text."""
        prompt = f"""Extract Linux-related entities and relationships from the following documentation.

Entity types: command, service, config_file, package, concept, directory, port, protocol, filesystem
Relationship types: configures, manages, requires, provides, uses, listens_on, depends_on, related_to

Output JSON with this exact format:
{{
  "entities": [
    {{"name": "nginx", "type": "service", "description": "web server"}},
    {{"name": "systemctl", "type": "command", "description": "systemd control"}}
  ],
  "relations": [
    {{"source": "systemctl", "target": "nginx", "type": "manages", "description": "systemctl manages nginx service"}}
  ]
}}

Documentation:
{text[:4000]}

JSON:"""
        
        try:
            import requests
            from ..model.client import get_ollama_endpoint
            
            endpoint = get_ollama_endpoint()
            response = requests.post(
                f"{endpoint}/api/generate",
                json={
                    "model": self.llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=60
            )
            response.raise_for_status()
            
            result_text = response.json().get("response", "{}")
            result = json.loads(result_text)
            
            return result.get("entities", []), result.get("relations", [])
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return [], []
    
    def _extract_with_patterns(self, text: str) -> Tuple[List[Dict], List[Dict]]:
        """Extract entities using regex patterns (fast fallback)."""
        entities = []
        relations = []
        
        # Command patterns
        command_patterns = [
            r'\b(systemctl|journalctl|pacman|apt|yum|dnf|docker|podman|kubectl)\b',
            r'\b(sudo|chmod|chown|ls|cat|grep|find|sed|awk|curl|wget)\b',
            r'\b(nginx|apache|mysql|postgresql|redis|mongodb)\b',
            r'\b(git|make|gcc|python|pip|npm|cargo)\b',
        ]
        
        for pattern in command_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                cmd = match.group(1).lower()
                entities.append({
                    "name": cmd,
                    "type": LinuxEntityType.COMMAND,
                    "description": f"{cmd} command"
                })
        
        # Config file patterns
        config_pattern = r'(/etc/[\w/.-]+\.(?:conf|cfg|yml|yaml|json|ini))'
        for match in re.finditer(config_pattern, text):
            path = match.group(1)
            entities.append({
                "name": path,
                "type": LinuxEntityType.CONFIG_FILE,
                "description": f"Configuration file {path}"
            })
        
        # Service patterns (*.service)
        service_pattern = r'\b([\w-]+)\.service\b'
        for match in re.finditer(service_pattern, text):
            svc = match.group(1)
            entities.append({
                "name": svc,
                "type": LinuxEntityType.SERVICE,
                "description": f"{svc} systemd service"
            })
        
        # Port patterns
        port_pattern = r'\bport\s+(\d{2,5})\b'
        for match in re.finditer(port_pattern, text, re.IGNORECASE):
            port = match.group(1)
            entities.append({
                "name": port,
                "type": LinuxEntityType.PORT,
                "description": f"Port {port}"
            })
        
        return entities, relations
    
    def add_entity(
        self,
        name: str,
        entity_type: str,
        description: str = "",
        source_doc: Optional[str] = None
    ) -> str:
        """Add or update an entity."""
        name_lower = name.lower()
        
        # Check if exists
        if name_lower in self._entity_by_name:
            ent_id = self._entity_by_name[name_lower]
            ent = self._entities[ent_id]
            if source_doc and source_doc not in ent.source_docs:
                ent.source_docs.append(source_doc)
            return ent_id
        
        # Create new
        ent_id = self._generate_entity_id(name, entity_type)
        entity = GraphEntity(
            id=ent_id,
            name=name,
            entity_type=entity_type,
            description=description,
            source_docs=[source_doc] if source_doc else [],
        )
        
        self._entities[ent_id] = entity
        self._entity_by_name[name_lower] = ent_id
        
        if entity_type not in self._entity_by_type:
            self._entity_by_type[entity_type] = set()
        self._entity_by_type[entity_type].add(ent_id)
        
        return ent_id
    
    def add_relation(
        self,
        source_name: str,
        target_name: str,
        relation_type: str,
        description: str = "",
        source_doc: Optional[str] = None
    ) -> Optional[str]:
        """Add a relationship between entities."""
        # Find or create entities
        source_id = self._entity_by_name.get(source_name.lower())
        target_id = self._entity_by_name.get(target_name.lower())
        
        if not source_id or not target_id:
            logger.debug(f"Cannot add relation: missing entity ({source_name} or {target_name})")
            return None
        
        rel_id = self._generate_relation_id(source_id, target_id, relation_type)
        
        # Check if exists
        if rel_id in self._relations:
            rel = self._relations[rel_id]
            if source_doc and source_doc not in rel.source_docs:
                rel.source_docs.append(source_doc)
            return rel_id
        
        # Create new
        relation = GraphRelation(
            id=rel_id,
            source=source_id,
            target=target_id,
            relation_type=relation_type,
            description=description,
            source_docs=[source_doc] if source_doc else [],
        )
        
        self._relations[rel_id] = relation
        
        if source_id not in self._outgoing:
            self._outgoing[source_id] = set()
        self._outgoing[source_id].add(rel_id)
        
        if target_id not in self._incoming:
            self._incoming[target_id] = set()
        self._incoming[target_id].add(rel_id)
        
        return rel_id
    
    def extract_from_text(
        self,
        text: str,
        doc_id: str,
        use_llm: bool = True
    ) -> Dict[str, int]:
        """
        Extract entities and relationships from text.
        
        Args:
            text: Document text
            doc_id: Document identifier
            use_llm: Use LLM for extraction (slower but better)
        
        Returns:
            Counts of entities and relations added
        """
        entities_added = 0
        relations_added = 0
        
        # Extract using patterns (fast)
        pattern_entities, pattern_relations = self._extract_with_patterns(text)
        
        for ent in pattern_entities:
            self.add_entity(
                name=ent["name"],
                entity_type=ent["type"],
                description=ent.get("description", ""),
                source_doc=doc_id
            )
            entities_added += 1
        
        # Extract using LLM (slow but comprehensive)
        if use_llm:
            llm_entities, llm_relations = self._extract_with_llm(text)
            
            for ent in llm_entities:
                self.add_entity(
                    name=ent.get("name", ""),
                    entity_type=ent.get("type", LinuxEntityType.CONCEPT),
                    description=ent.get("description", ""),
                    source_doc=doc_id
                )
                entities_added += 1
            
            for rel in llm_relations:
                result = self.add_relation(
                    source_name=rel.get("source", ""),
                    target_name=rel.get("target", ""),
                    relation_type=rel.get("type", LinuxRelationType.RELATED_TO),
                    description=rel.get("description", ""),
                    source_doc=doc_id
                )
                if result:
                    relations_added += 1
        
        self._save_to_disk()
        
        return {
            "entities_added": entities_added,
            "relations_added": relations_added,
        }
    
    def query_entity(self, name: str) -> Optional[GraphEntity]:
        """Get entity by name."""
        ent_id = self._entity_by_name.get(name.lower())
        return self._entities.get(ent_id) if ent_id else None
    
    def query_related(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to the given entity.
        
        Args:
            entity_name: Entity to find relations for
            relation_type: Filter by relation type
            direction: 'outgoing', 'incoming', or 'both'
        
        Returns:
            List of related entities with relation info
        """
        ent_id = self._entity_by_name.get(entity_name.lower())
        if not ent_id:
            return []
        
        results = []
        
        # Outgoing relations
        if direction in ("outgoing", "both"):
            for rel_id in self._outgoing.get(ent_id, set()):
                rel = self._relations.get(rel_id)
                if not rel:
                    continue
                if relation_type and rel.relation_type != relation_type:
                    continue
                
                target = self._entities.get(rel.target)
                if target:
                    results.append({
                        "entity": target.to_dict(),
                        "relation": rel.relation_type,
                        "direction": "outgoing",
                        "description": rel.description,
                    })
        
        # Incoming relations
        if direction in ("incoming", "both"):
            for rel_id in self._incoming.get(ent_id, set()):
                rel = self._relations.get(rel_id)
                if not rel:
                    continue
                if relation_type and rel.relation_type != relation_type:
                    continue
                
                source = self._entities.get(rel.source)
                if source:
                    results.append({
                        "entity": source.to_dict(),
                        "relation": rel.relation_type,
                        "direction": "incoming",
                        "description": rel.description,
                    })
        
        return results
    
    def get_graph_context(self, query: str, max_entities: int = 10) -> str:
        """
        Get graph-based context for a query.
        
        Finds relevant entities and their relationships to build context.
        """
        # Extract potential entity names from query
        words = re.findall(r'\b\w+\b', query.lower())
        
        relevant_entities = []
        for word in words:
            if word in self._entity_by_name:
                ent_id = self._entity_by_name[word]
                ent = self._entities.get(ent_id)
                if ent:
                    relevant_entities.append(ent)
        
        if not relevant_entities:
            return ""
        
        # Build context from entities and relations
        context_parts = ["=== Related Knowledge Graph ==="]
        
        for ent in relevant_entities[:max_entities]:
            context_parts.append(f"\n**{ent.name}** ({ent.entity_type})")
            if ent.description:
                context_parts.append(f"  {ent.description}")
            
            # Get relations
            related = self.query_related(ent.name)
            if related:
                context_parts.append("  Relations:")
                for r in related[:5]:
                    rel_ent = r["entity"]
                    direction = "→" if r["direction"] == "outgoing" else "←"
                    context_parts.append(
                        f"    {direction} {r['relation']} {rel_ent['name']} ({rel_ent['entity_type']})"
                    )
        
        return "\n".join(context_parts)
    
    def get_entities_by_type(self, entity_type: str) -> List[GraphEntity]:
        """Get all entities of a given type."""
        ent_ids = self._entity_by_type.get(entity_type, set())
        return [self._entities[eid] for eid in ent_ids if eid in self._entities]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        type_counts = {}
        for ent_type, ent_ids in self._entity_by_type.items():
            type_counts[ent_type] = len(ent_ids)
        
        rel_type_counts = {}
        for rel in self._relations.values():
            rel_type_counts[rel.relation_type] = rel_type_counts.get(rel.relation_type, 0) + 1
        
        return {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "entity_types": type_counts,
            "relation_types": rel_type_counts,
        }


# Singleton accessor
_graphrag_instance: Optional[LinuxGraphRAG] = None

def get_linux_graphrag() -> LinuxGraphRAG:
    """Get singleton LinuxGraphRAG instance."""
    global _graphrag_instance
    if _graphrag_instance is None:
        _graphrag_instance = LinuxGraphRAG()
    return _graphrag_instance


def build_graph_from_collection(
    collection_name: str = "linux_docs",
    max_docs: int = 50,
    use_llm: bool = False
) -> Dict[str, Any]:
    """
    Build knowledge graph from documents in a ChromaDB collection.
    
    Args:
        collection_name: ChromaDB collection to process
        max_docs: Maximum documents to process
        use_llm: Use LLM for extraction (slower but more comprehensive)
    
    Returns:
        Stats about the build process
    """
    from ..index.chroma_index import get_index
    
    graph = get_linux_graphrag()
    idx = get_index()
    
    try:
        col = idx.client.get_collection(collection_name)
        results = col.peek(max_docs)
    except Exception as e:
        logger.error(f"Failed to access collection {collection_name}: {e}")
        return {"error": str(e)}
    
    docs_processed = 0
    total_entities = 0
    total_relations = 0
    
    if results and results.get("documents"):
        documents = results["documents"]
        metadatas = results.get("metadatas", [{}] * len(documents))
        ids = results.get("ids", [f"doc_{i}" for i in range(len(documents))])
        
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            source = meta.get("source", meta.get("title", doc_id))
            
            result = graph.extract_from_text(doc, source, use_llm=use_llm)
            total_entities += result["entities_added"]
            total_relations += result["relations_added"]
            docs_processed += 1
    
    return {
        "collection": collection_name,
        "docs_processed": docs_processed,
        "entities_added": total_entities,
        "relations_added": total_relations,
        "graph_stats": graph.get_stats(),
    }
