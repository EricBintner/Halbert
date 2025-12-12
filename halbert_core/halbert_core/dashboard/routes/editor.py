"""
Config Editor API routes.
Handles file read/write, backups, sessions, and validation.
"""

import os
import json
import hashlib
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/editor", tags=["editor"])


# --- Models ---

class FileReadResponse(BaseModel):
    content: str
    path: str
    size: int
    modified: float
    language: str
    needs_sudo: bool


class FileWriteRequest(BaseModel):
    path: str
    content: str
    create_backup: bool = True
    backup_label: str = "Manual save"


class FileWriteResponse(BaseModel):
    success: bool
    message: str
    backup_id: Optional[str] = None


class Backup(BaseModel):
    id: str
    file_path: str
    timestamp: float
    label: str
    size: int


class BackupCreateRequest(BaseModel):
    path: str
    label: str = "Manual backup"


class BackupRestoreRequest(BaseModel):
    backup_id: str


class SessionState(BaseModel):
    id: str
    file_path: str
    original_content: str
    current_content: str
    chat_history: List[dict]
    created_at: float
    updated_at: float
    status: str  # "editing", "saved", "pending-reboot"


# --- Helpers ---

def get_config_dir() -> Path:
    """Get Halbert config directory."""
    config_dir = Path.home() / ".config" / "halbert"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_backup_dir(file_path: str) -> Path:
    """Get backup directory for a specific file."""
    encoded = file_path.replace("/", "_").replace("\\", "_")
    backup_dir = get_config_dir() / "backups" / encoded
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_session_dir() -> Path:
    """Get editor sessions directory."""
    session_dir = get_config_dir() / "editor-sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def detect_language(file_path: str) -> str:
    """Detect Monaco language from file path."""
    path_lower = file_path.lower()
    
    if path_lower.endswith('.json'):
        return 'json'
    elif path_lower.endswith(('.yaml', '.yml')):
        return 'yaml'
    elif path_lower.endswith('.xml'):
        return 'xml'
    elif path_lower.endswith('.toml'):
        return 'ini'  # Monaco doesn't have TOML, INI is close
    elif path_lower.endswith('.sh') or path_lower.endswith('.bash'):
        return 'shell'
    elif path_lower.endswith('.py'):
        return 'python'
    elif 'nginx' in path_lower:
        return 'nginx'
    elif path_lower.endswith(('.conf', '.ini', '.cfg')):
        return 'ini'
    elif 'systemd' in path_lower or path_lower.endswith('.service'):
        return 'ini'
    else:
        return 'plaintext'


def file_needs_sudo(file_path: str) -> bool:
    """Check if file requires sudo to read/write."""
    try:
        # Check if we can read it
        with open(file_path, 'r') as f:
            f.read(1)
        # Check if we can write (by checking directory permissions)
        parent = os.path.dirname(file_path)
        return not os.access(file_path, os.W_OK)
    except PermissionError:
        return True
    except FileNotFoundError:
        # Check parent directory
        parent = os.path.dirname(file_path)
        return not os.access(parent, os.W_OK)


def read_file_content(file_path: str) -> str:
    """Read file content, using sudo if needed."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except PermissionError:
        # Try with sudo (non-interactive)
        try:
            result = subprocess.run(
                ['sudo', '-n', 'cat', file_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout
            else:
                # Provide helpful error message
                if 'password is required' in result.stderr:
                    raise PermissionError(
                        f"This file requires root access. To enable editing:\n"
                        f"1. Run: sudo visudo\n"
                        f"2. Add: {os.getenv('USER', 'your_user')} ALL=(ALL) NOPASSWD: /usr/bin/cat {file_path}, /usr/bin/tee {file_path}\n"
                        f"Or temporarily: sudo chmod 644 {file_path}"
                    )
                raise PermissionError(f"Cannot read file: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise PermissionError("Sudo timeout - password required")


def write_file_content(file_path: str, content: str) -> bool:
    """Write file content, using sudo if needed."""
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    except PermissionError:
        # Try with sudo using tee
        try:
            result = subprocess.run(
                ['sudo', '-n', 'tee', file_path],
                input=content,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            raise PermissionError("Sudo timeout - password required")


# --- Routes ---

@router.get("/file")
async def read_file(path: str) -> FileReadResponse:
    """Read a config file."""
    if not path or not path.startswith('/'):
        raise HTTPException(400, "Invalid path - must be absolute")
    
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")
    
    if not os.path.isfile(path):
        raise HTTPException(400, "Path is not a file")
    
    try:
        content = read_file_content(path)
        stat = os.stat(path)
        
        return FileReadResponse(
            content=content,
            path=path,
            size=stat.st_size,
            modified=stat.st_mtime,
            language=detect_language(path),
            needs_sudo=file_needs_sudo(path)
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        raise HTTPException(500, str(e))


@router.post("/file")
async def write_file(request: FileWriteRequest) -> FileWriteResponse:
    """Write a config file."""
    path = request.path
    
    if not path or not path.startswith('/'):
        raise HTTPException(400, "Invalid path - must be absolute")
    
    backup_id = None
    
    # Create backup first if requested and file exists
    if request.create_backup and os.path.exists(path):
        try:
            backup = await create_backup(BackupCreateRequest(
                path=path,
                label=request.backup_label
            ))
            backup_id = backup.id
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    try:
        success = write_file_content(path, request.content)
        if success:
            return FileWriteResponse(
                success=True,
                message="File saved successfully",
                backup_id=backup_id
            )
        else:
            raise HTTPException(500, "Failed to write file")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        logger.error(f"Error writing file {path}: {e}")
        raise HTTPException(500, str(e))


@router.post("/backup")
async def create_backup(request: BackupCreateRequest) -> Backup:
    """Create a backup of a file."""
    path = request.path
    
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")
    
    backup_dir = get_backup_dir(path)
    timestamp = datetime.now()
    backup_id = timestamp.strftime("%Y%m%d-%H%M%S")
    backup_file = backup_dir / f"{backup_id}.bak"
    
    try:
        content = read_file_content(path)
        with open(backup_file, 'w') as f:
            f.write(content)
        
        # Save metadata
        metadata_file = backup_dir / f"{backup_id}.json"
        metadata = {
            "id": backup_id,
            "file_path": path,
            "timestamp": timestamp.timestamp(),
            "label": request.label,
            "size": len(content),
            "hash": hashlib.sha256(content.encode()).hexdigest()
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return Backup(
            id=backup_id,
            file_path=path,
            timestamp=timestamp.timestamp(),
            label=request.label,
            size=len(content)
        )
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(500, str(e))


@router.get("/backups")
async def list_backups(path: str) -> List[Backup]:
    """List all backups for a file."""
    backup_dir = get_backup_dir(path)
    backups = []
    
    for meta_file in sorted(backup_dir.glob("*.json"), reverse=True):
        try:
            with open(meta_file, 'r') as f:
                meta = json.load(f)
            backups.append(Backup(
                id=meta["id"],
                file_path=meta["file_path"],
                timestamp=meta["timestamp"],
                label=meta["label"],
                size=meta["size"]
            ))
        except Exception as e:
            logger.warning(f"Error reading backup metadata {meta_file}: {e}")
    
    return backups


@router.get("/backup/{backup_id}/content")
async def get_backup_content(backup_id: str, path: str) -> dict:
    """Get content of a specific backup."""
    backup_dir = get_backup_dir(path)
    backup_file = backup_dir / f"{backup_id}.bak"
    
    if not backup_file.exists():
        raise HTTPException(404, "Backup not found")
    
    try:
        with open(backup_file, 'r') as f:
            content = f.read()
        return {"content": content, "backup_id": backup_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/backup/restore")
async def restore_backup(request: BackupRestoreRequest, path: str) -> FileWriteResponse:
    """Restore a file from backup."""
    backup_dir = get_backup_dir(path)
    backup_file = backup_dir / f"{request.backup_id}.bak"
    
    if not backup_file.exists():
        raise HTTPException(404, "Backup not found")
    
    try:
        with open(backup_file, 'r') as f:
            content = f.read()
        
        # Create a backup of current state before restoring
        if os.path.exists(path):
            await create_backup(BackupCreateRequest(
                path=path,
                label="Before restore"
            ))
        
        success = write_file_content(path, content)
        if success:
            return FileWriteResponse(
                success=True,
                message=f"Restored from backup {request.backup_id}"
            )
        else:
            raise HTTPException(500, "Failed to restore file")
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        raise HTTPException(500, str(e))


@router.post("/session")
async def save_session(session: SessionState) -> dict:
    """Save editor session state."""
    session_dir = get_session_dir()
    
    # Use file path as session key
    encoded_path = session.file_path.replace("/", "_").replace("\\", "_")
    session_file = session_dir / f"{encoded_path}.json"
    
    try:
        session_data = session.model_dump()
        session_data["updated_at"] = datetime.now().timestamp()
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return {"success": True, "session_id": session.id}
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        raise HTTPException(500, str(e))


@router.get("/session")
async def get_session(path: str) -> Optional[SessionState]:
    """Get saved session for a file."""
    session_dir = get_session_dir()
    encoded_path = path.replace("/", "_").replace("\\", "_")
    session_file = session_dir / f"{encoded_path}.json"
    
    if not session_file.exists():
        return None
    
    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
        return SessionState(**data)
    except Exception as e:
        logger.warning(f"Error loading session: {e}")
        return None


@router.delete("/session")
async def delete_session(path: str) -> dict:
    """Delete a session."""
    session_dir = get_session_dir()
    encoded_path = path.replace("/", "_").replace("\\", "_")
    session_file = session_dir / f"{encoded_path}.json"
    
    if session_file.exists():
        session_file.unlink()
    
    return {"success": True}


@router.get("/sessions/pending")
async def get_pending_sessions() -> List[SessionState]:
    """Get all sessions pending reboot recovery."""
    session_dir = get_session_dir()
    pending = []
    
    for session_file in session_dir.glob("*.json"):
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
            if data.get("status") in ["pending-reboot", "editing"]:
                pending.append(SessionState(**data))
        except Exception as e:
            logger.warning(f"Error reading session {session_file}: {e}")
    
    return pending
