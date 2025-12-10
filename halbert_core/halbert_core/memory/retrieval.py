"""
Memory retrieval for Halbert.

Phase 3: Simple JSONL + keyword search
Phase 3+: Optional ChromaDB vector search upgrade
Phase 4: Per-persona memory isolation
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging
from datetime import datetime

logger = logging.getLogger('halbert.memory')


class MemoryRetrieval:
    """
    Memory retrieval for LLM context building.
    
    Phase 3: Supports core/ and runtime/ memory
    Phase 4: Add personas/ memory with isolation
    """
    
    def __init__(self, memory_root: Optional[Path] = None):
        """
        Initialize memory retrieval.
        
        Args:
            memory_root: Root directory for memory storage.
                        If None, uses default data directory.
        """
        if memory_root is None:
            memory_root = Path.home() / '.local/share/halbert/memory'
        
        self.memory_root = Path(memory_root)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories (Phase 3)
        self.core_dir = self.memory_root / 'core'
        self.runtime_dir = self.memory_root / 'runtime'
        self.shared_dir = self.memory_root / 'shared'
        
        for d in [self.core_dir, self.runtime_dir, self.shared_dir]:
            d.mkdir(exist_ok=True)
        
        # Phase 4: personas directory (placeholder)
        self.personas_dir = self.memory_root / 'personas'
        self.personas_dir.mkdir(exist_ok=True)
        
        logger.info(f"Memory root initialized at: {self.memory_root}")
    
    def retrieve_from(
        self,
        subdir: str,
        query: str,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve k most relevant memories from subdir.
        
        Phase 3: Simple keyword search in JSONL files
        Phase 3+: Can upgrade to ChromaDB vector search
        
        Args:
            subdir: Memory subdirectory (e.g., 'core', 'runtime', 'personas/friend')
            query: Search query
            k: Number of results to return
            filters: Optional filters (e.g., {'type': 'maintenance', 'ts_after': '2024-01-01'})
        
        Returns:
            List of memory entries (most relevant first)
        """
        path = self.memory_root / subdir
        
        if not path.exists():
            logger.warning(f"Memory subdirectory does not exist: {subdir}")
            return []
        
        results = []
        query_lower = query.lower()
        
        # Search through all JSONL files
        for jsonl_file in path.glob("**/*.jsonl"):
            try:
                with open(jsonl_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            entry = json.loads(line)
                            
                            # Apply filters if provided
                            if filters and not self._matches_filters(entry, filters):
                                continue
                            
                            # Simple keyword scoring
                            text = entry.get('text', '') + ' ' + entry.get('summary', '')
                            score = self._score_relevance(text.lower(), query_lower)
                            
                            if score > 0:
                                results.append({
                                    **entry,
                                    '_score': score,
                                    '_source': str(jsonl_file.relative_to(self.memory_root)),
                                    '_line': line_num
                                })
                        
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON in {jsonl_file}:{line_num}: {e}")
            
            except Exception as e:
                logger.error(f"Error reading {jsonl_file}: {e}")
        
        # Sort by score and return top k
        results.sort(key=lambda x: x['_score'], reverse=True)
        return results[:k]
    
    def _score_relevance(self, text: str, query: str) -> float:
        """
        Score relevance between text and query (simple keyword matching).
        
        Phase 3: Basic keyword overlap
        Phase 3+: Can upgrade to TF-IDF or embeddings
        """
        query_words = set(query.split())
        text_words = set(text.split())
        
        if not query_words:
            return 0.0
        
        # Count overlapping words
        overlap = len(query_words & text_words)
        
        # Normalize by query length
        score = overlap / len(query_words)
        
        return score
    
    def _matches_filters(self, entry: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if entry matches filters."""
        for key, value in filters.items():
            if key.endswith('_after'):
                # Timestamp filter (after)
                field = key[:-6]  # Remove '_after'
                if field not in entry:
                    return False
                if entry[field] < value:
                    return False
            
            elif key.endswith('_before'):
                # Timestamp filter (before)
                field = key[:-7]  # Remove '_before'
                if field not in entry:
                    return False
                if entry[field] > value:
                    return False
            
            else:
                # Exact match
                if entry.get(key) != value:
                    return False
        
        return True
    
    def build_context(
        self,
        query: str,
        persona: str = 'it_admin',
        k_core: int = 5,
        k_persona: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Build complete context for LLM.
        
        Phase 3: Always includes core + runtime memory
        Phase 4: Add persona-specific memory based on active persona
        
        Args:
            query: User query or task description
            persona: Active persona ('it_admin', 'friend', 'custom')
            k_core: Number of core memories to retrieve
            k_persona: Number of persona memories to retrieve
        
        Returns:
            List of memory entries for LLM context
        """
        context = []
        
        # Always include core IT knowledge (Phase 3)
        core_memories = self.retrieve_from('core', query, k=k_core)
        context.extend(core_memories)
        
        # Include runtime/autonomous decision history (Phase 3)
        runtime_memories = self.retrieve_from('runtime', query, k=3)
        context.extend(runtime_memories)
        
        # Phase 4: Include persona-specific memory
        if persona in ['friend', 'custom'] and (self.personas_dir / persona).exists():
            persona_memories = self.retrieve_from(f'personas/{persona}', query, k=k_persona)
            context.extend(persona_memories)
        
        # Add shared user profile (Phase 4)
        profile_path = self.shared_dir / 'user_profile.json'
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text())
                context.append({
                    'type': 'user_profile',
                    'text': json.dumps(profile),
                    '_score': 1.0,
                    '_source': 'shared/user_profile.json'
                })
            except Exception as e:
                logger.error(f"Error loading user profile: {e}")
        
        return context
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory storage statistics."""
        def count_lines(directory: Path) -> int:
            count = 0
            for jsonl_file in directory.glob("**/*.jsonl"):
                try:
                    with open(jsonl_file, 'r') as f:
                        count += sum(1 for line in f if line.strip())
                except Exception:
                    pass
            return count
        
        def get_size_mb(directory: Path) -> float:
            total = 0
            for file in directory.rglob("*"):
                if file.is_file():
                    total += file.stat().st_size
            return total / (1024 * 1024)
        
        return {
            'memory_root': str(self.memory_root),
            'core': {
                'entries': count_lines(self.core_dir),
                'size_mb': round(get_size_mb(self.core_dir), 2)
            },
            'runtime': {
                'entries': count_lines(self.runtime_dir),
                'size_mb': round(get_size_mb(self.runtime_dir), 2)
            },
            'personas': {
                'entries': count_lines(self.personas_dir),
                'size_mb': round(get_size_mb(self.personas_dir), 2)
            },
            'shared': {
                'size_mb': round(get_size_mb(self.shared_dir), 2)
            }
        }
