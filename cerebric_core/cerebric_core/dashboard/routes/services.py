"""
Services API routes.

Provides endpoints for service-specific operations including
AI-powered explanations and extended metadata.
"""

from __future__ import annotations
import logging
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

from ..routes.discovery import get_engine
from ...discovery.schema import DiscoveryType
from ...model.router import ModelRouter, TaskType

logger = logging.getLogger('cerebric.dashboard.routes.services')


# Common service name mappings to Arch Wiki articles
ARCH_WIKI_MAPPINGS = {
    'systemd': 'systemd',
    'networkmanager': 'NetworkManager',
    'network-manager': 'NetworkManager',
    'pulseaudio': 'PulseAudio',
    'pipewire': 'PipeWire',
    'bluetooth': 'Bluetooth',
    'cups': 'CUPS',
    'docker': 'Docker',
    'sshd': 'OpenSSH',
    'ssh': 'OpenSSH',
    'ufw': 'Uncomplicated_Firewall',
    'firewalld': 'Firewalld',
    'gdm': 'GDM',
    'sddm': 'SDDM',
    'lightdm': 'LightDM',
    'xorg': 'Xorg',
    'wayland': 'Wayland',
    'avahi': 'Avahi',
    'dbus': 'D-Bus',
    'polkit': 'Polkit',
    'udev': 'Udev',
    'cron': 'Cron',
    'systemd-timesyncd': 'systemd-timesyncd',
    'ntpd': 'Network_Time_Protocol_daemon',
    'smartd': 'S.M.A.R.T.',
    'smartmontools': 'S.M.A.R.T.',
    'snapd': 'Snap',
    'flatpak': 'Flatpak',
    'apparmor': 'AppArmor',
    'selinux': 'SELinux',
    'lvm': 'LVM',
    'btrfs': 'Btrfs',
    'zfs': 'ZFS',
}


def get_documentation_url(service_name: str) -> str:
    """Generate a documentation URL for a service.
    
    Tries to find an Arch Wiki article or falls back to man page search.
    """
    # Normalize service name (remove .service suffix, lowercase)
    base_name = service_name.replace('.service', '').lower()
    
    # Check for snap services
    if base_name.startswith('snap.'):
        # Extract the snap name
        parts = base_name.split('.')
        if len(parts) >= 2:
            return f"https://snapcraft.io/{parts[1]}"
    
    # Check for docker services
    if base_name.startswith('docker-') or 'container' in base_name:
        return "https://wiki.archlinux.org/title/Docker"
    
    # Check direct mappings
    for key, wiki_title in ARCH_WIKI_MAPPINGS.items():
        if key in base_name:
            return f"https://wiki.archlinux.org/title/{wiki_title}"
    
    # Check if it's a systemd service (many have man pages)
    if base_name.startswith('systemd-'):
        return f"https://man.archlinux.org/man/{base_name}.8"
    
    # Fallback to Arch Wiki search
    search_term = base_name.replace('-', '+').replace('_', '+')
    return f"https://wiki.archlinux.org/index.php?search={search_term}"


class ServiceExplanationResponse(BaseModel):
    """Response model for service explanation."""
    service_name: str
    explanation: str
    category: Optional[str] = None
    is_critical: bool = False
    install_source: Optional[str] = None


class ServiceDiagnosisResponse(BaseModel):
    """Response model for service failure diagnosis."""
    service_name: str
    diagnosis: str
    logs_analyzed: bool = False
    status_checked: bool = False


class ServiceActionRequest(BaseModel):
    """Request model for service control actions."""
    action: str  # start, stop, restart


class ServiceActionResponse(BaseModel):
    """Response model for service control actions."""
    service_name: str
    action: str
    success: bool
    message: str
    requires_approval: bool = False


# Singleton model router
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the model router singleton."""
    global _model_router
    if _model_router is None:
        try:
            _model_router = ModelRouter()
            logger.info("ModelRouter initialized for services")
        except Exception as e:
            logger.error(f"Failed to initialize ModelRouter: {e}")
            raise
    return _model_router


router = APIRouter() if FASTAPI_AVAILABLE else None


if FASTAPI_AVAILABLE:
    
    @router.post("/{service_name}/explain", response_model=ServiceExplanationResponse)
    async def explain_service(service_name: str):
        """
        Generate an AI-powered explanation of a service.
        
        Provides detailed information about what the service does,
        why it exists, and its role in the system.
        """
        # Try to find the service in discoveries
        engine = get_engine()
        service = None
        
        # Search for the service
        for discovery in engine.get_by_type(DiscoveryType.SERVICE):
            if discovery.name == service_name or discovery.name.replace('-', '_') == service_name:
                service = discovery
                break
        
        # Get metadata from service if found
        category = None
        is_critical = False
        install_source = None
        description = f"A Linux system service named {service_name}"
        
        if service:
            category = service.data.get('category', 'other')
            is_critical = service.data.get('is_critical', False)
            install_source = service.data.get('install_source', 'unknown')
            description = service.description or description
        
        # Try to generate LLM explanation
        try:
            model_router = get_model_router()
            
            # Generate documentation URL
            doc_url = get_documentation_url(service_name)
            
            prompt = f"""You are a Linux expert explaining a system service to users of varying technical levels.

Service: {service_name}
Description: {description}
Category: {category or 'unknown'}
Is Critical: {'Yes' if is_critical else 'No'}
Installed By: {install_source or 'unknown'}

Format your response EXACTLY like this:

## What this service does and why it exists

[1-2 simple sentences explaining what this service does in plain English. Assume the reader is not technical. Use an everyday analogy if helpful.]

## Technical Details

- **Purpose**: [one line about its technical function]
- **Runs when**: [when does it start/run]
- **Depends on**: [key dependencies, or "standalone" if none]

## Safe to disable?

[1-2 sentences about whether it's safe to disable and what would break]

## Learn More

[Documentation]({doc_url})

Keep it brief and scannable. Use simple language in the first section."""

            response = model_router.generate(
                prompt=prompt,
                task_type=TaskType.CHAT,
                max_tokens=512,
                temperature=0.7
            )
            
            explanation = response.text.strip()
            logger.info(f"Generated explanation for {service_name}")
            
        except Exception as e:
            logger.warning(f"LLM explanation failed for {service_name}: {e}")
            # Fallback to deterministic explanation
            explanation = generate_fallback_explanation(
                service_name, description, category, is_critical, install_source
            )
        
        return ServiceExplanationResponse(
            service_name=service_name,
            explanation=explanation,
            category=category,
            is_critical=is_critical,
            install_source=install_source,
        )

    @router.post("/{service_name}/diagnose", response_model=ServiceDiagnosisResponse)
    async def diagnose_service(service_name: str):
        """
        Diagnose why a service failed.
        
        Analyzes journalctl logs and systemctl status to determine
        the root cause of a service failure.
        """
        import subprocess
        
        logs_analyzed = False
        status_checked = False
        
        # Get service status
        status_output = ""
        try:
            result = subprocess.run(
                ["systemctl", "status", f"{service_name}.service", "--no-pager", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )
            status_output = result.stdout + result.stderr
            status_checked = True
        except Exception as e:
            logger.warning(f"Failed to get service status: {e}")
            status_output = f"Could not retrieve service status: {e}"
        
        # Get recent journal logs
        log_output = ""
        try:
            result = subprocess.run(
                ["journalctl", "-u", f"{service_name}.service", "-n", "50", "--no-pager", "-p", "err..emerg"],
                capture_output=True,
                text=True,
                timeout=10
            )
            log_output = result.stdout
            if not log_output.strip():
                # Try getting any recent logs if no errors found
                result = subprocess.run(
                    ["journalctl", "-u", f"{service_name}.service", "-n", "30", "--no-pager"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                log_output = result.stdout
            logs_analyzed = bool(log_output.strip())
        except Exception as e:
            logger.warning(f"Failed to get journal logs: {e}")
            log_output = f"Could not retrieve logs: {e}"
        
        # Try to generate LLM diagnosis
        try:
            model_router = get_model_router()
            
            prompt = f"""You are a Linux system administrator diagnosing a failed service.

**Service:** {service_name}

**Service Status:**
```
{status_output[:2000]}
```

**Recent Logs:**
```
{log_output[:3000]}
```

Based on the status and logs above, diagnose why this service failed. Provide:

1. **Root Cause**: What specifically caused the failure
2. **Key Error**: The most relevant error message from the logs
3. **Suggested Fix**: Concrete steps to resolve the issue

COMMAND FORMATTING: Put each shell command in its own separate ```bash code block. Never combine multiple commands in one block.

Be specific and actionable. If the logs don't provide enough information, say so and suggest what to check next."""

            response = model_router.generate(
                prompt=prompt,
                task_type=TaskType.CHAT,
                max_tokens=800,
                temperature=0.5  # Lower temperature for more factual analysis
            )
            
            diagnosis = response.text.strip()
            logger.info(f"Generated diagnosis for {service_name}")
            
        except Exception as e:
            logger.warning(f"LLM diagnosis failed for {service_name}: {e}")
            # Fallback to showing raw status/logs
            diagnosis = generate_fallback_diagnosis(service_name, status_output, log_output)
        
        return ServiceDiagnosisResponse(
            service_name=service_name,
            diagnosis=diagnosis,
            logs_analyzed=logs_analyzed,
            status_checked=status_checked,
        )


def generate_fallback_diagnosis(
    name: str,
    status_output: str,
    log_output: str
) -> str:
    """Generate a fallback diagnosis when LLM is unavailable."""
    parts = [f"**{name}** service failure analysis:\n"]
    
    if status_output:
        # Extract key info from status
        if "Active: failed" in status_output:
            parts.append("⚠️ **Status**: Service is in failed state\n")
        if "Main PID" in status_output:
            parts.append("The main process has exited.\n")
    
    if log_output:
        parts.append("\n**Recent Log Entries:**\n")
        # Show last few lines
        log_lines = log_output.strip().split('\n')[-10:]
        for line in log_lines:
            parts.append(f"- {line}\n")
    else:
        parts.append("\nNo error logs found. Try running:\n")
        parts.append(f"```bash\njournalctl -u {name}.service -n 50\n```")
    
    parts.append(f"\n**To investigate further:**\n")
    parts.append(f"```bash\nsystemctl status {name}.service\n```\n")
    parts.append(f"```bash\njournalctl -xe -u {name}.service\n```")
    
    return "".join(parts)


def generate_fallback_explanation(
    name: str,
    description: str,
    category: Optional[str],
    is_critical: bool,
    install_source: Optional[str]
) -> str:
    """Generate a fallback explanation when LLM is unavailable."""
    
    parts = [f"**{name}** is a Linux system service."]
    
    if description and description != f"A Linux system service named {name}":
        parts.append(f"\n\n{description}")
    
    # Category-based context
    category_info = {
        'audio': 'This service is part of the audio subsystem, managing sound hardware and routing.',
        'network': 'This service handles network connectivity, communication, or related protocols.',
        'storage': 'This service manages storage devices, filesystems, or data operations.',
        'desktop': 'This service is part of the desktop environment and user interface.',
        'security': 'This service provides security, authentication, or access control features.',
        'system': 'This is a core system service essential for OS functionality.',
        'print': 'This service manages printing operations and print queues.',
        'virtualization': 'This service provides containerization or virtualization capabilities.',
        'database': 'This service provides database or data storage functionality.',
        'web': 'This service provides web server or HTTP-related functionality.',
    }
    
    if category and category in category_info:
        parts.append(f"\n\n{category_info[category]}")
    
    # Installation source
    if install_source == 'system':
        parts.append("\n\nThis service was installed as part of the operating system.")
    elif install_source == 'user':
        parts.append("\n\nThis service was installed by the user or a third-party application.")
    
    # Criticality warning
    if is_critical:
        parts.append("\n\n⚠️ **Critical Service**: Stopping or disabling this service may affect system stability or functionality.")
    
    return "".join(parts)


if FASTAPI_AVAILABLE:
    @router.post("/services/{service_name}/control")
    async def control_service(service_name: str, request: ServiceActionRequest) -> ServiceActionResponse:
        """
        Control a systemd service (start, stop, restart).
        
        Requires appropriate system permissions.
        """
        import subprocess
        
        action = request.action.lower()
        if action not in ('start', 'stop', 'restart'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {action}. Must be start, stop, or restart."
            )
        
        logger.info(f"Controlling service {service_name}: {action}")
        
        # Build the systemctl command
        unit_name = service_name if service_name.endswith('.service') else f"{service_name}.service"
        
        try:
            # Run systemctl command
            result = subprocess.run(
                ['systemctl', action, unit_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully {action}ed service {service_name}")
                return ServiceActionResponse(
                    service_name=service_name,
                    action=action,
                    success=True,
                    message=f"Service {service_name} {action}ed successfully."
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                
                # Check if it's a permission error
                if "Access denied" in error_msg or "Permission denied" in error_msg or result.returncode == 1:
                    logger.warning(f"Permission denied for {action} on {service_name}")
                    return ServiceActionResponse(
                        service_name=service_name,
                        action=action,
                        success=False,
                        message=f"Permission denied. Try running with sudo or check polkit rules.",
                        requires_approval=True
                    )
                
                logger.error(f"Failed to {action} service {service_name}: {error_msg}")
                return ServiceActionResponse(
                    service_name=service_name,
                    action=action,
                    success=False,
                    message=f"Failed to {action} service: {error_msg}"
                )
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout while {action}ing service {service_name}")
            return ServiceActionResponse(
                service_name=service_name,
                action=action,
                success=False,
                message=f"Operation timed out after 30 seconds."
            )
        except Exception as e:
            logger.error(f"Error controlling service {service_name}: {e}")
            return ServiceActionResponse(
                service_name=service_name,
                action=action,
                success=False,
                message=f"Error: {str(e)}"
            )
