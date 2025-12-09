# Data Formats

Schema definitions for Cerebric data files.

---

## Telemetry Event (JSONL)

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "source": "journald",
  "unit": "docker.service",
  "priority": 3,
  "message": "Container started",
  "metadata": {}
}
```

| Field | Type | Required |
|-------|------|----------|
| `timestamp` | ISO 8601 | Yes |
| `source` | string | Yes |
| `unit` | string | No |
| `priority` | int (0-7) | No |
| `message` | string | Yes |
| `metadata` | object | No |

---

## Config Snapshot (JSON)

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "files": {
    "/etc/ssh/sshd_config": {
      "hash": "sha256:abc123...",
      "size": 3245,
      "mtime": "2024-01-10T08:00:00Z"
    }
  }
}
```

---

## Memory Entry (JSON)

```json
{
  "id": "mem-123",
  "type": "action_outcome",
  "content": "Restarted docker.service successfully",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "metadata": {
    "action": "restart_service",
    "target": "docker.service",
    "success": true
  }
}
```

---

## Job Definition (JSON)

```json
{
  "id": "nightly-health",
  "task": "health_check",
  "schedule": "0 2 * * *",
  "priority": 5,
  "state": "pending",
  "inputs": {},
  "created_at": "2024-01-15T10:30:00.000Z"
}
```

---

## Approval Request (JSON)

```json
{
  "id": "req-123",
  "task": "restart_service",
  "action": "restart docker.service",
  "confidence": 0.85,
  "risk_level": "medium",
  "requested_at": "2024-01-15T10:30:00.000Z",
  "dry_run_output": "Would restart docker.service"
}
```

---

## RAG Document (JSONL)

```json
{
  "content": "Document text...",
  "metadata": {
    "source": "arch-wiki",
    "source_url": "https://wiki.archlinux.org/...",
    "trust_tier": 1,
    "title": "systemd"
  }
}
```

| Trust Tier | Source Type |
|------------|-------------|
| 1 | Official docs |
| 2 | Verified community |
| 3 | Community content |
