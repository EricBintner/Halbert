"""
LLMLingua-2 token-pruning compressor for Halbert.

Uses microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank to
intelligently remove redundant tokens while preserving semantic meaning.

Ported from LinuxBrain Phase 72, adapted with sysadmin FORCE_TOKENS.

Dependencies: llmlingua, huggingface-hub
Model is lazy-loaded on first compress() call — never blocks startup.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from halbert_core.compression.compressor import CompressResult, ContextCompressor

logger = logging.getLogger("halbert.compression.lingua")


class LinguaCompressor(ContextCompressor):
    """LLMLingua-2 token-pruning compressor for natural-language content.

    Wraps ``llmlingua.PromptCompressor`` with the BERT-base multilingual
    model (178 MB).  The model is lazy-loaded on first ``compress()`` call
    so it never blocks server startup.

    Falls back to noop (returns input unchanged) on any error.
    """

    HF_MODEL_ID = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"

    # Compression-rate presets  (rate = fraction of tokens *kept*)
    LEVEL_RATES = {
        "light": 0.6,
        "standard": 0.4,
        "aggressive": 0.25,
    }

    # Tokens that must never be removed during compression.
    # Adapted for sysadmin/config content (LinuxBrain uses prose-oriented tokens).
    FORCE_TOKENS = [
        # Sentence structure
        "\n", ".", "?", "!",
        # Dialogue markers
        '"', "'",
        # Narrative markers
        "—", "...",
        # Clause separation
        ",",
        # Names and identity markers (preserve proper nouns)
        ":",
        # Sysadmin tokens (NEW for Halbert — preserve config/shell syntax)
        "/",    # file paths
        "=",    # config assignments
        "|",    # pipes
        ">",    # redirects
        "<",    # redirects
        "$",    # variables
        "`",    # inline code
        "#",    # comments, shebangs
    ]

    def __init__(self, *, model_id: Optional[str] = None) -> None:
        self._model_id = model_id or self.HF_MODEL_ID
        self._compressor: Any = None  # lazy llmlingua.PromptCompressor
        self._available: Optional[bool] = None

    def _ensure_loaded(self) -> Any:
        """Lazy-load the LLMLingua-2 model on first use."""
        if self._compressor is not None:
            return self._compressor
        try:
            from llmlingua import PromptCompressor  # type: ignore[import-untyped]

            self._compressor = PromptCompressor(
                model_name=self._model_id,
                use_llmlingua2=True,
                device_map="cpu",
            )
            self._available = True
            logger.info("LinguaCompressor loaded model: %s", self._model_id)
        except Exception as exc:
            logger.warning("LinguaCompressor failed to load: %s", exc)
            self._available = False
            self._compressor = None
        return self._compressor

    def compress(
        self,
        text: str,
        *,
        query: str = "",
        budget_chars: int = 0,
        level: str = "standard",
        timeout_s: float = 30.0,
    ) -> CompressResult:
        input_chars = len(text)
        if input_chars == 0:
            return CompressResult(compressed="", input_chars=0, output_chars=0)

        comp = self._ensure_loaded()
        if comp is None:
            # Fallback: return text unchanged
            return CompressResult(
                compressed=text,
                input_chars=input_chars,
                output_chars=input_chars,
                error="LLMLingua-2 model not available",
            )

        rate = self.LEVEL_RATES.get(level, self.LEVEL_RATES["standard"])

        t0 = time.perf_counter()
        try:
            result = comp.compress_prompt(
                [text],
                rate=rate,
                force_tokens=self.FORCE_TOKENS,
                drop_consecutive=True,
            )
            compressed = result.get("compressed_prompt", text)
            output_chars = len(compressed)
            timing_ms = (time.perf_counter() - t0) * 1000
            ratio = input_chars / output_chars if output_chars > 0 else 1.0
            return CompressResult(
                compressed=compressed,
                input_chars=input_chars,
                output_chars=output_chars,
                compression_ratio=round(ratio, 2),
                timing_ms=round(timing_ms, 1),
            )
        except Exception as exc:
            timing_ms = (time.perf_counter() - t0) * 1000
            logger.warning("LinguaCompressor.compress failed: %s", exc)
            return CompressResult(
                compressed=text,
                input_chars=input_chars,
                output_chars=input_chars,
                timing_ms=round(timing_ms, 1),
                error=str(exc),
            )

    def is_available(self) -> bool:
        """Check if llmlingua is installed."""
        if self._available is not None:
            return self._available
        try:
            import llmlingua  # type: ignore[import-untyped]  # noqa: F401
            return True
        except ImportError:
            return False

    def download_model(self) -> str:
        """Pre-download the LLMLingua-2 model from HuggingFace.

        Returns the path to the cached model directory.
        """
        from huggingface_hub import snapshot_download  # type: ignore[import-untyped]

        model_path = snapshot_download(
            repo_id=self._model_id,
            allow_patterns=["*.json", "*.bin", "*.safetensors", "*.txt"],
        )
        return model_path

    def is_downloaded(self) -> bool:
        """Check if model files are already cached locally."""
        try:
            from huggingface_hub import try_to_load_from_cache  # type: ignore[import-untyped]
            cached = try_to_load_from_cache(self._model_id, "config.json")
            return isinstance(cached, str)
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        loaded = self._compressor is not None
        return {
            "available": self.is_available(),
            "model": self._model_id,
            "loaded": loaded,
            "downloaded": self.is_downloaded(),
            "type": "lingua",
        }
