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
    A system discovery - the core data unit of Cerebric.
    
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
    
    @property
    def mention(self) -> str:
        """Get @mention string for this discovery."""
        return f"@{self.id}"
    
    @property
    def embedding_text(self) -> str:
        """
        Text used for generating embeddings.
        
        This is what ChromaDB indexes for semantic search.
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
    **extra_data
) -> Discovery:
    """
    Factory for backup discoveries.
    
    Simplifies scanner code by providing sensible defaults.
    """
    discovery_id = make_discovery_id(DiscoveryType.BACKUP, name)
    
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
        chat_context=f"This is a {service_type} service named '{name}'. "
                     f"Status: {status}. Enabled: {enabled}.",
    )
