"""
Abstract base class for platform-specific operations.

Defines the interface that all platform implementations must provide.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Iterator, Optional, Any


class PlatformBridge(ABC):
    """
    Abstract interface for platform-specific operations.
    
    All platform implementations (Linux, macOS, etc.) must implement
    this interface to provide consistent access to system resources.
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Get platform name (e.g., 'linux', 'macos').
        
        Returns:
            Platform identifier string
        """
        pass
    
    # ==========================================
    # System Information
    # ==========================================
    
    @abstractmethod
    def get_cpu_usage(self) -> float:
        """
        Get current CPU usage percentage.
        
        Returns:
            CPU usage as percentage (0.0 to 100.0)
        """
        pass
    
    @abstractmethod
    def get_memory_info(self) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Returns:
            Dict with keys: total, available, percent, used, free (in bytes)
        """
        pass
    
    @abstractmethod
    def get_disk_usage(self, path: str = '/') -> Dict[str, Any]:
        """
        Get disk usage for given path.
        
        Args:
            path: Path to check (default: root filesystem)
            
        Returns:
            Dict with keys: total, used, free, percent
        """
        pass
    
    @abstractmethod
    def get_system_info(self) -> Dict[str, Any]:
        """
        Get general system information.
        
        Returns:
            Dict with system details (hostname, OS, kernel, etc.)
        """
        pass
    
    # ==========================================
    # Log Collection
    # ==========================================
    
    @abstractmethod
    def collect_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        follow: bool = False
    ) -> Iterator[Dict[str, Any]]:
        """
        Collect system logs.
        
        Args:
            filters: Optional filters (processes, levels, etc.)
            follow: If True, continuously stream logs
            
        Yields:
            Log entries as dicts with keys: timestamp, message, level, etc.
        """
        pass
    
    # ==========================================
    # Sensor Reading
    # ==========================================
    
    @abstractmethod
    def read_sensors(self) -> List[Dict[str, Any]]:
        """
        Read hardware sensors (temperature, fan speed, etc.).
        
        Returns:
            List of sensor readings with keys: label, value, type, unit
        """
        pass
    
    # ==========================================
    # Service Management
    # ==========================================
    
    @abstractmethod
    def manage_service(
        self,
        name: str,
        action: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Manage system services.
        
        Args:
            name: Service name
            action: Action to perform (start, stop, restart, enable, disable, status)
            dry_run: If True, don't actually execute
            
        Returns:
            Dict with keys: ok (bool), message, stdout, stderr
        """
        pass
    
    @abstractmethod
    def list_services(self) -> List[Dict[str, Any]]:
        """
        List all system services.
        
        Returns:
            List of services with keys: name, status, enabled
        """
        pass
    
    # ==========================================
    # Package Management
    # ==========================================
    
    @abstractmethod
    def install_package(
        self,
        name: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Install a package.
        
        Args:
            name: Package name
            dry_run: If True, don't actually install
            
        Returns:
            Dict with keys: ok (bool), message
        """
        pass
    
    @abstractmethod
    def list_packages(
        self,
        pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List installed packages.
        
        Args:
            pattern: Optional search pattern
            
        Returns:
            List of packages with keys: name, version, description
        """
        pass
    
    # ==========================================
    # Utility Methods
    # ==========================================
    
    @abstractmethod
    def execute_command(
        self,
        command: List[str],
        dry_run: bool = False,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a system command.
        
        Args:
            command: Command and arguments as list
            dry_run: If True, don't actually execute
            timeout: Optional timeout in seconds
            
        Returns:
            Dict with keys: ok (bool), returncode, stdout, stderr
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform={self.platform_name}>"
