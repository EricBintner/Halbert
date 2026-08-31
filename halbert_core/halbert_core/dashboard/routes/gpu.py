# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
GPU API Routes

Provides endpoints for GPU hardware detection and driver information.
Phase 14: GPU Driver Assistant

The detection functions live in tools/gpu_tools.py (shared with the agent's
GPU tools); these routes only wrap them in HTTP. Deep analysis (POST
/api/gpu/analyze) is deprecated as a raw Ollama call — it now dispatches a
structured diagnostic prompt through the agent's send-message path
(specialist tier, host scope), so personality, intake, retrieval, and
thread persistence all apply. The endpoint stays answerable for backward
compatibility with older clients.
"""

import logging
import uuid
from contextlib import aclosing
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

from ...tools.gpu_tools import (
    get_deep_system_context,
    get_gpu_architecture,
    get_gpu_info,
    run_command,
    set_gpu_role,
)

logger = logging.getLogger("halbert.gpu")
router = APIRouter(prefix="/gpu", tags=["gpu"])


# ─────────────────────────────────────────────────────────────────────────────
# GPU Analysis Cache (persisted to YAML, valid for 7 days)
# ─────────────────────────────────────────────────────────────────────────────

def _get_analysis_cache_path():
    """Get path to GPU analysis cache file."""
    try:
        from ...utils.platform import get_config_dir
        return get_config_dir() / 'gpu_analysis_cache.yml'
    except Exception:
        return None


def save_gpu_analysis(analysis: Dict[str, Any]) -> bool:
    """Save GPU analysis to cache."""
    try:
        import yaml
        cache_path = _get_analysis_cache_path()
        if not cache_path:
            return False

        cache_path.parent.mkdir(parents=True, exist_ok=True)

        cache_data = {
            'analysis': analysis,
            'scanned_at': datetime.now().isoformat(),
            'version': 1,
        }

        with open(cache_path, 'w') as f:
            yaml.dump(cache_data, f, default_flow_style=False, sort_keys=False)

        logger.info(f"GPU analysis cached to {cache_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to cache GPU analysis: {e}")
        return False


def load_gpu_analysis() -> Optional[Dict[str, Any]]:
    """Load cached GPU analysis if available."""
    try:
        import yaml
        cache_path = _get_analysis_cache_path()
        if not cache_path or not cache_path.exists():
            return None

        with open(cache_path, 'r') as f:
            cache_data = yaml.safe_load(f) or {}

        if 'analysis' not in cache_data or 'scanned_at' not in cache_data:
            return None

        return cache_data
    except Exception as e:
        logger.warning(f"Failed to load GPU analysis cache: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Deep analysis via the agent path
# ─────────────────────────────────────────────────────────────────────────────

def _build_diagnostic_prompt(gpu_info: Dict[str, Any], system_context: Dict[str, Any]) -> str:
    """Build the structured diagnostic prompt for the agent specialist.

    The NVIDIA driver/CUDA compatibility tables that used to be hardcoded
    here moved to the knowledge base (data/knowledge/linux/
    nvidia_cuda_compatibility.md) — the specialist retrieves them through
    the host scope instead of reading them out of the prompt.
    """
    import json

    primary_gpu = gpu_info["gpus"][0]
    primary_gpu["architecture"] = get_gpu_architecture(primary_gpu["model"])

    # Determine GPU role description
    gpu_role = primary_gpu.get('role', 'auto')
    role_desc = {
        'auto': 'Auto-detected (assume display if only GPU)',
        'display': 'Display/Desktop GPU (drives monitor, needs compositor compatibility)',
        'compute': 'Compute-only GPU (ML/rendering, no display constraints)',
    }.get(gpu_role, 'Unknown')

    # Multi-GPU context
    multi_gpu_info = ""
    if len(gpu_info["gpus"]) > 1:
        multi_gpu_info = f"\n**Multi-GPU System**: {len(gpu_info['gpus'])} GPUs detected\n"
        for i, g in enumerate(gpu_info["gpus"]):
            multi_gpu_info += f"- GPU {i+1}: {g['model']} (Role: {g.get('role', 'auto')}, PCI: {g['pci_id']})\n"

    return f"""## GPU Analysis Request

Analyze my GPU setup on this system: driver and CUDA compatibility, ML
framework readiness, and whether anything needs attention. Use your GPU
tools (gpu_info, gpu_system_context) to gather live details, retrieve the
NVIDIA driver/CUDA compatibility guidance from your knowledge base, and
use web search for current driver releases if needed.

### Hardware Detected
- **Primary GPU**: {primary_gpu['model']}
- **Vendor**: {primary_gpu['vendor']}
- **Architecture**: {primary_gpu.get('architecture') or 'Unknown'}
- **VRAM**: {primary_gpu.get('vram_mb', 'Unknown')} MB
- **GPU Role**: {role_desc}
- **PCI ID**: {primary_gpu.get('pci_id', 'Unknown')}
{multi_gpu_info}
### Current Driver Setup
- **Driver Type**: {primary_gpu.get('driver_type', 'Unknown')}
- **Driver Version**: {primary_gpu.get('driver_version', 'Not detected')}
- **CUDA Version**: {primary_gpu.get('cuda_version', 'Not installed')}

### System Environment
- **Kernel**: {system_context.get('kernel', 'Unknown')}
- **Distro**: {system_context.get('distro', 'Unknown')} {system_context.get('distro_version', '')}
- **Display Server**: {system_context.get('display_server', 'Unknown')}
- **Secure Boot**: {system_context.get('secure_boot', 'Unknown')}

### Installed NVIDIA Packages
{json.dumps(system_context.get('nvidia_packages', []), indent=2)}

### ML Frameworks
{json.dumps(system_context.get('ml_frameworks', {}), indent=2)}

## Analysis Tasks
1. Is the current driver version optimal for this GPU and kernel? If already on a good version, say so clearly.
2. Consider the GPU role: Display GPUs need GNOME/KDE/Wayland compatibility. Compute GPUs only need CUDA/OpenCL.
3. Are there any compatibility issues between driver, CUDA, and ML frameworks?
4. Only recommend an upgrade if there's a SPECIFIC newer version that provides clear benefits.

Provide:
- An overall health assessment
- Specific recommendations with commands
- Any warnings about the current setup
"""


async def _run_agent_turn(query: str) -> str:
    """Run one agent turn through the send-message path and aggregate the text.

    Mirrors what routes/agent.py's POST /message does — specialist tier,
    host retrieval scope, thread persistence — minus the SSE: the
    deprecated analyze endpoint returns JSON, so the response chunks are
    joined into one analysis string instead of streamed.
    """
    from .agent import _thread_manager, get_agent

    agent = get_agent()

    parts: list = []
    async with aclosing(agent.process(
        query=query,
        session_id=str(uuid.uuid4()),
        thread_manager=_thread_manager(),
        tier_override="specialist",
        retrieval_scope="host",
    )) as stream:
        async for event in stream:
            if event.type == "response_chunk":
                parts.append(event.data.get("content", ""))
    return "".join(parts)


if FASTAPI_AVAILABLE:

    @router.get("/info")
    async def get_gpu_data() -> Dict[str, Any]:
        """Get GPU hardware and driver information."""
        try:
            return get_gpu_info()
        except Exception as e:
            logger.error(f"Failed to get GPU info: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.get("/nvidia-smi")
    async def get_nvidia_smi() -> Dict[str, Any]:
        """Get raw nvidia-smi output (if available)."""
        output = run_command(["nvidia-smi"])
        if output:
            return {"available": True, "output": output}
        return {"available": False, "output": None}


    @router.put("/role/{pci_id}")
    async def update_gpu_role(pci_id: str, role: str) -> Dict[str, Any]:
        """
        Set the role for a specific GPU.

        Roles:
        - 'auto': Let the system auto-detect (default)
        - 'display': This GPU drives the desktop/display output
        - 'compute': This GPU is used only for compute (ML, rendering, etc.)

        This affects driver recommendations since display GPUs have different
        constraints (compositor compatibility, Wayland support, etc.).
        """
        if role not in ('auto', 'display', 'compute'):
            raise HTTPException(status_code=400, detail=f"Invalid role '{role}'. Must be 'auto', 'display', or 'compute'.")

        # Normalize PCI ID format (replace URL-safe chars)
        pci_id = pci_id.replace('-', ':')

        if set_gpu_role(pci_id, role):
            logger.info(f"Set GPU {pci_id} role to '{role}'")
            return {"success": True, "pci_id": pci_id, "role": role}
        else:
            raise HTTPException(status_code=500, detail="Failed to save GPU role")


    @router.get("/deep-context")
    async def get_deep_context() -> Dict[str, Any]:
        """
        Get deep system context for GPU analysis.

        Gathers kernel, distro, packages, ML frameworks, etc.
        """
        try:
            gpu_info = get_gpu_info()
            system_context = get_deep_system_context()

            # Add architecture info to GPUs
            for gpu in gpu_info["gpus"]:
                gpu["architecture"] = get_gpu_architecture(gpu["model"])

            return {
                "gpu": gpu_info,
                "system": system_context,
            }
        except Exception as e:
            logger.error(f"Failed to get deep context: {e}")
            raise HTTPException(status_code=500, detail=str(e))


    @router.get("/analysis-cache")
    async def get_cached_analysis() -> Dict[str, Any]:
        """
        Get cached GPU analysis if available.

        Returns the cached analysis with timestamp and staleness info.
        Cache is considered stale after 7 days.
        """
        from datetime import timedelta

        cached = load_gpu_analysis()

        if not cached:
            return {
                "cached": False,
                "analysis": None,
                "scanned_at": None,
                "is_stale": True,
            }

        # Check staleness (7 days)
        try:
            scanned_at = datetime.fromisoformat(cached['scanned_at'])
            age = datetime.now() - scanned_at
            is_stale = age > timedelta(days=7)
            age_days = age.days
        except Exception:
            is_stale = True
            age_days = None

        return {
            "cached": True,
            "analysis": cached['analysis'],
            "scanned_at": cached['scanned_at'],
            "is_stale": is_stale,
            "age_days": age_days,
        }


    @router.post("/analyze")
    async def analyze_gpu_setup() -> Dict[str, Any]:
        """
        Deep GPU analysis (deprecated raw-Ollama path).

        Kept answerable for backward compatibility, but the diagnosis now
        runs through the agent specialist tier (host scope) instead of a
        raw requests.post to Ollama's /api/chat with a hardcoded system
        prompt. The agent gathers context with its GPU tools, retrieves
        driver/CUDA compatibility from the knowledge base, and returns a
        markdown analysis.
        """
        try:
            # Gather context for the prompt (the agent can re-check live
            # details with its own tools)
            gpu_info = get_gpu_info()
            system_context = get_deep_system_context()

            if not gpu_info["gpus"]:
                return {
                    "analysis": "No GPU detected in this system.",
                    "health_score": 0,
                    "recommendations": ["Install a GPU or check hardware connections."],
                    "driver_info": None,
                }

            prompt = _build_diagnostic_prompt(gpu_info, system_context)

            analysis_text = ""
            agent_error = None
            try:
                analysis_text = await _run_agent_turn(prompt)
            except Exception as e:
                logger.warning(f"Agent GPU analysis failed: {e}")
                agent_error = str(e)

            primary_gpu = gpu_info["gpus"][0]

            if not analysis_text:
                # Agent unavailable (no model configured, backend down) —
                # answer with what local detection found rather than 500ing.
                analysis_text = (
                    f"GPU {primary_gpu['model']} detected with "
                    f"{primary_gpu.get('driver_type') or 'unknown'} driver "
                    f"v{primary_gpu.get('driver_version') or 'unknown'}. "
                    f"Agent analysis unavailable{' — ' + agent_error if agent_error else ''}."
                )

            result = {
                "analysis": analysis_text,
                "delegated": True,
                "driver_status": gpu_info["driver_status"],
                "issues": gpu_info.get("issues", []),
                "raw_context": {
                    "gpu": primary_gpu,
                    "system": system_context,
                },
            }
            save_gpu_analysis(result)
            return result

        except Exception as e:
            logger.error(f"GPU analysis failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))