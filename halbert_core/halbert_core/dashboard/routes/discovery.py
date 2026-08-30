# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Discovery API routes.

Provides REST endpoints for discovery engine operations:
- List discoveries
- Get specific discovery
- Trigger scans
- Search discoveries
- Get backup history
"""

from __future__ import annotations
import logging
import subprocess
import re
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    BaseModel = object
    FileResponse = object

from ...discovery import DiscoveryType
from ...discovery.engine import get_engine  # Use the singleton from engine.py

logger = logging.getLogger('halbert.dashboard.routes.discovery')

router = APIRouter() if FASTAPI_AVAILABLE else None


if FASTAPI_AVAILABLE:
    
    @router.get("/")
    async def list_discoveries(
        type: Optional[str] = Query(None, description="Filter by type"),
        severity: Optional[str] = Query(None, description="Filter by severity"),
    ):
        """
        List all discoveries.
        
        Optionally filter by type or severity.
        """
        engine = get_engine()
        
        if type:
            try:
                discovery_type = DiscoveryType(type)
                discoveries = engine.get_by_type(discovery_type)
            except ValueError:
                raise HTTPException(400, f"Invalid type: {type}")
        else:
            discoveries = engine.get_all()
        
        # Filter by severity if specified
        if severity:
            discoveries = [d for d in discoveries if d.severity.value == severity]
        
        return {
            "discoveries": [d.to_dict() for d in discoveries],
            "count": len(discoveries),
        }
    
    
    @router.get("/stats")
    async def get_stats():
        """Get discovery statistics."""
        engine = get_engine()
        return engine.get_stats()
    
    
    @router.get("/mentionables")
    async def get_mentionables():
        """
        Get list of mentionable discoveries for chat autocomplete.
        
        Includes special mentionables like @terminal for terminal context.
        """
        engine = get_engine()
        
        # Start with discovery-based mentionables
        mentionables = engine.get_mentionables()
        
        # Add special mentionables (Phase 13)
        special_mentionables = [
            {
                "id": "terminal",
                "mention": "@terminal",
                "name": "Terminal History",
                "type": "context",
                "icon": "terminal",
            },
        ]
        
        return {
            "mentionables": special_mentionables + mentionables
        }
    
    
    @router.get("/icon")
    async def get_app_icon(path: str = Query(..., description="Icon file path")):
        """
        Serve an app icon file.
        
        Used to display Flatpak/Snap icons in the Apps page.
        Only serves files from allowed icon directories for security.
        """
        from pathlib import Path
        import mimetypes
        
        icon_path = Path(path)
        
        # Security: Only allow serving from known icon directories
        allowed_prefixes = [
            '/var/lib/flatpak/',
            '/var/lib/snapd/',
            '/snap/',
            str(Path.home() / '.local/share/flatpak/'),
        ]
        
        path_str = str(icon_path.resolve())
        if not any(path_str.startswith(prefix) for prefix in allowed_prefixes):
            raise HTTPException(403, "Icon path not allowed")
        
        if not icon_path.exists():
            raise HTTPException(404, "Icon not found")
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(str(icon_path))
        if content_type is None:
            content_type = 'application/octet-stream'
        
        return FileResponse(
            path=str(icon_path),
            media_type=content_type,
            filename=icon_path.name
        )
    
    
    @router.post("/scan")
    async def trigger_scan(type: Optional[str] = Query(None)):
        """
        Trigger a discovery scan.
        
        If type is specified, only scan that type.
        Otherwise, run all scanners.
        """
        engine = get_engine()
        
        if type:
            try:
                discovery_type = DiscoveryType(type)
                discoveries = engine.scan_type(discovery_type)
            except ValueError:
                raise HTTPException(400, f"Invalid type: {type}")
        else:
            discoveries = engine.scan_all()
        
        return {
            "message": "Scan complete",
            "discoveries_found": len(discoveries),
            "stats": engine.get_stats(),
        }
    
    
    @router.get("/search")
    async def search_discoveries(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, description="Max results"),
    ):
        """
        Search discoveries by text.
        
        Uses semantic search if ChromaDB is available.
        """
        engine = get_engine()
        discoveries = engine.search(q, limit=limit)
        
        return {
            "query": q,
            "discoveries": [d.to_dict() for d in discoveries],
            "count": len(discoveries),
        }
    
    
    @router.get("/backup/{backup_name}/history")
    async def get_backup_history(
        backup_name: str,
        limit: int = Query(10, description="Max history entries"),
    ):
        """
        Get execution history for a backup.
        
        Queries systemd journal, timeshift, or other sources based on backup type.
        """
        history = await _fetch_backup_history(backup_name, limit)
        
        # Also get current service status
        last_run_status = _get_last_run_status(f"{backup_name}.service")
        
        return {
            "backup_name": backup_name,
            "history": history,
            "count": len(history),
            "last_run_status": last_run_status,
        }
    
    
    @router.get("/backup/statuses")
    async def get_all_backup_statuses():
        """
        Get last run status for all discovered backups.
        
        Used on page load to show accurate status badges.
        """
        engine = get_engine()
        
        try:
            backup_type = DiscoveryType("backup")
            backups = engine.get_by_type(backup_type)
        except ValueError:
            backups = []
        
        statuses = {}
        for backup in backups:
            service_name = f"{backup.name}.service"
            last_status = _get_last_run_status(service_name)
            if last_status:
                statuses[backup.name] = {
                    "last_run_status": last_status,
                    "severity": "critical" if last_status == "failed" else "success",
                }
        
        return {"statuses": statuses}
    
    
    @router.get("/backup/{backup_name}/logs")
    async def get_backup_logs(
        backup_name: str,
        lines: int = Query(100, description="Number of log lines to fetch"),
    ):
        """
        Get journal logs for a backup service/timer.
        
        Fetches from both the .service and .timer units.
        """
        logs = []
        errors = []
        
        # Try service unit first
        service_name = f"{backup_name}.service"
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "-o", "short"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.stdout.strip():
                logs.append(f"=== {service_name} ===\n{result.stdout}")
        except Exception as e:
            errors.append(f"Failed to get {service_name} logs: {e}")
        
        # Also try timer unit
        timer_name = f"{backup_name}.timer"
        try:
            result = subprocess.run(
                ["journalctl", "-u", timer_name, "-n", str(min(lines, 50)), "--no-pager", "-o", "short"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.stdout.strip():
                logs.append(f"=== {timer_name} ===\n{result.stdout}")
        except Exception as e:
            errors.append(f"Failed to get {timer_name} logs: {e}")
        
        # If no logs found, provide helpful message
        if not logs:
            logs.append(f"No journal logs found for {backup_name}.\n\nThis backup may use a different logging mechanism or hasn't run yet.")
        
        return {
            "backup_name": backup_name,
            "logs": "\n\n".join(logs),
            "errors": errors if errors else None,
        }
    
    
    # ============== Learned Classifications ==============
    # Allows the system to learn and remember what components are
    
    class LearnedClassificationRequest(BaseModel):
        """Request to save a learned classification."""
        name: str  # Component name or pattern
        type: str  # Classification type (e.g., "Tailscale VPN")
        description: str  # What it does
        purpose: str = ""  # Why it's on the system
    
    @router.get("/learned/classifications")
    async def get_learned_classifications():
        """Get all learned classifications."""
        from ...discovery.learned import get_learned_store
        
        store = get_learned_store()
        classifications = store.get_all()
        
        return {
            "classifications": {k: v.to_dict() for k, v in classifications.items()},
            "count": len(classifications),
        }
    
    @router.post("/learned/classify")
    async def save_learned_classification(request: LearnedClassificationRequest):
        """
        Save a user-provided classification for a component.
        
        This allows users to correct AI guesses or classify unknown items.
        """
        from ...discovery.learned import get_learned_store
        
        store = get_learned_store()
        store.set(
            name=request.name,
            type=request.type,
            description=request.description,
            purpose=request.purpose,
            source='user',
            verified=True
        )
        
        return {
            "message": f"Classification saved for '{request.name}'",
            "type": request.type,
        }
    
    @router.delete("/learned/classifications/{name:path}")
    async def delete_learned_classification(name: str):
        """Delete a learned classification."""
        from ...discovery.learned import get_learned_store
        
        store = get_learned_store()
        if store.delete(name):
            return {"message": f"Classification deleted for '{name}'"}
        else:
            raise HTTPException(404, f"Classification not found: {name}")
    
    @router.post("/learned/identify")
    async def identify_unknown_component(
        name: str = Query(..., description="Component name to identify"),
        context: str = Query("", description="Additional context (MAC, operstate, etc.)"),
    ):
        """
        Use RAG + LLM to identify an unknown system component.
        
        Queries the knowledge base and uses AI to classify the component.
        Returns a suggested classification that can be saved.
        """
        from ...rag.pipeline import RAGPipeline
        from pathlib import Path
        import os
        
        # Build query for RAG
        query = f"What is {name}? {context}"
        
        try:
            # Initialize RAG pipeline
            data_dir = Path(os.environ.get('Halbert_DATA_DIR', Path.home() / '.local' / 'share' / 'halbert'))
            rag = RAGPipeline(data_dir=data_dir, use_reranking=False, top_k=3)
            
            # Check if we have indexed documents
            merged_path = data_dir / 'linux' / 'merged' / 'rag_corpus_merged.jsonl'
            if merged_path.exists():
                rag.load_and_index_documents(merged_path)
                
                # Retrieve relevant docs
                docs = rag.retrieve(query)
                
                if docs:
                    # Build context from retrieved docs
                    rag_context = "\n".join([
                        f"- {doc.get('name', 'Unknown')}: {doc.get('description', doc.get('content', '')[:200])}"
                        for doc in docs[:3]
                    ])
                    
                    return {
                        "name": name,
                        "found_in_knowledge_base": True,
                        "relevant_docs": [
                            {"name": d.get("name"), "description": d.get("description", "")[:200]}
                            for d in docs[:3]
                        ],
                        "suggested_type": _extract_type_from_docs(name, docs),
                        "suggested_description": _extract_description_from_docs(name, docs),
                        "confidence": 0.7 if docs else 0.3,
                    }
            
            # No RAG data available
            return {
                "name": name,
                "found_in_knowledge_base": False,
                "relevant_docs": [],
                "suggested_type": "Unknown",
                "suggested_description": f"Unidentified component: {name}",
                "confidence": 0.1,
            }
            
        except Exception as e:
            logger.error(f"Failed to identify component: {e}")
            return {
                "name": name,
                "found_in_knowledge_base": False,
                "error": str(e),
                "suggested_type": "Unknown",
                "suggested_description": f"Could not identify: {name}",
                "confidence": 0.0,
            }


    @router.post("/overview/{overview_type}")
    async def generate_overview(overview_type: str):
        """
        Generate an AI-powered ecosystem overview for complex setups.
        
        Provides a high-level description of the user's configuration in plain English.
        Useful for: backups (backup strategy), storage (disk layout), network (firewall rules)
        """
        engine = get_engine()
        
        try:
            discovery_type = DiscoveryType(overview_type)
            discoveries = engine.get_by_type(discovery_type)
        except ValueError:
            discoveries = []
        
        if not discoveries:
            return {
                "overview": f"No {overview_type} configurations discovered yet.",
                "complexity": "none",
            }
        
        # Build overview context based on type
        context = _build_overview_context(overview_type, discoveries)
        
        # Generate overview
        try:
            overview = await _generate_overview(context, overview_type)
            return overview
        except Exception as e:
            logger.error(f"Overview generation failed: {e}")
            return {
                "overview": f"Found {len(discoveries)} {overview_type} configurations.",
                "complexity": "unknown",
            }
    
    
    @router.get("/{discovery_id:path}")
    async def get_discovery(discovery_id: str):
        """
        Get a specific discovery by ID.
        
        ID format: {type}/{name}, e.g., "backup/rsync-home"
        """
        engine = get_engine()
        discovery = engine.get_by_id(discovery_id)
        
        if not discovery:
            raise HTTPException(404, f"Discovery not found: {discovery_id}")
        
        return discovery.to_dict()


async def _fetch_backup_history(backup_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch backup execution history from various sources.
    
    For systemd timers: queries journalctl
    For timeshift: queries timeshift --list
    For btrbk: queries btrbk list and parses snapshot timestamps
    """
    history: List[Dict[str, Any]] = []
    
    # Handle btrbk snapshot configs (btrbk-@, btrbk-@home, etc.)
    if backup_name.startswith("btrbk-"):
        history = await _fetch_btrbk_history(backup_name, limit)
        if history:
            return history
    
    # Try systemd journal first (most common for timer-based backups)
    service_name = f"{backup_name}.service"
    try:
        # Get journal entries for this service - go back 90 days for history
        result = subprocess.run(
            [
                "journalctl",
                "-u", service_name,
                "--no-pager",
                "-o", "json",
                "--since", "90 days ago",  # Get 90 days of history
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            history = _parse_systemd_journal(result.stdout, limit)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Failed to query journal for {service_name}: {e}")
    
    # If no systemd history, try timeshift for timeshift backups
    if not history and backup_name == "timeshift":
        history = await _fetch_timeshift_history(limit)
    
    return history


def _get_last_run_status(service_name: str) -> Optional[str]:
    """
    Get the status of the last run for a systemd service.
    
    Returns: 'success', 'failed', or None
    """
    try:
        # Check if service failed
        result = subprocess.run(
            ["systemctl", "is-failed", service_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip() == "failed":
            return "failed"
        
        # Check if service is active (for oneshot services, this means it succeeded)
        result = subprocess.run(
            ["systemctl", "show", service_name, "--property=Result"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "Result=success" in result.stdout:
            return "success"
        elif "Result=exit-code" in result.stdout or "Result=failed" in result.stdout:
            return "failed"
            
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None


def _parse_systemd_journal(journal_output: str, limit: int) -> List[Dict[str, Any]]:
    """Parse systemd journal JSON output into backup history entries."""
    import json
    
    history: List[Dict[str, Any]] = []
    runs: Dict[str, Dict[str, Any]] = {}  # Track runs by start time
    
    for line in journal_output.strip().split('\n'):
        if not line:
            continue
        try:
            entry = json.loads(line)
            message = entry.get('MESSAGE', '')
            # MESSAGE can be a list in some journal entries - normalize to string
            if isinstance(message, list):
                message = ' '.join(str(m) for m in message)
            elif not isinstance(message, str):
                message = str(message) if message else ''
            timestamp_us = entry.get('__REALTIME_TIMESTAMP')
            
            if not timestamp_us:
                continue
                
            # Convert microseconds to datetime
            timestamp = datetime.fromtimestamp(int(timestamp_us) / 1_000_000)
            ts_key = timestamp.strftime('%Y-%m-%d %H:%M')
            
            # Detect service start
            if 'Started' in message or 'Starting' in message:
                if ts_key not in runs:
                    runs[ts_key] = {
                        'timestamp': timestamp.isoformat(),
                        'status': 'running',
                        'start_time': timestamp,
                    }
            
            # Detect service completion
            elif 'Finished' in message or 'Succeeded' in message or 'Deactivated successfully' in message:
                # Find matching start
                for key in list(runs.keys()):
                    run = runs[key]
                    if run['status'] == 'running':
                        run['status'] = 'success'
                        run['end_time'] = timestamp
                        if 'start_time' in run:
                            duration = (timestamp - run['start_time']).total_seconds()
                            run['duration'] = _format_duration(duration)
                        break
                else:
                    # No matching start found, create completed entry
                    runs[ts_key] = {
                        'timestamp': timestamp.isoformat(),
                        'status': 'success',
                    }
            
            # Detect failures
            elif 'Failed' in message or 'failed' in message.lower() or 'error' in message.lower():
                for key in list(runs.keys()):
                    run = runs[key]
                    if run['status'] == 'running':
                        run['status'] = 'failed'
                        run['error'] = message[:200]
                        break
                else:
                    runs[ts_key] = {
                        'timestamp': timestamp.isoformat(),
                        'status': 'failed',
                        'error': message[:200],
                    }
                    
        except json.JSONDecodeError:
            continue
    
    # Convert runs to history list, sorted by timestamp descending
    for run in sorted(runs.values(), key=lambda x: x['timestamp'], reverse=True)[:limit]:
        entry = {
            'timestamp': run['timestamp'],
            'status': run['status'],
        }
        if 'duration' in run:
            entry['duration'] = run['duration']
        if 'error' in run:
            entry['error'] = run['error']
        history.append(entry)
    
    return history


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


async def _fetch_timeshift_history(limit: int) -> List[Dict[str, Any]]:
    """Fetch Timeshift snapshot history."""
    history: List[Dict[str, Any]] = []
    
    try:
        result = subprocess.run(
            ["timeshift", "--list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            # Parse timeshift output
            # Example: "  1   >  2024-01-15_10-30-00  O  Boot"
            for line in result.stdout.split('\n'):
                match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', line)
                if match:
                    ts_str = match.group(1)
                    try:
                        timestamp = datetime.strptime(ts_str, '%Y-%m-%d_%H-%M-%S')
                        history.append({
                            'timestamp': timestamp.isoformat(),
                            'status': 'success',
                            'size': _get_snapshot_size(ts_str),
                        })
                    except ValueError:
                        continue
                        
                if len(history) >= limit:
                    break
                    
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Failed to query timeshift: {e}")
    
    return history


def _get_snapshot_size(snapshot_name: str) -> Optional[str]:
    """Get size of a timeshift snapshot (if available)."""
    # This would require parsing timeshift config or checking disk usage
    # For now, return None - can be enhanced later
    return None


async def _fetch_btrbk_history(backup_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch btrbk snapshot history by scanning target directories.
    
    backup_name should be like 'btrbk-@' or 'btrbk-@home'
    
    This parses btrbk.conf to find target directories, then lists snapshots
    directly from the filesystem (avoids needing root for btrbk list).
    """
    from pathlib import Path
    
    history: List[Dict[str, Any]] = []
    
    # Extract the subvolume name from backup_name (btrbk-@ -> @, btrbk-@home -> @home)
    subvol = backup_name.replace("btrbk-", "")
    
    # Parse btrbk.conf to find target directory for this subvolume
    btrbk_conf = Path("/etc/btrbk/btrbk.conf")
    if not btrbk_conf.exists():
        logger.warning("btrbk.conf not found")
        return history
    
    try:
        content = btrbk_conf.read_text()
    except PermissionError:
        logger.warning("Cannot read btrbk.conf")
        return history
    
    # Find the target directory for this subvolume
    # Config format:
    #   volume /btrfs/root
    #     subvolume @
    #     target raw /mnt/Bcachefs/Backups/Ubuntu_snapshots
    target_dir = None
    current_volume = None
    current_subvol = None
    
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('volume '):
            current_volume = line.split()[1] if len(line.split()) > 1 else None
            current_subvol = None
        elif line.startswith('subvolume '):
            current_subvol = line.split()[1] if len(line.split()) > 1 else None
        elif line.startswith('target ') and current_subvol == subvol:
            # Found the target for our subvolume
            # Format: "target raw /path" or "target /path"
            parts = line.split()
            if len(parts) >= 2:
                # Last part is the path
                target_dir = parts[-1]
                break
    
    if not target_dir:
        logger.warning(f"No target directory found for subvolume {subvol}")
        return history
    
    # List snapshots in the target directory
    target_path = Path(target_dir)
    if not target_path.exists():
        logger.warning(f"Target directory does not exist: {target_dir}")
        return history
    
    # Pattern: @.20251214T0000.btrfs or @home.20251214T0000.btrfs
    pattern = rf'^{re.escape(subvol)}\.(\d{{8}}T\d{{4}})(?:\.btrfs)?$'
    
    try:
        for entry in target_path.iterdir():
            match = re.match(pattern, entry.name)
            if match:
                ts_str = match.group(1)
                try:
                    timestamp = datetime.strptime(ts_str, '%Y%m%dT%H%M')
                    # Get file size if possible
                    size = None
                    try:
                        if entry.is_file():
                            size_bytes = entry.stat().st_size
                            if size_bytes > 1024**3:
                                size = f"{size_bytes / 1024**3:.1f} GB"
                            elif size_bytes > 1024**2:
                                size = f"{size_bytes / 1024**2:.1f} MB"
                    except OSError:
                        pass
                    
                    history.append({
                        'timestamp': timestamp.isoformat(),
                        'status': 'success',
                        'snapshot_name': entry.name,
                        'size': size,
                    })
                except ValueError:
                    continue
    except PermissionError:
        logger.warning(f"Cannot list target directory: {target_dir}")
        return history
    
    # Sort by timestamp descending and limit
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    history = history[:limit]
    
    return history


def _investigate_backup(backup_name: str, backup_data: dict, status: str) -> Dict[str, Any]:
    """
    Deep investigation of a backup configuration.
    
    Reads the actual script, checks logs, and gathers real diagnostic data.
    """
    import subprocess
    from pathlib import Path
    
    investigation = {
        "name": backup_name,
        "status": status,
        "script_content": None,
        "script_exists": False,
        "script_executable": False,
        "recent_logs": None,
        "errors_found": [],
    }
    
    # Get script path
    script_path = backup_data.get("script_path")
    if script_path:
        path = Path(script_path)
        investigation["script_exists"] = path.exists()
        if path.exists():
            investigation["script_executable"] = os.access(script_path, os.X_OK)
            try:
                # Read script content (first 100 lines)
                content = path.read_text()
                lines = content.split('\n')[:100]
                investigation["script_content"] = '\n'.join(lines)
            except Exception as e:
                investigation["errors_found"].append(f"Cannot read script: {e}")
    
    # Get recent journal logs for this backup
    service_name = f"{backup_name}.service"
    try:
        result = subprocess.run(
            ["journalctl", "-u", service_name, "-n", "50", "--no-pager", "-o", "short"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.stdout:
            investigation["recent_logs"] = result.stdout[-3000:]  # Last 3KB of logs
        if result.returncode != 0 and result.stderr:
            # Try timer unit instead
            timer_name = f"{backup_name}.timer"
            result2 = subprocess.run(
                ["journalctl", "-u", timer_name, "-n", "30", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result2.stdout:
                investigation["recent_logs"] = result2.stdout[-2000:]
    except Exception as e:
        investigation["errors_found"].append(f"Cannot get logs: {e}")
    
    # Check for common issues in logs
    if investigation["recent_logs"]:
        logs_lower = investigation["recent_logs"].lower()
        if "permission denied" in logs_lower:
            investigation["errors_found"].append("Permission denied errors in logs")
        if "no such file" in logs_lower or "not found" in logs_lower:
            investigation["errors_found"].append("File not found errors in logs")
        if "failed" in logs_lower:
            investigation["errors_found"].append("Failure messages in logs")
        if "timeout" in logs_lower:
            investigation["errors_found"].append("Timeout errors in logs")
        if "disk full" in logs_lower or "no space" in logs_lower:
            investigation["errors_found"].append("Disk space issues in logs")
    
    return investigation


def _build_overview_context(overview_type: str, discoveries: list) -> str:
    """Build context for ecosystem overview generation."""
    context_parts = [f"## {overview_type.title()} Configuration Overview Request\n"]
    
    if overview_type == "backup":
        # Group by tool and collect details
        tools_used = set()
        destinations = set()
        schedules = []
        sources = set()
        
        for d in discoveries:
            if d.data:
                if d.data.get("tool"):
                    tools_used.add(d.data["tool"])
                if d.data.get("destination"):
                    destinations.add(d.data["destination"])
                if d.data.get("source_path"):
                    sources.add(d.data["source_path"])
                if d.data.get("schedule"):
                    schedules.append(f"{d.name}: {d.data['schedule']}")
        
        context_parts.append(f"**Backup tools in use**: {', '.join(tools_used) or 'unknown'}")
        context_parts.append(f"**Number of backup jobs**: {len(discoveries)}")
        context_parts.append(f"**Backup destinations**: {', '.join(destinations) or 'unknown'}")
        context_parts.append(f"**Source directories**: {', '.join(list(sources)[:5])}")
        if schedules:
            context_parts.append(f"**Schedules**:")
            for s in schedules[:5]:
                context_parts.append(f"  - {s}")
        
        context_parts.append("\nDescribe the backup strategy in 2-3 sentences: what's being backed up, where, how often.")
        
    elif overview_type == "storage":
        # Analyze disk layout
        disks = []
        filesystems = []
        pools = []
        
        for d in discoveries:
            if d.name.startswith("disk-"):
                disk_info = {
                    "model": d.data.get("model", "unknown"),
                    "size": d.data.get("size", "unknown"),
                    "type": d.data.get("type", "unknown"),
                    "smart": d.data.get("smart_status", "unknown"),
                }
                disks.append(disk_info)
            elif d.name.startswith("fs-"):
                fs_info = {
                    "mount": d.data.get("mount", d.name),
                    "fstype": d.data.get("fstype", "unknown"),
                    "size": d.data.get("size", "unknown"),
                    "percent": d.data.get("percent", 0),
                }
                filesystems.append(fs_info)
            elif "pool" in d.name.lower() or d.data.get("fstype") in ["bcachefs", "btrfs", "zfs"]:
                pools.append(d)
        
        context_parts.append(f"**Physical disks**: {len(disks)}")
        for disk in disks[:10]:
            context_parts.append(f"  - {disk['model']} ({disk['size']}) - {disk['type']} - SMART: {disk['smart']}")
        
        context_parts.append(f"\n**Filesystems**: {len(filesystems)}")
        key_mounts = [fs for fs in filesystems if fs['mount'] in ['/', '/home', '/boot', '/boot/efi']]
        for fs in key_mounts:
            context_parts.append(f"  - {fs['mount']}: {fs['fstype']} ({fs['percent']}% used)")
        
        if pools:
            context_parts.append(f"\n**Storage pools/arrays**: {len(pools)}")
        
        context_parts.append("\nDescribe the storage layout in 2-3 sentences: what disk types, any RAID/pools, how data is organized.")
        
    elif overview_type == "network":
        interfaces = []
        firewalls = []
        
        for d in discoveries:
            if d.name.startswith("interface-"):
                interfaces.append({
                    "name": d.data.get("name", d.name),
                    "type": d.data.get("type", "unknown"),
                    "ip": d.data.get("ipv4", "no IP"),
                    "state": d.data.get("operstate", "unknown"),
                })
            elif d.name.startswith("firewall-"):
                firewalls.append(d)
        
        context_parts.append(f"**Network interfaces**: {len(interfaces)}")
        for iface in interfaces[:5]:
            context_parts.append(f"  - {iface['name']}: {iface['type']} - {iface['ip']} ({iface['state']})")
        
        if firewalls:
            context_parts.append(f"\n**Firewalls configured**: {len(firewalls)}")
        
        context_parts.append("\nDescribe the network setup in 2-3 sentences: connection types, any VLANs/bridges, firewall status.")
    
    return "\n".join(context_parts)


async def _generate_overview(context: str, overview_type: str) -> Dict[str, Any]:
    """Generate ecosystem overview using the configured guide model."""
    import json
    from ...model.client import get_configured_model, get_ollama_endpoint
    
    model = get_configured_model()
    if not model:
        raise Exception("No model configured — choose one in Settings → AI Models")
    endpoint = get_ollama_endpoint()
    
    system_prompt = f"""You are describing a user's {overview_type} setup in plain English. 
Write a concise 2-3 sentence overview that a human would understand.

Examples:
- Storage: "Your system runs on a fast NVMe SSD for the OS, with a separate 1TB SSD for /home. You have a large bcachefs pool spanning 6 HDDs (24TB total) for bulk data storage."
- Backup: "You have a 3-tier backup strategy: Timeshift handles system snapshots hourly, rsync backs up /home daily to the NAS, and bcachefs snapshots protect the data pool weekly."
- Network: "You're connected via gigabit ethernet with a static IP. UFW firewall is active with SSH and HTTP allowed. A bridge interface connects to your VM network."

Respond with JSON:
{{
    "overview": "Your 2-3 sentence description",
    "complexity": "simple|moderate|complex",
    "key_components": ["list", "of", "main", "components"]
}}

Be specific about actual hardware models, sizes, and tools. Don't be generic."""

    try:
        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                "stream": False,
                "format": "json",
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "{}")
        
        try:
            result = json.loads(content)
            return {
                "overview": result.get("overview", "Configuration overview unavailable."),
                "complexity": result.get("complexity", "unknown"),
                "key_components": result.get("key_components", []),
            }
        except json.JSONDecodeError:
            return {
                "overview": content[:300],
                "complexity": "unknown",
                "key_components": [],
            }
    except Exception as e:
        raise Exception(f"Overview generation failed: {e}")


def _extract_type_from_docs(name: str, docs: List[Dict[str, Any]]) -> str:
    """Extract a type classification from retrieved docs."""
    name_lower = name.lower()
    
    # Check doc names and content for clues
    for doc in docs:
        doc_name = doc.get('name', '').lower()
        content = doc.get('content', '').lower()
        
        if 'tailscale' in doc_name or 'tailscale' in content:
            return 'Tailscale VPN'
        if 'wireguard' in doc_name or 'wireguard' in content:
            return 'WireGuard VPN'
        if 'bridge' in doc_name or 'bridge' in content:
            return 'Network Bridge'
        if 'bond' in doc_name or 'bonding' in content:
            return 'Network Bond'
        if 'docker' in doc_name or 'docker' in content:
            return 'Docker Network'
        if 'vpn' in doc_name or 'vpn' in content:
            return 'VPN Interface'
    
    return 'Other'


def _extract_description_from_docs(name: str, docs: List[Dict[str, Any]]) -> str:
    """Extract a description from retrieved docs."""
    if docs:
        first_doc = docs[0]
        desc = first_doc.get('description', '')
        if desc:
            return desc[:200]
        content = first_doc.get('content', '')
        if content:
            return content[:200]
    return f"System component: {name}"
