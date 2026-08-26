# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Ollama Management Utilities

Provides functions for:
- Checking Ollama installation and status
- Starting/stopping Ollama service
- Model management (list, pull, check)
- Health checks

Phase 31: Backend deployment support
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default Ollama endpoint
DEFAULT_ENDPOINT = "http://localhost:11434"


@dataclass
class OllamaModel:
    """Information about an Ollama model."""
    name: str
    size: str
    modified: str
    digest: str


@dataclass
class OllamaStatus:
    """Ollama service status."""
    installed: bool
    running: bool
    endpoint: str
    models: List[OllamaModel]
    error: Optional[str] = None


def check_installed() -> bool:
    """Check if Ollama is installed on the system."""
    try:
        result = subprocess.run(
            ['ollama', '--version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_running(endpoint: str = DEFAULT_ENDPOINT) -> bool:
    """Check if Ollama server is running and responsive."""
    try:
        import requests
        response = requests.get(f"{endpoint}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def get_models(endpoint: str = DEFAULT_ENDPOINT) -> List[OllamaModel]:
    """Get list of available models from Ollama."""
    try:
        import requests
        response = requests.get(f"{endpoint}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = []
            for m in data.get('models', []):
                models.append(OllamaModel(
                    name=m.get('name', ''),
                    size=_format_size(m.get('size', 0)),
                    modified=m.get('modified_at', ''),
                    digest=m.get('digest', '')[:12],
                ))
            return models
    except Exception as e:
        logger.debug(f"Failed to get models: {e}")
    return []


def list_models_raw(endpoint: str = DEFAULT_ENDPOINT) -> List[dict]:
    """
    Get raw model entries from Ollama ``GET /api/tags``.

    Each entry keeps the runtime metadata Ollama reports (``size`` in bytes,
    ``details.parameter_size``, ``details.quantization_level``) so callers
    can size models against a hardware budget without naming any model.
    """
    try:
        import requests
        response = requests.get(f"{endpoint}/api/tags", timeout=5)
        if response.status_code == 200:
            return list(response.json().get('models', []))
    except Exception as e:
        logger.debug(f"Failed to list models: {e}")
    return []


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def start_ollama() -> Tuple[bool, str]:
    """
    Start Ollama server if not already running.
    
    Returns:
        Tuple of (success, message)
    """
    if check_running():
        return True, "Ollama already running"
    
    if not check_installed():
        return False, "Ollama not installed. Install with: curl -fsSL https://ollama.com/install.sh | sh"
    
    try:
        # Start Ollama in background
        subprocess.Popen(
            ['ollama', 'serve'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Wait for it to start
        for _ in range(10):
            time.sleep(0.5)
            if check_running():
                return True, "Ollama started successfully"
        
        return False, "Ollama started but not responding"
    except Exception as e:
        return False, f"Failed to start Ollama: {e}"


def stop_ollama() -> Tuple[bool, str]:
    """
    Stop Ollama server.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        subprocess.run(['pkill', '-f', 'ollama serve'], timeout=5)
        time.sleep(1)
        
        if not check_running():
            return True, "Ollama stopped"
        return False, "Failed to stop Ollama"
    except Exception as e:
        return False, f"Error stopping Ollama: {e}"


def pull_model(model_name: str, endpoint: str = DEFAULT_ENDPOINT) -> Tuple[bool, str]:
    """
    Pull a model from Ollama registry.
    
    Args:
        model_name: Name of model to pull, as listed on the Ollama registry
        endpoint: Ollama API endpoint
    
    Returns:
        Tuple of (success, message)
    """
    try:
        import requests
        response = requests.post(
            f"{endpoint}/api/pull",
            json={"name": model_name},
            timeout=600  # 10 minute timeout for large models
        )
        
        if response.status_code == 200:
            return True, f"Model {model_name} pulled successfully"
        return False, f"Failed to pull model: {response.text}"
    except Exception as e:
        return False, f"Error pulling model: {e}"


def check_model_exists(model_name: str, endpoint: str = DEFAULT_ENDPOINT) -> bool:
    """Check if a specific model is available."""
    models = get_models(endpoint)
    return any(m.name == model_name or m.name.startswith(f"{model_name}:") for m in models)


def get_status(endpoint: str = DEFAULT_ENDPOINT) -> OllamaStatus:
    """
    Get comprehensive Ollama status.
    
    Returns:
        OllamaStatus with all relevant information
    """
    installed = check_installed()
    running = check_running(endpoint) if installed else False
    models = get_models(endpoint) if running else []
    
    error = None
    if not installed:
        error = "Ollama not installed"
    elif not running:
        error = "Ollama not running"
    
    return OllamaStatus(
        installed=installed,
        running=running,
        endpoint=endpoint,
        models=models,
        error=error
    )


def ensure_ready(endpoint: str = DEFAULT_ENDPOINT) -> Tuple[bool, str]:
    """
    Ensure Ollama is installed, running, and ready.
    
    Attempts to start Ollama if installed but not running.
    
    Returns:
        Tuple of (ready, message)
    """
    if not check_installed():
        return False, "Ollama not installed. Install with: curl -fsSL https://ollama.com/install.sh | sh"
    
    if check_running(endpoint):
        return True, "Ollama ready"
    
    return start_ollama()
