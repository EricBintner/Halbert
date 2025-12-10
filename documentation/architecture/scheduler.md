# Scheduler

Manages scheduled and autonomous task execution.

**Code**: `halbert_core/halbert_core/scheduler/`

---

## Components

| Component | Purpose |
|-----------|---------|
| `SchedulerEngine` | Job queue management |
| `AutonomousExecutor` | Cron-based execution |
| `Job` | Task definition |

---

## Job Structure

```python
Job(
    id="nightly-health",
    task="health_check",
    schedule="0 2 * * *",  # 2 AM daily
    priority=5,
    inputs={"verbose": True}
)
```

---

## CLI

```bash
# Add a job
python Halbert/main.py scheduler-add \
  --id nightly-health \
  --task health_check \
  --schedule "0 2 * * *" \
  --priority 5 \
  --inputs inputs.json

# List jobs
python Halbert/main.py scheduler-list

# Cancel
python Halbert/main.py scheduler-cancel --id nightly-health
```

---

## Autonomous Executor

```bash
# Schedule cron job
python Halbert/main.py executor-schedule \
  --job-id daily-check \
  --cron '{"hour": 2}' \
  --daemon

# List scheduled
python Halbert/main.py executor-list

# Cancel
python Halbert/main.py executor-cancel --job-id daily-check
```

---

## Related

- [architecture/approval-system.md](approval-system.md)
- [architecture/guardrails.md](guardrails.md)
