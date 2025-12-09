"""
GPU API Routes

Provides endpoints for GPU hardware detection and driver information.
Phase 14: GPU Driver Assistant
"""

import logging
import subprocess
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("cerebric.gpu")
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
# GPU Role Configuration (display vs compute)
# ─────────────────────────────────────────────────────────────────────────────

def _get_gpu_config_path():
    """Get path to GPU config file."""
    try:
        from ...utils.platform import get_config_dir
        return get_config_dir() / 'gpu_config.yml'
    except Exception:
        return None


def load_gpu_config() -> Dict[str, Any]:
    """Load GPU configuration (roles, etc.)."""
    try:
        import yaml
        config_path = _get_gpu_config_path()
        if not config_path or not config_path.exists():
            return {'gpu_roles': {}}
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {'gpu_roles': {}}
    except Exception as e:
        logger.warning(f"Failed to load GPU config: {e}")
        return {'gpu_roles': {}}


def save_gpu_config(config: Dict[str, Any]) -> bool:
    """Save GPU configuration."""
    try:
        import yaml
        config_path = _get_gpu_config_path()
        if not config_path:
            return False
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        logger.warning(f"Failed to save GPU config: {e}")
        return False


def get_gpu_role(pci_id: str) -> str:
    """Get role for a specific GPU. Returns 'auto', 'display', or 'compute'."""
    config = load_gpu_config()
    return config.get('gpu_roles', {}).get(pci_id, 'auto')


def set_gpu_role(pci_id: str, role: str) -> bool:
    """Set role for a specific GPU."""
    if role not in ('auto', 'display', 'compute'):
        return False
    
    config = load_gpu_config()
    if 'gpu_roles' not in config:
        config['gpu_roles'] = {}
    
    config['gpu_roles'][pci_id] = role
    return save_gpu_config(config)


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a command and return stdout, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_gpu_info() -> Dict[str, Any]:
    """Detect GPU hardware and driver information."""
    gpus = []
    issues = []
    has_nvidia = False
    has_amd = False
    has_intel = False
    nvidia_smi_available = False
    
    # Use lspci to detect GPUs
    lspci_output = run_command(["lspci", "-nn"])
    if lspci_output:
        for line in lspci_output.split("\n"):
            # VGA compatible controller or 3D controller
            if "VGA" in line or "3D controller" in line or "Display controller" in line:
                # Parse the line
                # Example: "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA106 [GeForce RTX 3060] [10de:2503] (rev a1)"
                pci_match = re.match(r'^([0-9a-f:.]+)\s+(.+?):\s+(.+?)(?:\s+\[([0-9a-f:]+)\])?(?:\s+\(rev.*\))?$', line, re.I)
                if pci_match:
                    pci_id = pci_match.group(1)
                    vendor_model = pci_match.group(3)
                    
                    # Determine vendor
                    vendor = "Unknown"
                    if "nvidia" in vendor_model.lower():
                        vendor = "NVIDIA"
                        has_nvidia = True
                    elif "amd" in vendor_model.lower() or "radeon" in vendor_model.lower():
                        vendor = "AMD"
                        has_amd = True
                    elif "intel" in vendor_model.lower():
                        vendor = "Intel"
                        has_intel = True
                    
                    gpu = {
                        "vendor": vendor,
                        "model": vendor_model,
                        "pci_id": pci_id,
                        "vram_mb": None,
                        "driver_version": None,
                        "driver_type": None,
                        "cuda_version": None,
                        "temperature_c": None,
                        "power_draw_w": None,
                        "power_limit_w": None,
                        "utilization_percent": None,
                        "memory_used_mb": None,
                        "memory_total_mb": None,
                        "role": get_gpu_role(pci_id),  # 'auto', 'display', or 'compute'
                    }
                    gpus.append(gpu)
    
    # Try nvidia-smi for NVIDIA GPUs
    nvidia_smi = run_command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw,power.limit,utilization.gpu", "--format=csv,noheader,nounits"])
    if nvidia_smi:
        nvidia_smi_available = True
        for i, line in enumerate(nvidia_smi.split("\n")):
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 8 and i < len(gpus):
                    # Find the NVIDIA GPU in our list
                    for gpu in gpus:
                        if gpu["vendor"] == "NVIDIA":
                            gpu["driver_version"] = parts[1] if parts[1] != "[N/A]" else None
                            gpu["driver_type"] = "nvidia"
                            try:
                                gpu["memory_total_mb"] = int(float(parts[2]))
                                gpu["vram_mb"] = gpu["memory_total_mb"]
                                gpu["memory_used_mb"] = int(float(parts[3]))
                                gpu["temperature_c"] = int(float(parts[4])) if parts[4] != "[N/A]" else None
                                gpu["power_draw_w"] = float(parts[5]) if parts[5] != "[N/A]" else None
                                gpu["power_limit_w"] = float(parts[6]) if parts[6] != "[N/A]" else None
                                gpu["utilization_percent"] = int(float(parts[7])) if parts[7] != "[N/A]" else None
                            except (ValueError, IndexError):
                                pass
                            break
        
        # Get CUDA version
        cuda_output = run_command(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
        nvcc_output = run_command(["nvcc", "--version"])
        if nvcc_output:
            cuda_match = re.search(r"release (\d+\.\d+)", nvcc_output)
            if cuda_match:
                for gpu in gpus:
                    if gpu["vendor"] == "NVIDIA":
                        gpu["cuda_version"] = cuda_match.group(1)
    
    # Check for nouveau driver
    if has_nvidia and not nvidia_smi_available:
        # Check if nouveau is loaded
        lsmod = run_command(["lsmod"])
        if lsmod and "nouveau" in lsmod:
            for gpu in gpus:
                if gpu["vendor"] == "NVIDIA":
                    gpu["driver_type"] = "nouveau"
                    issues.append("NVIDIA GPU using open-source nouveau driver. Consider installing proprietary drivers for better performance.")
    
    # Check for AMD driver
    if has_amd:
        lsmod = run_command(["lsmod"])
        if lsmod:
            if "amdgpu" in lsmod:
                for gpu in gpus:
                    if gpu["vendor"] == "AMD":
                        gpu["driver_type"] = "amdgpu"
            elif "radeon" in lsmod:
                for gpu in gpus:
                    if gpu["vendor"] == "AMD":
                        gpu["driver_type"] = "radeon"
                        issues.append("AMD GPU using legacy radeon driver. Consider amdgpu for newer GPUs.")
    
    # Check for Intel driver
    if has_intel:
        lsmod = run_command(["lsmod"])
        if lsmod and "i915" in lsmod:
            for gpu in gpus:
                if gpu["vendor"] == "Intel":
                    gpu["driver_type"] = "i915"
    
    # Determine overall driver status
    driver_status = "unknown"
    if len(gpus) == 0:
        driver_status = "missing"
    elif has_nvidia:
        if nvidia_smi_available:
            driver_status = "optimal"
        else:
            driver_status = "missing" if not any(g["driver_type"] for g in gpus if g["vendor"] == "NVIDIA") else "outdated"
    elif has_amd or has_intel:
        driver_status = "optimal" if any(g["driver_type"] for g in gpus) else "missing"
    
    return {
        "gpus": gpus,
        "has_nvidia": has_nvidia,
        "has_amd": has_amd,
        "has_intel": has_intel,
        "nvidia_smi_available": nvidia_smi_available,
        "recommended_driver": None,  # Could be populated with web search
        "driver_status": driver_status,
        "issues": issues,
    }


def get_deep_system_context() -> Dict[str, Any]:
    """
    Gather deep system context for GPU analysis.
    
    Collects: kernel, distro, display server, secure boot, installed packages,
    ML frameworks, container runtimes, etc.
    """
    context = {
        "kernel": None,
        "distro": None,
        "distro_version": None,
        "display_server": None,
        "secure_boot": None,
        "nvidia_packages": [],
        "cuda_paths": [],
        "ml_frameworks": {},
        "container_runtime": None,
    }
    
    # Kernel version
    kernel = run_command(["uname", "-r"])
    if kernel:
        context["kernel"] = kernel
    
    # Distro info
    os_release = run_command(["cat", "/etc/os-release"])
    if os_release:
        for line in os_release.split("\n"):
            if line.startswith("NAME="):
                context["distro"] = line.split("=")[1].strip('"')
            elif line.startswith("VERSION_ID="):
                context["distro_version"] = line.split("=")[1].strip('"')
    
    # Display server (X11 vs Wayland)
    session_type = run_command(["printenv", "XDG_SESSION_TYPE"])
    context["display_server"] = session_type or "unknown"
    
    # Secure Boot status
    mokutil = run_command(["mokutil", "--sb-state"])
    if mokutil:
        context["secure_boot"] = "enabled" if "enabled" in mokutil.lower() else "disabled"
    
    # Installed NVIDIA packages
    dpkg_nvidia = run_command(["dpkg", "-l"])
    if dpkg_nvidia:
        for line in dpkg_nvidia.split("\n"):
            if "nvidia" in line.lower() and line.startswith("ii"):
                parts = line.split()
                if len(parts) >= 3:
                    context["nvidia_packages"].append({
                        "name": parts[1],
                        "version": parts[2],
                    })
    
    # CUDA toolkit paths
    cuda_paths = ["/usr/local/cuda", "/usr/local/cuda-12", "/usr/local/cuda-11"]
    for path in cuda_paths:
        version_file = run_command(["cat", f"{path}/version.txt"])
        if version_file:
            context["cuda_paths"].append({"path": path, "version": version_file.strip()})
    
    # ML Frameworks detection
    # PyTorch
    pytorch_check = run_command(["python3", "-c", "import torch; print(torch.__version__, torch.cuda.is_available())"])
    if pytorch_check:
        parts = pytorch_check.split()
        context["ml_frameworks"]["pytorch"] = {
            "version": parts[0] if parts else "unknown",
            "cuda_available": "True" in pytorch_check,
        }
    
    # TensorFlow
    tf_check = run_command(["python3", "-c", "import tensorflow as tf; print(tf.__version__, len(tf.config.list_physical_devices('GPU')) > 0)"])
    if tf_check:
        parts = tf_check.split()
        context["ml_frameworks"]["tensorflow"] = {
            "version": parts[0] if parts else "unknown",
            "cuda_available": "True" in tf_check,
        }
    
    # Check for nvidia-container-toolkit
    nvidia_docker = run_command(["which", "nvidia-container-toolkit"])
    if nvidia_docker:
        context["container_runtime"] = "nvidia-container-toolkit"
    
    return context


def get_gpu_architecture(model: str) -> Optional[str]:
    """Determine GPU architecture from model name."""
    model_lower = model.lower()
    
    # NVIDIA architectures
    if "rtx 40" in model_lower or "ada" in model_lower:
        return "Ada Lovelace"
    elif "rtx 30" in model_lower or "ampere" in model_lower or "a2000" in model_lower or "a4000" in model_lower or "a5000" in model_lower or "a6000" in model_lower:
        return "Ampere"
    elif "rtx 20" in model_lower or "turing" in model_lower:
        return "Turing"
    elif "gtx 10" in model_lower or "pascal" in model_lower:
        return "Pascal"
    elif "gtx 9" in model_lower or "maxwell" in model_lower:
        return "Maxwell"
    
    # AMD architectures
    elif "rx 7" in model_lower or "rdna 3" in model_lower:
        return "RDNA 3"
    elif "rx 6" in model_lower or "rdna 2" in model_lower:
        return "RDNA 2"
    
    return None


async def search_latest_driver_info(gpu_model: str, vendor: str) -> Dict[str, Any]:
    """
    Use web grounding to find latest driver information.
    """
    try:
        from ..web.search import WebSearch
        
        search = WebSearch()
        
        if vendor == "NVIDIA":
            # Search for latest NVIDIA driver
            query = f"NVIDIA Linux driver latest version {gpu_model} 2024 2025"
            results = await search.search(query, max_results=5)
            
            driver_info = {
                "latest_stable": None,
                "latest_beta": None,
                "cuda_latest": None,
                "sources": [],
                "recommendations": [],
            }
            
            # Parse results for version numbers
            for result in results:
                driver_info["sources"].append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                })
                
                # Look for version patterns in snippets
                version_match = re.search(r"(\d{3}\.\d+(?:\.\d+)?)", result.snippet)
                if version_match:
                    version = version_match.group(1)
                    if not driver_info["latest_stable"]:
                        driver_info["latest_stable"] = version
            
            # Also search for CUDA
            cuda_query = "NVIDIA CUDA toolkit latest version Linux"
            cuda_results = await search.search(cuda_query, max_results=3)
            for result in cuda_results:
                cuda_match = re.search(r"CUDA (\d+\.\d+)", result.snippet)
                if cuda_match and not driver_info["cuda_latest"]:
                    driver_info["cuda_latest"] = cuda_match.group(1)
            
            return driver_info
            
        elif vendor == "AMD":
            query = f"AMD Linux amdgpu driver latest version {gpu_model}"
            results = await search.search(query, max_results=5)
            
            return {
                "sources": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
                "recommendations": [],
            }
        
        return {"sources": [], "recommendations": []}
        
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return {"error": str(e), "sources": []}


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
        Deep GPU analysis with web grounding.
        
        Gathers all context, searches for latest drivers,
        and provides AI-powered recommendations.
        """
        import json
        import requests
        
        try:
            # Gather all context
            gpu_info = get_gpu_info()
            system_context = get_deep_system_context()
            
            if not gpu_info["gpus"]:
                return {
                    "analysis": "No GPU detected in this system.",
                    "health_score": 0,
                    "recommendations": ["Install a GPU or check hardware connections."],
                    "driver_info": None,
                }
            
            # Get the primary GPU
            primary_gpu = gpu_info["gpus"][0]
            primary_gpu["architecture"] = get_gpu_architecture(primary_gpu["model"])
            
            # Search for latest driver info
            driver_search = await search_latest_driver_info(
                primary_gpu["model"], 
                primary_gpu["vendor"]
            )
            
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
                    g_role = g.get('role', 'auto')
                    multi_gpu_info += f"- GPU {i+1}: {g['model']} (Role: {g_role}, PCI: {g['pci_id']})\n"
            
            # Build comprehensive context for LLM
            context = f"""## GPU Analysis Request

### Hardware Detected
- **Primary GPU**: {primary_gpu['model']}
- **Vendor**: {primary_gpu['vendor']}
- **Architecture**: {primary_gpu.get('architecture', 'Unknown')}
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

### Web Search Results (Latest Driver Info)
{json.dumps(driver_search.get('sources', [])[:3], indent=2)}

## Analysis Tasks
1. Is the current driver version optimal for this GPU and kernel? If already on a good version, say so clearly.
2. Consider the GPU role: Display GPUs need GNOME/KDE/Wayland compatibility. Compute GPUs only need CUDA/OpenCL.
3. Are there any compatibility issues between driver, CUDA, and ML frameworks?
4. Only recommend an upgrade if there's a SPECIFIC newer version that provides clear benefits.
5. For multi-GPU systems, consider which GPU handles display vs compute workloads.

Provide:
- Health score (0-100)
- Specific recommendations with commands
- Any warnings about the current setup
"""
            
            # Call LLM for analysis
            try:
                # Get configured endpoint
                from ...utils.platform import get_config_dir
                import yaml
                
                endpoint = "http://localhost:11434"
                model = "llama3.1:8b"
                
                config_path = get_config_dir() / 'models.yml'
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
                    orch = config.get('orchestrator', {})
                    if orch.get('endpoint'):
                        endpoint = orch['endpoint']
                    if orch.get('model'):
                        model = orch['model']
                
                response = requests.post(
                    f"{endpoint}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": """You are a Linux GPU expert. Analyze GPU setups and provide specific, actionable recommendations.

KNOWN NVIDIA DRIVER/CUDA COMPATIBILITY (use this reference):
- Driver 575.x: CUDA 12.8+ (development/beta branch)
- Driver 565.x: CUDA 12.7 (latest production branch as of late 2024)
- Driver 560.x: CUDA 12.6 (stable, widely tested)
- Driver 555.x: CUDA 12.5
- Driver 550.x: CUDA 12.4 (LTS branch, very stable)
- Driver 545.x: CUDA 12.3
- Driver 535.x: CUDA 12.2 (previous LTS)
- Driver 525.x: CUDA 12.0
- Driver 520.x: CUDA 11.8
- Driver 515.x: CUDA 11.7

CUDA COMPATIBILITY RULES (BE CONSISTENT):
- CUDA is COMPATIBLE if installed version works with the driver (check table above)
- A driver ALWAYS supports its matched CUDA version AND all older CUDA versions
- Example: Driver 575.x supports CUDA 12.8, 12.7, 12.6, 12.5, 12.4, 12.3, 12.2, 12.0, 11.8, 11.7, etc.
- If CUDA is installed and driver supports it → compatible=true
- If CUDA version is NEWER than what driver supports → compatible=false (HIGH PRIORITY issue!)
- If CUDA is not installed but ML frameworks need it → recommend installing

IMPORTANT GUIDELINES:
- ALWAYS provide latest_stable_version using the reference above
- ALWAYS explain the tradeoffs in version_analysis
- CUDA incompatibility is a HIGH PRIORITY issue - add to warnings and recommendations
- Consider the GPU role: display GPUs need GNOME/KDE/Wayland compatibility
- For Ampere+ GPUs (RTX 30xx, A-series, RTX 40xx): 550+ drivers recommended

Your response MUST be valid JSON:
{
    "analysis": "2-3 sentence summary of the setup and your recommendation.",
    "health_score": 85,
    "current_status": "optimal|good|needs_attention|critical",
    "driver_assessment": {
        "current_version": "575.57.08",
        "latest_stable_version": "565.57",
        "version_comparison": "newer_than_stable|at_stable|older_than_stable",
        "action_recommended": "none|upgrade|consider_lts_downgrade",
        "version_analysis": "Explain: e.g., 'You are on 575 which is newer than latest stable 565. This is likely a dev/beta branch. No action needed unless you want LTS stability.'",
        "change_risk": "safe|moderate|high"
    },
    "cuda_assessment": {
        "compatible": true,
        "current_version": "12.0",
        "latest_version": "12.7",
        "version_analysis": "Explain CUDA compatibility"
    },
    "known_compatible_combos": [
        {"driver": "565.57", "cuda": "12.7", "note": "Latest production"},
        {"driver": "550.127", "cuda": "12.4", "note": "LTS, very stable"},
        {"driver": "535.183", "cuda": "12.2", "note": "Previous LTS"}
    ],
    "recommendations": [
        {
            "priority": "low",
            "action": "No action needed",
            "reason": "Current setup is working well"
        }
    ],
    "warnings": [],
    "ml_compatibility": {
        "pytorch": "compatible",
        "tensorflow": "compatible"
    }
}

Always include 2-3 known_compatible_combos as reference for users."""
                            },
                            {"role": "user", "content": context}
                        ],
                        "stream": False,
                        "format": "json",
                    },
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "{}")
                
                try:
                    result = json.loads(content)
                    result["web_sources"] = driver_search.get("sources", [])[:3]
                    result["raw_context"] = {
                        "gpu": primary_gpu,
                        "system": system_context,
                    }
                    # Cache the analysis
                    save_gpu_analysis(result)
                    return result
                except json.JSONDecodeError:
                    result = {
                        "analysis": content[:500],
                        "health_score": 50,
                        "recommendations": [],
                        "parse_error": True,
                    }
                    save_gpu_analysis(result)
                    return result
                    
            except Exception as e:
                logger.warning(f"LLM analysis failed: {e}")
                # Fallback analysis
                health = 100 if gpu_info["driver_status"] == "optimal" else 50
                result = {
                    "analysis": f"GPU {primary_gpu['model']} detected with {primary_gpu.get('driver_type', 'unknown')} driver v{primary_gpu.get('driver_version', 'unknown')}.",
                    "health_score": health,
                    "current_status": gpu_info["driver_status"],
                    "recommendations": gpu_info.get("issues", []),
                    "web_sources": driver_search.get("sources", [])[:3],
                    "llm_error": str(e),
                }
                save_gpu_analysis(result)
                return result
                
        except Exception as e:
            logger.error(f"GPU analysis failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
