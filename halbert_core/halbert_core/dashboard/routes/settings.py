# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Settings management API routes (Phase 11).

Provides REST API for:
- Model configuration (orchestrator/specialist)
- LLM endpoints management
- System preferences
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import yaml
import logging
import threading
from datetime import datetime, timezone

from ...utils.platform import get_config_dir

logger = logging.getLogger('halbert.dashboard')

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Background System Scan State
# ─────────────────────────────────────────────────────────────────────────────
_scan_state = {
    "is_running": False,
    "started_at": None,
    "current_phase": None,
    "progress_percent": 0,
    "error": None,
    "result": None,
}
_scan_lock = threading.Lock()


# Pydantic models


@router.get("/model/loaded")
async def get_loaded_model_status() -> Dict[str, Any]:
    """Which configured models are actually loaded in VRAM right now.

    Moved here from routes/chat.py (`/api/chat/models/loaded`) as part of
    the chat endpoint retirement (T4b.1). The legacy SidePanel pre-send
    status check reads this to show "Loading <model>..." vs
    "<model> thinking...".
    """
    try:
        from ...model.client import (
            get_configured_model,
            get_loaded_models,
            get_ollama_endpoint,
            get_specialist_model,
            is_model_loaded,
        )

        endpoint = get_ollama_endpoint()
        models = get_loaded_models(endpoint)

        configured_model = get_configured_model()
        configured_loaded = is_model_loaded(configured_model, endpoint)

        specialist_model, specialist_endpoint, specialist_provider =             get_specialist_model()
        specialist_loaded = (
            is_model_loaded(
                specialist_model, specialist_endpoint,
                specialist_provider or "ollama",
            )
            if specialist_model else None
        )

        return {
            "loaded_models": models,
            "configured_model": configured_model,
            "configured_loaded": configured_loaded,
            "endpoint": endpoint,
            "specialist_model": specialist_model,
            "specialist_endpoint": specialist_endpoint,
            "specialist_loaded": specialist_loaded,
        }
    except Exception as e:
        logger.error(f"Failed to get loaded models: {e}")
        return {"loaded_models": [], "error": str(e)}


def _detect_hardware_tier() -> Tuple[int, Optional[float]]:
    """(tier, total_vram_gb). Tier 1: <40GB CUDA, 2: >=40GB CUDA, 3: Apple Silicon."""
    tier, total_vram = 1, None
    try:
        import torch
        if torch.cuda.is_available():
            total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            tier = 2 if total_vram >= 40 else 1
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            tier = 3
    except ImportError:
        pass
    return tier, (round(total_vram, 1) if total_vram else None)


async def _ollama_models(client, url: str) -> Optional[List[Dict[str, Any]]]:
    """Raw ``GET /api/tags`` entries, or None when the server does not answer."""
    try:
        r = await client.get(f"{url.rstrip('/')}/api/tags")
        if r.status_code == 200:
            return list(r.json().get("models", []))
    except Exception as e:
        logger.debug(f"Ollama tags check failed for {url}: {e}")
    return None


async def _openai_model_ids(client, url: str, api_key: str) -> Optional[List[str]]:
    """Model ids from an OpenAI-style ``GET /v1/models``, or None when unreachable."""
    base = url.rstrip("/")
    base = base if base.endswith("/v1") else f"{base}/v1"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = await client.get(f"{base}/models", headers=headers)
        if r.status_code == 200:
            return [str(m.get("id", "")) for m in r.json().get("data", [])]
    except Exception as e:
        logger.debug(f"Model list check failed for {url}: {e}")
    return None


@router.get("/model/status")
async def get_model_status() -> Dict[str, Any]:
    """Read-only status for Settings -> AI Models' Quick-setup strip. Never writes config."""
    import httpx
    from ...model import llm_config as llm_store

    chat = llm_store.resolve("chat_model")
    tier, total_vram = _detect_hardware_tier()
    result: Dict[str, Any] = {
        "chat": {
            "configured": chat is not None,
            "model": chat.model if chat else "",
            "endpoint_url": chat.url if chat else "",
            "provider": chat.provider if chat else "",
            "reachable": False,
            "model_available": False,
        },
        "local_ollama": {"reachable": False, "url": llm_store.DEFAULT_OLLAMA_URL, "model_count": 0},
        "hardware": {"tier": tier, "total_vram_gb": total_vram},
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        local = await _ollama_models(client, llm_store.DEFAULT_OLLAMA_URL)
        if local is not None:
            result["local_ollama"].update(reachable=True, model_count=len(local))
        if chat is None:
            return result
        names: Optional[List[str]] = None
        if chat.provider == "ollama":
            if chat.url.rstrip("/") == llm_store.DEFAULT_OLLAMA_URL:
                entries = local
            else:
                entries = await _ollama_models(client, chat.url)
            names = [str(m.get("name", "")) for m in entries] if entries is not None else None
        else:
            names = await _openai_model_ids(client, chat.url, chat.api_key)
        if names is not None:
            result["chat"].update(reachable=True, model_available=chat.model in names)
    return result


@router.post("/model/apply-recommended")
async def apply_recommended_config() -> Dict[str, Any]:
    """
    Apply hardware-appropriate defaults based on the detected model size budget.

    Sets the context-compression backend by hardware tier (Tier 1 <40GB CUDA:
    semantic; Tier 2 >=40GB CUDA: lingua; Tier 3 Apple Silicon: lingua).

    For the chat model it never picks from a fixed list: it selects the
    largest model ALREADY INSTALLED on local Ollama (from GET /api/tags) that
    fits the detected budget. If nothing installed fits, it returns
    ``success: false`` and asks the user to pull a model of at most N billion
    parameters. Nothing is written in that case.
    """
    import httpx
    from ...model import llm_config as llm_store
    from ...model.hardware_detector import HardwareDetector, pick_installed_model

    tier, total_vram = _detect_hardware_tier()
    compression_backend = 'semantic' if tier == 1 else 'lingua'

    # Model size budget from detected hardware (parameter counts, no names)
    detector = HardwareDetector()
    budget = detector.recommend_budget(detector.detect())

    endpoint = llm_store.DEFAULT_OLLAMA_URL
    async with httpx.AsyncClient(timeout=5.0) as client:
        installed = await _ollama_models(client, endpoint) or []

    chosen = pick_installed_model(installed, budget)
    if not chosen:
        return {
            'success': False,
            'hardware_tier': tier,
            'total_vram_gb': total_vram,
            'budget': budget.to_dict(),
            'message': (
                f"No installed model fits your hardware budget "
                f"(~{budget.max_params_b_4bit}B parameters at 4-bit, "
                f"{budget.memory_budget_gb:.0f}GB for weights). "
                f"Pull a model of at most ~{budget.max_params_b_4bit}B parameters with "
                f"'ollama pull <model>' and try again, or pick one in Settings -> AI Models."
            ),
        }

    chat_model = chosen['name']
    try:
        endpoint_id = llm_store.ensure_ollama_endpoint(endpoint)
        llm_store.set_slot("chat_model", chat_model, endpoint_id)
        compression = dict(llm_store.load_file().get("compression") or {})
        compression.update(backend=compression_backend, enabled=True)
        llm_store.set_top_level("compression", compression)
    except llm_store.ConfigUnreadableError as e:
        logger.error("Cannot apply recommended config: %s", e)
        return {
            'success': False,
            'hardware_tier': tier,
            'total_vram_gb': total_vram,
            'budget': budget.to_dict(),
            'message': str(e),
        }

    return {
        'success': True,
        'hardware_tier': tier,
        'total_vram_gb': total_vram,
        'budget': budget.to_dict(),
        'applied': {
            'chat_model': chat_model,
            'compression_backend': compression_backend,
        },
        'message': (
            f"Applied Tier {tier} configuration: {chat_model} "
            f"(largest installed model within your ~{budget.max_params_b_4bit}B budget) "
            f"+ {compression_backend} compression"
        ),
    }


@router.post("/model/install")
async def install_model(model_name: str) -> Dict[str, Any]:
    """
    Install a model via Ollama pull and make it the chat model.

    This is a quick operation that starts the pull - Ollama handles
    the actual download in the background.
    """
    import httpx
    from ...model import llm_config as llm_store

    chat = llm_store.resolve("chat_model")
    endpoint = chat.url if chat and chat.provider == "ollama" else llm_store.DEFAULT_OLLAMA_URL

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for pull
            response = await client.post(
                f"{endpoint}/api/pull",
                json={"name": model_name, "stream": False}
            )

            if response.status_code == 200:
                try:
                    endpoint_id = llm_store.ensure_ollama_endpoint(endpoint)
                    llm_store.set_slot("chat_model", model_name, endpoint_id)
                except llm_store.ConfigUnreadableError as e:
                    # The pull succeeded; only the config write failed.
                    logger.error("Installed %s but could not save it: %s", model_name, e)
                    return {
                        'success': False,
                        'message': f'{model_name} was installed, but it could not be '
                                   f'saved as the chat model: {e}',
                        'model': model_name,
                    }
                logger.info(f"Model {model_name} installed successfully")
                return {
                    'success': True,
                    'message': f'Model {model_name} installed successfully!',
                    'model': model_name
                }
            return {
                'success': False,
                'message': f'Pull failed: HTTP {response.status_code}'
            }
    except httpx.TimeoutException:
        return {
            'success': False,
            'message': 'Download timed out - model may still be downloading in background'
        }
    except Exception as e:
        logger.error(f"Model install failed: {e}")
        return {
            'success': False,
            'message': str(e)
        }


@router.get("/persona-names")
async def get_persona_names() -> Dict[str, Any]:
    """Get the AI name and user preferences from onboarding.
    
    Name priority:
    1. ai_name from preferences (set during onboarding)
    2. System hostname
    3. "Halbert" (app default)
    """
    import socket
    
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        # Get system hostname as fallback
        try:
            hostname = socket.gethostname()
        except:
            hostname = None
        
        # Default result - use hostname or app name
        result = {
            'ai_name': hostname or 'Halbert',
            'user_name': None,
            'user_type': None,
            'names': {}  # Deprecated but kept for backwards compatibility
        }
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            
            # Priority: ai_name > hostname > "Halbert"
            if prefs.get('ai_name'):
                result['ai_name'] = prefs['ai_name']
            
            if prefs.get('user_name'):
                result['user_name'] = prefs['user_name']
            if prefs.get('user_type'):
                result['user_type'] = prefs['user_type']
        
        return result
    
    except Exception as e:
        logger.error(f"Error getting persona names: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ComputerNameUpdate(BaseModel):
    """Update the computer/AI name."""
    ai_name: str
    user_name: Optional[str] = None


@router.post("/computer-name")
async def update_computer_name(data: ComputerNameUpdate) -> Dict[str, Any]:
    """Update the AI name (computer name) in preferences.
    
    This is the name the AI uses to identify itself (e.g., "Linus", "HAL", etc.)
    """
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        # Load existing preferences
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
        else:
            prefs = {}
        
        # Update the AI name
        prefs['ai_name'] = data.ai_name
        if data.user_name:
            prefs['user_name'] = data.user_name
        
        # Save back
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(prefs, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Updated computer name to: {data.ai_name}")
        
        return {
            'success': True,
            'ai_name': data.ai_name,
            'user_name': prefs.get('user_name')
        }
    
    except Exception as e:
        logger.error(f"Error updating computer name: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PersonaNameUpdate(BaseModel):
    persona: str
    name: str


# ─────────────────────────────────────────────────────────────────────────────
# Custom AI Rules - User-defined guardrails for edge cases
# ─────────────────────────────────────────────────────────────────────────────

class AIRule(BaseModel):
    """A custom rule to guide AI behavior."""
    id: Optional[str] = None
    rule: str  # The rule text, e.g., "bcachefs requires kernel 6.8 or earlier"
    category: str = "general"  # general, storage, network, security, kernel, etc.
    priority: str = "high"  # high, medium, low - high rules are always included
    enabled: bool = True
    created_at: Optional[str] = None


@router.get("/ai-rules")
async def get_ai_rules() -> Dict[str, Any]:
    """Get all custom AI rules."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return {
                'rules': data.get('rules', []),
                'last_updated': data.get('last_updated')
            }
        
        # Return empty with example structure
        return {
            'rules': [],
            'last_updated': None,
            'examples': [
                "bcachefs requires kernel 6.8 or earlier - do not recommend kernel upgrades",
                "This system uses ZFS on root - grub-install requires special handling",
                "Docker storage is on /data/docker, not default location",
                "Always use 'apt' not 'apt-get' for package management suggestions",
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting AI rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-rules")
async def add_ai_rule(rule: AIRule) -> Dict[str, Any]:
    """Add a new custom AI rule."""
    import uuid
    
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {'rules': []}
        
        # Generate ID and timestamp
        new_rule = {
            'id': rule.id or str(uuid.uuid4())[:8],
            'rule': rule.rule,
            'category': rule.category,
            'priority': rule.priority,
            'enabled': rule.enabled,
            'created_at': rule.created_at or datetime.now().isoformat(),
        }
        
        data.setdefault('rules', []).append(new_rule)
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Added AI rule: {rule.rule[:50]}...")
        return {'success': True, 'rule': new_rule}
    
    except Exception as e:
        logger.error(f"Error adding AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ai-rules/{rule_id}")
async def delete_ai_rule(rule_id: str) -> Dict[str, Any]:
    """Delete a custom AI rule."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="No rules found")
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        rules = data.get('rules', [])
        original_count = len(rules)
        data['rules'] = [r for r in rules if r.get('id') != rule_id]
        
        if len(data['rules']) == original_count:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Deleted AI rule: {rule_id}")
        return {'success': True, 'deleted': rule_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ai-rules/{rule_id}")
async def update_ai_rule(rule_id: str, rule: AIRule) -> Dict[str, Any]:
    """Update an existing AI rule."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="No rules found")
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        rules = data.get('rules', [])
        updated = False
        
        for i, r in enumerate(rules):
            if r.get('id') == rule_id:
                rules[i] = {
                    'id': rule_id,
                    'rule': rule.rule,
                    'category': rule.category,
                    'priority': rule.priority,
                    'enabled': rule.enabled,
                    'created_at': r.get('created_at', datetime.now().isoformat()),
                }
                updated = True
                break
        
        if not updated:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        
        data['rules'] = rules
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Updated AI rule: {rule_id}")
        return {'success': True, 'rule': rules[i]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persona-name")
async def set_persona_name(update: PersonaNameUpdate) -> Dict[str, Any]:
    """Set the AI name for a specific persona."""
    try:
        config_path = get_config_dir() / 'preferences.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
        else:
            prefs = {}
        
        if 'persona_names' not in prefs:
            prefs['persona_names'] = {
                'it_admin': 'Halbert',
                'friend': 'Cera',
                'casual': 'Cera',
                'custom': 'Assistant'
            }
        
        prefs['persona_names'][update.persona] = update.name
        
        with open(config_path, 'w') as f:
            yaml.dump(prefs, f, default_flow_style=False)
        
        logger.info(f"Persona '{update.persona}' name set to: {update.name}")
        return {'success': True, 'persona': update.persona, 'name': update.name}
    
    except Exception as e:
        logger.error(f"Error setting persona name: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Keep old endpoint for backwards compatibility
@router.get("/computer-name")
async def get_computer_name() -> Dict[str, str]:
    """DEPRECATED: Use /persona-names instead. Get the default AI name."""
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            # Return the active persona's name or fallback
            persona_names = prefs.get('persona_names', {})
            return {'name': persona_names.get('it_admin', 'Halbert')}
        
        return {'name': 'Halbert'}
    
    except Exception as e:
        logger.error(f"Error getting computer name: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts")
async def get_prompt_settings() -> Dict[str, Any]:
    """Get current prompt configuration."""
    try:
        from ...model.prompt_manager import PromptManager, PromptMode
        
        manager = PromptManager()
        
        # Get all mode descriptions
        modes = {}
        for mode in PromptMode:
            modes[mode.value] = manager.get_mode_description(mode)
        
        return {
            'base_safety_prompt': manager.BASE_SAFETY_PROMPT[:200] + '...',  # Preview
            'modes': modes
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# System Profile (Phase 14: Self-Awareness)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/system-profile")
async def get_system_profile() -> Dict[str, Any]:
    """Get the current system profile (cached or from disk)."""
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        
        # Try to load from disk if not already scanned
        if not profiler.profile:
            profiler.load_profile()
        
        if profiler.profile:
            return {
                "status": "loaded",
                "profile": profiler.profile,
                "summary": profiler.get_summary(),
            }
        else:
            return {
                "status": "not_scanned",
                "message": "No system profile available. Run POST /api/settings/system-profile/scan to create one.",
            }
    
    except Exception as e:
        logger.error(f"Error getting system profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _run_background_scan():
    """Background thread function for system scan."""
    global _scan_state
    
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        from ...discovery.engine import get_engine
        from ...knowledge import bootstrap_from_profile
        
        profiler = get_system_profiler()
        
        # Phase 1: System Profile (10% of work)
        with _scan_lock:
            _scan_state["current_phase"] = "Scanning system profile..."
            _scan_state["progress_percent"] = 5
        logger.info("Starting system profile scan...")
        profile = profiler.scan_all()
        save_path = profiler.save_profile()
        with _scan_lock:
            _scan_state["progress_percent"] = 10
        
        # Phase 2: Discovery Scanners (80% of work - 10% to 90%)
        # Use callback for granular progress
        def discovery_progress(scanner_name: str, current: int, total: int):
            with _scan_lock:
                # Map scanner progress to 10-90% range
                scanner_percent = (current / max(total, 1)) * 80
                _scan_state["progress_percent"] = int(10 + scanner_percent)
                _scan_state["current_phase"] = f"Scanning {scanner_name}..."
        
        logger.info("Running discovery scanners...")
        engine = get_engine()
        discoveries = engine.scan_all(progress_callback=discovery_progress)
        discovery_count = len(discoveries)
        logger.info(f"Discovery scan complete: {discovery_count} items found")
        with _scan_lock:
            _scan_state["progress_percent"] = 90
        
        # Phase 3: Self-Knowledge (10% of work - 90% to 100%)
        with _scan_lock:
            _scan_state["current_phase"] = "Populating self-knowledge..."
            _scan_state["progress_percent"] = 92
        logger.info("Populating self-knowledge from profile...")
        knowledge_counts = bootstrap_from_profile(profile)
        total_knowledge = sum(knowledge_counts.values())
        logger.info(f"Self-knowledge populated: {total_knowledge} entries")
        
        # Done
        with _scan_lock:
            _scan_state["is_running"] = False
            _scan_state["current_phase"] = None
            _scan_state["progress_percent"] = 100
            _scan_state["result"] = {
                "status": "complete",
                "summary": profiler.get_summary(),
                "saved_to": str(save_path),
                "discoveries_scanned": discovery_count,
                "self_knowledge_added": total_knowledge,
            }
        logger.info("Background system scan complete")
        
    except Exception as e:
        logger.error(f"Background scan failed: {e}")
        with _scan_lock:
            _scan_state["is_running"] = False
            _scan_state["error"] = str(e)
            _scan_state["current_phase"] = None


@router.post("/system-profile/scan")
async def scan_system_profile() -> Dict[str, Any]:
    """Run a comprehensive system profile scan in background.
    
    Returns immediately. Poll /system-profile/scan/status for progress.
    
    This is the "Deep Scan" - it scans:
    1. System profile (hardware, OS, etc.)
    2. All discovery types (storage, services, network, backups, security)
    3. Populates self-knowledge from the profile (Genesis vision)
    """
    global _scan_state
    
    with _scan_lock:
        if _scan_state["is_running"]:
            return {
                "status": "already_running",
                "message": "Scan already in progress",
                "started_at": _scan_state["started_at"],
            }
        
        # Reset state and start
        _scan_state = {
            "is_running": True,
            "started_at": datetime.now().isoformat(),
            "current_phase": "Starting...",
            "progress_percent": 0,
            "error": None,
            "result": None,
        }
    
    # Start background thread
    scan_thread = threading.Thread(target=_run_background_scan, daemon=True)
    scan_thread.start()
    logger.info("Background system scan started")
    
    return {
        "status": "started",
        "message": "Scan started in background. Poll /api/settings/system-profile/scan/status for progress.",
    }


@router.get("/system-profile/scan/status")
async def get_scan_status() -> Dict[str, Any]:
    """Get status of background system scan."""
    with _scan_lock:
        return {
            "is_running": _scan_state["is_running"],
            "started_at": _scan_state["started_at"],
            "current_phase": _scan_state["current_phase"],
            "progress_percent": _scan_state.get("progress_percent", 0),
            "error": _scan_state["error"],
            "result": _scan_state["result"],
        }


@router.get("/system-profile/summary")
async def get_system_profile_summary() -> Dict[str, Any]:
    """Get just the human-readable system summary (for chat context)."""
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        
        # Try to load if not available
        if not profiler.profile:
            profiler.load_profile()
        
        if not profiler.profile:
            # Quick scan if no profile exists
            profiler.scan_all()
            profiler.save_profile()
        
        return {
            "summary": profiler.get_summary(),
            "scan_time": profiler.profile.get("scan_time"),
        }
    
    except Exception as e:
        logger.error(f"Error getting system summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-profile/quick-scan")
async def quick_scan_system() -> Dict[str, Any]:
    """
    Run a quick scan of frequently-changing items.
    
    Used on app startup. Takes 2-5 seconds.
    Updates: services, storage, network, containers, memory, uptime.
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        profile = profiler.quick_scan()
        
        return {
            "status": "complete",
            "scan_type": "quick",
            "profile": profile,
            "summary": profiler.get_summary(),
        }
    
    except Exception as e:
        logger.error(f"Error running quick scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-profile/scan-category/{category}")
async def scan_category(category: str) -> Dict[str, Any]:
    """
    Scan a specific category (for page rescans).
    
    Categories: storage, services, network, packages, security, 
                containers, users, hardware, os, kernel, boot,
                development, desktop, scheduled_tasks, virtualization
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        result = profiler.scan_category(category)
        
        return {
            "status": "complete",
            "category": category,
            "data": result,
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scanning category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_system_metrics() -> Dict[str, Any]:
    """
    Get real-time system metrics (CPU, memory, uptime).
    
    This provides a web fallback when Tauri is not available.
    """
    import psutil
    import time
    
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory
        mem = psutil.virtual_memory()
        memory_percent = mem.percent
        memory_total_gb = mem.total / (1024**3)
        memory_available_gb = mem.available / (1024**3)
        memory_used_gb = mem.used / (1024**3)
        
        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        
        # Disks
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "mount_point": partition.mountpoint,
                    "fs_type": partition.fstype,
                    "total_gb": usage.total / (1024**3),
                    "used_gb": usage.used / (1024**3),
                    "available_gb": usage.free / (1024**3),
                    "usage_percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_total_gb": round(memory_total_gb, 1),
            "memory_available_gb": round(memory_available_gb, 1),
            "memory_used_gb": round(memory_used_gb, 1),
            "uptime_seconds": uptime_seconds,
            "disks": disks,
        }
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/onboarding/status")
async def get_onboarding_status() -> Dict[str, Any]:
    """
    Check if onboarding is complete.
    
    Returns whether the user has completed first-time setup.
    """
    try:
        import socket
        from ...utils.platform import get_data_dir
        
        logger.info("Checking onboarding status...")
        
        config_dir = get_config_dir()
        data_dir = get_data_dir()
        onboarding_file = config_dir / "onboarding_complete"
        profile_file = data_dir / "system_profile.json"
        
        # Check if onboarding was completed
        is_complete = onboarding_file.exists() and profile_file.exists()
        
        # Get hostname for prefill
        hostname = socket.gethostname()
        
        # Check profile without loading full profiler (avoid heavy imports)
        has_profile = profile_file.exists()
        last_deep_scan = None
        last_quick_scan = None
        
        if has_profile:
            try:
                import json
                with open(profile_file) as f:
                    profile_data = json.load(f)
                last_deep_scan = profile_data.get("scan_time")
                last_quick_scan = profile_data.get("quick_scan_time")
            except Exception:
                pass
        
        logger.info(f"Onboarding status: complete={is_complete}, has_profile={has_profile}")
        
        return {
            "onboarding_complete": is_complete,
            "has_system_profile": has_profile,
            "suggested_name": hostname,
            "last_deep_scan": last_deep_scan,
            "last_quick_scan": last_quick_scan,
        }
    
    except Exception as e:
        logger.error(f"Error checking onboarding status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class OnboardingData(BaseModel):
    """Onboarding configuration."""
    computer_name: str
    admin_name: str = "Admin"  # IT Admin/user's name
    user_type: str = "casual"  # casual, it_admin, developer, ai_professional


@router.post("/onboarding/complete")
async def complete_onboarding(data: OnboardingData) -> Dict[str, Any]:
    """
    Complete the onboarding process.
    
    1. Run deep system scan
    2. Save computer name and user type
    3. Mark onboarding as complete
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        logger.info(f"Starting onboarding for {data.computer_name} ({data.user_type})")
        
        # Run deep scan
        profiler = get_system_profiler()
        profile = profiler.scan_all()
        
        # Add user preferences to profile
        profile["user_settings"] = {
            "computer_name": data.computer_name,
            "admin_name": data.admin_name,
            "user_type": data.user_type,
            "onboarding_date": datetime.now().isoformat() if 'datetime' in dir() else None,
        }
        
        # Save profile
        profiler.save_profile()
        
        # Mark onboarding complete
        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        
        onboarding_file = config_dir / "onboarding_complete"
        onboarding_file.write_text(f"{data.computer_name}\n{data.admin_name}\n{data.user_type}")
        
        # Save to preferences.yml so chat can read the AI name and user name
        preferences_path = config_dir / "preferences.yml"
        try:
            if preferences_path.exists():
                with open(preferences_path) as f:
                    prefs = yaml.safe_load(f) or {}
            else:
                prefs = {}
            
            # Set the AI name from onboarding (this is the "computer name" the user chose)
            prefs["ai_name"] = data.computer_name
            prefs["user_name"] = data.admin_name
            prefs["user_type"] = data.user_type
            
            # Remove deprecated persona_names if present
            prefs.pop("persona_names", None)
            prefs.pop("computer_name", None)  # Use ai_name instead
            
            with open(preferences_path, 'w') as f:
                yaml.dump(prefs, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved preferences: ai_name={data.computer_name}, user_name={data.admin_name}")
        except Exception as e:
            logger.warning(f"Failed to save preferences: {e}")
        
        return {
            "status": "complete",
            "computer_name": data.computer_name,
            "user_type": data.user_type,
            "profile_summary": profiler.get_summary(),
        }
    
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import datetime at module level for onboarding
from datetime import datetime


# =============================================================================
# Ingestion Service API
# =============================================================================

@router.get("/ingestion/status")
async def get_ingestion_status():
    """Get ingestion service status."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        return service.status()
    except Exception as e:
        logger.error(f"Failed to get ingestion status: {e}")
        return {
            "running": False,
            "error": str(e)
        }


@router.post("/ingestion/start")
async def start_ingestion():
    """Start the ingestion service."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        success = service.start()
        return {
            "success": success,
            "status": service.status()
        }
    except Exception as e:
        logger.error(f"Failed to start ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/stop")
async def stop_ingestion():
    """Stop the ingestion service."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        success = service.stop()
        return {
            "success": success,
            "status": service.status()
        }
    except Exception as e:
        logger.error(f"Failed to stop ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Document Indexing API
# =============================================================================

# Background indexing state (survives page navigation but resets on server restart)
# Note: If server crashes during indexing, state will be clean on restart
_indexing_state = {
    "is_running": False,
    "started_at": None,
    "completed_at": None,
    "total_indexed": 0,
    "current_source": None,
    "sources_completed": [],
    "sources_total": 0,
    "progress_percent": 0,
    "error": None
}

# Log that indexing state is fresh on module load
import logging as _settings_logging
_settings_logging.getLogger("halbert.dashboard").info("Indexing state initialized (fresh start)")

# Persistent last indexed timestamp (saved to file for persistence across restarts)
def _get_last_indexed_info() -> dict:
    """Get last indexed timestamp from persistent storage."""
    try:
        index_info_file = Path.home() / ".local" / "share" / "halbert" / "index_info.json"
        if index_info_file.exists():
            import json
            with open(index_info_file) as f:
                return json.load(f)
    except Exception:
        pass
    return {"last_indexed_at": None, "docs_count": 0}

def _save_last_indexed_info(docs_count: int):
    """Save last indexed timestamp to persistent storage."""
    try:
        index_info_file = Path.home() / ".local" / "share" / "halbert" / "index_info.json"
        index_info_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(index_info_file, 'w') as f:
            json.dump({
                "last_indexed_at": datetime.now(timezone.utc).isoformat(),
                "docs_count": docs_count
            }, f)
    except Exception as e:
        logger.warning(f"Failed to save index info: {e}")


def _reset_indexing_state():
    """Reset indexing state (for recovery from stuck state)."""
    global _indexing_state
    _indexing_state["is_running"] = False
    _indexing_state["started_at"] = None
    _indexing_state["completed_at"] = None
    _indexing_state["total_indexed"] = 0
    _indexing_state["current_source"] = None
    _indexing_state["sources_completed"] = []
    _indexing_state["sources_total"] = 0
    _indexing_state["progress_percent"] = 0
    _indexing_state["error"] = None
    logger.info("Indexing state reset")

def _run_background_index(max_docs: int, source: str = None):
    """Run indexing in background thread with progress tracking."""
    global _indexing_state
    import threading
    
    def do_index_work():
        global _indexing_state
        try:
            logger.info("Background indexing thread started")
            
            # Update state immediately so UI shows progress
            _indexing_state["current_source"] = "Starting..."
            
            # Get data directory path (fast operation, no ChromaDB)
            from pathlib import Path
            data_dir = Path.home() / "LinuxBrain" / "data" / "linux"
            if not data_dir.exists():
                # Try alternate location
                data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "linux"
            
            logger.info(f"Using data directory: {data_dir}")
            
            if not data_dir.exists():
                logger.error(f"Data directory does not exist: {data_dir}")
                _indexing_state["error"] = f"Data directory not found: {data_dir}"
                return
            
            # Find sources BEFORE initializing ChromaDB (which can be slow)
            priority_sources = [
                "man-pages", "arch-wiki", "arch-wiki-ext", "3k-push",
                "automation-docs", "linux-manual", "systemd-docs", "shell-docs",
                "security-docs", "networking-docs", "git-docs", "scheduling-docs",
                "logging-docs", "performance-docs", "flatpak-docs", "snap-docs",
                "appimage-docs", "network-docs", "docker-docs", "backup-docs",
            ]
            existing_sources = [src for src in priority_sources if (data_dir / src).exists()]
            logger.info(f"Found {len(existing_sources)} sources to index")
            _indexing_state["sources_total"] = len(existing_sources)
            _indexing_state["current_source"] = "Initializing..."
            
            # Now import the indexer (this triggers ChromaDB init which is slow)
            from ...rag.document_indexer import index_documents as do_index
            
            if source:
                # Single source
                _indexing_state["sources_total"] = 1
                _indexing_state["current_source"] = source
                stats = do_index(
                    data_dir=data_dir,
                    collection_name="linux_docs",
                    max_docs=max_docs,
                    sources=[source]
                )
                _indexing_state["total_indexed"] = stats.indexed_docs
                _indexing_state["sources_completed"] = [source]
                _indexing_state["progress_percent"] = 100
            else:
                # Use existing_sources we found earlier (before ChromaDB init)
                if not existing_sources:
                    logger.warning("No source directories found!")
                    _indexing_state["error"] = "No source directories found"
                    return
                
                total_docs = 0
                
                for i, src in enumerate(existing_sources):
                    _indexing_state["current_source"] = src
                    _indexing_state["progress_percent"] = int((i / len(existing_sources)) * 100)
                    logger.info(f"Indexing source {i+1}/{len(existing_sources)}: {src}")
                    
                    try:
                        stats = do_index(
                            data_dir=data_dir,
                            collection_name="linux_docs",
                            max_docs=max_docs,
                            sources=[src]
                        )
                        total_docs += stats.indexed_docs
                        _indexing_state["sources_completed"].append(src)
                        _indexing_state["total_indexed"] = total_docs
                    except Exception as e:
                        logger.warning(f"Failed to index {src}: {e}")
                
                _indexing_state["progress_percent"] = 100
            
            _indexing_state["completed_at"] = datetime.now(timezone.utc).isoformat()
            _indexing_state["error"] = None
            # Save persistent last indexed info
            _save_last_indexed_info(_indexing_state["total_indexed"])
            logger.info(f"Background indexing complete: {_indexing_state['total_indexed']} docs")
            
        except Exception as e:
            logger.error(f"Background indexing failed: {e}")
            _indexing_state["error"] = str(e)
            _indexing_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        finally:
            _indexing_state["is_running"] = False
            _indexing_state["current_source"] = None
    
    # Start background thread
    _indexing_state["is_running"] = True
    _indexing_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _indexing_state["completed_at"] = None
    _indexing_state["total_indexed"] = 0
    _indexing_state["sources_completed"] = []
    _indexing_state["sources_total"] = 0
    _indexing_state["progress_percent"] = 0
    _indexing_state["error"] = None
    
    thread = threading.Thread(target=do_index_work, daemon=True)
    thread.start()


@router.get("/docs/stats")
async def get_docs_stats():
    """Get document index statistics."""
    try:
        logger.info("Getting docs stats...")
        from ...rag.document_indexer import get_index_stats
        logger.info("Imported get_index_stats, calling...")
        stats = get_index_stats()
        logger.info(f"Got stats: {stats.get('total_docs', 0)} total docs")
        
        # Include indexing status with progress
        stats["indexing"] = {
            "is_running": _indexing_state["is_running"],
            "started_at": _indexing_state["started_at"],
            "completed_at": _indexing_state["completed_at"],
            "total_indexed": _indexing_state["total_indexed"],
            "current_source": _indexing_state["current_source"],
            "sources_completed": _indexing_state["sources_completed"],
            "sources_total": _indexing_state["sources_total"],
            "progress_percent": _indexing_state["progress_percent"],
            "error": _indexing_state["error"]
        }
        
        # Include last indexed info (persistent across restarts)
        last_indexed = _get_last_indexed_info()
        stats["freshness"] = {
            "last_indexed_at": last_indexed.get("last_indexed_at"),
            "docs_at_last_index": last_indexed.get("docs_count", 0),
            "update_mechanism": "manual",  # Could be "scheduled" in future
            "info": "Click Re-index to update documentation. Core sources are bundled with Halbert and updated with each release."
        }
        
        return stats
    except Exception as e:
        logger.error(f"Failed to get doc stats: {e}")
        return {"error": str(e), "linux_docs_count": 0}


@router.post("/docs/reset")
async def reset_indexing():
    """Reset stuck indexing state. Use if indexing appears stuck."""
    _reset_indexing_state()
    return {"status": "reset", "message": "Indexing state has been reset. You can now re-index."}


@router.post("/docs/index")
async def index_documents(max_docs: int = 1000, source: str = None, background: bool = True):
    """
    Index Linux documentation into ChromaDB.
    
    Args:
        max_docs: Maximum documents to index
        source: Specific source to index (None = priority sources)
        background: Run in background (default True) - allows page navigation
    """
    # Check if already running
    if _indexing_state["is_running"]:
        return {
            "status": "already_running",
            "message": "Indexing is already in progress. Check /docs/stats for status.",
            "started_at": _indexing_state["started_at"]
        }
    
    if background:
        # Start background indexing - user can navigate away
        _run_background_index(max_docs, source)
        return {
            "status": "started",
            "message": "Indexing started in background. You can navigate away - check /docs/stats for progress.",
            "started_at": _indexing_state["started_at"]
        }
    
    # Synchronous indexing (legacy behavior)
    try:
        from ...rag.document_indexer import index_documents as do_index, get_default_data_dir
        
        data_dir = get_default_data_dir()
        
        if source:
            # Index specific source
            stats = do_index(
                data_dir=data_dir,
                collection_name="linux_docs",
                max_docs=max_docs,
                sources=[source]
            )
            return {
                "source": source,
                "indexed": stats.indexed_docs,
                "skipped": stats.skipped_docs,
                "errors": stats.errors,
                "duration_s": (stats.completed_at - stats.started_at).total_seconds() if stats.completed_at else 0
            }
        else:
            # Index priority sources
            from ...rag.document_indexer import index_priority_docs
            results = index_priority_docs(max_per_source=max_docs)
            
            total_indexed = sum(s.indexed_docs for s in results.values())
            return {
                "sources_indexed": list(results.keys()),
                "total_indexed": total_indexed,
                "per_source": {k: v.indexed_docs for k, v in results.items()}
            }
    except Exception as e:
        logger.error(f"Failed to index documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/docs/query")
async def query_documents(q: str, k: int = 5):
    """
    Query indexed documents.
    
    Args:
        q: Search query
        k: Number of results
    """
    try:
        from ...rag.document_indexer import query_docs
        results = query_docs(q, k=k)
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Document query failed: {e}")
        return {"query": q, "results": [], "count": 0, "error": str(e)}


# =============================================================================
# Self-Knowledge API (System Ontology)
# =============================================================================

@router.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get self-knowledge statistics."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return sk.stats()
    except Exception as e:
        logger.error(f"Failed to get knowledge stats: {e}")
        return {"error": str(e), "total_entries": 0}


@router.get("/knowledge/identity")
async def get_system_identity():
    """Get core system identity."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return {
            "identity": sk.get_identity(),
            "hardware": [
                {"subject": e.subject, "content": e.content}
                for e in sk.get_by_type(sk._knowledge.get('hardware', {}).get('type') or 
                                       __import__('halbert_core.knowledge', fromlist=['KnowledgeType']).KnowledgeType.HARDWARE)
            ] if sk._knowledge else []
        }
    except Exception as e:
        logger.error(f"Failed to get identity: {e}")
        return {"identity": {}, "error": str(e)}


@router.post("/knowledge/bootstrap")
async def bootstrap_system_identity():
    """Bootstrap system identity from current system state."""
    try:
        from ...knowledge import bootstrap_identity
        identity = bootstrap_identity()
        return {"success": True, "identity": identity}
    except Exception as e:
        logger.error(f"Failed to bootstrap identity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TeachRequest(BaseModel):
    subject: str
    content: str
    rationale: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/knowledge/teach")
async def teach_system(request: TeachRequest):
    """
    Teach the system something about itself.
    
    Example:
        POST /api/settings/knowledge/teach
        {
            "subject": "bcachefs pool",
            "content": "The pool uses nvme0n1 and nvme1n1 in RAID1",
            "rationale": "For redundancy on critical data",
            "tags": ["storage", "bcachefs"]
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.teach(
            subject=request.subject,
            content=request.content,
            rationale=request.rationale,
            tags=request.tags
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Learned about: {request.subject}"
        }
    except Exception as e:
        logger.error(f"Failed to teach: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ConfigRationaleRequest(BaseModel):
    config_name: str
    description: str
    rationale: str
    tags: Optional[List[str]] = None


@router.post("/knowledge/explain-config")
async def explain_config(request: ConfigRationaleRequest):
    """
    Record WHY something is configured a certain way.
    
    Example:
        POST /api/settings/knowledge/explain-config
        {
            "config_name": "kernel version",
            "description": "Using kernel 6.8.12",
            "rationale": "bcachefs requires kernel 6.8 or earlier"
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.explain_config(
            config_name=request.config_name,
            description=request.description,
            rationale=request.rationale,
            tags=request.tags
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Recorded config rationale for: {request.config_name}"
        }
    except Exception as e:
        logger.error(f"Failed to explain config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RoleRequest(BaseModel):
    component: str
    role: str
    rationale: Optional[str] = None


@router.post("/knowledge/assign-role")
async def assign_role(request: RoleRequest):
    """
    Assign a role/purpose to a component.
    
    Example:
        POST /api/settings/knowledge/assign-role
        {
            "component": "sda",
            "role": "backup disk",
            "rationale": "Dedicated to Borg backup repository"
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.assign_role(
            component=request.component,
            role=request.role,
            rationale=request.rationale
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Assigned role '{request.role}' to {request.component}"
        }
    except Exception as e:
        logger.error(f"Failed to assign role: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/search")
async def search_knowledge(q: str, k: int = 5):
    """Search self-knowledge semantically."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        results = sk.search(q, k=k)
        
        return {
            "query": q,
            "results": [
                {
                    "id": e.id,
                    "type": e.type.value,
                    "subject": e.subject,
                    "content": e.content,
                    "rationale": e.rationale,
                    "source": e.source,
                }
                for e in results
            ],
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return {"query": q, "results": [], "count": 0, "error": str(e)}


@router.get("/knowledge/all")
async def get_all_knowledge():
    """Get all self-knowledge entries."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        entries = []
        for entry in sk._knowledge.values():
            entries.append({
                "id": entry.id,
                "type": entry.type.value,
                "subject": entry.subject,
                "content": entry.content,
                "rationale": entry.rationale,
                "source": entry.source,
                "created_at": entry.created_at,
                "tags": entry.tags,
            })
        
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        logger.error(f"Failed to get knowledge: {e}")
        return {"entries": [], "count": 0, "error": str(e)}


@router.delete("/knowledge/{entry_id:path}")
async def delete_knowledge(entry_id: str):
    """Delete a self-knowledge entry by ID."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        if entry_id in sk._knowledge:
            del sk._knowledge[entry_id]
            sk._save()
            return {"success": True, "deleted": entry_id}
        else:
            raise HTTPException(status_code=404, detail=f"Knowledge entry not found: {entry_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/stats")
async def get_knowledge_stats():
    """
    Get memory operation statistics.
    
    Sprint 1: Mem0-style memory tracking.
    Returns counts of ADD/UPDATE/DELETE/NOOP operations.
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return sk.get_memory_stats()
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2: Knowledge Graph API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/knowledge/graph/stats")
async def get_graph_stats():
    """Get knowledge graph statistics."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        return graph.get_stats()
    except Exception as e:
        logger.error(f"Failed to get graph stats: {e}")
        return {"error": str(e)}


@router.get("/knowledge/graph/relations")
async def get_all_relations():
    """Get all relations in the knowledge graph."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        return {
            "relations": [r.to_dict() for r in graph._relations.values()],
            "count": len(graph._relations),
        }
    except Exception as e:
        logger.error(f"Failed to get relations: {e}")
        return {"error": str(e)}


@router.get("/knowledge/graph/node/{node_id:path}")
async def get_node_relations(node_id: str):
    """Get all relations for a specific node."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        
        outgoing = [r.to_dict() for r in graph.get_outgoing(node_id)]
        incoming = [r.to_dict() for r in graph.get_incoming(node_id)]
        
        return {
            "node": node_id,
            "outgoing": outgoing,
            "incoming": incoming,
            "total": len(outgoing) + len(incoming),
        }
    except Exception as e:
        logger.error(f"Failed to get node relations: {e}")
        return {"error": str(e)}


@router.get("/knowledge/graph/impact/{node_id:path}")
async def get_impact_analysis(node_id: str):
    """
    Analyze what would be affected if a node fails.
    
    Sprint 2: Graph-based impact analysis.
    """
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        return graph.impact_analysis(node_id)
    except Exception as e:
        logger.error(f"Failed to perform impact analysis: {e}")
        return {"error": str(e)}


@router.get("/knowledge/graph/dependents/{node_id:path}")
async def get_dependents(node_id: str):
    """Get what depends on this node."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        return {
            "node": node_id,
            "dependents": graph.get_dependents(node_id),
        }
    except Exception as e:
        logger.error(f"Failed to get dependents: {e}")
        return {"error": str(e)}


@router.get("/knowledge/graph/dependencies/{node_id:path}")
async def get_dependencies(node_id: str):
    """Get what this node depends on."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        return {
            "node": node_id,
            "dependencies": graph.get_dependencies(node_id),
        }
    except Exception as e:
        logger.error(f"Failed to get dependencies: {e}")
        return {"error": str(e)}


@router.post("/knowledge/graph/relation")
async def add_relation(
    source: str,
    target: str,
    relation_type: str,
    strength: float = 1.0,
    bidirectional: bool = False
):
    """Add a new relation to the knowledge graph."""
    try:
        from ...knowledge import get_knowledge_graph, RelationType
        graph = get_knowledge_graph()
        
        # Validate relation type
        try:
            rel_type = RelationType(relation_type)
        except ValueError:
            valid_types = [rt.value for rt in RelationType]
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid relation_type. Must be one of: {valid_types}"
            )
        
        rel_id = graph.add_relation(
            source=source,
            target=target,
            relation_type=rel_type,
            strength=strength,
            bidirectional=bidirectional,
        )
        
        return {"success": True, "relation_id": rel_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add relation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/knowledge/graph/relation/{rel_id:path}")
async def delete_relation(rel_id: str):
    """Delete a relation from the knowledge graph."""
    try:
        from ...knowledge import get_knowledge_graph
        graph = get_knowledge_graph()
        
        if graph.remove_relation(rel_id):
            return {"success": True, "deleted": rel_id}
        else:
            raise HTTPException(status_code=404, detail=f"Relation not found: {rel_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete relation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 3: Self-Reflection API
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/knowledge/reflect")
async def reflect_on_query(query: str, max_contexts: int = 10):
    """
    Reflect on a query before answering.
    
    Sprint 3: Self-RAG inspired reflection.
    Analyzes query, retrieves relevant knowledge, scores relevance,
    and provides confidence assessment.
    """
    try:
        from ...knowledge import reflect_before_answer
        result = reflect_before_answer(query, max_contexts=max_contexts)
        return result.to_dict()
    except Exception as e:
        logger.error(f"Failed to reflect on query: {e}")
        return {"error": str(e)}


@router.get("/knowledge/reflect/context")
async def get_reflection_context(query: str, max_entries: int = 5):
    """
    Get formatted context string for LLM consumption.
    
    Returns a human-readable summary of relevant self-knowledge.
    """
    try:
        from ...knowledge import reflect_before_answer
        result = reflect_before_answer(query)
        return {
            "query": query,
            "confidence": result.confidence.value,
            "context": result.get_context_string(max_entries),
        }
    except Exception as e:
        logger.error(f"Failed to get reflection context: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4: Hierarchical Knowledge API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/knowledge/hierarchical/stats")
async def get_hierarchical_stats():
    """Get hierarchical knowledge statistics."""
    try:
        from ...knowledge import get_hierarchical_knowledge
        hk = get_hierarchical_knowledge()
        return hk.get_stats()
    except Exception as e:
        logger.error(f"Failed to get hierarchical stats: {e}")
        return {"error": str(e)}


@router.post("/knowledge/hierarchical/build")
async def build_hierarchy():
    """
    Build hierarchical documents from self-knowledge.
    
    Sprint 4: RAPTOR-style document organization.
    Creates LEAF, CLUSTER, and SUMMARY tier documents.
    """
    try:
        from ...knowledge import get_hierarchical_knowledge
        hk = get_hierarchical_knowledge()
        counts = hk.build_from_knowledge()
        return {"success": True, "counts": counts}
    except Exception as e:
        logger.error(f"Failed to build hierarchy: {e}")
        return {"error": str(e)}


@router.get("/knowledge/hierarchical/retrieve")
async def retrieve_hierarchical(
    query: str, 
    tier: Optional[str] = None,
    max_results: int = 5
):
    """
    Retrieve documents at appropriate abstraction level.
    
    Args:
        query: Search query
        tier: Preferred tier (leaf, cluster, summary) or auto
        max_results: Maximum documents to return
    """
    try:
        from ...knowledge import get_hierarchical_knowledge, DocumentTier
        hk = get_hierarchical_knowledge()
        
        preferred_tier = None
        if tier:
            try:
                preferred_tier = DocumentTier(tier)
            except ValueError:
                pass
        
        docs = hk.retrieve(query, preferred_tier=preferred_tier, max_results=max_results)
        return {
            "query": query,
            "tier": tier or "auto",
            "results": [d.to_dict() for d in docs],
            "count": len(docs),
        }
    except Exception as e:
        logger.error(f"Failed to retrieve hierarchical: {e}")
        return {"error": str(e)}


@router.get("/knowledge/hierarchical/tier/{tier}")
async def get_tier_documents(tier: str):
    """Get all documents at a specific tier."""
    try:
        from ...knowledge import get_hierarchical_knowledge, DocumentTier
        hk = get_hierarchical_knowledge()
        
        try:
            doc_tier = DocumentTier(tier)
        except ValueError:
            return {"error": f"Invalid tier: {tier}. Must be leaf, cluster, or summary"}
        
        docs = hk.get_by_tier(doc_tier)
        return {
            "tier": tier,
            "documents": [d.to_dict() for d in docs],
            "count": len(docs),
        }
    except Exception as e:
        logger.error(f"Failed to get tier documents: {e}")
        return {"error": str(e)}


@router.get("/knowledge/hierarchical/category/{category}")
async def get_category_documents(category: str):
    """Get all documents in a category."""
    try:
        from ...knowledge import get_hierarchical_knowledge
        hk = get_hierarchical_knowledge()
        docs = hk.get_by_category(category)
        return {
            "category": category,
            "documents": [d.to_dict() for d in docs],
            "count": len(docs),
        }
    except Exception as e:
        logger.error(f"Failed to get category documents: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 23: Approval & Guardrails API
# ─────────────────────────────────────────────────────────────────────────────

from ...approval.engine import ApprovalEngine, ApprovalRequest, ApprovalDecision
from ...autonomy.guardrails import GuardrailEnforcer

_approval_engine: Optional[ApprovalEngine] = None
_guardrail_enforcer: Optional[GuardrailEnforcer] = None

def get_approval_engine() -> ApprovalEngine:
    """Get singleton approval engine."""
    global _approval_engine
    if _approval_engine is None:
        _approval_engine = ApprovalEngine()
    return _approval_engine

def get_guardrail_enforcer() -> GuardrailEnforcer:
    """Get singleton guardrail enforcer."""
    global _guardrail_enforcer
    if _guardrail_enforcer is None:
        _guardrail_enforcer = GuardrailEnforcer()
    return _guardrail_enforcer


def _load_ai_rules() -> list:
    """Load AI rules from config file."""
    try:
        from ...utils.platform import get_config_dir
        import yaml
        
        config_path = get_config_dir() / 'ai_rules.yml'
        if not config_path.exists():
            return []
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        return [r for r in data.get('rules', []) if r.get('enabled', True)]
    except Exception:
        return []


def _check_approval_conflicts(action: str, task: str, affected_resources: list) -> dict:
    """
    Check if an approval request conflicts with any AI rules.
    
    Returns dict with conflict info if found, else None.
    """
    rules = _load_ai_rules()
    if not rules:
        return None
    
    # Build searchable text from approval
    search_text = f"{action} {task} {' '.join(affected_resources or [])}".lower()
    
    for rule in rules:
        rule_text = rule.get('rule', '').lower()
        category = rule.get('category', '')
        
        # Check for kernel-related rules vs kernel updates
        if category == 'kernel' or 'kernel' in rule_text:
            if 'kernel' in search_text and ('update' in search_text or 'upgrade' in search_text):
                return {
                    "has_conflict": True,
                    "conflicting_rule": rule.get('rule'),
                    "rule_category": category,
                    "rule_priority": rule.get('priority', 'medium')
                }
        
        # Check for general keyword matches
        # Look for negative keywords in rules (don't, avoid, never, etc.)
        negative_patterns = ['don\'t', 'dont', 'do not', 'avoid', 'never', 'skip', 'exclude']
        if any(neg in rule_text for neg in negative_patterns):
            # Extract key terms from rule
            keywords = [w for w in rule_text.split() if len(w) > 3 and w not in negative_patterns]
            # If any keyword appears in the approval, flag it
            for kw in keywords[:5]:  # Check first 5 significant words
                if kw in search_text:
                    return {
                        "has_conflict": True,
                        "conflicting_rule": rule.get('rule'),
                        "rule_category": category,
                        "rule_priority": rule.get('priority', 'medium')
                    }
    
    return None


@router.get("/approvals/pending")
async def get_pending_approvals(include_blocked: bool = False):
    """
    Get all pending approval requests.
    
    By default, approvals that conflict with AI Rules are FILTERED OUT.
    Set include_blocked=true to see them with warnings.
    """
    try:
        engine = get_approval_engine()
        pending = engine.get_pending_requests()
        
        results = []
        blocked_count = 0
        
        for req in pending:
            # Check for AI rule conflicts
            conflict = _check_approval_conflicts(
                req.action, 
                req.task, 
                req.affected_resources
            )
            
            # By default, BLOCK approvals that conflict with rules
            if conflict and not include_blocked:
                blocked_count += 1
                logger.info(f"Blocking approval '{req.id}' - conflicts with rule: {conflict.get('conflicting_rule')}")
                continue
            
            item = {
                "id": req.id,
                "task": req.task,
                "action": req.action,
                "reasoning": req.reasoning,
                "confidence": req.confidence,
                "risk_level": req.risk_level,
                "affected_resources": req.affected_resources,
                "requested_at": req.requested_at,
                "simulation_result": req.simulation_result,
            }
            
            if conflict:
                item["rule_conflict"] = conflict
            
            results.append(item)
        
        return {
            "status": "ok",
            "pending": results,
            "count": len(results),
            "blocked_by_rules": blocked_count
        }
    except Exception as e:
        logger.error(f"Failed to get pending approvals: {e}")
        return {"status": "error", "error": str(e), "pending": [], "count": 0}


@router.get("/approvals/history")
async def get_approval_history(limit: int = 50, approved_only: bool = False):
    """Get approval history."""
    try:
        engine = get_approval_engine()
        history = engine.get_approval_history(limit=limit, approved_only=approved_only)
        return {"status": "ok", "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Failed to get approval history: {e}")
        return {"status": "error", "error": str(e), "history": [], "count": 0}


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    reason: Optional[str] = None
    save_to_memory: bool = True  # Store rejection in AI memory for learning


@router.post("/approvals/{request_id}/decide")
async def decide_approval(request_id: str, decision: ApprovalDecisionRequest):
    """Approve or reject a pending request."""
    try:
        engine = get_approval_engine()
        req = engine.get_request(request_id)
        
        if not req:
            return {"status": "error", "error": f"Request {request_id} not found"}
        
        if req.status != "pending":
            return {"status": "error", "error": f"Request {request_id} is not pending (status: {req.status})"}
        
        # Create decision
        from datetime import datetime, timezone
        approval_decision = ApprovalDecision(
            request_id=request_id,
            approved=decision.approved,
            reason=decision.reason,
            decided_by="dashboard_user",
            decided_at=datetime.now(timezone.utc).isoformat() + 'Z'
        )
        
        # Update request
        req.status = "approved" if decision.approved else "rejected"
        if decision.approved:
            req.approved_at = approval_decision.decided_at
            req.approved_by = "dashboard_user"
        else:
            req.rejected_at = approval_decision.decided_at
            req.rejection_reason = decision.reason
        
        engine._save_request(req)
        engine._save_decision(approval_decision)
        
        # Store ALL decisions in ChromaDB for AI learning
        saved_to_memory = False
        if decision.save_to_memory:
            try:
                from ...index.chroma_index import get_index
                index = get_index()
                
                from datetime import datetime, timezone
                timestamp = datetime.now(timezone.utc).isoformat()
                
                if decision.approved:
                    # Store approval - AI learns what user accepts
                    memory_content = (
                        f"User APPROVED an autonomous action.\n"
                        f"Action: {req.action}\n"
                        f"Task: {req.task}\n"
                        f"AI Reasoning: {req.reasoning}\n"
                        f"Confidence: {req.confidence:.0%}\n"
                        f"Risk Level: {req.risk_level}\n"
                        f"Learn: Similar actions at this confidence/risk level are acceptable to the user."
                    )
                    doc_id = f"approval:{request_id}"
                    doc_type = "user_approval"
                else:
                    # Store rejection - AI learns what to avoid
                    memory_content = (
                        f"User REJECTED an autonomous action.\n"
                        f"Action: {req.action}\n"
                        f"Task: {req.task}\n"
                        f"AI Reasoning: {req.reasoning}\n"
                        f"Confidence: {req.confidence:.0%}\n"
                        f"Risk Level: {req.risk_level}\n"
                        f"User's rejection reason: {decision.reason or 'Not specified'}\n"
                        f"Learn: Avoid similar actions or ask for confirmation. User prefers not to do this."
                    )
                    doc_id = f"rejection:{request_id}"
                    doc_type = "user_rejection"
                
                index.upsert_memory(
                    collection="self_knowledge_all",
                    doc_id=doc_id,
                    text=memory_content,
                    metadata={
                        "type": doc_type,
                        "request_id": request_id,
                        "action": req.action,
                        "task": req.task,
                        "confidence": req.confidence,
                        "risk_level": req.risk_level,
                        "approved": decision.approved,
                        "reason": decision.reason,
                        "timestamp": timestamp
                    }
                )
                logger.info(f"Saved {doc_type} to memory: {request_id}")
                saved_to_memory = True
            except Exception as mem_err:
                logger.warning(f"Failed to save decision to memory: {mem_err}")
        
        return {
            "status": "ok",
            "request_id": request_id,
            "decision": "approved" if decision.approved else "rejected",
            "reason": decision.reason,
            "saved_to_memory": saved_to_memory
        }
    except Exception as e:
        logger.error(f"Failed to process approval decision: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Policy Configuration API
# ─────────────────────────────────────────────────────────────────────────────

def _get_policy_path() -> Path:
    """Get the policy.yml path."""
    # Check user config first, then system
    from ...utils.platform import get_config_dir
    user_path = get_config_dir() / 'policy.yml'
    if user_path.exists():
        return user_path
    # Fall back to project config
    return Path("config/policy.yml")


@router.get("/policy")
async def get_policy():
    """Get current policy configuration."""
    try:
        import yaml
        path = _get_policy_path()
        
        if not path.exists():
            return {
                "status": "ok",
                "policy": {"default_allow": True, "tools": {}},
                "path": str(path),
                "exists": False
            }
        
        with open(path, 'r') as f:
            policy = yaml.safe_load(f) or {}
        
        return {
            "status": "ok",
            "policy": policy,
            "path": str(path),
            "exists": True
        }
    except Exception as e:
        logger.error(f"Failed to get policy: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/policy")
async def update_policy(request: Request):
    """Update policy configuration."""
    try:
        import yaml
        data = await request.json()
        
        policy = data.get("policy", {})
        path = _get_policy_path()
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with comments
        content = """# Halbert Policy Configuration
# Controls whether side-effecting tools may apply changes.

# If true, tools are allowed by default unless overridden below.
# If false, tools are denied by default unless explicitly allowed.
default_allow: {default_allow}

# Per-tool overrides
tools:
""".format(default_allow=str(policy.get('default_allow', True)).lower())
        
        tools = policy.get('tools', {})
        for tool_name, tool_config in tools.items():
            if isinstance(tool_config, dict):
                content += f"  {tool_name}:\n"
                for key, value in tool_config.items():
                    content += f"    {key}: {str(value).lower() if isinstance(value, bool) else value}\n"
            else:
                content += f"  {tool_name}: {tool_config}\n"
        
        with open(path, 'w') as f:
            f.write(content)
        
        logger.info(f"Updated policy at {path}")
        return {"status": "ok", "path": str(path)}
    except Exception as e:
        logger.error(f"Failed to update policy: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/policy/tool")
async def set_tool_policy(request: Request):
    """Set policy for a specific tool."""
    try:
        import yaml
        data = await request.json()
        
        tool_name = data.get("tool")
        allow = data.get("allow", True)
        require_approval = data.get("require_approval", False)
        
        if not tool_name:
            return {"status": "error", "error": "Tool name required"}
        
        path = _get_policy_path()
        
        # Load existing policy
        if path.exists():
            with open(path, 'r') as f:
                policy = yaml.safe_load(f) or {}
        else:
            policy = {"default_allow": True, "tools": {}}
        
        # Update tool config
        if "tools" not in policy:
            policy["tools"] = {}
        
        policy["tools"][tool_name] = {
            "allow": allow,
            "require_approval": require_approval
        }
        
        # Save back
        with open(path, 'w') as f:
            yaml.dump(policy, f, default_flow_style=False)
        
        return {"status": "ok", "tool": tool_name, "config": policy["tools"][tool_name]}
    except Exception as e:
        logger.error(f"Failed to set tool policy: {e}")
        return {"status": "error", "error": str(e)}


@router.delete("/policy/tool/{tool_name}")
async def delete_tool_policy(tool_name: str):
    """Remove policy override for a specific tool."""
    try:
        import yaml
        path = _get_policy_path()
        
        if not path.exists():
            return {"status": "error", "error": "Policy file not found"}
        
        with open(path, 'r') as f:
            policy = yaml.safe_load(f) or {}
        
        if "tools" in policy and tool_name in policy["tools"]:
            del policy["tools"][tool_name]
            
            with open(path, 'w') as f:
                yaml.dump(policy, f, default_flow_style=False)
            
            return {"status": "ok", "tool": tool_name, "deleted": True}
        
        return {"status": "ok", "tool": tool_name, "deleted": False}
    except Exception as e:
        logger.error(f"Failed to delete tool policy: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/guardrails/status")
async def get_guardrails_status():
    """Get current guardrails status."""
    try:
        enforcer = get_guardrail_enforcer()
        return {
            "status": "ok",
            "safe_mode_active": enforcer.is_safe_mode_active(),
            "config": enforcer.config
        }
    except Exception as e:
        logger.error(f"Failed to get guardrails status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/guardrails/safe-mode/enter")
async def enter_safe_mode(reason: str = "Manual activation"):
    """Enter safe mode (pause autonomous operations)."""
    try:
        enforcer = get_guardrail_enforcer()
        enforcer.enter_safe_mode(reason)
        return {"status": "ok", "safe_mode_active": True, "reason": reason}
    except Exception as e:
        logger.error(f"Failed to enter safe mode: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/guardrails/safe-mode/exit")
async def exit_safe_mode():
    """Exit safe mode (resume autonomous operations)."""
    try:
        enforcer = get_guardrail_enforcer()
        enforcer.exit_safe_mode("dashboard_user")
        return {"status": "ok", "safe_mode_active": False}
    except Exception as e:
        logger.error(f"Failed to exit safe mode: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton anomaly detector
_anomaly_detector = None

def get_anomaly_detector():
    """Get or create singleton anomaly detector."""
    global _anomaly_detector
    if _anomaly_detector is None:
        from ...autonomy import AnomalyDetector
        import yaml
        try:
            with open("config/autonomy.yml", "r") as f:
                config = yaml.safe_load(f) or {}
            anomaly_config = config.get("anomalies", {
                "cpu_spike_threshold": 90,
                "memory_leak_mb": 500,
                "repeated_failures": 3,
                "error_rate_threshold": 0.5
            })
        except Exception:
            anomaly_config = {
                "cpu_spike_threshold": 90,
                "memory_leak_mb": 500,
                "repeated_failures": 3,
                "error_rate_threshold": 0.5
            }
        _anomaly_detector = AnomalyDetector(anomaly_config)
    return _anomaly_detector


@router.get("/anomaly/status")
async def get_anomaly_status():
    """Get anomaly detection status and recent anomalies."""
    try:
        detector = get_anomaly_detector()
        summary = detector.get_summary()
        recent = detector.get_recent_anomalies(hours=24)
        
        return {
            "status": "ok",
            "summary": summary,
            "recent_anomalies": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description,
                    "metrics": a.metrics
                }
                for a in recent
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get anomaly status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/anomaly/check")
async def run_anomaly_check():
    """Run anomaly detection checks now."""
    try:
        detector = get_anomaly_detector()
        
        results = {
            "cpu_spike": detector.check_cpu_spike(),
            "error_rate_high": detector.check_error_rate()
        }
        
        # Get updated summary
        summary = detector.get_summary()
        
        return {
            "status": "ok",
            "checks": results,
            "anomalies_detected": any(results.values()),
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Failed to run anomaly check: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Playbooks API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton recovery executor
_recovery_executor = None

def get_recovery_executor():
    """Get or create singleton recovery executor."""
    global _recovery_executor
    if _recovery_executor is None:
        from ...autonomy import RecoveryExecutor
        import yaml
        try:
            with open("config/autonomy.yml", "r") as f:
                config = yaml.safe_load(f) or {}
            recovery_config = config.get("recovery", {
                "rollback": {"enabled": True, "max_rollback_depth": 5},
                "restart_service": {"enabled": True, "max_restart_attempts": 3},
                "alert_user": {"enabled": True, "throttle_minutes": 30}
            })
        except Exception:
            recovery_config = {
                "rollback": {"enabled": True, "max_rollback_depth": 5},
                "restart_service": {"enabled": True, "max_restart_attempts": 3},
                "alert_user": {"enabled": True, "throttle_minutes": 30}
            }
        _recovery_executor = RecoveryExecutor(recovery_config)
    return _recovery_executor


@router.get("/recovery/status")
async def get_recovery_status():
    """Get recovery playbook status and history."""
    try:
        executor = get_recovery_executor()
        summary = executor.get_summary()
        
        return {
            "status": "ok",
            "summary": summary,
            "config": executor.config
        }
    except Exception as e:
        logger.error(f"Failed to get recovery status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/rollback")
async def execute_rollback(request: Request):
    """Execute rollback for a config file."""
    try:
        data = await request.json()
        file_path = data.get("file_path")
        
        if not file_path:
            return {"status": "error", "error": "file_path required"}
        
        executor = get_recovery_executor()
        result = executor.execute_rollback(file_path)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message,
            "details": result.details
        }
    except Exception as e:
        logger.error(f"Failed to execute rollback: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/restart-service")
async def execute_restart_service(request: Request):
    """Execute service restart recovery."""
    try:
        data = await request.json()
        service_name = data.get("service")
        
        if not service_name:
            return {"status": "error", "error": "service required"}
        
        executor = get_recovery_executor()
        result = executor.execute_restart_service(service_name)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message,
            "details": result.details
        }
    except Exception as e:
        logger.error(f"Failed to execute service restart: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/alert")
async def execute_alert(request: Request):
    """Send recovery alert to user."""
    try:
        data = await request.json()
        message = data.get("message", "Recovery alert")
        severity = data.get("severity", "warning")
        
        executor = get_recovery_executor()
        result = executor.execute_alert_user(message, severity)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message
        }
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Dry-Run Simulation API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton simulator
_dry_run_simulator = None

def get_dry_run_simulator():
    """Get or create singleton dry-run simulator."""
    global _dry_run_simulator
    if _dry_run_simulator is None:
        from ...approval.simulator import DryRunSimulator
        _dry_run_simulator = DryRunSimulator()
    return _dry_run_simulator


@router.post("/simulate/file-write")
async def simulate_file_write(request: Request):
    """Simulate a file write operation (dry-run preview)."""
    try:
        data = await request.json()
        path = data.get("path")
        new_content = data.get("content", "")
        current_content = data.get("current_content")
        
        if not path:
            return {"status": "error", "error": "path required"}
        
        # Try to read current content if not provided
        if current_content is None:
            from pathlib import Path
            file_path = Path(path)
            if file_path.exists():
                try:
                    current_content = file_path.read_text()
                except Exception:
                    current_content = None
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_file_write(path, new_content, current_content)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "affected_files": result.affected_files,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate file write: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/command")
async def simulate_command(request: Request):
    """Simulate a command execution (dry-run preview)."""
    try:
        data = await request.json()
        command = data.get("command")
        dry_run_flag = data.get("dry_run_flag")
        
        if not command:
            return {"status": "error", "error": "command required"}
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_command(command, dry_run_flag)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate command: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/service-restart")
async def simulate_service_restart(request: Request):
    """Simulate a service restart (dry-run preview)."""
    try:
        data = await request.json()
        service = data.get("service")
        
        if not service:
            return {"status": "error", "error": "service required"}
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_service_restart(service)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "affected_services": result.affected_services,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate service restart: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/tool")
async def simulate_tool_call(request: Request):
    """
    Simulate any tool call based on tool name and arguments.
    Routes to appropriate simulation based on tool type.
    """
    try:
        data = await request.json()
        tool_name = data.get("tool")
        tool_args = data.get("args", {})
        
        if not tool_name:
            return {"status": "error", "error": "tool required"}
        
        simulator = get_dry_run_simulator()
        
        # Route to appropriate simulation based on tool
        if tool_name == "write_config":
            path = tool_args.get("path", "")
            content = tool_args.get("content", "")
            result = simulator.simulate_file_write(path, content)
        elif tool_name == "run_command":
            command = tool_args.get("command", "")
            result = simulator.simulate_command(command)
        elif tool_name == "restart_service":
            service = tool_args.get("service", "")
            result = simulator.simulate_service_restart(service)
        elif tool_name == "update_packages":
            packages = tool_args.get("packages", [])
            pm = tool_args.get("package_manager", "apt")
            result = simulator.simulate_package_update(packages, pm)
        elif tool_name == "fan_control":
            current = tool_args.get("current_rpm", 2000)
            target = tool_args.get("target_rpm", 3000)
            hwmon = tool_args.get("hwmon_path", "/sys/class/hwmon/hwmon0/pwm1")
            result = simulator.simulate_fan_throttle(current, target, hwmon)
        else:
            # Generic simulation for unknown tools
            return {
                "status": "ok",
                "simulation": {
                    "success": True,
                    "action": f"Execute tool: {tool_name}",
                    "changes": [{"type": "tool_call", "tool": tool_name, "args": tool_args}],
                    "warnings": [f"No specific simulation for '{tool_name}' - showing args only"],
                    "commands_to_run": [f"{tool_name}({tool_args})"],
                    "estimated_duration_s": 1.0,
                    "reversible": False
                }
            }
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "before": result.before,
                "after": result.after,
                "changes": result.changes,
                "affected_files": result.affected_files,
                "affected_services": result.affected_services,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate tool call: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 23: Scheduler API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and job list."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {
                "status": "ok",
                "scheduler": {
                    "running": False,
                    "reason": "Scheduler not initialized"
                }
            }
        
        status = _scheduler_executor.get_status()
        jobs = _scheduler_executor.get_scheduled_jobs()
        
        return {
            "status": "ok",
            "scheduler": status,
            "jobs": jobs
        }
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/scheduler/jobs")
async def list_scheduler_jobs():
    """List all scheduled jobs."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {"status": "ok", "jobs": []}
        
        jobs = _scheduler_executor.get_scheduled_jobs()
        return {"status": "ok", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return {"status": "error", "error": str(e), "jobs": []}


@router.post("/scheduler/jobs/{job_id}/cancel")
async def cancel_scheduler_job(job_id: str):
    """Cancel a scheduled job."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {"status": "error", "error": "Scheduler not running"}
        
        success = _scheduler_executor.cancel_job(job_id)
        return {"status": "ok" if success else "error", "cancelled": success}
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Testing Endpoints (Development Only)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/approvals/test/create")
async def create_test_approval(
    task: str = "Test Action",
    action: str = "This is a test approval request for development",
    risk_level: str = "medium"
):
    """
    Create a test approval request for development/testing.
    
    This helps verify the approval flow works end-to-end.
    """
    try:
        import uuid
        from datetime import datetime, timezone
        from ...approval.engine import ApprovalRequest
        
        engine = get_approval_engine()
        
        request = ApprovalRequest(
            id=f"test_{uuid.uuid4().hex[:8]}",
            task=task,
            action=action,
            reasoning="Created via test endpoint for development purposes",
            confidence=0.7,  # Below auto-execute threshold
            risk_level=risk_level,
            system_state={"source": "test_endpoint"},
            affected_resources=["test"],
            requested_at=datetime.now(timezone.utc).isoformat() + 'Z',
            requested_by="test_endpoint"
        )
        
        engine.queue_request(request)
        
        return {
            "status": "ok",
            "message": "Test approval created",
            "request_id": request.id,
            "note": "Check the Approvals page to see it"
        }
    except Exception as e:
        logger.error(f"Failed to create test approval: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Being Configuration (Phase 6 / T6a.2)
# ─────────────────────────────────────────────────────────────────────────────

class BeingConfigUpdate(BaseModel):
    voice: Optional[str] = None
    proactivity: Optional[str] = None
    purpose: Optional[str] = None
    quiet_hours: Optional[Dict[str, str]] = None
    morning_report: Optional[Dict[str, Any]] = None
    category_overrides: Optional[Dict[str, str]] = None


@router.get("/being")
async def get_being_config() -> Dict[str, Any]:
    """Get current being configuration."""
    try:
        from ...config.being_config import load_being_config
        cfg = load_being_config()
        return {"status": "ok", "config": cfg.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to load being config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/being")
async def update_being_config(update: BeingConfigUpdate) -> Dict[str, Any]:
    """Update being configuration. Validates and persists to being.yml."""
    try:
        from ...config.being_config import load_being_config, save_being_config
        cfg = load_being_config()

        # Apply partial updates (only non-None fields)
        if update.voice is not None:
            cfg.voice = update.voice
        if update.proactivity is not None:
            cfg.proactivity = update.proactivity
        if update.purpose is not None:
            cfg.purpose = update.purpose
        if update.quiet_hours is not None:
            cfg.quiet_hours = update.quiet_hours
        if update.morning_report is not None:
            cfg.morning_report = update.morning_report
        if update.category_overrides is not None:
            cfg.category_overrides = update.category_overrides

        # Validate + save
        save_being_config(cfg)

        return {"status": "ok", "config": cfg.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to save being config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
