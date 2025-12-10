# Approval System

Human-in-the-loop confirmation for high-risk actions.

**Code**: `halbert_core/halbert_core/approval/`

---

## Flow

```
Action Proposed
      │
      ▼
┌─────────────┐
│ Policy Check│ → Blocked? → Reject
└─────────────┘
      │
      ▼
  Needs Approval?
      │
   Yes│    No
      ▼     ▼
┌─────────┐  Execute
│ Request │
│ Approval│
└─────────┘
      │
   Approved?
      │
   Yes│    No
      ▼     ▼
  Execute  Reject
```

---

## Request Structure

```python
ApprovalRequest(
    id="req-123",
    task="restart_service",
    action="restart docker.service",
    confidence=0.85,
    risk_level="medium",
    dry_run_output="Would restart docker.service"
)
```

---

## CLI

```bash
# List pending
python Halbert/main.py approval-list

# View history
python Halbert/main.py approval-history --limit 20
```

---

## Dry-Run Preview

Before requesting approval, actions run in dry-run mode:

```python
from halbert_core.halbert_core.approval.simulator import DryRunSimulator

sim = DryRunSimulator()
preview = sim.simulate(action)
# "Would restart docker.service (currently running, uptime 3d)"
```

---

## Related

- [architecture/policy-engine.md](policy-engine.md)
- [architecture/guardrails.md](guardrails.md)
