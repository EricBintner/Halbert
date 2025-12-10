"""
Memory purge functionality for persona memory (Phase 4 M1).

Allows users to safely purge persona-specific memory while protecting
core IT knowledge.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import shutil
import json
import logging

from ..obs.logging import get_logger
from ..obs.audit import write_audit

logger = get_logger("halbert")


@dataclass
class PurgeConfirmation:
    """Confirmation details for memory purge."""
    persona: str
    memory_dir: str
    estimated_entries: int
    estimated_size_mb: float
    will_delete: list[str]
    will_preserve: list[str]
    requires_export: bool


class MemoryPurge:
    """
    Safely purge persona-specific memory.
    
    SAFETY: Core IT knowledge is NEVER purged.
    Only persona-specific memory can be purged.
    
    Usage:
        purge = MemoryPurge()
        
        # Get purge preview
        confirmation = purge.preview_purge("friend")
        print(f"Will delete {confirmation.estimated_entries} entries")
        
        # Execute purge
        result = purge.execute_purge("friend", user="admin")
    """
    
    def __init__(self, memory_root: Optional[Path] = None):
        """
        Initialize memory purge manager.
        
        Args:
            memory_root: Root memory directory.
                        If None, uses default location.
        """
        if memory_root is None:
            memory_root = Path.home() / '.local/share/halbert/memory'
        
        self.memory_root = Path(memory_root)
        
        # Protected directories (NEVER purge)
        self.protected_dirs = ['core', 'runtime', 'shared']
        
        logger.info("MemoryPurge initialized", extra={
            "memory_root": str(self.memory_root),
            "protected_dirs": self.protected_dirs
        })
    
    def preview_purge(self, persona: str) -> PurgeConfirmation:
        """
        Preview what would be deleted by a purge.
        
        Args:
            persona: Persona to purge (e.g., 'friend', 'custom')
        
        Returns:
            PurgeConfirmation with details
        
        Raises:
            ValueError: If persona is invalid or protected
        """
        # Validate persona
        if persona in self.protected_dirs:
            raise ValueError(
                f"Cannot purge protected directory: {persona}. "
                f"Core IT knowledge is never purged."
            )
        
        if persona == "it_admin":
            raise ValueError(
                "Cannot purge IT Admin persona (uses core memory). "
                "Core IT knowledge is never purged."
            )
        
        # Determine memory directory
        memory_dir = f"personas/{persona}"
        target_dir = self.memory_root / memory_dir
        
        if not target_dir.exists():
            raise ValueError(f"Persona memory directory does not exist: {memory_dir}")
        
        # Count entries and size
        estimated_entries = 0
        estimated_size = 0
        will_delete = []
        
        for file in target_dir.rglob("*"):
            if file.is_file():
                estimated_size += file.stat().st_size
                will_delete.append(str(file.relative_to(self.memory_root)))
                
                # Count JSONL entries
                if file.suffix == '.jsonl':
                    try:
                        with open(file, 'r') as f:
                            estimated_entries += sum(1 for line in f if line.strip())
                    except Exception as e:
                        logger.warning(f"Failed to count entries in {file}: {e}")
        
        estimated_size_mb = estimated_size / (1024 * 1024)
        
        return PurgeConfirmation(
            persona=persona,
            memory_dir=memory_dir,
            estimated_entries=estimated_entries,
            estimated_size_mb=round(estimated_size_mb, 2),
            will_delete=will_delete,
            will_preserve=[
                "core/ (IT knowledge)",
                "runtime/ (autonomous decisions)",
                "shared/ (user profile)"
            ],
            requires_export=estimated_entries > 0
        )
    
    def execute_purge(
        self,
        persona: str,
        user: str,
        export_before: bool = True,
        export_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Execute memory purge for a persona.
        
        Args:
            persona: Persona to purge
            user: User who authorized the purge
            export_before: Export memory before purging (recommended)
            export_path: Path for export (if export_before=True)
        
        Returns:
            Result dict with stats
        
        Raises:
            ValueError: If persona is invalid or protected
        """
        # Get purge preview (validates persona)
        confirmation = self.preview_purge(persona)
        
        # Export if requested
        export_file = None
        if export_before:
            if export_path is None:
                export_path = Path.home() / f"halbert_persona_{persona}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
            
            export_file = self._export_memory(persona, export_path)
        
        # Execute purge
        target_dir = self.memory_root / confirmation.memory_dir
        
        try:
            # Remove directory
            shutil.rmtree(target_dir)
            
            # Recreate empty directory
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Audit log
            write_audit(
                tool="persona",
                mode="memory_purge",
                request_id="",
                ok=True,
                summary=f"Purged {persona} memory ({confirmation.estimated_entries} entries, {confirmation.estimated_size_mb}MB)",
                user=user,
                persona=persona,
                exported=export_file is not None
            )
            
            logger.info(f"Memory purged for persona: {persona}", extra={
                "persona": persona,
                "entries_deleted": confirmation.estimated_entries,
                "size_mb": confirmation.estimated_size_mb,
                "user": user,
                "exported": export_file is not None
            })
            
            return {
                "success": True,
                "persona": persona,
                "entries_deleted": confirmation.estimated_entries,
                "size_mb_deleted": confirmation.estimated_size_mb,
                "exported": export_file is not None,
                "export_path": str(export_file) if export_file else None
            }
        
        except Exception as e:
            logger.error(f"Memory purge failed for {persona}: {e}")
            write_audit(
                tool="persona",
                mode="memory_purge",
                request_id="",
                ok=False,
                summary=f"Purge failed for {persona}: {e}",
                user=user
            )
            
            return {
                "success": False,
                "persona": persona,
                "error": str(e)
            }
    
    def _export_memory(self, persona: str, export_path: Path) -> Path:
        """
        Export persona memory to tar.gz archive.
        
        Args:
            persona: Persona to export
            export_path: Target export file
        
        Returns:
            Path to exported file
        """
        memory_dir = f"personas/{persona}"
        source_dir = self.memory_root / memory_dir
        
        if not source_dir.exists():
            raise ValueError(f"Persona memory directory does not exist: {memory_dir}")
        
        try:
            import tarfile
            
            with tarfile.open(export_path, 'w:gz') as tar:
                tar.add(source_dir, arcname=persona)
            
            logger.info(f"Exported {persona} memory to {export_path}")
            return export_path
        
        except Exception as e:
            logger.error(f"Memory export failed: {e}")
            raise
    
    def export_to_jsonl(self, persona: str, output_path: Path) -> Path:
        """
        Export persona memory to consolidated JSONL file.
        
        Args:
            persona: Persona to export
            output_path: Target JSONL file
        
        Returns:
            Path to exported file
        """
        memory_dir = f"personas/{persona}"
        source_dir = self.memory_root / memory_dir
        
        if not source_dir.exists():
            raise ValueError(f"Persona memory directory does not exist: {memory_dir}")
        
        try:
            with open(output_path, 'w') as out_file:
                for jsonl_file in source_dir.rglob("*.jsonl"):
                    with open(jsonl_file, 'r') as in_file:
                        for line in in_file:
                            line = line.strip()
                            if line:
                                # Add source file metadata
                                try:
                                    entry = json.loads(line)
                                    entry['_export_source'] = str(jsonl_file.relative_to(source_dir))
                                    out_file.write(json.dumps(entry) + '\n')
                                except json.JSONDecodeError:
                                    logger.warning(f"Invalid JSON in {jsonl_file}, skipping line")
            
            logger.info(f"Exported {persona} memory to {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"JSONL export failed: {e}")
            raise
