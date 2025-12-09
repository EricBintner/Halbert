"""
Discovery Engine - Orchestrates system scanning and discovery storage.

The engine:
1. Manages registered scanners
2. Runs scans on demand or on schedule
3. Stores discoveries in ChromaDB
4. Provides query interface for UI and chat
"""

from __future__ import annotations
from typing import List, Optional, Dict, Type
from datetime import datetime
import logging
import threading
import time

from .schema import Discovery, DiscoveryType, DiscoverySeverity
from .scanners.base import BaseScanner
from .scanners.backup import BackupScanner
from .scanners.service import ServiceScanner
from .scanners.storage import StorageScanner
from .scanners.network import NetworkScanner
from .scanners.security import SecurityScanner
from .scanners.sharing import SharingScanner


logger = logging.getLogger('cerebric.discovery.engine')


class DiscoveryEngine:
    """
    Central discovery orchestrator for Cerebric.
    
    Usage:
        engine = DiscoveryEngine()
        engine.register_scanner(BackupScanner())
        
        # Run all scans
        discoveries = engine.scan_all()
        
        # Query discoveries
        backups = engine.get_by_type(DiscoveryType.BACKUP)
        by_id = engine.get_by_id("backup/rsync-home")
    """
    
    def __init__(self, use_chromadb: bool = False):
        """
        Initialize the discovery engine.
        
        Args:
            use_chromadb: Enable ChromaDB storage (requires chromadb package)
        """
        self._scanners: Dict[DiscoveryType, BaseScanner] = {}
        self._discoveries: Dict[str, Discovery] = {}
        self._lock = threading.Lock()
        self._last_scan: Optional[datetime] = None
        
        self.use_chromadb = use_chromadb
        self._chromadb_client = None
        self._collection = None
        
        if use_chromadb:
            self._init_chromadb()
        
        # Register default scanners
        self._register_default_scanners()
    
    def _init_chromadb(self):
        """Initialize ChromaDB for persistent storage."""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Use persistent storage
            self._chromadb_client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self._get_data_dir() / "chromadb"),
                anonymized_telemetry=False,
            ))
            
            self._collection = self._chromadb_client.get_or_create_collection(
                name="discoveries",
                metadata={"description": "Cerebric system discoveries"}
            )
            
            logger.info("ChromaDB initialized for discovery storage")
        except ImportError:
            logger.warning("ChromaDB not installed, using in-memory storage")
            self.use_chromadb = False
    
    def _get_data_dir(self):
        """Get data directory for persistent storage."""
        from pathlib import Path
        data_dir = Path.home() / ".local" / "share" / "cerebric"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    def _register_default_scanners(self):
        """Register built-in scanners."""
        self.register_scanner(BackupScanner())
        self.register_scanner(ServiceScanner())
        self.register_scanner(StorageScanner())
        self.register_scanner(NetworkScanner())
        self.register_scanner(SecurityScanner())
        self.register_scanner(SharingScanner())
    
    # ─────────────────────────────────────────────────────────────
    # Scanner Management
    # ─────────────────────────────────────────────────────────────
    
    def register_scanner(self, scanner: BaseScanner):
        """
        Register a scanner with the engine.
        
        Args:
            scanner: Scanner instance to register
        """
        if not scanner.is_available():
            logger.info(f"Scanner {scanner.name} not available on this system")
            return
        
        self._scanners[scanner.discovery_type] = scanner
        logger.debug(f"Registered scanner: {scanner.name}")
    
    def get_scanner(self, discovery_type: DiscoveryType) -> Optional[BaseScanner]:
        """Get scanner for a discovery type."""
        return self._scanners.get(discovery_type)
    
    @property
    def registered_scanners(self) -> List[str]:
        """Get names of registered scanners."""
        return [s.name for s in self._scanners.values()]
    
    # ─────────────────────────────────────────────────────────────
    # Scanning
    # ─────────────────────────────────────────────────────────────
    
    def scan_all(self) -> List[Discovery]:
        """
        Run all registered scanners.
        
        Returns:
            List of all discoveries found.
        """
        all_discoveries = []
        
        for scanner in self._scanners.values():
            try:
                logger.info(f"Running scanner: {scanner.name}")
                discoveries = scanner.scan()
                all_discoveries.extend(discoveries)
                
                # Store discoveries
                for d in discoveries:
                    self._store_discovery(d)
                    
            except Exception as e:
                logger.error(f"Scanner {scanner.name} failed: {e}")
        
        self._last_scan = datetime.now()
        logger.info(f"Scan complete. Found {len(all_discoveries)} discoveries.")
        
        return all_discoveries
    
    def scan_type(self, discovery_type: DiscoveryType) -> List[Discovery]:
        """
        Run scanner for a specific type.
        
        Args:
            discovery_type: Type of discoveries to scan for.
        
        Returns:
            List of discoveries found.
        """
        scanner = self._scanners.get(discovery_type)
        if not scanner:
            logger.warning(f"No scanner registered for {discovery_type}")
            return []
        
        try:
            discoveries = scanner.scan()
            for d in discoveries:
                self._store_discovery(d)
            return discoveries
        except Exception as e:
            logger.error(f"Scanner {scanner.name} failed: {e}")
            return []
    
    # ─────────────────────────────────────────────────────────────
    # Storage
    # ─────────────────────────────────────────────────────────────
    
    def _store_discovery(self, discovery: Discovery):
        """Store a discovery in memory and optionally ChromaDB."""
        with self._lock:
            self._discoveries[discovery.id] = discovery
        
        if self.use_chromadb and self._collection:
            try:
                self._collection.upsert(
                    ids=[discovery.id],
                    documents=[discovery.embedding_text],
                    metadatas=[{
                        "type": discovery.type.value,
                        "severity": discovery.severity.value,
                        "status": discovery.status or "",
                        "name": discovery.name,
                    }],
                )
            except Exception as e:
                logger.error(f"Failed to store in ChromaDB: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # Query Interface
    # ─────────────────────────────────────────────────────────────
    
    def get_all(self) -> List[Discovery]:
        """Get all discoveries."""
        with self._lock:
            return list(self._discoveries.values())
    
    def get_by_id(self, discovery_id: str) -> Optional[Discovery]:
        """Get a discovery by ID."""
        with self._lock:
            return self._discoveries.get(discovery_id)
    
    def get_by_type(self, discovery_type: DiscoveryType) -> List[Discovery]:
        """Get all discoveries of a specific type."""
        with self._lock:
            return [
                d for d in self._discoveries.values()
                if d.type == discovery_type
            ]
    
    def get_by_severity(self, severity: DiscoverySeverity) -> List[Discovery]:
        """Get all discoveries with a specific severity."""
        with self._lock:
            return [
                d for d in self._discoveries.values()
                if d.severity == severity
            ]
    
    def get_critical(self) -> List[Discovery]:
        """Get all critical discoveries."""
        return self.get_by_severity(DiscoverySeverity.CRITICAL)
    
    def get_warnings(self) -> List[Discovery]:
        """Get all warning discoveries."""
        return self.get_by_severity(DiscoverySeverity.WARNING)
    
    def search(self, query: str, limit: int = 10) -> List[Discovery]:
        """
        Search discoveries by text.
        
        Uses ChromaDB semantic search if available,
        otherwise falls back to simple text matching.
        """
        if self.use_chromadb and self._collection:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=limit,
                )
                
                discovery_ids = results.get('ids', [[]])[0]
                return [
                    self._discoveries[id_] 
                    for id_ in discovery_ids 
                    if id_ in self._discoveries
                ]
            except Exception as e:
                logger.error(f"ChromaDB search failed: {e}")
        
        # Fallback: simple text matching
        query_lower = query.lower()
        matches = []
        
        with self._lock:
            for d in self._discoveries.values():
                if (query_lower in d.name.lower() or
                    query_lower in d.title.lower() or
                    query_lower in d.description.lower()):
                    matches.append(d)
        
        return matches[:limit]
    
    def resolve_mention(self, mention: str) -> Optional[Discovery]:
        """
        Resolve an @mention to a discovery.
        
        Args:
            mention: Mention string like "@backup/rsync-home"
        
        Returns:
            Discovery if found, None otherwise.
        """
        # Strip @ prefix if present
        if mention.startswith('@'):
            mention = mention[1:]
        
        return self.get_by_id(mention)
    
    def get_mentionables(self) -> List[dict]:
        """
        Get list of mentionable discoveries for autocomplete.
        
        Returns:
            List of dicts with 'id', 'name', 'type', 'icon' keys.
        """
        with self._lock:
            return [
                {
                    "id": d.id,
                    "mention": d.mention,
                    "name": d.name,
                    "type": d.type.value,
                    "icon": d.icon,
                }
                for d in self._discoveries.values()
                if d.mentionable
            ]
    
    # ─────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────
    
    def get_stats(self) -> dict:
        """Get discovery statistics."""
        with self._lock:
            by_type = {}
            by_severity = {}
            
            for d in self._discoveries.values():
                by_type[d.type.value] = by_type.get(d.type.value, 0) + 1
                by_severity[d.severity.value] = by_severity.get(d.severity.value, 0) + 1
            
            return {
                "total": len(self._discoveries),
                "by_type": by_type,
                "by_severity": by_severity,
                "last_scan": self._last_scan.isoformat() if self._last_scan else None,
                "scanners": self.registered_scanners,
            }
    
    def to_dict(self) -> dict:
        """Export all discoveries as dict."""
        return {
            "discoveries": [d.to_dict() for d in self.get_all()],
            "stats": self.get_stats(),
        }


# Singleton instance for easy access
_engine: Optional[DiscoveryEngine] = None


def get_engine() -> DiscoveryEngine:
    """Get the global discovery engine instance."""
    global _engine
    if _engine is None:
        _engine = DiscoveryEngine()
    return _engine
