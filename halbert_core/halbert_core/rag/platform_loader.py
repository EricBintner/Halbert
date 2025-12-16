"""
Platform-aware RAG data loader.

Phase 25: Separates knowledge bases by platform so:
- Linux builds only include data/linux + data/common
- macOS builds only include data/macos + data/bsd + data/common

This ensures each platform ships with appropriate documentation.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Optional
import yaml

from ..utils.platform import get_platform, is_linux, is_macos

logger = logging.getLogger('halbert.rag')


class PlatformDataLoader:
    """
    Load RAG data based on current platform.
    
    Ensures Linux-specific docs don't ship to Mac and vice versa.
    """
    
    def __init__(self, base_data_dir: Path, config_path: Optional[Path] = None):
        """
        Initialize platform data loader.
        
        Args:
            base_data_dir: Base data directory (e.g., /path/to/data)
            config_path: Optional path to platforms.yml config
        """
        self.base_data_dir = Path(base_data_dir)
        self.config_path = config_path
        self.platform = get_platform()
        self._config = None
    
    @property
    def config(self) -> dict:
        """Load platform configuration."""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> dict:
        """Load platforms.yml configuration."""
        if self.config_path and self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f)
        
        # Default configuration
        return {
            'platforms': {
                'linux': {
                    'data_dirs': ['data/linux', 'data/common'],
                },
                'darwin': {
                    'data_dirs': ['data/macos', 'data/bsd', 'data/common'],
                },
            }
        }
    
    def get_data_dirs(self) -> List[Path]:
        """
        Get data directories for current platform.
        
        Returns:
            List of Path objects for platform-appropriate data dirs
        """
        platform_key = 'darwin' if is_macos() else 'linux'
        
        platform_config = self.config.get('platforms', {}).get(platform_key, {})
        data_dirs = platform_config.get('data_dirs', [])
        
        # Convert to absolute paths
        result = []
        for dir_path in data_dirs:
            # Handle both relative and absolute paths
            if Path(dir_path).is_absolute():
                full_path = Path(dir_path)
            else:
                # Strip leading 'data/' if present since base_data_dir is already data/
                dir_name = dir_path.replace('data/', '') if dir_path.startswith('data/') else dir_path
                full_path = self.base_data_dir / dir_name
            
            if full_path.exists():
                result.append(full_path)
                logger.debug(f"Including data dir: {full_path}")
            else:
                logger.warning(f"Data dir not found: {full_path}")
        
        return result
    
    def get_excluded_dirs(self) -> List[str]:
        """
        Get data directories to exclude for current platform.
        
        Useful for ensuring wrong-platform data isn't accidentally loaded.
        
        Returns:
            List of directory names to exclude
        """
        if is_macos():
            return ['linux']
        else:
            return ['macos', 'bsd']
    
    def list_available_sources(self) -> List[dict]:
        """
        List all available data sources for current platform.
        
        Returns:
            List of source info dicts
        """
        sources = []
        
        for data_dir in self.get_data_dirs():
            if not data_dir.exists():
                continue
            
            for source_dir in data_dir.iterdir():
                if source_dir.is_dir() and not source_dir.name.startswith('.'):
                    # Count files
                    file_count = len(list(source_dir.glob('**/*.jsonl')))
                    file_count += len(list(source_dir.glob('**/*.json')))
                    file_count += len(list(source_dir.glob('**/*.md')))
                    
                    sources.append({
                        'name': source_dir.name,
                        'path': str(source_dir),
                        'platform': data_dir.name,
                        'file_count': file_count,
                    })
        
        return sources
    
    def validate_platform_separation(self) -> dict:
        """
        Validate that platform data is properly separated.
        
        Returns:
            Validation result dict
        """
        issues = []
        
        # Check that Linux data exists
        linux_dir = self.base_data_dir / 'linux'
        if not linux_dir.exists():
            issues.append("data/linux directory not found")
        
        # Check that macOS data exists
        macos_dir = self.base_data_dir / 'macos'
        if not macos_dir.exists():
            issues.append("data/macos directory not found (create with .gitkeep)")
        
        # Check that common data exists
        common_dir = self.base_data_dir / 'common'
        if not common_dir.exists():
            issues.append("data/common directory not found (create with .gitkeep)")
        
        # Check current platform dirs
        current_dirs = self.get_data_dirs()
        if not current_dirs:
            issues.append(f"No data directories found for platform: {self.platform}")
        
        return {
            'valid': len(issues) == 0,
            'platform': self.platform,
            'data_dirs': [str(d) for d in current_dirs],
            'issues': issues,
        }


def get_platform_data_dirs(base_path: Path) -> List[Path]:
    """
    Convenience function to get platform-appropriate data directories.
    
    Args:
        base_path: Base data directory path
        
    Returns:
        List of data directory paths for current platform
    """
    loader = PlatformDataLoader(base_path)
    return loader.get_data_dirs()


def get_platform_sources(base_path: Path) -> List[str]:
    """
    Get list of source names available for current platform.
    
    Args:
        base_path: Base data directory path
        
    Returns:
        List of source names
    """
    loader = PlatformDataLoader(base_path)
    sources = loader.list_available_sources()
    return [s['name'] for s in sources]
