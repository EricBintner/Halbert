"""
Platform detection utilities for cross-platform support (Phase 5 M3 / Phase 6 prep).

Provides platform-specific behavior and detection for Linux and macOS.
"""

import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger('cerebric')


def get_platform() -> str:
    """
    Get current platform.
    
    Returns:
        "linux", "darwin" (macOS), or "windows"
    """
    return platform.system().lower()


def is_linux() -> bool:
    """Check if running on Linux."""
    return get_platform() == "linux"


def is_macos() -> bool:
    """Check if running on macOS."""
    return get_platform() == "darwin"


def is_windows() -> bool:
    """Check if running on Windows."""
    return get_platform() == "windows"


def get_linux_distro() -> Dict[str, str]:
    """
    Detect Linux distribution and package manager.
    
    Returns dict with:
        - name: e.g., "Ubuntu", "Arch Linux", "Fedora"
        - id: e.g., "ubuntu", "arch", "fedora"  
        - version: e.g., "24.04", "rolling"
        - package_manager: e.g., "apt", "pacman", "dnf"
        - family: e.g., "debian", "arch", "rhel"
    """
    result = {
        "name": "Linux",
        "id": "linux",
        "version": "",
        "package_manager": "",
        "family": "linux",
    }
    
    if not is_linux():
        return result
    
    # Try /etc/os-release (standard on modern distros)
    os_release = Path("/etc/os-release")
    if os_release.exists():
        try:
            with open(os_release) as f:
                for line in f:
                    line = line.strip()
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip('"').strip("'")
                        if key == "NAME":
                            result["name"] = value
                        elif key == "ID":
                            result["id"] = value.lower()
                        elif key == "VERSION_ID":
                            result["version"] = value
                        elif key == "ID_LIKE":
                            result["family"] = value.split()[0].lower()  # First entry
        except Exception as e:
            logger.debug(f"Failed to parse /etc/os-release: {e}")
    
    # If family not set, use id as family
    if result["family"] == "linux":
        result["family"] = result["id"]
    
    # Detect package manager based on distro family
    distro_id = result["id"]
    family = result["family"]
    
    if distro_id in ("ubuntu", "debian", "linuxmint", "pop") or family == "debian":
        result["package_manager"] = "apt"
        result["family"] = "debian"
    elif distro_id in ("arch", "manjaro", "endeavouros") or family == "arch":
        result["package_manager"] = "pacman"
        result["family"] = "arch"
    elif distro_id in ("fedora", "rhel", "centos", "rocky", "alma") or family in ("fedora", "rhel"):
        result["package_manager"] = "dnf" if distro_id != "centos" else "yum"
        result["family"] = "rhel"
    elif distro_id in ("opensuse", "sles") or "suse" in family:
        result["package_manager"] = "zypper"
        result["family"] = "suse"
    elif distro_id == "nixos":
        result["package_manager"] = "nix"
        result["family"] = "nixos"
    elif distro_id == "gentoo":
        result["package_manager"] = "emerge"
        result["family"] = "gentoo"
    elif distro_id == "void":
        result["package_manager"] = "xbps"
        result["family"] = "void"
    else:
        # Fallback: check for common package managers
        if Path("/usr/bin/apt").exists():
            result["package_manager"] = "apt"
        elif Path("/usr/bin/pacman").exists():
            result["package_manager"] = "pacman"
        elif Path("/usr/bin/dnf").exists():
            result["package_manager"] = "dnf"
        elif Path("/usr/bin/yum").exists():
            result["package_manager"] = "yum"
    
    return result


def is_mac_apple_silicon() -> bool:
    """
    Detect if running on Mac with Apple Silicon (M1/M2/M3).
    
    Returns:
        True if Mac with Apple Silicon, False otherwise
    """
    if not is_macos():
        return False
    
    try:
        # Check processor architecture
        arch = platform.machine().lower()
        
        # Apple Silicon uses arm64
        if arch == "arm64":
            return True
        
        # Alternative: check with sysctl
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        return "Apple" in result.stdout
    
    except Exception as e:
        logger.debug(f"Failed to detect Apple Silicon: {e}")
        return False


def get_unified_memory_gb() -> Optional[int]:
    """
    Get unified memory size on Mac Apple Silicon.
    
    Returns:
        Memory size in GB, or None if not available
    """
    if not is_mac_apple_silicon():
        return None
    
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # Convert bytes to GB
        memory_bytes = int(result.stdout.strip())
        memory_gb = memory_bytes // (1024 ** 3)
        
        logger.info(f"Detected Mac unified memory: {memory_gb}GB")
        return memory_gb
    
    except Exception as e:
        logger.debug(f"Failed to get unified memory size: {e}")
        return None


def get_config_dir() -> Path:
    """
    Get platform-appropriate configuration directory.
    
    Returns:
        Path to config directory
    
    Platform-specific locations:
    - Linux: ~/.config/cerebric
    - macOS: ~/Library/Application Support/Cerebric
    - Windows: %APPDATA%/Cerebric
    """
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Cerebric"
    elif is_windows():
        # Use AppData/Roaming on Windows
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Cerebric"
    else:  # Linux and others
        return Path.home() / ".config" / "cerebric"


def get_data_dir() -> Path:
    """
    Get platform-appropriate data directory.
    
    Returns:
        Path to data directory
    
    Platform-specific locations:
    - Linux: ~/.local/share/cerebric
    - macOS: ~/Library/Application Support/Cerebric/Data
    - Windows: %LOCALAPPDATA%/Cerebric
    """
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Cerebric" / "Data"
    elif is_windows():
        localappdata = Path.home() / "AppData" / "Local"
        return localappdata / "Cerebric"
    else:  # Linux
        return Path.home() / ".local" / "share" / "cerebric"


def get_cache_dir() -> Path:
    """
    Get platform-appropriate cache directory.
    
    Returns:
        Path to cache directory
    
    Platform-specific locations:
    - Linux: ~/.cache/cerebric
    - macOS: ~/Library/Caches/Cerebric
    - Windows: %LOCALAPPDATA%/Cerebric/Cache
    """
    if is_macos():
        return Path.home() / "Library" / "Caches" / "Cerebric"
    elif is_windows():
        localappdata = Path.home() / "AppData" / "Local"
        return localappdata / "Cerebric" / "Cache"
    else:  # Linux
        return Path.home() / ".cache" / "cerebric"


def get_recommended_provider() -> str:
    """
    Get recommended model provider for current platform.
    
    Returns:
        Provider name: "mlx", "ollama", or "llamacpp"
    """
    if is_mac_apple_silicon():
        # MLX is optimal for Apple Silicon
        return "mlx"
    else:
        # Ollama works well on Linux and Intel Mac
        return "ollama"


def get_platform_info() -> Dict[str, Any]:
    """
    Get comprehensive platform information.
    
    Returns:
        Dictionary with platform details
    """
    info = {
        "platform": get_platform(),
        "is_linux": is_linux(),
        "is_macos": is_macos(),
        "is_windows": is_windows(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "recommended_provider": get_recommended_provider(),
    }
    
    # Add Mac-specific info
    if is_macos():
        info["is_apple_silicon"] = is_mac_apple_silicon()
        if is_mac_apple_silicon():
            info["unified_memory_gb"] = get_unified_memory_gb()
    
    return info


def ensure_directories():
    """
    Ensure platform-specific directories exist.
    
    Creates config, data, and cache directories if they don't exist.
    """
    dirs = [
        get_config_dir(),
        get_data_dir(),
        get_cache_dir(),
    ]
    
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {directory}")


def get_platform_name_friendly() -> str:
    """
    Get human-friendly platform name.
    
    Returns:
        "Linux", "macOS", or "Windows"
    """
    system = get_platform()
    
    if system == "darwin":
        if is_mac_apple_silicon():
            memory = get_unified_memory_gb()
            if memory:
                return f"macOS (Apple Silicon, {memory}GB)"
            return "macOS (Apple Silicon)"
        return "macOS (Intel)"
    elif system == "linux":
        return "Linux"
    elif system == "windows":
        return "Windows"
    else:
        return system.capitalize()
