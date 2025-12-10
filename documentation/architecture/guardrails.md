# Autonomy Guardrails

Safety controls for autonomous operation.

**Code**: `halbert_core/halbert_core/autonomy/`

---

## Components

| Component | Purpose |
|-----------|---------|
| `GuardrailEnforcer` | Policy enforcement |
| `AnomalyDetector` | Unusual behavior detection |
| `RecoveryExecutor` | Automatic recovery |

---

## Configuration

```yaml
# ~/.config/halbert/autonomy.yml

confidence:
  min_auto_execute: 0.9
  min_approval_execute: 0.5
  block_below: 0.3

budgets:
  cpu_percent_max: 50
  memory_mb_max: 2048
  time_minutes_max: 30
  frequency_per_hour_max: 10

anomalies:
  cpu_spike_threshold: 90
  memory_leak_mb: 500
  repeated_failures: 3
```

---

## Safe Mode

Emergency stop for all autonomous operations.

```bash
# Pause everything
python Halbert/main.py autonomy-pause --reason "maintenance"

# Resume
python Halbert/main.py autonomy-resume --user $USER
```

---

## CLI

```bash
# Status
python Halbert/main.py autonomy-status

# View anomalies
python Halbert/main.py autonomy-anomalies --hours 24

# Recovery history
python Halbert/main.py autonomy-recovery --limit 20
```

---

## Confidence Gating

| Confidence | Action |
|------------|--------|
| ≥ 0.9 | Auto-execute |
| 0.5 - 0.9 | Request approval |
| < 0.5 | Block |

---

## Related

- [architecture/approval-system.md](approval-system.md)
- [architecture/policy-engine.md](policy-engine.md)
