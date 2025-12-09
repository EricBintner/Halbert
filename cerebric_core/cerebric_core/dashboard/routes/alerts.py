"""
Alerts API routes.

Provides endpoints for alert management.
"""

from __future__ import annotations
import logging
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

from ...alerts.engine import get_alert_engine

logger = logging.getLogger('cerebric.dashboard.routes.alerts')

router = APIRouter() if FASTAPI_AVAILABLE else None


if FASTAPI_AVAILABLE:
    
    @router.get("/")
    async def get_alerts(active_only: bool = True, limit: int = 50):
        """Get alerts."""
        engine = get_alert_engine()
        
        if active_only:
            alerts = engine.get_active_alerts()
        else:
            alerts = engine.get_alert_history(limit)
        
        return {
            "alerts": [a.to_dict() for a in alerts],
            "active_count": len(engine.active_alerts),
        }
    
    
    @router.get("/stats")
    async def get_alert_stats():
        """Get alert statistics."""
        engine = get_alert_engine()
        
        active = engine.get_active_alerts()
        by_severity = {}
        for alert in active:
            sev = alert.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        return {
            "active_count": len(active),
            "by_severity": by_severity,
            "rules_count": len(engine.rules),
            "history_count": len(engine.alert_history),
        }
    
    
    @router.post("/check")
    async def check_alerts():
        """Manually trigger alert check."""
        engine = get_alert_engine()
        new_alerts = engine.check_rules()
        
        return {
            "checked": len(engine.rules),
            "new_alerts": [a.to_dict() for a in new_alerts],
        }
    
    
    @router.post("/{alert_id}/acknowledge")
    async def acknowledge_alert(alert_id: str):
        """Acknowledge an alert."""
        engine = get_alert_engine()
        
        if alert_id not in engine.active_alerts:
            raise HTTPException(404, "Alert not found")
        
        engine.acknowledge_alert(alert_id)
        return {"acknowledged": True}
    
    
    @router.post("/{alert_id}/resolve")
    async def resolve_alert(alert_id: str):
        """Manually resolve an alert."""
        engine = get_alert_engine()
        
        if alert_id not in engine.active_alerts:
            raise HTTPException(404, "Alert not found")
        
        engine.resolve_alert(alert_id)
        return {"resolved": True}
    
    
    @router.get("/rules")
    async def get_rules():
        """Get all alert rules."""
        engine = get_alert_engine()
        
        rules = []
        for rule in engine.rules.values():
            rules.append({
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity.value,
                "enabled": rule.enabled,
                "cooldown_seconds": rule.cooldown_seconds,
            })
        
        return {"rules": rules}
