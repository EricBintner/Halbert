# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Configuration wizard for model setup (Phase 5 M3).

Interactive wizard that detects hardware, reports the model size budget
that fits it, and writes models.yml around the model the user chooses.
It never recommends or names specific models.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import re
import yaml

from . import llm_config
from .auto_provision import auto_provision_apple_intelligence
from .hardware_detector import (
    HardwareDetector, HardwareCapabilities, HardwareProfile, ModelBudget,
    pick_installed_model,
)
from ..utils.ollama import list_models_raw, DEFAULT_ENDPOINT
from ..obs.logging import get_logger

logger = get_logger("halbert")


def _is_home_variant() -> bool:
    """True when the active instance runs a home automation variant.

    secure_model is a sysadmin-instance slot: an HA variant's LLM reaches
    the house through tool calls that abstract credentials away, so the
    wizard neither provisions nor writes the slot for home. The
    import is lazy so the model layer carries no module-level dependency
    on the integrations package.
    """
    try:
        from ..integrations.cognition_wiring import is_home_variant
        return is_home_variant()
    except Exception:
        return False


class ConfigWizard:
    """
    Interactive configuration wizard for model setup.
    
    Phase 5 M3: User-friendly setup
    
    Usage:
        wizard = ConfigWizard()
        config = wizard.run_interactive()
        wizard.save_config(config)
    """
    
    def __init__(self):
        """Initialize configuration wizard."""
        self.detector = HardwareDetector()
        logger.info("ConfigWizard initialized")
    
    def detect_hardware(self) -> HardwareCapabilities:
        """
        Detect hardware capabilities.
        
        Returns:
            Hardware capabilities
        """
        return self.detector.detect()
    
    def get_budget(self, hardware: HardwareCapabilities) -> ModelBudget:
        """
        Get the model size budget for detected hardware.
        
        Args:
            hardware: Hardware capabilities
        
        Returns:
            Model size budget (parameter counts, never model names)
        """
        return self.detector.recommend_budget(hardware)
    
    def find_installed_model(
        self,
        budget: ModelBudget,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> Optional[str]:
        """
        Pick the largest model already installed on the endpoint that fits.
        
        Returns:
            Model name, or None when nothing installed fits (or Ollama is down).
        """
        chosen = pick_installed_model(list_models_raw(endpoint), budget)
        return chosen["name"] if chosen else None
    
    def run_auto(
        self,
        model: Optional[str] = None,
        endpoint: str = DEFAULT_ENDPOINT,
        peer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run automatic configuration (non-interactive).

        Detects hardware and writes a configuration around ``model``. When no
        model is given, the largest already-installed model that fits the
        budget is used; if none fits, the guide model is left unset and must
        be chosen in Settings -> AI Models.

        Offload-only devices (SBC_LOW_POWER, <4GB RAM) run no local model at
        all: the installed-model lookup is skipped and the configuration
        carries the compute peer ``peer`` instead — a compute peer is
        required for LLM functionality on these devices.

        Args:
            model: Model name as served by the endpoint (optional)
            endpoint: Ollama endpoint used to look up installed models
            peer: Compute peer address (hostname:port, or a peer:// URL)
                for offload-only devices

        Returns:
            Configuration dictionary
        """
        logger.info("Running automatic configuration")

        # Normalise the --peer value to the peer:// URL form up front
        peer = self._resolve_peer(peer)

        # Detect hardware
        hardware = self.detect_hardware()
        logger.info(f"Detected profile: {hardware.profile.value}")

        # Apple Intelligence: provision secure_model (and chat_model on
        # 16-24GB Macs) before looking at Ollama. On 16-24GB Macs the
        # single-model rule means chat_model is already set and the Ollama
        # model lookup below is skipped. Apple Intelligence provisioning
        # for secure_model is gated by the secure_model capability —
        # the variant preset sets defaults (home = no secure_model), but
        # being.yml can override.
        if hardware.apple_intelligence_available:
            _has_secure_cap = False
            try:
                from ..capabilities import has_capability, CAP_SECURE_MODEL
                _has_secure_cap = has_capability(CAP_SECURE_MODEL)
            except Exception:
                pass
            if not _has_secure_cap:
                logger.info(
                    "Apple Intelligence provisioning skipped "
                    "(no secure_model capability)"
                )
            else:
                auto_provision_apple_intelligence(hardware)
                logger.info("Apple Intelligence (On-Device) detected — configured as secure model")

        # Size budget
        budget = self.get_budget(hardware)
        logger.info(f"Model budget: {budget.summary}")

        # Offload-only devices (SBC_LOW_POWER, <4GB RAM) run no local
        # model: the budget is zeroed, nothing installed can fit, and
        # the configuration carries a compute peer instead. Template
        # thoughts cover the peer-asleep gap.
        if hardware.profile == HardwareProfile.SBC_LOW_POWER:
            if peer:
                logger.info(f"Offload-only device — compute peer: {peer}")
            else:
                logger.warning(
                    "Offload-only device (SBC_LOW_POWER) with no compute peer — "
                    "pass --peer <hostname:port> so LLM work can be offloaded"
                )
            return self._build_config(
                None, "ollama", budget, hardware, endpoint=endpoint, peer_url=peer,
            )

        # On 16-24GB Macs with Apple Intelligence, chat_model is already
        # assigned — skip the Ollama model lookup.
        chat_already_set = (
            hardware.apple_intelligence_available
            and hardware.unified_memory_gb
            and hardware.unified_memory_gb <= 24
        )
        if chat_already_set and not model:
            logger.info("Chat model already set to Apple Intelligence (single local model rule)")
        else:
            if not model:
                model = self.find_installed_model(budget, endpoint)
            if model:
                logger.info(f"Guide model: {model}")
            else:
                logger.warning("No model configured - choose one in Settings -> AI Models")

        # Build configuration
        config = self._build_config(
            model, "ollama", budget, hardware, endpoint=endpoint, peer_url=peer,
        )

        return config
    
    def run_interactive(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        peer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run interactive configuration wizard.

        Guides user through setup with prompts. Offload-only devices
        (SBC_LOW_POWER, <4GB RAM) are never offered local models — the
        wizard prompts for a compute peer address instead.

        Args:
            endpoint: Ollama endpoint used to look up installed models
            peer: Default compute peer address (from --peer), pre-filled
                in the prompt on offload-only devices

        Returns:
            Configuration dictionary
        """
        # Normalise the --peer default to the peer:// URL form up front
        peer = self._resolve_peer(peer)

        print("=" * 70)
        print("Halbert MODEL CONFIGURATION WIZARD")
        print("=" * 70)
        print()
        
        # Detect hardware
        print("🔍 Detecting hardware...")
        hardware = self.detect_hardware()
        
        # Show hardware info
        print()
        print("Hardware Profile:")
        print(f"  Platform: {hardware.platform_friendly}")
        print(f"  RAM: {hardware.total_ram_gb}GB")
        print(f"  CPUs: {hardware.cpu_count}")
        
        if hardware.is_apple_silicon:
            print(f"  Apple Silicon: Yes ({hardware.unified_memory_gb}GB unified memory)")
        if hardware.metal_gpu:
            print(f"  Metal GPU: {hardware.metal_gpu['gpu_name']} ({hardware.metal_gpu['metal_version']})")
        if hardware.apple_intelligence_available:
            status = "running" if hardware.apple_intelligence_bridge_running else "eligible (bridge not started)"
            print(f"  Apple Intelligence: {status}")
        if hardware.has_nvidia_gpu:
            print(f"  NVIDIA GPU: Yes ({hardware.gpu_memory_gb}GB VRAM)" if hardware.gpu_memory_gb else "  NVIDIA GPU: Yes")

        print(f"  Profile: {hardware.profile.value}")
        print()
        
        # Size budget
        print("Model size budget:")
        budget = self.get_budget(hardware)
        print(f"  {budget.summary}")
        for note in budget.notes:
            print(f"  - {note}")
        print()

        # Apple Intelligence provisioning. Gated by the secure_model
        # capability — the variant preset sets defaults (home = no
        # secure_model), but being.yml can override. chat_model still
        # gets Apple Intelligence on 16-24GB Macs — that is the Mac's
        # own on-device use, written by _build_config).
        if hardware.apple_intelligence_available:
            _has_secure_cap = False
            try:
                from ..capabilities import has_capability, CAP_SECURE_MODEL
                _has_secure_cap = has_capability(CAP_SECURE_MODEL)
            except Exception:
                pass
            if _has_secure_cap:
                auto_provision_apple_intelligence(hardware)
            print("Apple Intelligence (On-Device) detected:")
            if not _has_secure_cap:
                print("  secure_model: left empty (no secure_model capability)")
            else:
                print(f"  secure_model: Apple Intelligence (zero download, ANE-powered)")
            mem = hardware.unified_memory_gb or 0
            if mem and mem <= 24:
                print(f"  chat_model: Apple Intelligence (single local model rule for {mem}GB)")
            else:
                print(f"  chat_model: not set (configure cloud or local model in Settings)")
            print()

        # Offload-only devices (SBC_LOW_POWER, <4GB RAM) run no local
        # model at all: skip the installed-model listing and the
        # guide-model prompt, and point the node at a compute peer.
        peer_url: Optional[str] = None
        model: Optional[str] = None
        if hardware.profile == HardwareProfile.SBC_LOW_POWER:
            print("Local LLM: not supported on this device — offload only.")
            print("  A compute peer (a Halbert node with a GPU or Apple Silicon) is")
            print("  required for LLM functionality; template thoughts cover the gap")
            print("  while the peer is asleep.")
            print()
            peer_url = self._prompt_compute_peer(peer)
        else:
            # Installed models on the endpoint (the user's own, not suggestions)
            installed = list_models_raw(endpoint)
            default_model = None
            if installed:
                print(f"Models installed on {endpoint}:")
                for entry in installed:
                    size_gb = (entry.get("size") or 0) / (1024 ** 3)
                    fits = "fits" if budget.fits_bytes(entry.get("size") or 0) else "too large"
                    print(f"  - {entry.get('name')}  ({size_gb:.1f} GB, {fits})")
                chosen = pick_installed_model(installed, budget)
                default_model = chosen["name"] if chosen else None
            else:
                print("No models found on the endpoint. Pull one that fits the budget with")
                print("  ollama pull <model>")
            print()

            prompt = "Guide model name"
            if default_model:
                prompt += f" [{default_model}]"
            prompt += " (leave blank to choose later in Settings): "
            model = input(prompt).strip() or default_model

        print()
        print("Configuration:")
        print(f"  Guide model: {model or 'not set'}")
        if peer_url:
            print(f"  Compute peer: {peer_url}")
        print(f"  Provider: {'peer (offload)' if peer_url else 'ollama'}")
        print()
        
        # Ask for confirmation
        choice = input("Accept this configuration? [Y/n]: ").strip().lower()
        
        if choice in ('n', 'no'):
            print()
            print("Configuration cancelled. You can manually edit ~/.config/halbert/models.yml")
            return {}
        
        # Build configuration
        config = self._build_config(
            model, "ollama", budget, hardware, endpoint=endpoint, peer_url=peer_url,
        )

        print()
        print("✅ Configuration created!")
        if peer_url:
            print("   Compute peer saved — this device offloads all LLM work to it")
        elif not model:
            print("   No model configured — choose one in Settings → AI Models")

        return config

    def _resolve_peer(self, raw: Optional[str]) -> Optional[str]:
        """Normalise a --peer value to the peer:// URL form.

        A malformed value is logged and dropped (None), never a hard
        error: the wizard still writes a valid config without a peer.
        """
        if not raw:
            return None
        url, error = self._normalise_peer_url(raw)
        if error:
            logger.warning(f"Ignoring compute peer {raw!r}: {error}")
            return None
        return url

    def _prompt_compute_peer(self, default: Optional[str] = None) -> Optional[str]:
        """Prompt for a compute peer address, with an optional reachability test.

        Accepts hostname:port (LAN IP, mDNS name, or Tailscale name), with
        or without an http(s):// or peer:// scheme; a missing port defaults
        to the fleet's usual 8000. Returns the normalized peer:// URL, or
        None when the user leaves it blank.
        """
        print("Compute peer (another Halbert node that serves LLM requests):")
        prompt = "Compute peer address"
        if default:
            prompt += f" [{default}]"
        prompt += " (hostname:port, port defaults to 8000 — leave blank to configure later): "

        url: Optional[str] = None
        while url is None:
            raw = input(prompt).strip() or (default or "")
            if not raw:
                print("No compute peer configured — rerun the wizard with --peer <hostname:port>")
                print()
                return None
            url, error = self._normalise_peer_url(raw)
            if error:
                print(f"  {error}")

        print()
        choice = input(f"Test {url} now? [Y/n]: ").strip().lower()
        if choice not in ('n', 'no'):
            ok, detail = self._test_compute_peer(url)
            if ok:
                print(f"  Peer reachable ({detail}).")
            else:
                print(f"  Could not reach the peer: {detail}")
                print("  The address is still saved — check the peer and retest later.")
        print()
        return url

    @staticmethod
    def _normalise_peer_url(raw: str) -> Tuple[Optional[str], Optional[str]]:
        """Normalise a user-entered peer address to the models.yml peer:// form.

        Returns:
            (peer_url, None) on success, or (None, reason) when the address
            cannot be parsed.
        """
        value = raw.strip().rstrip("/")
        for prefix in ("peer://", "http://", "https://"):
            if value.lower().startswith(prefix):
                value = value[len(prefix):]
                break
        value = value.split("/", 1)[0]   # compute endpoints are host:port only
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?::(\d{1,5}))?$", value)
        if not match:
            return None, f"'{raw}' is not a hostname:port address"
        host = match.group(1)
        port = match.group(2) or "8000"
        if not 1 <= int(port) <= 65535:
            return None, f"port {port} in '{raw}' is out of range"
        return f"peer://{host}:{port}", None

    @staticmethod
    def _test_compute_peer(url: str) -> Tuple[bool, str]:
        """Best-effort reachability test of a compute peer's health route.

        Returns:
            (reachable, detail) — detail says why not on failure. The test
            never raises: an unreachable peer is an ordinary outcome, the
            address is saved either way.
        """
        import requests

        from ..federation.compute_endpoint import COMPUTE_HEALTH_PATH

        http_url = url.replace("peer://", "http://", 1) + COMPUTE_HEALTH_PATH
        try:
            resp = requests.get(http_url, timeout=1.5)
            if resp.status_code == 200:
                return True, "health route answered"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)
    
    def _build_config(
        self,
        model: Optional[str],
        provider: str,
        budget: ModelBudget,
        hardware: HardwareCapabilities,
        endpoint: str = DEFAULT_ENDPOINT,
        peer_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build configuration dictionary using the llm_config schema.

        Args:
            model: Chat model name (None leaves the slot unset)
            provider: Runtime serving the model
            budget: Model size budget
            hardware: Hardware capabilities
            endpoint: Endpoint URL for the local Ollama
            peer_url: Compute peer endpoint to save (peer://host:port),
                as prompted on offload-only devices. The endpoint is
                saved for the Compute Peer settings surface to assign;
                on an offload-only device no local model exists, so the
                slots stay unset here.

        Returns:
            Configuration dictionary
        """
        ep_id = "ep_local_ollama" if model else ""

        # Apple Intelligence: when the host is eligible, include the
        # apple-foundation endpoint and set secure_model (and chat_model
        # on 16-24GB Macs per the single local model rule). This must be
        # in _build_config because save_config writes ALL slots via
        # deep-merge — an empty secure_model here would clobber what
        # auto_provision_apple_intelligence wrote to the store.
        #
        # Home automation variants never configure secure_model (their LLM
        # reaches the house through tool calls that abstract credentials
        # away), so the slot is written empty for them — and it must be
        # written, not omitted: the deep-merge would otherwise keep a
        # stale assignment from an earlier sysadmin-style run.
        ai_available = hardware.apple_intelligence_available
        ai_ep_id = "ep_apple_foundation" if ai_available else ""
        ai_model = llm_config.APPLE_FOUNDATION_MODEL if ai_available else ""
        mem = hardware.unified_memory_gb or 0
        ai_takes_chat = ai_available and mem and mem <= 24
        _has_secure_cap = False
        try:
            from ..capabilities import has_capability, CAP_SECURE_MODEL
            _has_secure_cap = has_capability(CAP_SECURE_MODEL)
        except Exception:
            pass
        secure_allowed = _has_secure_cap
        secure_model = ai_model if secure_allowed else ""
        secure_ep_id = ai_ep_id if secure_allowed else ""

        # On 16-24GB Macs with Apple Intelligence, chat_model is set to
        # Apple Intelligence and the Ollama model is not used.
        if ai_takes_chat:
            chat_ep_id = ai_ep_id
            chat_model = ai_model
        else:
            chat_ep_id = ep_id
            chat_model = model or ""

        endpoints = []
        if model and not ai_takes_chat:
            endpoints.append({
                "id": "ep_local_ollama",
                "name": "Local Ollama",
                "provider": provider,
                "url": endpoint,
                "api_key": "",
            })
        if ai_available:
            endpoints.append({
                "id": "ep_apple_foundation",
                "name": "Apple Intelligence (On-Device)",
                "provider": llm_config.APPLE_FOUNDATION_PROVIDER,
                "url": llm_config.APPLE_FOUNDATION_URL,
                "api_key": "",
            })
        if peer_url:
            # Offload target for devices that run no local model. The
            # peer:// scheme is the models.yml shape the peer provider
            # resolves to http:// for the actual call.
            endpoints.append({
                "id": "ep_compute_peer",
                "name": "Compute Peer",
                "provider": "peer",
                "url": peer_url,
                "api_key": "",
            })

        config = {
            "# Halbert Model Configuration": None,
            "# Generated by configuration wizard": None,
            "# Edit this file to customize model selection": None,

            "llm_config": {
                "saved_endpoints": endpoints,
                "chat_model": {
                    "enabled": bool(chat_model),
                    "endpoint_id": chat_ep_id,
                    "model": chat_model,
                },
                "specialist_model": {
                    "enabled": False,
                    "endpoint_id": "",
                    "model": "",
                },
                "vision_model": {
                    "enabled": False,
                    "endpoint_id": "",
                    "model": "",
                },
                "secure_model": {
                    "enabled": bool(secure_model),
                    "endpoint_id": secure_ep_id,
                    "model": secure_model,
                },
            },

            "routing": {
                "strategy": "auto",
                "prefer_specialist_for": [
                    "code_generation",
                    "code_analysis",
                ],
            },

            "handoff": {
                "strategy": "summarized",
                "max_context_tokens": 4096,
                "include_rag": True,
            },

            "# Hardware Profile": None,
            "hardware": {
                "profile": hardware.profile.value,
                "total_ram_gb": hardware.total_ram_gb,
                "platform": hardware.platform,
                "is_apple_silicon": hardware.is_apple_silicon,
                "apple_intelligence_available": hardware.apple_intelligence_available,
                "model_budget": budget.to_dict(),
            },
        }

        return config
    
    def save_config(self, config: Dict[str, Any]) -> Optional[Path]:
        """
        Save configuration through the models.yml store.

        Args:
            config: Configuration dictionary from :meth:`run_auto` /
                :meth:`run_interactive`

        Returns:
            Path the store wrote to, or None when there was nothing to save

        Dumping the whole file in place is what let a rerun of the wizard
        delete every key the store owns but the wizard does not build —
        compression settings, a workspace declaration, saved API keys — and
        leave a file that may hold those keys world-readable. Going through
        the store merges instead, and keeps the backup, atomic rename and
        0600 mode with it.
        """
        if not config:
            logger.warning("Empty configuration, not saving")
            return None

        clean_config = {k: v for k, v in config.items() if not k.startswith('#')}
        llm = dict(clean_config.pop("llm_config", None) or {})

        # Only the store can mint an endpoint id, and a slot naming an id the
        # store never saved is disabled on the next read — so the wizard's own
        # placeholder ids are translated here, not persisted.
        saved_ids = {
            str(ep.get("id") or ""): llm_config.ensure_endpoint(
                ep.get("url") or "",
                ep.get("provider") or "ollama",
                ep.get("name") or "",
            )
            for ep in (llm.pop("saved_endpoints", None) or [])
            if isinstance(ep, dict) and ep.get("url")
        }

        slots: Dict[str, Any] = {}
        for slot in llm_config.SLOTS:
            chosen = llm.get(slot)
            if not isinstance(chosen, dict):
                continue
            endpoint_id = saved_ids.get(str(chosen.get("endpoint_id") or ""), "")
            model = str(chosen.get("model") or "")
            slots[slot] = {
                "enabled": bool(model and endpoint_id),
                "endpoint_id": endpoint_id,
                "model": model,
            }
        llm_config.update(slots)

        for key, value in clean_config.items():
            llm_config.set_top_level(key, value)

        config_path = llm_config.global_config_path()
        logger.info(f"Configuration saved to: {config_path}")

        return config_path

    def validate_config(self, config_path: Optional[Path] = None) -> bool:
        """
        Validate existing configuration.
        
        Args:
            config_path: Path to config file
        
        Returns:
            True if valid, False otherwise

        With no path it validates the file the store actually reads, so
        ``$HALBERT_MODELS_CONFIG`` is not reported as a missing config.
        """
        if config_path is None:
            config_path = llm_config.global_config_path()
        if config_path is None:
            logger.warning("No configuration file found")
            return False

        config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return False
        
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Check required keys
            required = ["llm_config", "routing", "handoff"]
            for key in required:
                if key not in config:
                    logger.error(f"Missing required key: {key}")
                    return False

            # Check llm_config has the three slots
            llm = config["llm_config"]
            for slot in ("chat_model", "specialist_model", "vision_model", "secure_model"):
                if slot not in llm:
                    logger.error(f"llm_config missing '{slot}' slot")
                    return False

            logger.info("Configuration validated successfully")
            return True
        
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False
    
    def generate_summary(
        self,
        hardware: HardwareCapabilities,
        budget: ModelBudget,
        model: Optional[str] = None,
    ) -> str:
        """
        Generate human-readable configuration summary.
        
        Args:
            hardware: Hardware capabilities
            budget: Model size budget
            model: Configured guide model, if any
        
        Returns:
            Summary string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("Halbert MODEL CONFIGURATION SUMMARY")
        lines.append("=" * 70)
        lines.append("")
        
        lines.append("Hardware:")
        lines.append(f"  Platform: {hardware.platform_friendly}")
        lines.append(f"  RAM: {hardware.total_ram_gb}GB")
        lines.append(f"  Profile: {hardware.profile.value}")
        
        if hardware.is_apple_silicon:
            lines.append(f"  Apple Silicon: {hardware.unified_memory_gb}GB unified memory")
        
        lines.append("")
        lines.append("Model size budget:")
        lines.append(f"  {budget.summary}")
        for note in budget.notes:
            lines.append(f"  • {note}")
        
        lines.append("")
        lines.append("Configuration:")
        lines.append(f"  Guide model: {model or 'not set (choose one in Settings -> AI Models)'}")
        lines.append(f"    Provider: ollama")
        lines.append(f"    Always loaded: Yes")
        lines.append(f"  Specialist: Disabled")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
