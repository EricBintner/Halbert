# Tools System

Tools are the actions Halbert can perform on the system. All tools follow a consistent interface with dry-run support.

---

## Overview

Tools bridge the LLM's reasoning to system actions. Every tool:

1. Supports dry-run mode (preview without execution)
2. Returns structured results
3. Is subject to policy enforcement

**Code**: `halbert_core/halbert_core/tools/`

---

## Tool Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolResult:
    success: bool
    output: str
    dry_run: bool = True
    error: str | None = None

class BaseTool(ABC):
    name: str
    description: str
    
    @abstractmethod
    def execute(self, inputs: dict, dry_run: bool = True) -> ToolResult:
        """Execute the tool."""
        pass
```

---

## Built-in Tools

### Read Tools (Safe)

| Tool | Purpose |
|------|---------|
| `read_logs` | Query journald logs |
| `query_memory` | Search memory/RAG |
| `read_config` | Read configuration files |
| `system_status` | Get system metrics |

### Write Tools (Require Approval)

| Tool | Purpose |
|------|---------|
| `restart_service` | Restart systemd services |
| `modify_config` | Edit configuration files |
| `schedule_task` | Add scheduled jobs |
| `write_memory` | Store to memory |

---

## Dry-Run Mode

All tools support dry-run by default:

```python
class RestartServiceTool(BaseTool):
    name = "restart_service"
    description = "Restart a systemd service"
    
    def execute(self, inputs: dict, dry_run: bool = True) -> ToolResult:
        service = inputs["service"]
        
        if dry_run:
            # Preview only
            return ToolResult(
                success=True,
                output=f"Would restart: {service}",
                dry_run=True
            )
        
        # Actual execution
        result = subprocess.run(
            ["systemctl", "restart", service],
            capture_output=True
        )
        
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout.decode(),
            dry_run=False,
            error=result.stderr.decode() if result.returncode != 0 else None
        )
```

---

## Policy Integration

Tools are gated by the policy engine:

```yaml
# config/policy.yml
rules:
  - tool: read_logs
    action: allow
    require_approval: false
    
  - tool: restart_service
    action: allow
    require_approval: true
    dry_run_first: true
```

```python
from halbert_core.halbert_core.policy.engine import decide

# Before execution
decision = decide(policy, "restart_service", is_apply=True)

if not decision.allow:
    return ToolResult(success=False, error=decision.reason)

if decision.require_approval:
    approved = request_user_approval()
    if not approved:
        return ToolResult(success=False, error="User rejected")
```

---

## Creating Custom Tools

### 1. Define the Tool

```python
# halbert_core/halbert_core/tools/disk_analyzer.py

from .base import BaseTool, ToolResult

class DiskAnalyzerTool(BaseTool):
    name = "analyze_disk"
    description = "Analyze disk usage and find large files"
    
    def execute(self, inputs: dict, dry_run: bool = True) -> ToolResult:
        path = inputs.get("path", "/")
        threshold_mb = inputs.get("threshold_mb", 100)
        
        if dry_run:
            return ToolResult(
                success=True,
                output=f"Would analyze {path} for files > {threshold_mb}MB",
                dry_run=True
            )
        
        # Run analysis
        large_files = self._find_large_files(path, threshold_mb)
        
        return ToolResult(
            success=True,
            output=f"Found {len(large_files)} files > {threshold_mb}MB",
            dry_run=False
        )
    
    def _find_large_files(self, path: str, threshold_mb: int) -> list:
        # Implementation
        pass
```

### 2. Register the Tool

```python
# halbert_core/halbert_core/tools/__init__.py

from .disk_analyzer import DiskAnalyzerTool

TOOLS = {
    # ... existing tools
    "analyze_disk": DiskAnalyzerTool(),
}
```

### 3. Add Policy Rule

```yaml
# config/policy.yml
rules:
  - tool: analyze_disk
    action: allow
    require_approval: false  # Read-only, safe
```

### 4. Add CLI Command (Optional)

```python
# Halbert/main.py

def cmd_analyze_disk(args):
    tool = TOOLS["analyze_disk"]
    result = tool.execute(
        {"path": args.path, "threshold_mb": args.threshold},
        dry_run=not args.execute
    )
    print(result.output)
```

---

## Tool Execution Flow

```
LLM decides to use tool
         │
         ▼
┌─────────────────┐
│  Policy Check   │  Is this tool allowed?
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Dry-Run First  │  Preview the action
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ Approval (if    │  User confirms
│ required)       │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Execute Live   │  Perform the action
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Log Result     │  Audit trail
└─────────────────┘
```

---

## Tool Catalog

### System Tools

```python
# Read system logs
tool.execute({"unit": "docker.service", "lines": 100})

# Get system status
tool.execute({"include_disk": True, "include_memory": True})
```

### Service Tools

```python
# Restart service
tool.execute({"service": "nginx.service"}, dry_run=False)

# Check service status
tool.execute({"service": "docker.service"})
```

### Configuration Tools

```python
# Read config
tool.execute({"path": "/etc/nginx/nginx.conf"})

# Modify config (requires approval)
tool.execute({
    "path": "/etc/nginx/nginx.conf",
    "changes": [{"line": 10, "old": "worker_processes 1", "new": "worker_processes 4"}]
}, dry_run=False)
```

---

## Error Handling

```python
def execute(self, inputs: dict, dry_run: bool = True) -> ToolResult:
    try:
        # Tool logic
        result = self._do_work(inputs)
        return ToolResult(success=True, output=result)
        
    except PermissionError:
        return ToolResult(
            success=False,
            error="Permission denied. May require elevated privileges."
        )
    except FileNotFoundError as e:
        return ToolResult(
            success=False,
            error=f"File not found: {e.filename}"
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Unexpected error: {str(e)}"
        )
```

---

## Related

- [architecture/runtime-engine.md](runtime-engine.md) - Tool invocation
- [CONFIGURATION.md](../CONFIGURATION.md) - Policy configuration
- [reference/code-map.md](../reference/code-map.md) - File locations
