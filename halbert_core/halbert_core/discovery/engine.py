# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Discovery Engine - Orchestrates system scanning and discovery storage.

The engine:
1. Manages registered scanners
2. Runs scans on demand or on schedule
3. Stores discoveries in ChromaDB
4. Provides query interface for UI and chat
"""

from __future__ import annotations
from typing import List, Optional, Dict, Type, Callable
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
from .scanners.apps import FlatpakScanner, SnapScanner, AppImageScanner


logger = logging.getLogger('halbert.discovery.engine')


class DiscoveryEngine:
    """
    Central discovery orchestrator for Halbert.
    
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
        # Changed: Use list of scanners per type to support multiple scanners (e.g., Flatpak, Snap, AppImage all use PACKAGE type)
        self._scanners: Dict[DiscoveryType, List[BaseScanner]] = {}
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
        """Initialize ChromaDB for persistent storage using shared client."""
        try:
            # Use the shared index client to avoid SQLite lock contention
            from ..index.chroma_index import get_index
            shared_index = get_index()
            
            if shared_index.client is None:
                logger.warning("Shared ChromaDB client not available, using in-memory storage")
                self.use_chromadb = False
                return
            
            self._chromadb_client = shared_index.client
            self._collection = self._chromadb_client.get_or_create_collection(
                name="discoveries",
                metadata={"description": "Halbert system discoveries"}
            )
            
            logger.debug("Discovery engine using shared ChromaDB client")
        except ImportError:
            logger.warning("ChromaDB not installed, using in-memory storage")
            self.use_chromadb = False
        except Exception as e:
            logger.warning(f"ChromaDB init failed ({e}), using in-memory storage")
            self.use_chromadb = False
    
    def _get_data_dir(self):
        """Get data directory for persistent storage."""
        from pathlib import Path
        data_dir = Path.home() / ".local" / "share" / "halbert"
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
        # Phase 26: App scanners
        self.register_scanner(FlatpakScanner())
        self.register_scanner(SnapScanner())
        self.register_scanner(AppImageScanner())
    
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
        
        # Support multiple scanners per type (e.g., Flatpak, Snap, AppImage all use PACKAGE)
        if scanner.discovery_type not in self._scanners:
            self._scanners[scanner.discovery_type] = []
        self._scanners[scanner.discovery_type].append(scanner)
        logger.debug(f"Registered scanner: {scanner.name}")
    
    def get_scanners(self, discovery_type: DiscoveryType) -> List[BaseScanner]:
        """Get scanners for a discovery type."""
        return self._scanners.get(discovery_type, [])
    
    @property
    def registered_scanners(self) -> List[str]:
        """Get names of registered scanners."""
        names = []
        for scanner_list in self._scanners.values():
            names.extend([s.name for s in scanner_list])
        return names
    
    # ─────────────────────────────────────────────────────────────
    # Scanning
    # ─────────────────────────────────────────────────────────────
    
    def scan_all(self, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> List[Discovery]:
        """
        Run all registered scanners.
        
        Args:
            progress_callback: Optional callback(scanner_name, current, total) for progress updates.
        
        Returns:
            List of all discoveries found.
        """
        all_discoveries = []
        
        # Count total scanners for progress
        all_scanners = []
        for scanner_list in self._scanners.values():
            all_scanners.extend(scanner_list)
        total_scanners = len(all_scanners)
        
        # Iterate over all scanners
        for idx, scanner in enumerate(all_scanners):
            try:
                if progress_callback:
                    progress_callback(scanner.name, idx, total_scanners)
                
                logger.info(f"Running scanner: {scanner.name}")
                discoveries = scanner.scan()
                all_discoveries.extend(discoveries)
                
                # Store discoveries in batch for performance
                self._store_discoveries_batch(discoveries)
                    
            except Exception as e:
                logger.error(f"Scanner {scanner.name} failed: {e}")
        
        # Final callback
        if progress_callback:
            progress_callback("Complete", total_scanners, total_scanners)
        
        self._last_scan = datetime.now()
        logger.info(f"Scan complete. Found {len(all_discoveries)} discoveries.")
        
        return all_discoveries
    
    def scan_type(self, discovery_type: DiscoveryType) -> List[Discovery]:
        """
        Run all scanners for a specific type.
        
        Args:
            discovery_type: Type of discoveries to scan for.
        
        Returns:
            List of discoveries found.
        """
        scanners = self._scanners.get(discovery_type, [])
        if not scanners:
            logger.warning(f"No scanner registered for {discovery_type}")
            return []
        
        all_discoveries = []
        for scanner in scanners:
            try:
                logger.info(f"Running scanner: {scanner.name}")
                discoveries = scanner.scan()
                self._store_discoveries_batch(discoveries)
                all_discoveries.extend(discoveries)
            except Exception as e:
                logger.error(f"Scanner {scanner.name} failed: {e}")
        
        return all_discoveries
    
    # ─────────────────────────────────────────────────────────────
    # Storage
    # ─────────────────────────────────────────────────────────────
    
    def _store_discovery(self, discovery: Discovery):
        """Store a discovery in memory and optionally ChromaDB."""
        with self._lock:
            self._discoveries[discovery.id] = discovery
        
        # Skip ChromaDB for single items - use batch instead
    
    def _store_discoveries_batch(self, discoveries: List[Discovery]):
        """Store discoveries in batch for performance."""
        if not discoveries:
            return
        
        # Store in memory
        with self._lock:
            for d in discoveries:
                self._discoveries[d.id] = d
        
        # Batch upsert to ChromaDB
        if self.use_chromadb and self._collection:
            try:
                self._collection.upsert(
                    ids=[d.id for d in discoveries],
                    documents=[d.embedding_text for d in discoveries],
                    metadatas=[{
                        "type": d.type.value,
                        "severity": d.severity.value,
                        "status": d.status or "",
                        "name": d.name,
                    } for d in discoveries],
                )
            except Exception as e:
                logger.error(f"Failed to batch store in ChromaDB: {e}")
    
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


def get_engine(use_chromadb: bool = True) -> DiscoveryEngine:
    """
    Get the global discovery engine instance.
    
    Args:
        use_chromadb: Enable ChromaDB for persistent vector storage.
                      Default is True for production use.
    """
    global _engine
    if _engine is None:
        _engine = DiscoveryEngine(use_chromadb=use_chromadb)
    return _engine
