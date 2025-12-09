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
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    BaseModel = object

from ...discovery import DiscoveryType
from ...discovery.engine import get_engine  # Use the singleton from engine.py

logger = logging.getLogger('cerebric.dashboard.routes.discovery')

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
            data_dir = Path(os.environ.get('Cerebric_DATA_DIR', Path.home() / '.local' / 'share' / 'cerebric'))
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


    class AnalysisRequest(BaseModel):
        """Request for AI analysis."""
        type: str = "backup"  # backup, service, storage, etc.
        use_specialist: bool = False  # Use 70b model for deep research
    
    
    @router.post("/analyze/{analysis_type}")
    async def analyze_discoveries(analysis_type: str, use_specialist: bool = False):
        """
        Get AI-powered analysis of discoveries.
        
        Uses the orchestrator model (7b) for quick overview,
        or specialist model (70b) for deep research if use_specialist=true.
        """
        engine = get_engine()
        
        try:
            discovery_type = DiscoveryType(analysis_type)
            discoveries = engine.get_by_type(discovery_type)
        except ValueError:
            discoveries = []
        
        if not discoveries:
            return {
                "analysis": f"No {analysis_type} configurations found on this system.",
                "health_score": 0,
                "issues_found": False,
                "recommendations": [f"Set up {analysis_type} configurations for better system management."],
            }
        
        # Get statuses for backups
        statuses = {}
        if analysis_type == "backup":
            for d in discoveries:
                status = _get_last_run_status(f"{d.name}.service")
                if status:
                    statuses[d.name] = status
        
        # Build context for AI
        context = _build_analysis_context(analysis_type, discoveries, statuses)
        
        # Call LLM
        try:
            analysis = await _call_llm_analysis(context, use_specialist)
            return analysis
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            # Fallback to basic analysis
            return _generate_fallback_analysis(analysis_type, discoveries, statuses)
    
    
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
    """
    history: List[Dict[str, Any]] = []
    
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


def _build_analysis_context(
    analysis_type: str, 
    discoveries: list, 
    statuses: Dict[str, str]
) -> str:
    """Build context string for AI analysis with real investigation data."""
    context_parts = [
        f"## {analysis_type.title()} Analysis Request",
        f"Found {len(discoveries)} {analysis_type} configuration(s):",
        "",
    ]
    
    # For backups, do deep investigation of failed ones
    if analysis_type == "backup":
        failed_backups = []
        for d in discoveries:
            status = statuses.get(d.name, "unknown")
            if status == "failed":
                investigation = _investigate_backup(d.name, d.data or {}, status)
                failed_backups.append(investigation)
        
        if failed_backups:
            context_parts.append("## ⚠️ FAILED BACKUP INVESTIGATION")
            context_parts.append("The following backups have failed. Here is the investigation data:\n")
            
            for inv in failed_backups:
                context_parts.append(f"### {inv['name']} - FAILED")
                
                # Script analysis
                if inv["script_content"]:
                    context_parts.append(f"\n**Script exists**: Yes")
                    context_parts.append(f"**Script executable**: {inv['script_executable']}")
                    if not inv["script_executable"]:
                        context_parts.append("⚠️ Script is NOT executable - this is likely the problem!")
                    context_parts.append(f"\n**Script content** (first 100 lines):\n```bash\n{inv['script_content']}\n```\n")
                elif inv.get("script_exists") is False:
                    context_parts.append("⚠️ **Script file does not exist!** This is the problem.")
                
                # Log analysis
                if inv["recent_logs"]:
                    context_parts.append(f"**Recent logs**:\n```\n{inv['recent_logs']}\n```\n")
                
                # Detected errors
                if inv["errors_found"]:
                    context_parts.append("**Detected issues**:")
                    for err in inv["errors_found"]:
                        context_parts.append(f"- {err}")
                
                context_parts.append("")
            
            context_parts.append("Based on the script content and logs above, identify the ROOT CAUSE of the failure.\n")
    
    # For storage, first highlight any SMART failures prominently
    if analysis_type == "storage":
        failing_disks = []
        healthy_disks = []
        for d in discoveries:
            if d.name.startswith("disk-") and hasattr(d, 'data') and d.data:
                smart_status = d.data.get("smart_status", "unknown")
                disk_info = f"{d.data.get('model', d.name)} ({d.data.get('size', 'unknown')})"
                if smart_status == "FAILED":
                    failing_disks.append(disk_info)
                elif smart_status == "PASSED":
                    healthy_disks.append(disk_info)
        
        if failing_disks:
            context_parts.append("## ⚠️ CRITICAL: FAILING DISKS DETECTED")
            context_parts.append("The following disks have FAILED SMART tests and may fail soon:")
            for disk in failing_disks:
                context_parts.append(f"- **{disk}** - SMART FAILED")
            context_parts.append("")
            context_parts.append(f"Healthy disks: {len(healthy_disks)}, Failing disks: {len(failing_disks)}")
            context_parts.append("")
    
    for d in discoveries:
        status = statuses.get(d.name, "unknown")
        context_parts.append(f"### {d.name}")
        context_parts.append(f"- **Status**: {status}")
        context_parts.append(f"- **Description**: {d.description or 'No description'}")
        
        if hasattr(d, 'data') and d.data:
            for key, value in d.data.items():
                if value:
                    context_parts.append(f"- **{key}**: {value}")
        context_parts.append("")
    
    # Add specific questions based on type
    if analysis_type == "backup":
        context_parts.extend([
            "## Your Investigation Tasks:",
            "1. For any FAILED backups: Analyze the script and logs above to find the EXACT error",
            "2. Identify the specific line, command, or condition causing the failure",
            "3. Provide the exact fix command to resolve the issue",
            "4. Note any missing directories, permissions issues, or configuration problems",
        ])
    elif analysis_type == "service":
        context_parts.extend([
            "## Analysis Questions:",
            "1. Are there any failed or problematic services?",
            "2. Are critical system services running properly?",
            "3. Are there any services consuming excessive resources?",
            "4. What services might be unnecessary and can be disabled?",
        ])
    elif analysis_type == "storage":
        context_parts.extend([
            "## Analysis Questions:",
            "1. Is disk space usage healthy across all volumes?",
            "2. Are there any SMART warnings or disk health issues?",
            "3. Is the storage configuration optimal for the workload?",
            "4. What improvements would you recommend?",
        ])
    elif analysis_type == "network":
        context_parts.extend([
            "## Analysis Questions:",
            "1. Are all network interfaces configured correctly?",
            "2. Are there any connectivity or DNS issues?",
            "3. Are firewall rules configured properly?",
            "4. What security improvements would you recommend?",
        ])
    elif analysis_type == "security":
        context_parts.extend([
            "## Analysis Questions:",
            "1. Are there any obvious security vulnerabilities?",
            "2. Is the system properly hardened?",
            "3. Are user permissions configured correctly?",
            "4. What security improvements are most critical?",
        ])
    
    return "\n".join(context_parts)


async def _call_llm_analysis(context: str, use_specialist: bool = False) -> Dict[str, Any]:
    """
    Call the LLM for analysis.
    
    Uses orchestrator (7b) by default, or specialist (70b) if requested.
    """
    import json
    
    # Determine model to use
    model = "llama3.1:70b" if use_specialist else "llama3.1:8b"
    
    system_prompt = """You are a Linux system analyst and debugger. You have access to actual script contents, logs, and configuration files from this system.

YOUR TWO MODES:
1. DEBUGGING MODE (when failures exist): Find the ROOT CAUSE - the exact line, command, or config causing the problem
2. OPTIMIZATION MODE (when everything works): Look for opportunities to improve efficiency, security, or reliability

INVESTIGATION APPROACH:
- If script content is provided, analyze it for bugs, typos, missing dependencies, or logic errors
- If logs are provided, find the specific error messages and explain what they mean  
- Identify the EXACT line or command that's failing, not just "there's a failure"
- When healthy, suggest optimizations like better scheduling, redundancy, or monitoring

Your response MUST be valid JSON with this exact structure:
{
    "analysis": "2-3 sentences explaining what's wrong (if issues) or what could be improved (if healthy)",
    "health_score": 85,
    "issues_found": true,
    "critical_issues": ["Specific issues with root cause - empty array [] if none"],
    "recommendations": ["Specific fix commands OR optimization suggestions - always provide 2-3"]
}

Be a debugger AND advisor. When things fail, find the exact problem. When things work, find ways to make them better.

Health scores:
- 100: Everything perfect, no suggestions
- 80-99: Working well, minor optimizations possible
- 60-79: Some problems or significant optimization opportunities  
- 40-59: Significant issues
- 0-39: Critical failures"""

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                "stream": False,
                "format": "json",
            },
            timeout=120 if use_specialist else 60
        )
        response.raise_for_status()
        data = response.json()
        
        content = data.get("message", {}).get("content", "{}")
        
        # Parse JSON response
        try:
            analysis = json.loads(content)
            # Ensure required fields
            return {
                "analysis": analysis.get("analysis", "Analysis completed."),
                "health_score": analysis.get("health_score", 50),
                "issues_found": analysis.get("issues_found", False),
                "critical_issues": analysis.get("critical_issues", []),
                "recommendations": analysis.get("recommendations", []),
                "model_used": model,
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw text
            return {
                "analysis": content[:500],
                "health_score": 50,
                "issues_found": False,
                "recommendations": [],
                "model_used": model,
            }
            
    except requests.exceptions.Timeout:
        raise Exception("LLM request timed out")
    except requests.exceptions.ConnectionError:
        raise Exception("Could not connect to Ollama - is it running?")


def _generate_fallback_analysis(
    analysis_type: str, 
    discoveries: list, 
    statuses: Dict[str, str]
) -> Dict[str, Any]:
    """Generate basic analysis without LLM (fallback)."""
    critical_issues = []
    recommendations = []
    
    # Handle storage-specific analysis
    if analysis_type == "storage":
        failing_disks = []
        healthy_disks = 0
        high_usage_fs = []
        
        for d in discoveries:
            if d.name.startswith("disk-") and hasattr(d, 'data') and d.data:
                smart_status = d.data.get("smart_status", "unknown")
                model = d.data.get("model", d.name)
                size = d.data.get("size", "unknown")
                if smart_status == "FAILED":
                    failing_disks.append(f"{model} ({size})")
                elif smart_status == "PASSED":
                    healthy_disks += 1
            elif d.name.startswith("fs-") and hasattr(d, 'data') and d.data:
                percent = d.data.get("percent", 0)
                if percent and percent > 85:
                    high_usage_fs.append(f"{d.data.get('mount', d.name)}: {percent}%")
        
        if failing_disks:
            health_score = max(20, 50 - len(failing_disks) * 15)
            issues_found = True
            critical_issues = [f"SMART failure detected on: {disk}" for disk in failing_disks]
            analysis = f"⚠️ CRITICAL: {len(failing_disks)} disk(s) have failing SMART tests. These disks may fail soon and should be replaced immediately. {healthy_disks} disk(s) are healthy."
            recommendations = [
                "Back up all data from failing disks immediately",
                "Replace failing drives as soon as possible",
                "Run 'smartctl -a /dev/sdX' for detailed SMART data",
                "Consider setting up email alerts for disk health",
            ]
        elif high_usage_fs:
            health_score = 70
            issues_found = True
            analysis = f"Disk health is good ({healthy_disks} healthy disks), but {len(high_usage_fs)} filesystem(s) have high usage."
            critical_issues = [f"High disk usage: {fs}" for fs in high_usage_fs]
            recommendations = ["Free up disk space or expand storage", "Identify large files with 'ncdu' or 'du -sh'"]
        else:
            health_score = 100
            issues_found = False
            analysis = f"All {healthy_disks} disk(s) are healthy (SMART passed). Storage configuration looks good."
            recommendations = ["Continue monitoring disk health regularly"]
        
        return {
            "analysis": analysis,
            "health_score": int(health_score),
            "issues_found": issues_found,
            "critical_issues": critical_issues,
            "recommendations": recommendations,
            "model_used": "fallback",
        }
    
    # Default fallback for other types
    failed_count = sum(1 for s in statuses.values() if s == "failed")
    total = len(discoveries)
    
    if failed_count > 0:
        health_score = max(0, 100 - (failed_count / total * 100))
        issues_found = True
        analysis = f"Found {failed_count} failed {analysis_type}(s) out of {total}. Immediate attention required."
        recommendations = [
            f"Check logs for failed {analysis_type}s",
            "Verify configuration files are correct",
            "Ensure required services are running",
        ]
        critical_issues = [f"{name} has failed" for name, status in statuses.items() if status == "failed"]
    else:
        health_score = 100
        issues_found = False
        analysis = f"All {total} {analysis_type} configuration(s) are operating normally."
        recommendations = ["Consider periodic verification of configuration"]
        critical_issues = []
    
    return {
        "analysis": analysis,
        "health_score": int(health_score),
        "issues_found": issues_found,
        "critical_issues": critical_issues,
        "recommendations": recommendations,
        "model_used": "fallback",
    }


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
    """Generate ecosystem overview using LLM."""
    import json
    
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
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.1:8b",
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
