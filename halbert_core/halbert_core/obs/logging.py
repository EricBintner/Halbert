from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Include common structured fields if provided via LoggerAdapter/extra
        for key in ("request_id", "agent", "node", "tool", "duration_ms", "error_code", "host", "tags"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)

def get_logger(name: str = "halbert") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger
