"""
Memory writer for Cerebric.

Phase 3: Append-only JSONL storage
Phase 4: Per-persona memory isolation
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import json
import logging
from datetime import datetime

logger = logging.getLogger('cerebric.memory')


class MemoryWriter:
    """
    Memory writer for persistent storage.
    
    Phase 3: Supports core/ and runtime/ memory
    Phase 4: Add personas/ memory with isolation
    """
    
    def __init__(self, memory_root: Optional[Path] = None):
        """
        Initialize memory writer.
        
        Args:
            memory_root: Root directory for memory storage.
                        If None, uses default data directory.
        """
        if memory_root is None:
            memory_root = Path.home() / '.local/share/cerebric/memory'
        
        self.memory_root = Path(memory_root)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories (Phase 3)
        self.core_dir = self.memory_root / 'core'
        self.runtime_dir = self.memory_root / 'runtime'
        self.shared_dir = self.memory_root / 'shared'
        
        for d in [self.core_dir, self.runtime_dir, self.shared_dir]:
            d.mkdir(exist_ok=True)
        
        # Phase 4: personas directory
        self.personas_dir = self.memory_root / 'personas'
        self.personas_dir.mkdir(exist_ok=True)
        
        logger.info(f"Memory writer initialized at: {self.memory_root}")
    
    def write_core_knowledge(
        self,
        entry: Dict[str, Any],
        filename: str = 'system_knowledge.jsonl'
    ) -> bool:
        """
        Write to core IT knowledge (never purged).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: system_knowledge.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.core_dir / filename, entry)
    
    def write_maintenance_history(
        self,
        entry: Dict[str, Any],
        filename: str = 'maintenance_history.jsonl'
    ) -> bool:
        """
        Write to maintenance history (core memory).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: maintenance_history.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.core_dir / filename, entry)
    
    def write_learned_pattern(
        self,
        entry: Dict[str, Any],
        filename: str = 'learned_patterns.jsonl'
    ) -> bool:
        """
        Write learned pattern (user preferences for IT tasks).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: learned_patterns.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.core_dir / filename, entry)
    
    def write_confidence_history(
        self,
        entry: Dict[str, Any],
        filename: str = 'confidence_history.jsonl'
    ) -> bool:
        """
        Write confidence estimation history (runtime memory).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: confidence_history.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.runtime_dir / filename, entry)
    
    def write_action_outcome(
        self,
        entry: Dict[str, Any],
        filename: str = 'action_outcomes.jsonl'
    ) -> bool:
        """
        Write autonomous action outcome (runtime memory).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: action_outcomes.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.runtime_dir / filename, entry)
    
    def write_anomaly_event(
        self,
        entry: Dict[str, Any],
        filename: str = 'anomaly_events.jsonl'
    ) -> bool:
        """
        Write anomaly detection event (runtime memory).
        
        Args:
            entry: Memory entry to write
            filename: Target file (default: anomaly_events.jsonl)
        
        Returns:
            True if successful
        """
        return self._append_jsonl(self.runtime_dir / filename, entry)
    
    def write_persona_memory(
        self,
        persona: str,
        entry: Dict[str, Any],
        filename: str = 'conversations.jsonl'
    ) -> bool:
        """
        Write to persona-specific memory (Phase 4).
        
        Args:
            persona: Persona name (e.g., 'friend', 'custom')
            entry: Memory entry to write
            filename: Target file (default: conversations.jsonl)
        
        Returns:
            True if successful
        """
        persona_dir = self.personas_dir / persona
        persona_dir.mkdir(exist_ok=True)
        return self._append_jsonl(persona_dir / filename, entry)
    
    def write_user_profile(self, profile: Dict[str, Any]) -> bool:
        """
        Write/update user profile (shared memory).
        
        Args:
            profile: User profile data
        
        Returns:
            True if successful
        """
        profile_path = self.shared_dir / 'user_profile.json'
        
        try:
            # Add timestamp
            profile['updated_at'] = datetime.utcnow().isoformat() + 'Z'
            
            # Write as formatted JSON (not JSONL, single file)
            with open(profile_path, 'w') as f:
                json.dump(profile, f, indent=2)
            
            logger.info(f"User profile updated at {profile_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error writing user profile: {e}")
            return False
    
    def _append_jsonl(self, path: Path, entry: Dict[str, Any]) -> bool:
        """
        Append entry to JSONL file.
        
        Args:
            path: File path
            entry: Entry to append
        
        Returns:
            True if successful
        """
        try:
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add timestamp if not present
            if 'ts' not in entry:
                entry['ts'] = datetime.utcnow().isoformat() + 'Z'
            
            # Append to file
            with open(path, 'a') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            logger.debug(f"Wrote entry to {path}")
            return True
        
        except Exception as e:
            logger.error(f"Error writing to {path}: {e}")
            return False
    
    def purge_persona_memory(self, persona: str) -> bool:
        """
        Purge all memory for a persona (Phase 4).
        
        Args:
            persona: Persona name (e.g., 'friend', 'custom')
        
        Returns:
            True if successful
        """
        import shutil
        
        persona_dir = self.personas_dir / persona
        
        if not persona_dir.exists():
            logger.warning(f"Persona directory does not exist: {persona}")
            return False
        
        try:
            shutil.rmtree(persona_dir)
            logger.info(f"Purged persona memory: {persona}")
            return True
        
        except Exception as e:
            logger.error(f"Error purging persona memory {persona}: {e}")
            return False
    
    def export_persona_memory(
        self,
        persona: str,
        output_path: Path
    ) -> bool:
        """
        Export persona memory to a single JSONL file (Phase 4).
        
        Args:
            persona: Persona name
            output_path: Output file path
        
        Returns:
            True if successful
        """
        persona_dir = self.personas_dir / persona
        
        if not persona_dir.exists():
            logger.warning(f"Persona directory does not exist: {persona}")
            return False
        
        try:
            with open(output_path, 'w') as out_f:
                for jsonl_file in persona_dir.glob("**/*.jsonl"):
                    with open(jsonl_file, 'r') as in_f:
                        for line in in_f:
                            line = line.strip()
                            if line:
                                out_f.write(line + '\n')
            
            logger.info(f"Exported persona memory {persona} to {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error exporting persona memory {persona}: {e}")
            return False
