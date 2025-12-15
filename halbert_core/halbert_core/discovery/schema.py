"""
Discovery Schema - Unified data model for all system discoveries.

Every scanner produces Discovery objects that conform to this schema.
The UI renders these generically using DiscoveryCard components.

Based on Phase 9 research - see docs/Phase9/STRATEGIC-SYNTHESIS.md
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import json
import hashlib


class DiscoveryType(str, Enum):
    """
    Categories of discoveries aligned with Phase 9 domains.
    
    Each type corresponds to a deep-dive document and has
    specific UI treatment and scanner implementation.
    """
    # Critical Priority (Phase 9)
    SYSTEM_PRESERVATION = "system_preservation"  # 00
    PERFORMANCE = "performance"                   # 01
    BACKUP = "backup"                             # 02
    NETWORK = "network"                           # 03
    
    # High Priority
    FILESYSTEM = "filesystem"                     # 04
    SERVICE = "service"                           # 05
    PACKAGE = "package"                           # 06
    SECURITY = "security"                         # 07
    DESKTOP = "desktop"                           # 08
    
    # Medium Priority
    STORAGE = "storage"                           # 09
    HARDWARE = "hardware"                         # 10
    GPU = "gpu"                                   # 11, 12
    TASK = "task"                                 # 13
    CONTAINER = "container"                       # 14
    POWER = "power"                               # 15
    SHARING = "sharing"                           # 17 - Network shares, VPN peers
    
    # Lower Priority
    PROCESS = "process"                           # 16
    ALERT = "alert"                               # 17
    SESSION = "session"                           # 18
    PRINTER = "printer"                           # 19


class DiscoverySeverity(str, Enum):
    """
    Severity levels for discoveries.
    
    Determines UI treatment (colors, prominence) and alert behavior.
    """
    CRITICAL = "critical"   # 🔴 Red - Immediate action required
    WARNING = "warning"     # 🟡 Yellow - Attention needed soon
    INFO = "info"           # 🔵 Blue - Informational
    SUCCESS = "success"     # 🟢 Green - Healthy/good state


@dataclass
class DiscoveryAction:
    """
    An action that can be taken on a discovery.
    
    Actions appear as buttons in the UI and can:
    - Run commands (with approval if dangerous)
    - Open dialogs
    - Navigate to other pages
    - Start chat conversations
    """
    id: str                          # Unique action identifier
    label: str                       # Button text
    icon: Optional[str] = None       # Lucide icon name
    command: Optional[str] = None    # Shell command to execute
    requires_approval: bool = False  # Show in Approvals page first
    danger: bool = False             # Red button, extra confirmation
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "command": self.command,
            "requires_approval": self.requires_approval,
            "danger": self.danger,
        }


@dataclass
class Discovery:
    """
    A system discovery - the core data unit of Halbert.
    
    Discoveries are:
    - Found by Scanners (BackupScanner, NetworkScanner, etc.)
    - Stored in ChromaDB (with embeddings for semantic search)
    - Displayed in UI via DiscoveryCard components
    - Referenced in chat via @mentions
    
    Example discoveries:
    - @backup/rsync-home: rsync backup found in crontab
    - @service/nginx: nginx.service systemd unit
    - @storage/dev-sda: Physical disk with SMART data
    - @network/samba-docs: Samba share configuration
    """
    
    # Identity
    id: str                          # Unique ID: {type}/{name}
    type: DiscoveryType              # Category from Phase 9 domains
    name: str                        # Human-readable name
    
    # Display
    title: str                       # Card title
    description: str                 # Card description (1-2 sentences)
    icon: Optional[str] = None       # Lucide icon name
    
    # Status
    severity: DiscoverySeverity = DiscoverySeverity.INFO
    status: Optional[str] = None     # e.g., "Running", "Failed", "Healthy"
    status_detail: Optional[str] = None  # Additional status info
    
    # Metadata
    source: Optional[str] = None     # Where we found this (file path, command, etc.)
    last_scanned: datetime = field(default_factory=datetime.now)
    data: dict = field(default_factory=dict)  # Scanner-specific data
    
    # Actions
    actions: list[DiscoveryAction] = field(default_factory=list)
    
    # Chat integration
    mentionable: bool = True         # Can be @mentioned in chat
    chat_context: Optional[str] = None  # Context injected into chat prompts
    
    # Consolidation (Phase 24) - for grouping related discoveries
    config_path: Optional[str] = None    # Shared config file path (e.g., /etc/btrbk/btrbk.conf)
    group_key: Optional[str] = None      # Key for grouping (e.g., "btrbk:/etc/btrbk/btrbk.conf")
    suppress_display: bool = False       # Hide from main list (e.g., service when config shown)
    related_to: list[str] = field(default_factory=list)  # IDs of related discoveries
    
    @property
    def mention(self) -> str:
        """Get @mention string for this discovery."""
        return f"@{self.id}"
    
    @property
    def embedding_text(self) -> str:
        """
        Text used for generating embeddings.
        
        This is what ChromaDB indexes for semantic search.
        Includes relationship data for better correlation search.
        """
        parts = [
            f"{self.type.value}: {self.name}",
            self.title,
            self.description,
            self.status or "",
            self.status_detail or "",
        ]
        if self.chat_context:
            parts.append(self.chat_context)
        
        # Include key relationship data for semantic search
        if self.data:
            # Storage relationships
            if self.data.get('devices'):
                parts.append(f"devices: {' '.join(self.data['devices'][:5])}")
            if self.data.get('failed_devices'):
                parts.append(f"failed devices: {' '.join(self.data['failed_devices'])}")
            if self.data.get('mount_point'):
                parts.append(f"mount point: {self.data['mount_point']}")
            if self.data.get('smart_status'):
                parts.append(f"SMART: {self.data['smart_status']}")
            # Service relationships
            if self.data.get('is_mount_service'):
                parts.append("mount service")
                if self.data.get('mount_fstype'):
                    parts.append(f"filesystem: {self.data['mount_fstype']}")
            if self.data.get('related_storage'):
                parts.append(f"uses devices: {' '.join(self.data['related_storage'][:5])}")
        
        return " ".join(filter(None, parts))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "severity": self.severity.value,
            "status": self.status,
            "status_detail": self.status_detail,
            "source": self.source,
            "last_scanned": self.last_scanned.isoformat(),
            "data": self.data,
            "actions": [a.to_dict() for a in self.actions],
            "mentionable": self.mentionable,
            "mention": self.mention,
            # Consolidation fields (Phase 24)
            "config_path": self.config_path,
            "group_key": self.group_key,
            "suppress_display": self.suppress_display,
            "related_to": self.related_to,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> Discovery:
        """Create from dictionary."""
        actions = [
            DiscoveryAction(**a) for a in data.get("actions", [])
        ]
        return cls(
            id=data["id"],
            type=DiscoveryType(data["type"]),
            name=data["name"],
            title=data["title"],
            description=data["description"],
            icon=data.get("icon"),
            severity=DiscoverySeverity(data.get("severity", "info")),
            status=data.get("status"),
            status_detail=data.get("status_detail"),
            source=data.get("source"),
            last_scanned=datetime.fromisoformat(data["last_scanned"]) if "last_scanned" in data else datetime.now(),
            data=data.get("data", {}),
            actions=actions,
            mentionable=data.get("mentionable", True),
            chat_context=data.get("chat_context"),
            # Consolidation fields (Phase 24)
            config_path=data.get("config_path"),
            group_key=data.get("group_key"),
            suppress_display=data.get("suppress_display", False),
            related_to=data.get("related_to", []),
        )
    
    def content_hash(self) -> str:
        """
        Generate hash of discovery content.
        
        Used to detect changes between scans.
        """
        content = json.dumps({
            "type": self.type.value,
            "name": self.name,
            "status": self.status,
            "data": self.data,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# Convenience factory functions
def make_discovery_id(type_: DiscoveryType, name: str) -> str:
    """Create standardized discovery ID."""
    # Sanitize name for ID usage
    safe_name = name.lower().replace(" ", "-").replace("/", "-")
    return f"{type_.value}/{safe_name}"


def backup_discovery(
    name: str,
    description: str,
    schedule: Optional[str] = None,
    last_run: Optional[datetime] = None,
    destination: Optional[str] = None,
    source_path: Optional[str] = None,
    tool: str = "unknown",
    status: str = "unknown",
    severity: DiscoverySeverity = DiscoverySeverity.INFO,
    # Consolidation fields (Phase 24)
    config_path: Optional[str] = None,
    group_key: Optional[str] = None,
    suppress_display: bool = False,
    related_to: Optional[list[str]] = None,
    **extra_data
) -> Discovery:
    """
    Factory for backup discoveries.
    
    Simplifies scanner code by providing sensible defaults.
    
    Consolidation fields (Phase 24):
    - config_path: Path to shared config file (e.g., /etc/btrbk/btrbk.conf)
    - group_key: Key for grouping related backups (e.g., "btrbk:/etc/btrbk/btrbk.conf")
    - suppress_display: Hide from main list (for service entries when config shown)
    - related_to: List of related discovery IDs
    """
    discovery_id = make_discovery_id(DiscoveryType.BACKUP, name)
    
    # Auto-generate group_key if config_path provided but group_key not
    if config_path and not group_key:
        group_key = f"{tool}:{config_path}"
    
    return Discovery(
        id=discovery_id,
        type=DiscoveryType.BACKUP,
        name=name,
        title=f"{tool.title()} Backup: {name}",
        description=description,
        icon="archive",
        severity=severity,
        status=status,
        status_detail=f"Schedule: {schedule}" if schedule else None,
        data={
            "tool": tool,
            "schedule": schedule,
            "last_run": last_run.isoformat() if last_run else None,
            "destination": destination,
            "source_path": source_path,
            **extra_data,
        },
        actions=[
            DiscoveryAction(
                id="run_now",
                label="Run Now",
                icon="play",
                requires_approval=True,
            ),
            DiscoveryAction(
                id="view_logs",
                label="View Logs",
                icon="file-text",
            ),
            DiscoveryAction(
                id="chat",
                label="Chat",
                icon="message-circle",
            ),
        ],
        # Consolidation fields
        config_path=config_path,
        group_key=group_key,
        suppress_display=suppress_display,
        related_to=related_to or [],
        chat_context=f"This is a {tool} backup named '{name}'. "
                     f"It backs up {source_path or 'files'} to {destination or 'unknown destination'}. "
                     f"Schedule: {schedule or 'unknown'}. Status: {status}.",
    )


def service_discovery(
    name: str,
    description: str,
    status: str = "unknown",
    service_type: str = "systemd",  # systemd, docker, process
    enabled: bool = True,
    memory_mb: Optional[float] = None,
    cpu_percent: Optional[float] = None,
    severity: DiscoverySeverity = DiscoverySeverity.INFO,
    **extra_data
) -> Discovery:
    """Factory for service discoveries."""
    discovery_id = make_discovery_id(DiscoveryType.SERVICE, name)
    
    # Determine icon based on service type
    icons = {
        "systemd": "server",
        "docker": "container",
        "process": "cpu",
    }
    
    return Discovery(
        id=discovery_id,
        type=DiscoveryType.SERVICE,
        name=name,
        title=f"{name}",
        description=description,
        icon=icons.get(service_type, "server"),
        severity=severity,
        status=status,
        data={
            "service_type": service_type,
            "enabled": enabled,
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            **extra_data,
        },
        actions=[
            DiscoveryAction(
                id="restart",
                label="Restart",
                icon="refresh-cw",
                requires_approval=True,
            ),
            DiscoveryAction(
                id="stop",
                label="Stop",
                icon="square",
                requires_approval=True,
                danger=True,
            ),
            DiscoveryAction(
                id="logs",
                label="Logs",
                icon="file-text",
            ),
        ],
        chat_context=_build_service_chat_context(name, service_type, status, enabled, extra_data),
    )


def _build_service_chat_context(name: str, service_type: str, status: str, enabled: bool, extra_data: dict) -> str:
    """Build rich chat context for service discoveries, including storage relationships."""
    parts = [f"This is a {service_type} service named '{name}'. Status: {status}. Enabled: {enabled}."]
    
    # Add mount/storage relationship info if present
    if extra_data.get('is_mount_service'):
        mount_point = extra_data.get('mount_point')
        mount_device = extra_data.get('mount_device')
        mount_fstype = extra_data.get('mount_fstype')
        related_storage = extra_data.get('related_storage', [])
        
        if mount_point:
            parts.append(f"This service mounts to: {mount_point}")
        if mount_fstype:
            parts.append(f"Filesystem type: {mount_fstype}")
        if mount_device:
            parts.append(f"Device: {mount_device}")
        if related_storage:
            parts.append(f"Related devices: {', '.join(related_storage)}")
        
        # Critical hint for correlation
        if status.lower() in ['failed', 'error']:
            parts.append("⚠️ If this mount service failed, check if any of its devices have SMART failures or if the pool is healthy.")
    
    return " ".join(parts)
