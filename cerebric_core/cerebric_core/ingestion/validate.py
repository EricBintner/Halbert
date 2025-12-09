from __future__ import annotations
from typing import Any, Dict, Optional

try:
    from jsonschema import Draft202012Validator  # type: ignore
except Exception:  # pragma: no cover
    Draft202012Validator = None  # type: ignore

import json


class TelemetryValidator:
    def __init__(self, schema_path: Optional[str] = None) -> None:
        self.validator = None
        if schema_path and Draft202012Validator is not None:
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                self.validator = Draft202012Validator(schema)
            except Exception:
                self.validator = None

    def validate(self, event: Dict[str, Any]) -> bool:
        if self.validator is None:
            return True
        try:
            self.validator.validate(event)
            return True
        except Exception:
            return False
