from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from ..utils.paths import data_subdir


class SpanExporter:
    """
    Phase 2 tracing span exporter.
    Writes spans to a JSONL file for dashboard consumption.
    """
    def __init__(self, output_dir: str | None = None):
        self.output_dir = output_dir or data_subdir("traces")
        os.makedirs(self.output_dir, exist_ok=True)

    def export_span(self, span: Dict[str, Any]) -> None:
        """Export a single span to JSONL."""
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(self.output_dir, f"spans-{day}.jsonl")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(span, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Fail-safe: don't crash on span export errors


_global_exporter: SpanExporter | None = None


def get_exporter() -> SpanExporter:
    """Get or create the global span exporter."""
    global _global_exporter
    if _global_exporter is None:
        _global_exporter = SpanExporter()
    return _global_exporter
