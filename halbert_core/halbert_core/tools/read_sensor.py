from __future__ import annotations
import os
from typing import Any, Dict
from .base import BaseTool, ToolRequest, ToolResponse

class ReadSensor(BaseTool):
    name = "read_sensor"
    side_effects = False

    def execute(self, req: ToolRequest) -> ToolResponse:
        metric = req.inputs.get("metric", "temp")
        path = req.inputs.get("sensor_path")
        if not path or not os.path.exists(path):
            return ToolResponse(request_id=req.request_id, ok=False, error="sensor_path not found", outputs={})
        try:
            with open(path, "r") as f:
                raw = f.read().strip()
            # hwmon temps are often millidegrees C
            try:
                val = float(raw)
                if metric == "temp" and val > 1000:
                    val = val / 1000.0
            except ValueError:
                val = raw
            return ToolResponse(request_id=req.request_id, ok=True, outputs={"value": val, "metric": metric})
        except Exception as e:
            return ToolResponse(request_id=req.request_id, ok=False, error=str(e), outputs={})
