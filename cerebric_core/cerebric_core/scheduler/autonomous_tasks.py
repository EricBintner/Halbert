"""
Autonomous task implementations with LLM-driven decision making.

Phase 3 M3: LLM-powered autonomous maintenance routines.

Example autonomous tasks:
- System health check
- Log analysis and cleanup
- Package update check
- Resource optimization
"""

from __future__ import annotations
import logging
import json
import subprocess
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger('cerebric.scheduler.autonomous_tasks')


@dataclass
class TaskDecision:
    """
    LLM decision for an autonomous task.
    
    Follows Phase 3 autonomous prompt format.
    """
    step: int
    action: str
    confidence: float
    reasoning: str
    requires_approval: bool
    approval_reason: Optional[str] = None
    risk_level: str = 'medium'  # low, medium, high


class AutonomousTask:
    """
    Base class for autonomous tasks with LLM integration.
    
    Subclass this to create specific autonomous tasks.
    """
    
    def __init__(
        self,
        model_manager=None,
        prompt_manager=None,
        memory_retrieval=None,
        memory_writer=None,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize autonomous task.
        
        Args:
            model_manager: ModelManager instance for LLM
            prompt_manager: PromptManager for prompts
            memory_retrieval: MemoryRetrieval for context
            memory_writer: MemoryWriter for outcomes
            confidence_threshold: Minimum confidence for autonomous execution
        """
        self.model_manager = model_manager
        self.prompt_manager = prompt_manager
        self.memory_retrieval = memory_retrieval
        self.memory_writer = memory_writer
        self.confidence_threshold = confidence_threshold
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the autonomous task.
        
        Args:
            context: Task-specific context
        
        Returns:
            Result dict with success status and details
        """
        raise NotImplementedError("Subclass must implement execute()")
    
    def _make_decision(
        self,
        task_description: str,
        current_state: Dict[str, Any],
        step: int = 1
    ) -> TaskDecision:
        """
        Use LLM to make an autonomous decision.
        
        Args:
            task_description: What we're trying to accomplish
            current_state: Current system state
            step: Step number in multi-step task
        
        Returns:
            TaskDecision with LLM's recommendation
        """
        if not self.model_manager or not self.prompt_manager:
            # Fallback: No LLM available
            return TaskDecision(
                step=step,
                action="Skip (no LLM available)",
                confidence=0.0,
                reasoning="LLM not configured",
                requires_approval=True,
                approval_reason="Cannot make autonomous decisions without LLM"
            )
        
        # Build context from memory
        memory_context = ""
        if self.memory_retrieval:
            try:
                relevant_memories = self.memory_retrieval.retrieve_from(
                    'core', task_description, k=3
                )
                if relevant_memories:
                    memory_context = "\n\nRELEVANT KNOWLEDGE:\n"
                    for mem in relevant_memories:
                        memory_context += f"- {mem.get('text', '')}\n"
            except Exception as e:
                logger.warning(f"Failed to retrieve memory context: {e}")
        
        # Build prompt
        from ..model.prompt_manager import PromptMode
        
        system_prompt = self.prompt_manager.build_prompt(
            mode=PromptMode.AUTONOMOUS,
            task_context=f"""
TASK: {task_description}

CURRENT STATE:
{json.dumps(current_state, indent=2)}
{memory_context}

STEP: {step}

Analyze the current state and recommend the next action.
Output ONLY a JSON object matching this format (no other text):
{{
  "step": {step},
  "action": "<specific action to take>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>",
  "requires_approval": <true|false>,
  "approval_reason": "<reason if true, otherwise null>",
  "risk_level": "<low|medium|high>"
}}
"""
        )
        
        try:
            # Generate decision
            response = self.model_manager.generate(
                prompt=system_prompt,
                max_tokens=512,
                temperature=0.3  # Low temperature for consistent decisions
            )
            
            # Parse JSON response
            # Try to extract JSON from response (LLM might add extra text)
            response_cleaned = response.strip()
            
            # Find JSON block
            if '{' in response_cleaned and '}' in response_cleaned:
                json_start = response_cleaned.find('{')
                json_end = response_cleaned.rfind('}') + 1
                json_str = response_cleaned[json_start:json_end]
                decision_data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
            
            # Create TaskDecision
            decision = TaskDecision(
                step=decision_data.get('step', step),
                action=decision_data.get('action', 'Unknown'),
                confidence=float(decision_data.get('confidence', 0.0)),
                reasoning=decision_data.get('reasoning', 'No reasoning provided'),
                requires_approval=decision_data.get('requires_approval', True),
                approval_reason=decision_data.get('approval_reason'),
                risk_level=decision_data.get('risk_level', 'medium')
            )
            
            # Enforce confidence threshold
            if decision.confidence < self.confidence_threshold:
                decision.requires_approval = True
                decision.approval_reason = (
                    f"Confidence {decision.confidence:.2f} below threshold "
                    f"{self.confidence_threshold:.2f}"
                )
            
            # Enforce risk-based approval
            if decision.risk_level == 'high':
                decision.requires_approval = True
                if not decision.approval_reason:
                    decision.approval_reason = "High-risk operation requires approval"
            
            logger.info(
                f"LLM decision: action='{decision.action}', "
                f"confidence={decision.confidence:.2f}, "
                f"approval={decision.requires_approval}"
            )
            
            return decision
        
        except Exception as e:
            logger.error(f"Failed to get LLM decision: {e}")
            # Fallback: Conservative decision
            return TaskDecision(
                step=step,
                action="Skip (LLM error)",
                confidence=0.0,
                reasoning=f"LLM failed: {str(e)}",
                requires_approval=True,
                approval_reason="Cannot proceed without valid LLM decision"
            )


class SystemHealthCheckTask(AutonomousTask):
    """
    Autonomous system health check task.
    
    Checks CPU, memory, disk, and recommends actions if needed.
    """
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute health check.
        
        Args:
            context: Optional context (unused for health check)
        
        Returns:
            Health check results
        """
        logger.info("Starting autonomous system health check")
        
        # Gather system state
        current_state = self._gather_system_state()
        
        # Ask LLM for decision
        decision = self._make_decision(
            task_description="Perform system health check and recommend maintenance actions",
            current_state=current_state,
            step=1
        )
        
        # Log decision
        if self.memory_writer:
            try:
                self.memory_writer.write_action_outcome({
                    'task': 'system_health_check',
                    'decision': decision.__dict__,
                    'state': current_state,
                    'ts': self._get_timestamp()
                })
            except Exception as e:
                logger.warning(f"Failed to log decision: {e}")
        
        return {
            'success': True,
            'decision': decision.__dict__,
            'state': current_state,
            'requires_approval': decision.requires_approval
        }
    
    def _gather_system_state(self) -> Dict[str, Any]:
        """Gather current system state."""
        import psutil
        
        state = {}
        
        try:
            # CPU
            state['cpu_percent'] = psutil.cpu_percent(interval=1)
            state['cpu_temp'] = self._get_cpu_temp()
            
            # Memory
            mem = psutil.virtual_memory()
            state['memory_percent'] = mem.percent
            state['memory_available_gb'] = mem.available / (1024**3)
            
            # Disk
            disk = psutil.disk_usage('/')
            state['disk_percent'] = disk.percent
            state['disk_free_gb'] = disk.free / (1024**3)
            
            # Load average
            state['load_avg'] = psutil.getloadavg()
        
        except Exception as e:
            logger.error(f"Failed to gather system state: {e}")
            state['error'] = str(e)
        
        return state
    
    def _get_cpu_temp(self) -> Optional[float]:
        """Get CPU temperature if available."""
        try:
            import psutil
            temps = psutil.sensors_temperatures()
            
            # Try common sensor names
            for name in ['coretemp', 'k10temp', 'cpu_thermal']:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            
            return None
        
        except Exception:
            return None
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat() + 'Z'


class LogCleanupTask(AutonomousTask):
    """
    Autonomous log cleanup task.
    
    Analyzes log disk usage and recommends cleanup actions.
    """
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute log cleanup analysis.
        
        Args:
            context: Optional context (e.g., max_age_days)
        
        Returns:
            Cleanup recommendations
        """
        logger.info("Starting autonomous log cleanup analysis")
        
        # Analyze log directories
        log_analysis = self._analyze_logs()
        
        # Ask LLM for decision
        decision = self._make_decision(
            task_description="Analyze log disk usage and recommend cleanup actions",
            current_state=log_analysis,
            step=1
        )
        
        # Log decision
        if self.memory_writer:
            try:
                self.memory_writer.write_action_outcome({
                    'task': 'log_cleanup',
                    'decision': decision.__dict__,
                    'analysis': log_analysis,
                    'ts': self._get_timestamp()
                })
            except Exception as e:
                logger.warning(f"Failed to log decision: {e}")
        
        return {
            'success': True,
            'decision': decision.__dict__,
            'analysis': log_analysis,
            'requires_approval': decision.requires_approval
        }
    
    def _analyze_logs(self) -> Dict[str, Any]:
        """Analyze log directory sizes."""
        import os
        
        log_dirs = [
            '/var/log',
            '/var/log/journal',
            '/var/log/nginx',
            '/var/log/apache2'
        ]
        
        analysis = {'directories': []}
        
        for log_dir in log_dirs:
            if not os.path.exists(log_dir):
                continue
            
            try:
                # Get directory size
                total_size = 0
                file_count = 0
                
                for dirpath, dirnames, filenames in os.walk(log_dir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                            file_count += 1
                        except (OSError, FileNotFoundError):
                            pass
                
                analysis['directories'].append({
                    'path': log_dir,
                    'size_gb': total_size / (1024**3),
                    'file_count': file_count
                })
            
            except Exception as e:
                logger.warning(f"Failed to analyze {log_dir}: {e}")
        
        return analysis
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat() + 'Z'


# Factory function for creating tasks
def create_autonomous_task(
    task_type: str,
    model_manager=None,
    prompt_manager=None,
    memory_retrieval=None,
    memory_writer=None,
    confidence_threshold: float = 0.7,
    approval_engine=None
) -> AutonomousTask:
    """
    Create an autonomous task instance.
    
    Args:
        task_type: Type of task ('health_check', 'log_cleanup')
        model_manager: ModelManager instance
        prompt_manager: PromptManager instance
        memory_retrieval: MemoryRetrieval instance
        memory_writer: MemoryWriter instance
        confidence_threshold: Minimum confidence for autonomous execution
    
    Returns:
        AutonomousTask instance
    
    Raises:
        ValueError: If task_type is unknown
    """
    tasks = {
        'health_check': SystemHealthCheckTask,
        'log_cleanup': LogCleanupTask
    }
    
    task_class = tasks.get(task_type)
    if not task_class:
        raise ValueError(f"Unknown task type: {task_type}")
    
    return task_class(
        model_manager=model_manager,
        prompt_manager=prompt_manager,
        memory_retrieval=memory_retrieval,
        memory_writer=memory_writer,
        confidence_threshold=confidence_threshold,
        approval_engine=approval_engine
    )
