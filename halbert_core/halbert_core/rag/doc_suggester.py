# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Documentation Suggester - Auto-discover documentation opportunities.

Bridges the Discovery System with RAG by:
1. Analyzing discovered services/apps
2. Finding relevant documentation sources
3. Suggesting documentation additions to users

Implements the self-learning ideology: Halbert learns what's on your system
and proactively helps you build a knowledge base for it.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Documentation Source Registry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DocSource:
    """A documentation source that can be added to RAG."""
    name: str                    # Display name
    url: str                     # Primary documentation URL
    description: str             # What this documentation covers
    keywords: List[str]          # Keywords for matching to discoveries
    category: str = "general"    # Category: tool, service, language, etc.
    priority: int = 5            # 1-10, higher = more important
    official: bool = True        # Is this official documentation?


# Registry of known documentation sources mapped to services/tools
DOC_SOURCE_REGISTRY: Dict[str, DocSource] = {
    # ═══════════════════════════════════════════════════════════════════════════
    # VPN & Networking Tools
    # ═══════════════════════════════════════════════════════════════════════════
    "tailscale": DocSource(
        name="Tailscale Documentation",
        url="https://tailscale.com/kb",
        description="Tailscale VPN mesh network - setup, configuration, ACLs, and troubleshooting",
        keywords=["tailscale", "tailscaled", "mesh", "vpn", "wireguard"],
        category="networking",
        priority=8,
    ),
    "wireguard": DocSource(
        name="WireGuard Documentation",
        url="https://www.wireguard.com/quickstart/",
        description="WireGuard VPN - fast, modern VPN tunnel",
        keywords=["wireguard", "wg", "wg-quick"],
        category="networking",
        priority=8,
    ),
    "openvpn": DocSource(
        name="OpenVPN Documentation",
        url="https://openvpn.net/community-resources/",
        description="OpenVPN - SSL VPN solution",
        keywords=["openvpn"],
        category="networking",
        priority=7,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Container & Orchestration
    # ═══════════════════════════════════════════════════════════════════════════
    "docker": DocSource(
        name="Docker Documentation",
        url="https://docs.docker.com/",
        description="Docker container platform - images, containers, compose, networking",
        keywords=["docker", "dockerd", "containerd", "docker-compose"],
        category="containers",
        priority=9,
    ),
    "podman": DocSource(
        name="Podman Documentation",
        url="https://docs.podman.io/",
        description="Podman - daemonless container engine",
        keywords=["podman"],
        category="containers",
        priority=8,
    ),
    "kubernetes": DocSource(
        name="Kubernetes Documentation",
        url="https://kubernetes.io/docs/",
        description="Kubernetes container orchestration",
        keywords=["kubernetes", "kubectl", "kubelet", "k8s", "minikube", "k3s"],
        category="containers",
        priority=9,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Web Servers & Proxies
    # ═══════════════════════════════════════════════════════════════════════════
    "nginx": DocSource(
        name="NGINX Documentation",
        url="https://nginx.org/en/docs/",
        description="NGINX web server and reverse proxy",
        keywords=["nginx"],
        category="webserver",
        priority=9,
    ),
    "apache": DocSource(
        name="Apache HTTP Server Documentation",
        url="https://httpd.apache.org/docs/",
        description="Apache HTTP Server - web server",
        keywords=["apache", "apache2", "httpd"],
        category="webserver",
        priority=8,
    ),
    "caddy": DocSource(
        name="Caddy Documentation",
        url="https://caddyserver.com/docs/",
        description="Caddy - automatic HTTPS web server",
        keywords=["caddy"],
        category="webserver",
        priority=7,
    ),
    "traefik": DocSource(
        name="Traefik Documentation",
        url="https://doc.traefik.io/traefik/",
        description="Traefik - cloud native reverse proxy",
        keywords=["traefik"],
        category="webserver",
        priority=8,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Databases
    # ═══════════════════════════════════════════════════════════════════════════
    "postgresql": DocSource(
        name="PostgreSQL Documentation",
        url="https://www.postgresql.org/docs/",
        description="PostgreSQL relational database",
        keywords=["postgresql", "postgres", "psql"],
        category="database",
        priority=9,
    ),
    "mysql": DocSource(
        name="MySQL Documentation",
        url="https://dev.mysql.com/doc/",
        description="MySQL relational database",
        keywords=["mysql", "mysqld", "mariadb"],
        category="database",
        priority=9,
    ),
    "redis": DocSource(
        name="Redis Documentation",
        url="https://redis.io/docs/",
        description="Redis in-memory data store",
        keywords=["redis", "redis-server"],
        category="database",
        priority=8,
    ),
    "mongodb": DocSource(
        name="MongoDB Documentation",
        url="https://www.mongodb.com/docs/",
        description="MongoDB document database",
        keywords=["mongodb", "mongod"],
        category="database",
        priority=8,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Monitoring & Observability
    # ═══════════════════════════════════════════════════════════════════════════
    "prometheus": DocSource(
        name="Prometheus Documentation",
        url="https://prometheus.io/docs/",
        description="Prometheus monitoring and alerting",
        keywords=["prometheus"],
        category="monitoring",
        priority=8,
    ),
    "grafana": DocSource(
        name="Grafana Documentation",
        url="https://grafana.com/docs/",
        description="Grafana visualization and dashboards",
        keywords=["grafana", "grafana-server"],
        category="monitoring",
        priority=8,
    ),
    "netdata": DocSource(
        name="Netdata Documentation",
        url="https://learn.netdata.cloud/",
        description="Netdata real-time monitoring",
        keywords=["netdata"],
        category="monitoring",
        priority=7,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Backup & Storage
    # ═══════════════════════════════════════════════════════════════════════════
    "restic": DocSource(
        name="Restic Documentation",
        url="https://restic.readthedocs.io/",
        description="Restic backup program",
        keywords=["restic"],
        category="backup",
        priority=8,
    ),
    "borgbackup": DocSource(
        name="BorgBackup Documentation",
        url="https://borgbackup.readthedocs.io/",
        description="BorgBackup deduplicating backup",
        keywords=["borg", "borgbackup"],
        category="backup",
        priority=8,
    ),
    "rclone": DocSource(
        name="Rclone Documentation",
        url="https://rclone.org/docs/",
        description="Rclone - sync to cloud storage",
        keywords=["rclone"],
        category="backup",
        priority=8,
    ),
    "btrbk": DocSource(
        name="btrbk Documentation",
        url="https://digint.ch/btrbk/doc/btrbk.1.html",
        description="btrbk - btrfs snapshot backup tool",
        keywords=["btrbk"],
        category="backup",
        priority=7,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Message Queues & Streaming
    # ═══════════════════════════════════════════════════════════════════════════
    "rabbitmq": DocSource(
        name="RabbitMQ Documentation",
        url="https://www.rabbitmq.com/docs",
        description="RabbitMQ message broker",
        keywords=["rabbitmq", "rabbitmq-server"],
        category="messaging",
        priority=8,
    ),
    "kafka": DocSource(
        name="Apache Kafka Documentation",
        url="https://kafka.apache.org/documentation/",
        description="Apache Kafka event streaming",
        keywords=["kafka"],
        category="messaging",
        priority=8,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Development Tools
    # ═══════════════════════════════════════════════════════════════════════════
    "git": DocSource(
        name="Git Documentation",
        url="https://git-scm.com/doc",
        description="Git version control",
        keywords=["git"],
        category="development",
        priority=9,
    ),
    "nodejs": DocSource(
        name="Node.js Documentation",
        url="https://nodejs.org/docs/",
        description="Node.js JavaScript runtime",
        keywords=["node", "nodejs", "npm"],
        category="development",
        priority=8,
    ),
    "python": DocSource(
        name="Python Documentation",
        url="https://docs.python.org/3/",
        description="Python programming language",
        keywords=["python", "python3", "pip"],
        category="development",
        priority=9,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Security
    # ═══════════════════════════════════════════════════════════════════════════
    "fail2ban": DocSource(
        name="Fail2ban Documentation",
        url="https://www.fail2ban.org/wiki/index.php/MANUAL_0_8",
        description="Fail2ban intrusion prevention",
        keywords=["fail2ban"],
        category="security",
        priority=8,
    ),
    "ufw": DocSource(
        name="UFW Documentation",
        url="https://help.ubuntu.com/community/UFW",
        description="Uncomplicated Firewall",
        keywords=["ufw"],
        category="security",
        priority=7,
    ),
    "crowdsec": DocSource(
        name="CrowdSec Documentation",
        url="https://docs.crowdsec.net/",
        description="CrowdSec security engine",
        keywords=["crowdsec"],
        category="security",
        priority=8,
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # System Services
    # ═══════════════════════════════════════════════════════════════════════════
    "sshd": DocSource(
        name="OpenSSH Documentation",
        url="https://www.openssh.com/manual.html",
        description="OpenSSH server and client",
        keywords=["ssh", "sshd", "openssh"],
        category="system",
        priority=9,
    ),
    "cron": DocSource(
        name="Cron Documentation",
        url="https://man7.org/linux/man-pages/man5/crontab.5.html",
        description="Cron job scheduler",
        keywords=["cron", "crond", "anacron"],
        category="system",
        priority=8,
    ),
    "systemd": DocSource(
        name="systemd Documentation",
        url="https://www.freedesktop.org/wiki/Software/systemd/",
        description="systemd system and service manager",
        keywords=["systemd", "systemctl", "journald"],
        category="system",
        priority=9,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Documentation Suggestion
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DocSuggestion:
    """A suggestion to add documentation to RAG."""
    doc_source: DocSource           # The documentation source
    discovery_id: str               # What triggered this suggestion
    discovery_name: str             # Human-readable discovery name  
    confidence: float               # 0.0-1.0 match confidence
    reason: str                     # Why we're suggesting this
    already_indexed: bool = False   # Already in RAG?
    dismissed: bool = False         # User dismissed this suggestion?
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "doc_key": self._get_doc_key(),
            "doc_name": self.doc_source.name,
            "doc_url": self.doc_source.url,
            "doc_description": self.doc_source.description,
            "doc_category": self.doc_source.category,
            "discovery_id": self.discovery_id,
            "discovery_name": self.discovery_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "already_indexed": self.already_indexed,
            "dismissed": self.dismissed,
            "priority": self.doc_source.priority,
        }
    
    def _get_doc_key(self) -> str:
        """Get the registry key for this doc source."""
        for key, source in DOC_SOURCE_REGISTRY.items():
            if source == self.doc_source:
                return key
        return "unknown"


class DocSuggester:
    """
    Analyzes system discoveries and suggests relevant documentation.
    
    This implements the self-learning concept: Halbert discovers what's
    running on your system and helps you build knowledge for it.
    """
    
    def __init__(self):
        self._dismissed: set = set()  # Dismissed suggestion keys
        self._indexed: set = set()    # Already indexed doc keys
        self._load_state()
    
    def _load_state(self):
        """Load dismissed/indexed state from disk."""
        try:
            from pathlib import Path
            import json
            state_file = Path.home() / ".local" / "share" / "halbert" / "doc_suggestions.json"
            if state_file.exists():
                data = json.loads(state_file.read_text())
                self._dismissed = set(data.get("dismissed", []))
                self._indexed = set(data.get("indexed", []))
        except Exception as e:
            logger.debug(f"Could not load suggestion state: {e}")
    
    def _save_state(self):
        """Save dismissed/indexed state to disk."""
        try:
            from pathlib import Path
            import json
            state_file = Path.home() / ".local" / "share" / "halbert" / "doc_suggestions.json"
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps({
                "dismissed": list(self._dismissed),
                "indexed": list(self._indexed),
            }))
        except Exception as e:
            logger.warning(f"Could not save suggestion state: {e}")
    
    def analyze_discoveries(self, discoveries: List[dict]) -> List[DocSuggestion]:
        """
        Analyze discoveries and return documentation suggestions.
        
        Args:
            discoveries: List of discovery dicts from the discovery engine
            
        Returns:
            List of DocSuggestion objects, sorted by priority
        """
        suggestions = []
        seen_docs = set()
        
        for discovery in discoveries:
            disc_name = discovery.get("name", "").lower()
            disc_title = discovery.get("title", "").lower()
            disc_id = discovery.get("id", "")
            disc_type = discovery.get("type", "")
            
            # Check against registry
            for doc_key, doc_source in DOC_SOURCE_REGISTRY.items():
                if doc_key in seen_docs:
                    continue
                    
                # Match by keywords
                confidence, reason = self._match_discovery(
                    disc_name, disc_title, disc_id, disc_type,
                    doc_source.keywords, doc_source.name
                )
                
                if confidence > 0.5:
                    suggestion = DocSuggestion(
                        doc_source=doc_source,
                        discovery_id=disc_id,
                        discovery_name=discovery.get("title", disc_name),
                        confidence=confidence,
                        reason=reason,
                        already_indexed=doc_key in self._indexed,
                        dismissed=doc_key in self._dismissed,
                    )
                    suggestions.append(suggestion)
                    seen_docs.add(doc_key)
        
        # Sort by priority * confidence, non-indexed first
        suggestions.sort(
            key=lambda s: (s.already_indexed, s.dismissed, -s.doc_source.priority * s.confidence)
        )
        
        return suggestions
    
    def _match_discovery(
        self, 
        name: str, 
        title: str, 
        disc_id: str,
        disc_type: str,
        keywords: List[str],
        doc_name: str
    ) -> Tuple[float, str]:
        """
        Match a discovery against doc keywords.
        
        Returns:
            Tuple of (confidence, reason)
        """
        name_lower = name.lower()
        title_lower = title.lower()
        id_lower = disc_id.lower()
        
        for keyword in keywords:
            kw = keyword.lower()
            
            # Exact name match
            if kw == name_lower or kw in name_lower.split('-'):
                return 1.0, f"'{name}' service matches {doc_name}"
            
            # Name contains keyword
            if kw in name_lower:
                return 0.9, f"'{name}' contains '{keyword}'"
            
            # Title contains keyword
            if kw in title_lower:
                return 0.8, f"'{title}' mentions '{keyword}'"
            
            # ID contains keyword
            if kw in id_lower:
                return 0.7, f"Discovery ID contains '{keyword}'"
        
        return 0.0, ""
    
    def dismiss_suggestion(self, doc_key: str):
        """Dismiss a suggestion so it won't appear again."""
        self._dismissed.add(doc_key)
        self._save_state()
    
    def mark_indexed(self, doc_key: str):
        """Mark a doc as indexed in RAG."""
        self._indexed.add(doc_key)
        self._save_state()
    
    def reset_dismissed(self):
        """Reset all dismissed suggestions."""
        self._dismissed.clear()
        self._save_state()


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════

_suggester: Optional[DocSuggester] = None

def get_suggester() -> DocSuggester:
    """Get singleton suggester instance."""
    global _suggester
    if _suggester is None:
        _suggester = DocSuggester()
    return _suggester


def get_suggestions_for_system() -> List[dict]:
    """
    Get documentation suggestions based on current system discoveries.
    
    This is the main entry point for the UI to get suggestions.
    """
    try:
        from ..discovery.engine import get_engine
        
        engine = get_engine()
        # Get cached discoveries (don't trigger new scan)
        discoveries = [d.to_dict() for d in engine.get_all()]
        
        suggester = get_suggester()
        suggestions = suggester.analyze_discoveries(discoveries)
        
        # Filter out dismissed and already indexed (unless user wants to see all)
        active_suggestions = [
            s.to_dict() for s in suggestions
            if not s.dismissed and not s.already_indexed
        ]
        
        return active_suggestions
    except Exception as e:
        logger.error(f"Failed to get suggestions: {e}")
        return []


def get_all_doc_sources() -> List[dict]:
    """Get all available documentation sources for manual browsing."""
    return [
        {
            "key": key,
            "name": source.name,
            "url": source.url,
            "description": source.description,
            "category": source.category,
            "priority": source.priority,
            "official": source.official,
        }
        for key, source in DOC_SOURCE_REGISTRY.items()
    ]
