# Policy Engine

Controls which actions Halbert can perform and under what conditions.

**Code**: `halbert_core/halbert_core/policy/`

---

## Configuration

```yaml
# ~/.config/halbert/policy.yml

defaults:
  dry_run: true
  require_approval: true

rules:
  - tool: read_logs
    action: allow
    require_approval: false
    
  - tool: restart_service
    action: allow
    require_approval: true
    dry_run_first: true
    
  - tool: delete_file
    action: block
```

---

## Rule Structure

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Tool name or `*` for all |
| `action` | enum | `allow`, `block` |
| `require_approval` | bool | User must confirm |
| `dry_run_first` | bool | Preview before execute |
| `conditions` | object | Optional constraints |

---

## Evaluation

```python
from halbert_core.halbert_core.policy.engine import decide

decision = decide(policy, tool_name="restart_service", is_apply=True)

if not decision.allow:
    print(f"Blocked: {decision.reason}")
elif decision.require_approval:
    # Request user confirmation
    pass
```

---

## CLI

```bash
# Show current policy
python Halbert/main.py policy-show

# Evaluate a decision
python Halbert/main.py policy-eval --tool restart_service --inputs inputs.json
```

---

## Related

- [CONFIGURATION.md](../CONFIGURATION.md)
- [architecture/tools.md](tools.md)
