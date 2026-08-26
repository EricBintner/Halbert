# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
RAG Data Freshness Management

Provides:
1. Data version manifest for tracking RAG corpus versions
2. Staleness detection for individual documents
3. Update checking against remote (HuggingFace) releases
4. Freshness-aware query routing (prefer live search for stale topics)

Phase 54: Data Freshness Strategy
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib

logger = logging.getLogger("halbert")


# Staleness thresholds (in days)
STALENESS_THRESHOLDS = {
    "fresh": 30,        # < 30 days old = fresh
    "aging": 90,        # 30-90 days = aging  
    "stale": 180,       # 90-180 days = stale
    "outdated": 365,    # > 365 days = outdated
}

# Sources that change frequently (prefer live search when stale)
VOLATILE_SOURCES = [
    "arch_wiki",        # Wiki pages updated frequently
    "stackoverflow",    # Answers get updated
    "serverfault",      # Same
    "vendor_docs",      # Software docs change with versions
]

# Sources that are relatively stable (staleness less critical)
STABLE_SOURCES = [
    "linux_man",        # Man pages change slowly
    "man_pages",        # Same
    "tldr",             # Curated, updated periodically
    "unix_commands",    # Fundamental commands don't change
]

# Topics that benefit from live search regardless of data age
TIME_SENSITIVE_TOPICS = [
    "latest", "newest", "current version", "update", "upgrade",
    "release", "changelog", "security", "cve", "vulnerability",
    "deprecated", "removed", "breaking change", "migration",
    "2024", "2025", "2026",  # Year references suggest currency matters
]


@dataclass
class DataManifest:
    """
    Manifest describing a RAG data corpus version.
    
    Stored alongside data files to track versioning.
    """
    version: str                          # Semantic version (e.g., "1.2.0")
    release_date: str                     # ISO date of this release
    description: str                      # What's in this version
    sources: Dict[str, Dict[str, Any]]    # Per-source metadata
    total_documents: int = 0
    total_chunks: int = 0
    index_schema_version: str = "1.0"     # For compatibility checking
    
    # Remote update info
    remote_url: str = ""                  # HuggingFace dataset URL
    check_updates_url: str = ""           # URL to check for updates
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "release_date": self.release_date,
            "description": self.description,
            "sources": self.sources,
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "index_schema_version": self.index_schema_version,
            "remote_url": self.remote_url,
            "check_updates_url": self.check_updates_url,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataManifest':
        return cls(
            version=data.get("version", "0.0.0"),
            release_date=data.get("release_date", ""),
            description=data.get("description", ""),
            sources=data.get("sources", {}),
            total_documents=data.get("total_documents", 0),
            total_chunks=data.get("total_chunks", 0),
            index_schema_version=data.get("index_schema_version", "1.0"),
            remote_url=data.get("remote_url", ""),
            check_updates_url=data.get("check_updates_url", ""),
        )
    
    def save(self, path: Path):
        """Save manifest to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved data manifest v{self.version} to {path}")
    
    @classmethod
    def load(cls, path: Path) -> Optional['DataManifest']:
        """Load manifest from JSON file."""
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load manifest from {path}: {e}")
            return None


@dataclass
class FreshnessInfo:
    """Information about data freshness for a single document or query result."""
    scraped_at: Optional[datetime] = None
    age_days: int = 0
    freshness_level: str = "unknown"      # fresh, aging, stale, outdated, unknown
    source: str = ""
    is_volatile_source: bool = False
    recommend_live_search: bool = False
    warning_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "age_days": self.age_days,
            "freshness_level": self.freshness_level,
            "source": self.source,
            "is_volatile_source": self.is_volatile_source,
            "recommend_live_search": self.recommend_live_search,
            "warning_message": self.warning_message,
        }


class FreshnessChecker:
    """
    Checks and manages RAG data freshness.
    
    Responsibilities:
    - Parse scraped_at timestamps from documents
    - Determine freshness level
    - Generate staleness warnings
    - Recommend when to use live search
    """
    
    def __init__(
        self,
        staleness_thresholds: Optional[Dict[str, int]] = None,
        volatile_sources: Optional[List[str]] = None,
        stable_sources: Optional[List[str]] = None,
    ):
        self.thresholds = staleness_thresholds or STALENESS_THRESHOLDS
        self.volatile_sources = volatile_sources or VOLATILE_SOURCES
        self.stable_sources = stable_sources or STABLE_SOURCES
    
    def check_document(
        self,
        doc: Dict[str, Any],
        query: Optional[str] = None
    ) -> FreshnessInfo:
        """
        Check freshness of a single document.
        
        Args:
            doc: Document dict with metadata
            query: Optional query for context-aware recommendations
            
        Returns:
            FreshnessInfo with staleness assessment
        """
        info = FreshnessInfo()
        
        # Extract source
        info.source = (
            doc.get("source") or 
            doc.get("metadata", {}).get("source", "") or
            ""
        )
        info.is_volatile_source = info.source.lower() in [s.lower() for s in self.volatile_sources]
        
        # Extract and parse scraped_at
        scraped_at_str = (
            doc.get("scraped_at") or
            doc.get("metadata", {}).get("scraped_at", "")
        )
        
        if scraped_at_str:
            info.scraped_at = self._parse_timestamp(scraped_at_str)
        
        if info.scraped_at:
            # Calculate age
            now = datetime.now()
            age = now - info.scraped_at
            info.age_days = age.days
            
            # Determine freshness level
            info.freshness_level = self._get_freshness_level(info.age_days)
            
            # Generate warning if stale
            if info.freshness_level in ("stale", "outdated"):
                info.warning_message = self._generate_warning(info)
                
                # Recommend live search for volatile sources when stale
                if info.is_volatile_source:
                    info.recommend_live_search = True
        else:
            info.freshness_level = "unknown"
        
        # Check if query suggests time-sensitivity
        if query and self._is_time_sensitive_query(query):
            info.recommend_live_search = True
            if not info.warning_message:
                info.warning_message = "This query may benefit from current web results."
        
        return info
    
    def check_results(
        self,
        results: List[Dict[str, Any]],
        query: str
    ) -> Tuple[List[FreshnessInfo], str]:
        """
        Check freshness of multiple results and generate aggregate warning.
        
        Args:
            results: List of document results
            query: The search query
            
        Returns:
            Tuple of (per-document freshness info, aggregate warning message)
        """
        freshness_infos = []
        stale_count = 0
        oldest_days = 0
        
        for doc in results:
            info = self.check_document(doc, query)
            freshness_infos.append(info)
            
            if info.freshness_level in ("stale", "outdated"):
                stale_count += 1
            if info.age_days > oldest_days:
                oldest_days = info.age_days
        
        # Generate aggregate warning
        aggregate_warning = ""
        
        if stale_count > 0:
            if stale_count == len(results):
                aggregate_warning = f"⚠️ All results are from data scraped {oldest_days}+ days ago. Consider verifying with current documentation."
            elif stale_count > len(results) // 2:
                aggregate_warning = f"⚠️ Most results ({stale_count}/{len(results)}) are from older data. Some information may be outdated."
        
        # Add time-sensitive query warning
        if self._is_time_sensitive_query(query):
            if aggregate_warning:
                aggregate_warning += " This query may benefit from live web search."
            else:
                aggregate_warning = "ℹ️ This query may benefit from current web search results."
        
        return freshness_infos, aggregate_warning
    
    def should_prefer_live_search(
        self,
        query: str,
        rag_results: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, str]:
        """
        Determine if live web search should be preferred over cached RAG.
        
        Args:
            query: User query
            rag_results: Optional RAG results to check staleness
            
        Returns:
            Tuple of (should_use_live, reason)
        """
        reasons = []
        
        # Check if query is time-sensitive
        if self._is_time_sensitive_query(query):
            reasons.append("query requests current information")
        
        # Check RAG results staleness
        if rag_results:
            _, warning = self.check_results(rag_results, query)
            if warning and "outdated" in warning.lower():
                reasons.append("cached results are outdated")
        
        if reasons:
            return True, "; ".join(reasons)
        
        return False, ""
    
    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse various timestamp formats."""
        if not ts_str:
            return None
        
        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",      # ISO with microseconds
            "%Y-%m-%dT%H:%M:%S",          # ISO basic
            "%Y-%m-%dT%H:%M:%S.%fZ",      # ISO with Z
            "%Y-%m-%dT%H:%M:%SZ",         # ISO with Z
            "%Y-%m-%d %H:%M:%S",          # Space-separated
            "%Y-%m-%d",                   # Date only
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(ts_str[:26], fmt)
            except ValueError:
                continue
        
        logger.debug(f"Could not parse timestamp: {ts_str}")
        return None
    
    def _get_freshness_level(self, age_days: int) -> str:
        """Determine freshness level from age in days."""
        if age_days < self.thresholds["fresh"]:
            return "fresh"
        elif age_days < self.thresholds["aging"]:
            return "aging"
        elif age_days < self.thresholds["stale"]:
            return "stale"
        else:
            return "outdated"
    
    def _generate_warning(self, info: FreshnessInfo) -> str:
        """Generate human-readable staleness warning."""
        if info.age_days < 60:
            age_str = f"{info.age_days} days"
        elif info.age_days < 365:
            months = info.age_days // 30
            age_str = f"{months} month{'s' if months > 1 else ''}"
        else:
            years = info.age_days // 365
            age_str = f"{years} year{'s' if years > 1 else ''}"
        
        source_note = ""
        if info.is_volatile_source:
            source_note = f" ({info.source} content updates frequently)"
        
        return f"This information is {age_str} old{source_note}. Verify with current documentation if critical."
    
    def _is_time_sensitive_query(self, query: str) -> bool:
        """Check if query suggests need for current information."""
        query_lower = query.lower()
        return any(term in query_lower for term in TIME_SENSITIVE_TOPICS)


@dataclass
class UpdateInfo:
    """Information about available data updates."""
    current_version: str
    latest_version: str
    update_available: bool
    release_date: str = ""
    release_notes: str = ""
    download_url: str = ""
    size_mb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "release_date": self.release_date,
            "release_notes": self.release_notes,
            "download_url": self.download_url,
            "size_mb": self.size_mb,
        }


class UpdateChecker:
    """
    Checks for RAG data updates from remote sources (e.g., HuggingFace).
    
    Compares local manifest version against remote releases.
    """
    
    def __init__(
        self,
        manifest_path: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.manifest_path = manifest_path
        self.cache_dir = cache_dir or Path.home() / ".cache" / "halbert" / "rag"
        self._manifest: Optional[DataManifest] = None
        self._last_check: Optional[datetime] = None
        self._check_interval = timedelta(hours=24)  # Check once per day
    
    @property
    def manifest(self) -> Optional[DataManifest]:
        """Get current manifest (lazy load)."""
        if self._manifest is None and self.manifest_path:
            self._manifest = DataManifest.load(self.manifest_path)
        return self._manifest
    
    def get_current_version(self) -> str:
        """Get currently installed data version."""
        if self.manifest:
            return self.manifest.version
        return "unknown"
    
    def get_release_date(self) -> str:
        """Get release date of current data."""
        if self.manifest:
            return self.manifest.release_date
        return "unknown"
    
    async def check_for_updates(self, force: bool = False) -> Optional[UpdateInfo]:
        """
        Check for available updates from remote source.
        
        Args:
            force: Force check even if recently checked
            
        Returns:
            UpdateInfo if check succeeded, None otherwise
        """
        # Rate limit checks
        if not force and self._last_check:
            if datetime.now() - self._last_check < self._check_interval:
                logger.debug("Skipping update check (checked recently)")
                return None
        
        self._last_check = datetime.now()
        
        if not self.manifest or not self.manifest.check_updates_url:
            logger.debug("No update URL configured")
            return None
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.manifest.check_updates_url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Update check failed: HTTP {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    latest_version = data.get("version", "0.0.0")
                    current_version = self.manifest.version
                    
                    update_available = self._compare_versions(current_version, latest_version) < 0
                    
                    return UpdateInfo(
                        current_version=current_version,
                        latest_version=latest_version,
                        update_available=update_available,
                        release_date=data.get("release_date", ""),
                        release_notes=data.get("release_notes", ""),
                        download_url=data.get("download_url", ""),
                        size_mb=data.get("size_mb", 0.0),
                    )
                    
        except ImportError:
            logger.warning("aiohttp not available for update check")
            return None
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
            return None
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare semantic versions. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
        def parse_version(v: str) -> Tuple[int, ...]:
            try:
                return tuple(int(x) for x in v.split("."))
            except ValueError:
                return (0, 0, 0)
        
        p1, p2 = parse_version(v1), parse_version(v2)
        
        if p1 < p2:
            return -1
        elif p1 > p2:
            return 1
        return 0


def create_manifest(
    version: str,
    description: str,
    sources: Dict[str, Dict[str, Any]],
    output_path: Path,
    remote_url: str = "",
) -> DataManifest:
    """
    Create a new data manifest for a RAG corpus release.
    
    Args:
        version: Semantic version string
        description: Release description
        sources: Dict mapping source name to metadata
        output_path: Where to save the manifest
        remote_url: Optional HuggingFace URL
        
    Returns:
        Created manifest
    """
    total_docs = sum(s.get("document_count", 0) for s in sources.values())
    total_chunks = sum(s.get("chunk_count", 0) for s in sources.values())
    
    manifest = DataManifest(
        version=version,
        release_date=datetime.now().isoformat()[:10],
        description=description,
        sources=sources,
        total_documents=total_docs,
        total_chunks=total_chunks,
        remote_url=remote_url,
    )
    
    manifest.save(output_path)
    return manifest


# Global freshness checker instance
_freshness_checker: Optional[FreshnessChecker] = None


def get_freshness_checker() -> FreshnessChecker:
    """Get or create global freshness checker."""
    global _freshness_checker
    if _freshness_checker is None:
        _freshness_checker = FreshnessChecker()
    return _freshness_checker
