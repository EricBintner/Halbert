# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Prompt Loader - Load and cache XML prompt components.

Part of Phase 40: Prompt Infrastructure
"""

from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PromptLoader:
    """Load and cache prompt components from XML files."""
    
    def __init__(self, prompts_dir: Path):
        """
        Initialize the prompt loader.
        
        Args:
            prompts_dir: Path to config/prompts directory
        """
        self.prompts_dir = Path(prompts_dir)
        self.v2_dir = self.prompts_dir / "v2"
        self._cache: Dict[str, str] = {}
        self._validate_structure()
    
    def clear_cache(self):
        """Clear the file cache to force reload from disk."""
        self._cache.clear()
        logger.info("Loader cache cleared")
    
    def _validate_structure(self) -> None:
        """Validate that required directories exist."""
        required_dirs = [
            self.v2_dir / "base",
            self.v2_dir / "tiers",
            self.v2_dir / "templates",
        ]
        
        for dir_path in required_dirs:
            if not dir_path.exists():
                logger.warning(f"Prompt directory missing: {dir_path}")
    
    def load_base_components(self) -> Dict[str, str]:
        """
        Load all base prompt components.
        
        Returns:
            Dict mapping component name to content
        """
        base_dir = self.v2_dir / "base"
        components = {}
        
        if not base_dir.exists():
            logger.error(f"Base directory not found: {base_dir}")
            return components
        
        for xml_file in base_dir.glob("*.xml"):
            name = xml_file.stem
            try:
                components[name] = self._load_file(xml_file)
                logger.debug(f"Loaded base component: {name}")
            except Exception as e:
                logger.error(f"Failed to load {xml_file}: {e}")
        
        return components
    
    # Core tools always included (most commonly used)
    CORE_TOOLS = [
        "check_disk_space",
        "get_service_status",
        "get_system_load",
        "run_command",
        "read_file",
        "rag_search",
    ]
    
    def load_tools(self, core_only: bool = False, tool_names: Optional[List[str]] = None) -> str:
        """
        Load tool definitions.
        
        Args:
            core_only: If True, only load core tools (reduces token count)
            tool_names: If provided, only load these specific tools
        
        Returns:
            Combined tool definitions as string
        """
        tools_dir = self.v2_dir / "tools"
        tools: List[str] = []
        
        if not tools_dir.exists():
            logger.warning(f"Tools directory not found: {tools_dir}")
            return ""
        
        for xml_file in sorted(tools_dir.glob("*.xml")):
            if xml_file.stem.startswith("_"):
                continue  # Skip schema/internal files
            
            # Filter based on parameters
            if tool_names is not None:
                if xml_file.stem not in tool_names:
                    continue
            elif core_only:
                if xml_file.stem not in self.CORE_TOOLS:
                    continue
            
            try:
                tools.append(self._load_file(xml_file))
                logger.debug(f"Loaded tool: {xml_file.stem}")
            except Exception as e:
                logger.error(f"Failed to load tool {xml_file}: {e}")
        
        return "\n".join(tools)
    
    def load_tier(self, tier: str) -> str:
        """
        Load tier-specific prompt additions.
        
        Args:
            tier: One of 'guide', 'specialist', 'vision'
            
        Returns:
            Tier prompt content or empty string
        """
        tier_file = self.v2_dir / "tiers" / f"{tier}.xml"
        
        if not tier_file.exists():
            logger.warning(f"Tier file not found: {tier_file}")
            return ""
        
        try:
            return self._load_file(tier_file)
        except Exception as e:
            logger.error(f"Failed to load tier {tier}: {e}")
            return ""
    
    def load_template(self, template_name: str) -> str:
        """
        Load a template file for dynamic injection.
        
        Args:
            template_name: Name of template (without .xml)
            
        Returns:
            Template content
        """
        template_file = self.v2_dir / "templates" / f"{template_name}.xml"
        
        if not template_file.exists():
            logger.warning(f"Template not found: {template_file}")
            return ""
        
        try:
            return self._load_file(template_file)
        except Exception as e:
            logger.error(f"Failed to load template {template_name}: {e}")
            return ""
    
    def load_legacy_prompt(self) -> str:
        """
        Load the legacy base-safety.txt for fallback.
        
        Returns:
            Legacy prompt content
        """
        legacy_file = self.prompts_dir / "base-safety.txt"
        
        if not legacy_file.exists():
            logger.warning("Legacy prompt not found")
            return ""
        
        try:
            return self._load_file(legacy_file)
        except Exception as e:
            logger.error(f"Failed to load legacy prompt: {e}")
            return ""
    
    def _load_file(self, filepath: Path) -> str:
        """
        Load file content with caching.
        
        Args:
            filepath: Path to file
            
        Returns:
            File content as string
        """
        cache_key = str(filepath.resolve())
        
        if cache_key not in self._cache:
            self._cache[cache_key] = filepath.read_text(encoding="utf-8")
        
        return self._cache[cache_key]
    
    def clear_cache(self) -> None:
        """Clear the file cache."""
        self._cache.clear()
        logger.debug("Prompt cache cleared")
    
    def reload(self) -> None:
        """Clear cache and reload all components."""
        self.clear_cache()
        # Pre-warm cache
        self.load_base_components()
        self.load_tools()
        logger.info("Prompts reloaded")
