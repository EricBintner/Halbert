"""
CLaRa Provider for Halbert.

Provides context compression using Apple's CLaRa model.
Supports both local execution (14GB+ VRAM) and remote CLaRa-Remembers-It-All server.

Usage:
    provider = get_clara_provider()
    
    if provider.config.enabled:
        result = provider.compress_memories(
            memories=["User asked about systemd", "Halbert explained unit files"],
            query="What did we discuss about systemd?"
        )

Remote Setup:
    See https://github.com/EricBintner/CLaRa-Remembers-It-All
"""

import logging
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger('halbert.model.clara')

# Config persistence paths
CLARA_CACHE_DIR = Path.home() / '.cache' / 'halbert' / 'clara'
CLARA_CONFIG_PATH = Path.home() / '.local' / 'share' / 'halbert' / 'clara_config.json'


@dataclass
class ClaraConfig:
    """CLaRa configuration."""
    # Phase 58: Disabled by default - requires 14GB VRAM or remote server
    # Auto-enabled for users with 48GB+ VRAM via tier detection
    enabled: bool = False
    model_name: str = "apple/CLaRa-7B-Instruct"
    model_subfolder: str = "compression-16"  # compression-16 or compression-128
    # NOTE: 4-bit quantization not available for CLaRa yet - always uses FP16 (~14GB)
    use_4bit: bool = False
    auto_compress_threshold: int = 3  # Compress when > N memories
    # Remote mode: use CLaRa-Remembers-It-All server instead of local model
    use_remote: bool = False
    remote_url: str = ""  # e.g., "http://192.168.1.100:8765"
    remote_api_key: str = ""  # Optional API key for remote server
    
    @classmethod
    def load(cls) -> 'ClaraConfig':
        """Load config from disk."""
        if CLARA_CONFIG_PATH.exists():
            try:
                with open(CLARA_CONFIG_PATH) as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception as e:
                logger.warning(f"Failed to load CLaRa config: {e}")
        return cls()
    
    def save(self):
        """Save config to disk."""
        CLARA_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CLARA_CONFIG_PATH, 'w') as f:
            json.dump(asdict(self), f, indent=2)


class ClaraProvider:
    """
    CLaRa context compression provider.
    
    Supports two modes:
    - Remote: Uses CLaRa-Remembers-It-All HTTP server (recommended)
    - Local: Loads model directly (requires 14GB+ VRAM)
    
    The app works with or without CLaRa enabled.
    """
    
    def __init__(self):
        """Initialize CLaRa provider."""
        self.config = ClaraConfig.load()
        self._model = None
        self._initialized = False
        self._load_time = 0.0
        self._last_error: Optional[str] = None
        
        # Create cache dir
        CLARA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    @property
    def dependencies_installed(self) -> bool:
        """Check if CLaRa dependencies are installed."""
        try:
            import transformers
            import accelerate
            # Note: bitsandbytes not needed - 4-bit not available for CLaRa
            return True
        except ImportError:
            return False
    
    @property
    def is_available(self) -> bool:
        """Check if CLaRa can be used (either remote or local initialized)."""
        if self.config.use_remote and self.config.remote_url:
            return True
        return self.dependencies_installed and self._initialized
    
    @property
    def cache_path(self) -> Path:
        """Path to cached quantized model."""
        quant_suffix = "_4bit" if self.config.use_4bit else "_fp16"
        safe_name = self.config.model_name.replace('/', '_')
        subfolder = self.config.model_subfolder.replace('/', '_')
        return CLARA_CACHE_DIR / f"{safe_name}_{subfolder}{quant_suffix}"
    
    @property
    def model_cached(self) -> bool:
        """Check if model is already cached."""
        return self.cache_path.exists()
    
    def check_vram(self) -> Dict[str, Any]:
        """Check if enough VRAM is available."""
        try:
            import torch
            if not torch.cuda.is_available():
                # Check for MPS (Apple Silicon)
                if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    return {
                        'cuda_available': False,
                        'mps_available': True,
                        'can_run': True,  # MPS uses unified memory
                    }
                return {
                    'cuda_available': False,
                    'error': 'No GPU available (CUDA or MPS)',
                    'can_run': False,
                }
            
            # Get VRAM info
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            free = total - allocated
            
            # CLaRa requires ~14GB VRAM (4-bit quantization not available)
            required = 14.0
            
            return {
                'cuda_available': True,
                'total_gb': round(total, 1),
                'allocated_gb': round(allocated, 1),
                'free_gb': round(free, 1),
                'required_gb': required,
                'can_run': free >= required,
            }
        except Exception as e:
            return {
                'cuda_available': False,
                'error': str(e),
                'can_run': False,
            }
    
    def install_dependencies(self) -> Dict[str, Any]:
        """Install CLaRa dependencies."""
        import subprocess
        import sys
        
        packages = ['transformers', 'accelerate', 'peft']
        if self.config.use_4bit:
            packages.append('bitsandbytes')
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install'] + packages,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return {'success': True, 'message': 'Dependencies installed'}
            else:
                return {'success': False, 'error': result.stderr}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def initialize(self, force_reload: bool = False) -> bool:
        """
        Initialize/load the CLaRa model locally.
        
        First load: Downloads and quantizes (~30 seconds)
        Subsequent loads: Instant from cache
        
        Returns:
            True if successful
        """
        if self._initialized and not force_reload:
            return True
        
        if not self.dependencies_installed:
            self._last_error = "Dependencies not installed"
            return False
        
        # Check VRAM
        vram = self.check_vram()
        if not vram.get('can_run') and not vram.get('mps_available'):
            self._last_error = f"Insufficient VRAM: {vram.get('free_gb', 0):.1f}GB free, need {vram.get('required_gb', 14)}GB"
            logger.warning(self._last_error)
        
        start = time.time()
        
        try:
            import torch
            from transformers import AutoModel
            
            # Check for cached model
            if self.model_cached and not force_reload:
                logger.info(f"Loading cached CLaRa from {self.cache_path}")
                device_map = {"": 0} if torch.cuda.is_available() else "auto"
                self._model = AutoModel.from_pretrained(
                    str(self.cache_path),
                    trust_remote_code=True,
                    device_map=device_map,
                )
                self._initialized = True
                self._load_time = time.time() - start
                self._last_error = None
                logger.info(f"CLaRa loaded from cache in {self._load_time:.1f}s")
                return True
            
            # Download and cache model
            from huggingface_hub import snapshot_download
            
            logger.info("Downloading CLaRa model from HuggingFace...")
            local_dir = snapshot_download(
                repo_id=self.config.model_name,
                local_dir=str(CLARA_CACHE_DIR / "hf_download"),
            )
            
            model_path = f"{local_dir}/{self.config.model_subfolder}"
            logger.info(f"Loading from {model_path}")
            
            self._model = AutoModel.from_pretrained(
                model_path,
                trust_remote_code=True,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True,
            )
            
            # Cache for future loads
            logger.info(f"Caching model to {self.cache_path}")
            self._model.save_pretrained(str(self.cache_path))
            
            self._initialized = True
            self._load_time = time.time() - start
            self._last_error = None
            logger.info(f"CLaRa initialized in {self._load_time:.1f}s")
            return True
            
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Failed to initialize CLaRa")
            return False
    
    def unload(self):
        """Unload the model to free VRAM."""
        if self._model is not None:
            del self._model
            self._model = None
            self._initialized = False
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass
            
            logger.info("CLaRa model unloaded")
    
    def _compress_remote(
        self,
        memories: List[str],
        query: str,
        max_new_tokens: int = 128,
    ) -> Dict[str, Any]:
        """Compress memories using remote CLaRa-Remembers-It-All server."""
        import requests
        
        url = self.config.remote_url.rstrip('/')
        headers = {'Content-Type': 'application/json'}
        
        if self.config.remote_api_key:
            headers['Authorization'] = f'Bearer {self.config.remote_api_key}'
        
        try:
            start = time.time()
            response = requests.post(
                f"{url}/compress",
                json={
                    'memories': memories,
                    'query': query,
                    'max_new_tokens': max_new_tokens,
                },
                headers=headers,
                timeout=60,
            )
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                data['remote'] = True
                data['remote_url'] = url
                data['latency_ms'] = round(latency)
                return data
            else:
                return {
                    'success': False,
                    'error': f"Server returned {response.status_code}: {response.text}",
                    'answer': None,
                }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': f"Cannot connect to CLaRa server at {url}",
                'answer': None,
            }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': "Request timed out",
                'answer': None,
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Remote compression failed: {str(e)}",
                'answer': None,
            }
    
    def check_remote_health(self) -> Dict[str, Any]:
        """Check if remote CLaRa server is healthy."""
        import requests
        
        if not self.config.remote_url:
            return {'healthy': False, 'error': 'No remote URL configured'}
        
        url = self.config.remote_url.rstrip('/')
        try:
            response = requests.get(f"{url}/health", timeout=5)
            if response.status_code == 200:
                return {'healthy': True, 'url': url, **response.json()}
            else:
                return {'healthy': False, 'error': f"Status {response.status_code}"}
        except requests.exceptions.ConnectionError:
            return {'healthy': False, 'error': f"Cannot connect to {url}"}
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
    
    def compress_memories(
        self,
        memories: List[str],
        query: str,
        max_new_tokens: int = 128,
    ) -> Dict[str, Any]:
        """
        Compress memories and generate contextual answer.
        
        Uses remote server if configured, otherwise local model.
        
        Args:
            memories: List of memory strings to compress
            query: User query to answer from memories
            max_new_tokens: Max tokens to generate
        
        Returns:
            Dict with 'answer', 'original_tokens', 'compressed_tokens', 'success'
        """
        if not self.config.enabled:
            return {
                'success': False,
                'error': 'CLaRa is disabled',
                'answer': None,
            }
        
        # Use remote if configured
        if self.config.use_remote and self.config.remote_url:
            logger.info(f"Using remote CLaRa: {self.config.remote_url}")
            return self._compress_remote(memories, query, max_new_tokens)
        
        # Local mode
        if not self._initialized:
            if not self.initialize():
                return {
                    'success': False,
                    'error': self._last_error or 'Failed to initialize',
                    'answer': None,
                }
        
        try:
            import torch
            
            documents = [memories]  # CLaRa expects [[doc1, doc2, ...]]
            questions = [query]
            
            with torch.no_grad():
                output = self._model.generate_from_text(
                    questions=questions,
                    documents=documents,
                    max_new_tokens=max_new_tokens,
                )
            
            # Estimate token savings
            original_tokens = sum(len(m.split()) * 1.3 for m in memories)
            compressed_tokens = original_tokens / 16
            
            return {
                'success': True,
                'answer': output[0] if output else None,
                'original_tokens': int(original_tokens),
                'compressed_tokens': int(compressed_tokens),
                'compression_ratio': 16.0,
                'remote': False,
            }
            
        except Exception as e:
            logger.exception("Compression failed")
            return {
                'success': False,
                'error': str(e),
                'answer': None,
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status."""
        vram = self.check_vram()
        
        remote_health = None
        if self.config.use_remote and self.config.remote_url:
            remote_health = self.check_remote_health()
        
        return {
            'enabled': self.config.enabled,
            'initialized': self._initialized,
            'dependencies_installed': self.dependencies_installed,
            'model': self.config.model_name,
            'quantization': '4-bit' if self.config.use_4bit else 'fp16',
            'vram_required_gb': 4.0 if self.config.use_4bit else 14.0,
            'model_cached': self.model_cached,
            'cache_path': str(self.cache_path),
            'load_time_seconds': round(self._load_time, 1) if self._load_time else None,
            'last_error': self._last_error,
            'auto_compress_threshold': self.config.auto_compress_threshold,
            'vram': vram,
            'use_remote': self.config.use_remote,
            'remote_url': self.config.remote_url if self.config.use_remote else None,
            'remote_health': remote_health,
        }
    
    def update_config(self, **kwargs) -> Dict[str, Any]:
        """Update configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.config.save()
        return {'success': True, 'config': asdict(self.config)}
    
    def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable CLaRa."""
        self.config.enabled = enabled
        self.config.save()
        
        if not enabled and self._initialized:
            self.unload()
        
        return {
            'enabled': enabled,
            'initialized': self._initialized,
        }


# Singleton instance
_clara_provider: Optional[ClaraProvider] = None


def get_clara_provider() -> ClaraProvider:
    """Get global CLaRa provider instance."""
    global _clara_provider
    if _clara_provider is None:
        _clara_provider = ClaraProvider()
    return _clara_provider


def clara_available() -> bool:
    """Quick check if CLaRa is available and enabled."""
    provider = get_clara_provider()
    return provider.config.enabled and provider.is_available
