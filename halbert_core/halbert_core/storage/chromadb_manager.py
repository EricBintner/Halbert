"""
ChromaDB storage management for Halbert.

Provides:
- Storage health monitoring (size, orphan detection)
- Safe cleanup of orphaned collections (resumable, non-destructive)
- Disk type detection for performance recommendations
- Storage metrics for the settings UI
"""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger("halbert.storage")


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


class DiskType(str, Enum):
    NVME = "nvme"
    SSD = "ssd"
    HDD = "hdd"
    OPTANE = "optane"
    UNKNOWN = "unknown"


@dataclass
class OrphanedDirectory:
    """Represents an orphaned ChromaDB collection directory."""
    id: str
    path: str
    size_bytes: int
    size_human: str
    modified: Optional[str] = None


@dataclass
class CollectionInfo:
    """Information about an active ChromaDB collection."""
    name: str
    id: str
    count: int
    size_bytes: int = 0
    size_human: str = "0 B"


@dataclass
class DiskInfo:
    """Information about the storage disk."""
    mount_point: str
    total_bytes: int
    free_bytes: int
    used_bytes: int
    disk_type: DiskType = DiskType.UNKNOWN
    device: str = ""


@dataclass
class CleanupState:
    """Tracks cleanup progress for resumability."""
    job_id: str
    started_at: str
    orphans_to_delete: List[str]
    deleted: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    bytes_freed: int = 0
    completed: bool = False
    error: Optional[str] = None


@dataclass
class StorageMetrics:
    """Complete storage metrics for ChromaDB."""
    status: HealthStatus
    location: str
    total_size_bytes: int
    total_size_human: str
    sqlite_size_bytes: int
    sqlite_size_human: str
    active_collections: List[CollectionInfo]
    orphaned_data: Dict[str, Any]
    disk_info: DiskInfo
    last_cleanup: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)


def _format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    if size_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(size_bytes) < 1024:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} EB"


def _is_valid_uuid(s: str) -> bool:
    """Check if string is a valid UUID format."""
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(s))


def _get_dir_size(path: str) -> int:
    """
    Get actual disk usage of a directory recursively.
    
    Uses st_blocks * 512 instead of st_size to handle sparse files correctly.
    This matches what `du` reports (actual disk blocks used).
    """
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        stat = entry.stat(follow_symlinks=False)
                        # Use st_blocks * 512 for actual disk usage (handles sparse files)
                        # st_blocks is in 512-byte units on Linux
                        total += stat.st_blocks * 512
                    elif entry.is_dir(follow_symlinks=False):
                        total += _get_dir_size(entry.path)
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def _detect_disk_type(path: str) -> DiskType:
    """Detect the type of disk where path is located."""
    try:
        # Get the device for this path
        stat_info = os.statvfs(path)
        
        # Try to find device from /proc/mounts
        real_path = os.path.realpath(path)
        
        with open("/proc/mounts", "r") as f:
            mounts = f.readlines()
        
        # Find the mount point for this path
        best_match = ""
        device = ""
        for line in mounts:
            parts = line.split()
            if len(parts) >= 2:
                mount_point = parts[1]
                if real_path.startswith(mount_point) and len(mount_point) > len(best_match):
                    best_match = mount_point
                    device = parts[0]
        
        if not device:
            return DiskType.UNKNOWN
        
        # Extract device name (e.g., nvme0n1 from /dev/nvme0n1p1)
        device_name = os.path.basename(device)
        
        # Remove partition number
        base_device = re.sub(r'p?\d+$', '', device_name)
        
        # Check for NVMe
        if base_device.startswith("nvme"):
            # Check if it's Optane
            try:
                model_path = f"/sys/block/{base_device}/device/model"
                if os.path.exists(model_path):
                    with open(model_path, "r") as f:
                        model = f.read().strip().lower()
                        if "optane" in model or "3dxpoint" in model:
                            return DiskType.OPTANE
            except Exception:
                pass
            return DiskType.NVME
        
        # Check rotational flag for SSD vs HDD
        rotational_path = f"/sys/block/{base_device}/queue/rotational"
        if os.path.exists(rotational_path):
            with open(rotational_path, "r") as f:
                if f.read().strip() == "0":
                    return DiskType.SSD
                else:
                    return DiskType.HDD
        
        return DiskType.UNKNOWN
        
    except Exception as e:
        logger.debug(f"Could not detect disk type: {e}")
        return DiskType.UNKNOWN


def _get_disk_info(path: str) -> DiskInfo:
    """Get disk information for the given path."""
    try:
        stat = os.statvfs(path)
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        
        # Find mount point
        real_path = os.path.realpath(path)
        mount_point = real_path
        
        try:
            with open("/proc/mounts", "r") as f:
                mounts = f.readlines()
            
            best_match = ""
            device = ""
            for line in mounts:
                parts = line.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    if real_path.startswith(mp) and len(mp) > len(best_match):
                        best_match = mp
                        device = parts[0]
            
            if best_match:
                mount_point = best_match
        except Exception:
            pass
        
        return DiskInfo(
            mount_point=mount_point,
            total_bytes=total,
            free_bytes=free,
            used_bytes=used,
            disk_type=_detect_disk_type(path),
            device=device if 'device' in dir() else ""
        )
    except Exception as e:
        logger.warning(f"Could not get disk info: {e}")
        return DiskInfo(
            mount_point=path,
            total_bytes=0,
            free_bytes=0,
            used_bytes=0,
            disk_type=DiskType.UNKNOWN
        )


class ChromaDBManager:
    """
    Manages ChromaDB storage health and cleanup.
    
    Usage:
        manager = ChromaDBManager()
        metrics = manager.get_storage_metrics()
        
        if metrics.orphaned_data["count"] > 0:
            # Preview what will be deleted
            orphans = manager.list_orphans()
            
            # Run cleanup
            manager.cleanup_orphans(progress_callback=lambda p: print(f"{p}%"))
    """
    
    def __init__(self, chroma_path: Optional[str] = None):
        """
        Initialize the ChromaDB manager.
        
        Args:
            chroma_path: Path to ChromaDB storage. Defaults to XDG data dir.
        """
        if chroma_path:
            self._chroma_path = Path(chroma_path)
        else:
            from ..utils.paths import data_dir
            self._chroma_path = Path(data_dir()) / "chromadb"
        
        self._cleanup_lock = threading.Lock()
        self._current_cleanup: Optional[CleanupState] = None
    
    @property
    def chroma_path(self) -> Path:
        return self._chroma_path
    
    def _get_state_file(self) -> Path:
        """Get path to cleanup state file."""
        return self._chroma_path / ".cleanup_state.json"
    
    def _get_last_cleanup_file(self) -> Path:
        """Get path to last cleanup timestamp file."""
        return self._chroma_path / ".last_cleanup"
    
    def _save_cleanup_state(self, state: CleanupState) -> None:
        """Save cleanup state for resumability."""
        state_file = self._get_state_file()
        try:
            with open(state_file, "w") as f:
                json.dump(asdict(state), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cleanup state: {e}")
    
    def _load_cleanup_state(self) -> Optional[CleanupState]:
        """Load existing cleanup state if any."""
        state_file = self._get_state_file()
        if not state_file.exists():
            return None
        try:
            with open(state_file, "r") as f:
                data = json.load(f)
                return CleanupState(**data)
        except Exception as e:
            logger.warning(f"Could not load cleanup state: {e}")
            return None
    
    def _clear_cleanup_state(self) -> None:
        """Remove cleanup state file after successful completion."""
        state_file = self._get_state_file()
        try:
            state_file.unlink(missing_ok=True)
        except Exception:
            pass
    
    def _record_last_cleanup(self) -> None:
        """Record timestamp of last successful cleanup."""
        try:
            with open(self._get_last_cleanup_file(), "w") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass
    
    def _get_last_cleanup(self) -> Optional[str]:
        """Get timestamp of last successful cleanup."""
        try:
            cleanup_file = self._get_last_cleanup_file()
            if cleanup_file.exists():
                return cleanup_file.read_text().strip()
        except Exception:
            pass
        return None
    
    def get_active_collection_ids(self) -> set:
        """Get set of active collection UUIDs from ChromaDB."""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self._chroma_path))
            collections = client.list_collections()
            return {str(c.id) for c in collections}
        except ImportError:
            logger.warning("ChromaDB not installed")
            return set()
        except Exception as e:
            logger.warning(f"Could not get active collections: {e}")
            return set()
    
    def _get_collection_segment_ids(self) -> Dict[str, List[str]]:
        """Get mapping of collection IDs to their segment IDs from SQLite."""
        collection_segments: Dict[str, List[str]] = {}
        sqlite_path = self._chroma_path / "chroma.sqlite3"
        
        if not sqlite_path.exists():
            return collection_segments
        
        try:
            import sqlite3
            conn = sqlite3.connect(str(sqlite_path))
            cur = conn.cursor()
            # Get segment IDs for vector segments (these have directories on disk)
            cur.execute("""
                SELECT id, collection FROM segments 
                WHERE scope = 'VECTOR' AND type LIKE '%hnsw-local-persisted%'
            """)
            for segment_id, collection_id in cur.fetchall():
                if collection_id not in collection_segments:
                    collection_segments[collection_id] = []
                collection_segments[collection_id].append(segment_id)
            conn.close()
        except Exception as e:
            logger.debug(f"Could not query segments: {e}")
        
        return collection_segments
    
    def get_active_collections(self) -> List[CollectionInfo]:
        """Get list of active collections with metadata."""
        collections = []
        
        # Get segment ID mapping
        segment_map = self._get_collection_segment_ids()
        
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self._chroma_path))
            
            for col in client.list_collections():
                try:
                    count = col.count()
                    
                    # Get size from segment directories
                    size = 0
                    col_id = str(col.id)
                    if col_id in segment_map:
                        for segment_id in segment_map[col_id]:
                            segment_dir = self._chroma_path / segment_id
                            if segment_dir.exists():
                                size += _get_dir_size(str(segment_dir))
                    
                    collections.append(CollectionInfo(
                        name=col.name,
                        id=col_id,
                        count=count,
                        size_bytes=size,
                        size_human=_format_bytes(size)
                    ))
                except Exception as e:
                    logger.debug(f"Could not get info for collection {col.name}: {e}")
                    collections.append(CollectionInfo(
                        name=col.name,
                        id=str(col.id),
                        count=0
                    ))
        except ImportError:
            logger.warning("ChromaDB not installed")
        except Exception as e:
            logger.warning(f"Could not list collections: {e}")
        
        return sorted(collections, key=lambda c: -c.count)
    
    def _get_active_segment_ids(self) -> set:
        """Get all active segment IDs from SQLite (these are the directory names on disk)."""
        segment_ids = set()
        sqlite_path = self._chroma_path / "chroma.sqlite3"
        
        if not sqlite_path.exists():
            return segment_ids
        
        try:
            import sqlite3
            conn = sqlite3.connect(str(sqlite_path))
            cur = conn.cursor()
            # Get ALL segment IDs (both VECTOR and METADATA types)
            cur.execute("SELECT id FROM segments")
            for (segment_id,) in cur.fetchall():
                segment_ids.add(segment_id)
            conn.close()
        except Exception as e:
            logger.debug(f"Could not query segments: {e}")
        
        return segment_ids
    
    def list_orphans(self) -> List[OrphanedDirectory]:
        """List orphaned segment directories (directories not in active segments)."""
        orphans = []
        
        if not self._chroma_path.exists():
            return orphans
        
        # Get active SEGMENT IDs (not collection IDs) - these match directory names
        active_segment_ids = self._get_active_segment_ids()
        
        try:
            for entry in os.scandir(self._chroma_path):
                if entry.is_dir(follow_symlinks=False) and _is_valid_uuid(entry.name):
                    if entry.name not in active_segment_ids:
                        try:
                            size = _get_dir_size(entry.path)
                            stat = entry.stat(follow_symlinks=False)
                            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                        except Exception:
                            size = 0
                            modified = None
                        
                        orphans.append(OrphanedDirectory(
                            id=entry.name,
                            path=entry.path,
                            size_bytes=size,
                            size_human=_format_bytes(size),
                            modified=modified
                        ))
        except Exception as e:
            logger.warning(f"Could not scan for orphans: {e}")
        
        # Sort by size descending
        return sorted(orphans, key=lambda o: -o.size_bytes)
    
    def get_storage_metrics(self) -> StorageMetrics:
        """Get comprehensive storage metrics for the settings UI."""
        warnings = []
        tips = []
        
        # Get SQLite size
        sqlite_path = self._chroma_path / "chroma.sqlite3"
        sqlite_size = sqlite_path.stat().st_size if sqlite_path.exists() else 0
        
        # Get active collections
        active_collections = self.get_active_collections()
        
        # Get orphans
        orphans = self.list_orphans()
        orphan_total = sum(o.size_bytes for o in orphans)
        
        # Calculate total size
        total_size = sqlite_size + orphan_total
        for col in active_collections:
            total_size += col.size_bytes
        
        # Get disk info
        disk_info = _get_disk_info(str(self._chroma_path))
        
        # Determine health status
        status = HealthStatus.HEALTHY
        
        # Check for orphans
        if orphan_total > 1024 * 1024 * 1024:  # > 1GB
            status = HealthStatus.WARNING
            warnings.append(f"Large orphaned data detected: {_format_bytes(orphan_total)}")
        elif orphan_total > 100 * 1024 * 1024:  # > 100MB
            status = HealthStatus.WARNING
            warnings.append(f"Orphaned data detected: {_format_bytes(orphan_total)}")
        
        # Check disk space
        if disk_info.free_bytes > 0:
            free_percent = disk_info.free_bytes / disk_info.total_bytes * 100
            if free_percent < 10:
                status = HealthStatus.WARNING
                warnings.append(f"Low disk space: {free_percent:.1f}% free")
        
        # Add tips based on disk type
        if disk_info.disk_type == DiskType.OPTANE:
            tips.append("Intel Optane detected! Optimal for vector database workloads.")
        elif disk_info.disk_type == DiskType.NVME:
            tips.append("NVMe SSD provides good performance for vector search.")
        elif disk_info.disk_type == DiskType.SSD:
            tips.append("SATA SSD is acceptable but NVMe would be faster.")
        elif disk_info.disk_type == DiskType.HDD:
            tips.append("⚠️ HDD detected. Consider moving ChromaDB to an SSD for better performance.")
        
        # Add general tips
        total_docs = sum(c.count for c in active_collections)
        if total_docs > 500000:
            tips.append("Large knowledge base. Consider enabling LRU cache for memory management.")
        
        if total_size > 5 * 1024 * 1024 * 1024:  # > 5GB
            tips.append("Database is larger than typical. Review indexed sources if unexpected.")
        
        return StorageMetrics(
            status=status,
            location=str(self._chroma_path),
            total_size_bytes=total_size,
            total_size_human=_format_bytes(total_size),
            sqlite_size_bytes=sqlite_size,
            sqlite_size_human=_format_bytes(sqlite_size),
            active_collections=active_collections,
            orphaned_data={
                "count": len(orphans),
                "total_size_bytes": orphan_total,
                "total_size_human": _format_bytes(orphan_total),
                "directories": [asdict(o) for o in orphans]
            },
            disk_info=disk_info,
            last_cleanup=self._get_last_cleanup(),
            warnings=warnings,
            tips=tips
        )
    
    def cleanup_orphans(
        self,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> CleanupState:
        """
        Clean up orphaned collection directories.
        
        This operation is:
        - Safe: Only deletes directories not in active collections
        - Resumable: Tracks progress in state file
        - Non-destructive: Never touches active collection data
        
        Args:
            dry_run: If True, only returns what would be deleted
            progress_callback: Called with (completed, total, bytes_freed)
            
        Returns:
            CleanupState with results
        """
        with self._cleanup_lock:
            orphans = self.list_orphans()
            
            if not orphans:
                return CleanupState(
                    job_id=f"cleanup-{int(time.time())}",
                    started_at=datetime.now().isoformat(),
                    orphans_to_delete=[],
                    completed=True
                )
            
            # Check for existing incomplete cleanup
            existing_state = self._load_cleanup_state()
            if existing_state and not existing_state.completed:
                logger.info(f"Resuming previous cleanup job: {existing_state.job_id}")
                state = existing_state
                # Filter out already deleted orphans
                remaining = [o for o in orphans if o.id not in state.deleted]
            else:
                state = CleanupState(
                    job_id=f"cleanup-{int(time.time())}",
                    started_at=datetime.now().isoformat(),
                    orphans_to_delete=[o.id for o in orphans]
                )
                remaining = orphans
            
            if dry_run:
                state.completed = True
                return state
            
            # Perform cleanup
            total = len(remaining)
            for i, orphan in enumerate(remaining):
                try:
                    # Double-check it's still orphaned (in case collections were created)
                    active_ids = self.get_active_collection_ids()
                    if orphan.id in active_ids:
                        logger.info(f"Skipping {orphan.id} - now active")
                        continue
                    
                    # Delete the directory
                    shutil.rmtree(orphan.path)
                    
                    state.deleted.append(orphan.id)
                    state.bytes_freed += orphan.size_bytes
                    
                    logger.info(f"Deleted orphan {orphan.id} ({orphan.size_human})")
                    
                except Exception as e:
                    logger.error(f"Failed to delete {orphan.id}: {e}")
                    state.failed.append(orphan.id)
                    state.error = str(e)
                
                # Save state after each deletion for resumability
                self._save_cleanup_state(state)
                
                if progress_callback:
                    progress_callback(i + 1, total, state.bytes_freed)
            
            state.completed = True
            self._save_cleanup_state(state)
            
            # Clear state file and record completion
            self._clear_cleanup_state()
            self._record_last_cleanup()
            
            logger.info(f"Cleanup complete: freed {_format_bytes(state.bytes_freed)}")
            
            return state
    
    def get_cleanup_status(self) -> Optional[CleanupState]:
        """Get status of current or last cleanup operation."""
        if self._current_cleanup:
            return self._current_cleanup
        return self._load_cleanup_state()
    
    def get_performance_tips(self) -> List[Dict[str, str]]:
        """Get storage performance tips for the user."""
        disk_info = _get_disk_info(str(self._chroma_path))
        tips = []
        
        tips.append({
            "title": "Storage Type Recommendations",
            "content": (
                "For best vector search performance:\n"
                "• Intel Optane / 3D XPoint: ⭐ Ideal (<10µs latency)\n"
                "• NVMe SSD: ✅ Recommended (~100µs latency)\n"
                "• SATA SSD: ⚠️ Acceptable\n"
                "• HDD: ❌ Not recommended (high seek latency)"
            ),
            "current": f"Your disk: {disk_info.disk_type.value.upper()}"
        })
        
        tips.append({
            "title": "Why Fast Storage Matters",
            "content": (
                "ChromaDB uses HNSW (Hierarchical Navigable Small World) algorithm "
                "which requires many random reads during vector search. "
                "Low-latency storage dramatically improves search speed."
            )
        })
        
        tips.append({
            "title": "Memory Management",
            "content": (
                "For large knowledge bases (>500k documents), enable LRU cache:\n"
                "Set CHROMA_SEGMENT_CACHE_POLICY=LRU and "
                "CHROMA_MEMORY_LIMIT_BYTES=10000000000 (10GB)"
            )
        })
        
        return tips


@dataclass
class MigrationState:
    """State for tracking database migration progress."""
    job_id: str
    source_path: str
    dest_path: str
    started_at: str
    status: str = "pending"  # pending, copying, verifying, completed, failed
    total_bytes: int = 0
    copied_bytes: int = 0
    files_total: int = 0
    files_copied: int = 0
    verified: bool = False
    error: Optional[str] = None
    completed_at: Optional[str] = None


class ChromaDBMigrator:
    """
    Handles safe migration of ChromaDB to a new location.
    
    Features:
    - Progress tracking
    - Verification after copy
    - Safe deletion of old location only after verification
    - Resumable if interrupted
    """
    
    def __init__(self, source_path: str, dest_path: str):
        self.source_path = Path(source_path)
        self.dest_path = Path(dest_path)
        self._state: Optional[MigrationState] = None
        self._lock = threading.Lock()
    
    def _count_files_and_size(self, path: Path) -> tuple[int, int]:
        """Count files and total size in directory."""
        total_files = 0
        total_size = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                total_files += 1
                total_size += entry.stat().st_size
        return total_files, total_size
    
    def _verify_copy(self) -> tuple[bool, str]:
        """Verify the copied database matches the source."""
        try:
            # Check SQLite file exists
            source_sqlite = self.source_path / "chroma.sqlite3"
            dest_sqlite = self.dest_path / "chroma.sqlite3"
            
            if source_sqlite.exists() and not dest_sqlite.exists():
                return False, "SQLite database not copied"
            
            if source_sqlite.exists() and dest_sqlite.exists():
                # Compare sizes
                if source_sqlite.stat().st_size != dest_sqlite.stat().st_size:
                    return False, "SQLite database size mismatch"
            
            # Count collections (UUID directories)
            source_uuids = set()
            dest_uuids = set()
            
            for entry in self.source_path.iterdir():
                if entry.is_dir() and _is_valid_uuid(entry.name):
                    source_uuids.add(entry.name)
            
            for entry in self.dest_path.iterdir():
                if entry.is_dir() and _is_valid_uuid(entry.name):
                    dest_uuids.add(entry.name)
            
            if source_uuids != dest_uuids:
                missing = source_uuids - dest_uuids
                if missing:
                    return False, f"Missing collection directories: {len(missing)}"
            
            # Verify each collection directory has the expected files
            for uuid in source_uuids:
                source_dir = self.source_path / uuid
                dest_dir = self.dest_path / uuid
                
                source_files = set(f.name for f in source_dir.iterdir() if f.is_file())
                dest_files = set(f.name for f in dest_dir.iterdir() if f.is_file())
                
                if source_files != dest_files:
                    return False, f"File mismatch in collection {uuid}"
            
            return True, "Verification passed"
            
        except Exception as e:
            return False, f"Verification error: {e}"
    
    def start_migration(
        self,
        progress_callback: Optional[Callable[[MigrationState], None]] = None
    ) -> MigrationState:
        """
        Start the migration process.
        
        Args:
            progress_callback: Called periodically with migration state
            
        Returns:
            Final MigrationState
        """
        with self._lock:
            job_id = f"migrate-{int(time.time())}"
            
            # Validate paths
            if not self.source_path.exists():
                return MigrationState(
                    job_id=job_id,
                    source_path=str(self.source_path),
                    dest_path=str(self.dest_path),
                    started_at=datetime.now().isoformat(),
                    status="failed",
                    error="Source path does not exist"
                )
            
            if self.dest_path.exists() and any(self.dest_path.iterdir()):
                return MigrationState(
                    job_id=job_id,
                    source_path=str(self.source_path),
                    dest_path=str(self.dest_path),
                    started_at=datetime.now().isoformat(),
                    status="failed",
                    error="Destination path already exists and is not empty"
                )
            
            # Count files and size
            total_files, total_bytes = self._count_files_and_size(self.source_path)
            
            self._state = MigrationState(
                job_id=job_id,
                source_path=str(self.source_path),
                dest_path=str(self.dest_path),
                started_at=datetime.now().isoformat(),
                status="copying",
                total_bytes=total_bytes,
                files_total=total_files
            )
            
            if progress_callback:
                progress_callback(self._state)
            
            try:
                # Create destination directory
                self.dest_path.mkdir(parents=True, exist_ok=True)
                
                # Copy files with progress tracking
                for entry in self.source_path.rglob("*"):
                    if entry.is_file():
                        rel_path = entry.relative_to(self.source_path)
                        dest_file = self.dest_path / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        
                        shutil.copy2(entry, dest_file)
                        
                        self._state.files_copied += 1
                        self._state.copied_bytes += entry.stat().st_size
                        
                        if progress_callback and self._state.files_copied % 10 == 0:
                            progress_callback(self._state)
                
                # Verification phase
                self._state.status = "verifying"
                if progress_callback:
                    progress_callback(self._state)
                
                verified, verify_msg = self._verify_copy()
                self._state.verified = verified
                
                if not verified:
                    self._state.status = "failed"
                    self._state.error = verify_msg
                    # Clean up failed copy
                    if self.dest_path.exists():
                        shutil.rmtree(self.dest_path)
                else:
                    self._state.status = "completed"
                    self._state.completed_at = datetime.now().isoformat()
                    logger.info(f"Migration completed: {self.source_path} -> {self.dest_path}")
                
            except Exception as e:
                self._state.status = "failed"
                self._state.error = str(e)
                logger.error(f"Migration failed: {e}")
                # Clean up partial copy
                if self.dest_path.exists():
                    try:
                        shutil.rmtree(self.dest_path)
                    except Exception:
                        pass
            
            if progress_callback:
                progress_callback(self._state)
            
            return self._state
    
    def delete_source(self) -> tuple[bool, str]:
        """
        Delete the source directory after successful migration.
        
        Only works if migration completed successfully and was verified.
        """
        if not self._state or self._state.status != "completed" or not self._state.verified:
            return False, "Cannot delete source: migration not completed or not verified"
        
        try:
            shutil.rmtree(self.source_path)
            logger.info(f"Deleted source directory: {self.source_path}")
            return True, "Source deleted successfully"
        except Exception as e:
            logger.error(f"Failed to delete source: {e}")
            return False, f"Failed to delete: {e}"


# Singleton instance
_manager: Optional[ChromaDBManager] = None
_current_migration: Optional[MigrationState] = None


def get_chromadb_manager(chroma_path: Optional[str] = None) -> ChromaDBManager:
    """Get the global ChromaDB manager instance."""
    global _manager
    if _manager is None:
        _manager = ChromaDBManager(chroma_path=chroma_path)
    return _manager


def start_chromadb_migration(
    source_path: str,
    dest_path: str,
    progress_callback: Optional[Callable[[MigrationState], None]] = None
) -> MigrationState:
    """Start a ChromaDB migration in the background."""
    global _current_migration
    
    migrator = ChromaDBMigrator(source_path, dest_path)
    _current_migration = migrator.start_migration(progress_callback)
    return _current_migration


def get_migration_status() -> Optional[MigrationState]:
    """Get current migration status."""
    return _current_migration


def delete_old_chromadb(source_path: str) -> tuple[bool, str]:
    """Delete old ChromaDB directory after verified migration."""
    global _current_migration
    
    if not _current_migration:
        return False, "No migration has been performed"
    
    if _current_migration.source_path != source_path:
        return False, "Source path doesn't match last migration"
    
    if _current_migration.status != "completed" or not _current_migration.verified:
        return False, "Migration not completed or not verified"
    
    try:
        shutil.rmtree(source_path)
        logger.info(f"Deleted old ChromaDB: {source_path}")
        return True, f"Deleted {source_path}"
    except Exception as e:
        return False, f"Failed to delete: {e}"
