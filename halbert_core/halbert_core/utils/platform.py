# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Platform detection utilities for cross-platform support (Phase 5 M3 / Phase 6 prep).

Provides platform-specific behavior and detection for Linux and macOS.
"""

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger('halbert')


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


def get_macos_version() -> Optional[Tuple[int, int]]:
    """The macOS version as ``(major, minor)``, or None on non-Mac.

    macOS 15.1 (Darwin 24.1) is the first version with Apple Intelligence.
    """
    if not is_macos():
        return None
    try:
        ver_str = platform.mac_ver()[0]
        if not ver_str:
            return None
        parts = ver_str.split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except Exception as e:
        logger.debug(f"Failed to get macOS version: {e}")
        return None


def detect_metal_gpu() -> Optional[Dict[str, Any]]:
    """Detect Metal GPU support on macOS via ``system_profiler``.

    Returns a dict with ``metal_version`` and ``gpu_name`` when Metal is
    available, or None on non-Mac / systems without Metal. Never raises.

    Metal is implied by Apple Silicon, but an explicit check is defensive:
    it catches VMs (UTM/Parallels on the Apple Silicon hypervisor) that
    report ``arm64`` but have no Metal GPU, and it lets the UI display the
    GPU name and Metal version.
    """
    if not is_macos():
        return None
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        displays = (
            data.get("SPDisplaysDataType", [])
            if isinstance(data, dict)
            else data
        )
        if not isinstance(displays, list):
            return None
        for gpu in displays:
            if not isinstance(gpu, dict):
                continue
            # macOS reports Metal support under several possible keys
            # depending on version: mtlgpufamilysupport (modern), or
            # metal-support / metal_support (older schemas).
            metal = (
                gpu.get("spdisplays_mtlgpufamilysupport")
                or gpu.get("spdisplays_metal-support")
                or gpu.get("spdisplays_metal_support")
            )
            if metal:
                return {
                    "metal_version": str(metal),
                    "gpu_name": str(
                        gpu.get("sppci_model") or gpu.get("spdisplays_vendor")
                        or "Apple GPU"
                    ),
                }
    except Exception as e:
        logger.debug(f"Failed to detect Metal GPU: {e}")
    return None


# macOS 15.1 (Darwin 24.1) is the first version with Apple Intelligence.
_APPLE_INTELLIGENCE_MIN_MACOS = (15, 1)

# Halbert-specific RAM floor: macOS + WindowServer (~4-5GB) + Halbert +
# dashboard + the on-device model (~2.5-3GB ANE) leaves nothing on an 8GB
# machine. 16GB is the operational minimum, not Apple's 8GB official floor.
_APPLE_INTELLIGENCE_MIN_RAM_GB = 16


def apple_intelligence_eligible(min_ram_gb: int = _APPLE_INTELLIGENCE_MIN_RAM_GB) -> bool:
    """True when the host qualifies for Apple Intelligence on-device models.

    All four conditions must hold:

    1. Apple Silicon (M1+) — ``is_mac_apple_silicon()``
    2. macOS >= 15.1 (Sequoia) — Apple Intelligence first shipped here
    3. Unified memory >= ``min_ram_gb`` (default 16GB — Halbert's floor)
    4. Metal GPU detected — defensive against arm64 VMs without Metal

    This check does NOT probe the Swift bridge: a qualifying host may have
    the bridge not yet bundled. Use :func:`probe_apple_foundation_bridge`
    (in ``model.hardware_detector``) for the live availability check.
    """
    if not is_mac_apple_silicon():
        return False
    ver = get_macos_version()
    if ver is None or ver < _APPLE_INTELLIGENCE_MIN_MACOS:
        return False
    mem = get_unified_memory_gb()
    if mem is None or mem < min_ram_gb:
        return False
    if detect_metal_gpu() is None:
        return False
    return True


def _is_root() -> bool:
    """True when running as uid 0. False on platforms without geteuid."""
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - Windows
        return False


def get_config_dir() -> Path:
    """
    Get platform-appropriate configuration directory.
    
    Honours HALBERT_CONFIG_DIR (and legacy Halbert_CONFIG_DIR) env overrides
    for multi-instance isolation.
    
    Returns:
        Path to config directory
    
    Platform-specific locations:
    - Linux: ~/.config/halbert
    - macOS: ~/Library/Application Support/Halbert
    - Windows: %APPDATA%/Halbert
    """
    override = os.environ.get("HALBERT_CONFIG_DIR") or os.environ.get("Halbert_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    # A root-run Halbert configures the MACHINE, not one login account's
    # home. This branch came from utils/paths.config_dir when the resolvers
    # were folded together; losing it would have put a system install's
    # config under /var/root.
    if _is_root():
        return Path("/etc/halbert")
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Halbert"
    elif is_windows():
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Halbert"
    else:  # Linux and others
        return Path.home() / ".config" / "halbert"


def get_data_dir() -> Path:
    """
    Get platform-appropriate data directory.
    
    Honours HALBERT_DATA_DIR (and legacy Halbert_DATA_DIR) env overrides
    for multi-instance isolation.
    
    Returns:
        Path to data directory
    
    Platform-specific locations:
    - Linux: ~/.local/share/halbert
    - macOS: ~/Library/Application Support/Halbert/Data
    - Windows: %LOCALAPPDATA%/Halbert
    """
    override = os.environ.get("HALBERT_DATA_DIR") or os.environ.get("Halbert_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Halbert" / "Data"
    elif is_windows():
        localappdata = Path.home() / "AppData" / "Local"
        return localappdata / "Halbert"
    else:  # Linux
        return Path.home() / ".local" / "share" / "halbert"


def get_cache_dir() -> Path:
    """
    Get platform-appropriate cache directory.
    
    Returns:
        Path to cache directory
    
    Platform-specific locations:
    - Linux: ~/.cache/halbert
    - macOS: ~/Library/Caches/Halbert
    - Windows: %LOCALAPPDATA%/Halbert/Cache
    """
    if is_macos():
        return Path.home() / "Library" / "Caches" / "Halbert"
    elif is_windows():
        localappdata = Path.home() / "AppData" / "Local"
        return localappdata / "Halbert" / "Cache"
    else:  # Linux
        return Path.home() / ".cache" / "halbert"


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
