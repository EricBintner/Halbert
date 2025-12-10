"""
Base Scanner - Abstract base class for all discovery scanners.

Scanners:
1. Probe the system (files, commands, APIs)
2. Parse results into Discovery objects
3. Return list of discoveries

Each scanner targets a specific domain from Phase 9 research.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
import logging
import subprocess
import os
from pathlib import Path

from ..schema import Discovery, DiscoveryType


class BaseScanner(ABC):
    """
    Abstract base class for discovery scanners.
    
    Subclasses must implement:
    - discovery_type: The type of discoveries this scanner produces
    - scan(): The main scanning method
    
    Optional overrides:
    - is_available(): Check if scanner can run on this system
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f'halbert.scanner.{self.name}')
    
    @property
    @abstractmethod
    def discovery_type(self) -> DiscoveryType:
        """The type of discoveries this scanner produces."""
        pass
    
    @property
    def name(self) -> str:
        """Scanner name for logging."""
        return self.__class__.__name__
    
    @abstractmethod
    def scan(self) -> List[Discovery]:
        """
        Perform system scan and return discoveries.
        
        Returns:
            List of Discovery objects found on this system.
        """
        pass
    
    def is_available(self) -> bool:
        """
        Check if this scanner can run on this system.
        
        Override in subclasses to check for required tools/files.
        Default returns True.
        """
        return True
    
    # ─────────────────────────────────────────────────────────────
    # Utility methods for subclasses
    # ─────────────────────────────────────────────────────────────
    
    def run_command(
        self, 
        cmd: List[str], 
        timeout: int = 30,
        check: bool = False
    ) -> tuple[int, str, str]:
        """
        Run a shell command safely.
        
        Args:
            cmd: Command and arguments as list
            timeout: Timeout in seconds
            check: Raise exception on non-zero exit
        
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if check and result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Command timed out: {' '.join(cmd)}")
            return -1, "", "timeout"
        except FileNotFoundError:
            self.logger.debug(f"Command not found: {cmd[0]}")
            return -1, "", f"command not found: {cmd[0]}"
    
    def command_exists(self, cmd: str) -> bool:
        """Check if a command exists on the system."""
        code, _, _ = self.run_command(["which", cmd])
        return code == 0
    
    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        return Path(path).exists()
    
    def read_file(self, path: str) -> str | None:
        """
        Safely read a file.
        
        Returns:
            File contents or None if not readable.
        """
        try:
            return Path(path).read_text()
        except (OSError, PermissionError) as e:
            self.logger.debug(f"Cannot read {path}: {e}")
            return None
    
    def get_home_dir(self) -> Path:
        """Get current user's home directory."""
        return Path.home()
    
    def get_user(self) -> str:
        """Get current username."""
        return os.environ.get('USER', 'unknown')
    
    def parse_crontab(self, content: str) -> List[dict]:
        """
        Parse crontab content into list of jobs.
        
        Returns:
            List of dicts with 'schedule' and 'command' keys.
        """
        jobs = []
        for line in content.splitlines():
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Skip variable assignments
            if '=' in line.split()[0] if line.split() else False:
                continue
            
            parts = line.split(None, 5)
            if len(parts) >= 6:
                schedule = ' '.join(parts[:5])
                command = parts[5]
                jobs.append({
                    'schedule': schedule,
                    'command': command,
                    'raw': line,
                })
        return jobs
