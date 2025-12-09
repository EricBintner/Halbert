# Ingestion Pipeline

The ingestion pipeline collects system telemetry from journald, hardware sensors, and configuration files.

---

## Overview

Ingestion transforms raw system data into structured events that feed the memory system and RAG pipeline.

**Code**: `cerebric_core/cerebric_core/ingestion/`

---

## Data Sources

### journald

System logs via `systemd-journald`.

```bash
python Cerebric/main.py ingest-journald
```

**Code**: `cerebric_core/cerebric_core/ingestion/runner.py`

Captures:
- Service start/stop events
- Error messages
- Warnings
- Security events (auth failures)

### hwmon

Hardware temperature sensors.

```bash
python Cerebric/main.py ingest-hwmon
```

**Code**: `cerebric_core/cerebric_core/ingestion/hwmon_runner.py`

Captures:
- CPU temperature
- NVMe/disk temperature
- GPU temperature (if available)
- Fan speeds

### Configuration Snapshots

Point-in-time captures of config files.

```bash
python Cerebric/main.py snapshot-configs
python Cerebric/main.py watch-configs
```

**Code**: `cerebric_core/cerebric_core/config/snapshot.py`

---

## Event Schema

All ingested data follows a standard schema:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "source": "journald",
  "unit": "docker.service",
  "priority": 3,
  "message": "Container abc123 started",
  "metadata": {
    "container_id": "abc123",
    "image": "nginx:latest"
  }
}
```

Schema definition: `docs/Phase1/schemas/telemetry-event.schema.json`

---

## Configuration

### ingestion.yml

```yaml
journald:
  enabled: true
  units:
    - docker.service
    - sshd.service
    - nginx.service
  priority_max: 4
  follow: true
  batch_size: 100

hwmon:
  enabled: true
  interval_seconds: 30
  sensors:
    - coretemp
    - nvme
```

### config-registry.yml

```yaml
files:
  - path: /etc/ssh/sshd_config
    description: SSH daemon configuration
  - path: /etc/docker/daemon.json
    description: Docker daemon settings
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingestion Pipeline                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐            │
│  │ journald │   │  hwmon   │   │ config files │            │
│  └────┬─────┘   └────┬─────┘   └──────┬───────┘            │
│       │              │                │                     │
│       ▼              ▼                ▼                     │
│  ┌──────────────────────────────────────────────┐          │
│  │              Event Normalizer                 │          │
│  │    (common schema, timestamps, metadata)      │          │
│  └──────────────────────────────────────────────┘          │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────────────────────────────────┐          │
│  │               JSONL Writer                    │          │
│  │    (~/.local/share/cerebric/telemetry/)      │          │
│  └──────────────────────────────────────────────┘          │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────────────────────────────────┐          │
│  │             Vector Indexer                    │          │
│  │    (ChromaDB for semantic search)             │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Output Formats

### JSONL Files

```
~/.local/share/cerebric/telemetry/
├── journald/
│   └── 2024-01-15.jsonl
├── hwmon/
│   └── 2024-01-15.jsonl
└── configs/
    └── snapshots/
        └── 2024-01-15T10-30-00.json
```

### Vector Index

Events are embedded and stored in ChromaDB for semantic search.

```python
# Query recent errors
from cerebric_core.cerebric_core.memory.retrieval import MemoryRetrieval

mem = MemoryRetrieval()
errors = mem.retrieve_from("runtime", "docker container failed", k=10)
```

---

## Filtering

### Priority Levels (journald)

| Priority | Meaning |
|----------|---------|
| 0 | Emergency |
| 1 | Alert |
| 2 | Critical |
| 3 | Error |
| 4 | Warning |
| 5 | Notice |
| 6 | Info |
| 7 | Debug |

`priority_max: 4` captures warnings and above.

### Unit Filtering

Only capture specific systemd units:

```yaml
journald:
  units:
    - docker.service
    - sshd.service
```

---

## CLI Commands

```bash
# Start journald ingestion (foreground)
python Cerebric/main.py ingest-journald

# Start hwmon polling (foreground)
python Cerebric/main.py ingest-hwmon

# Snapshot configs
python Cerebric/main.py snapshot-configs

# Watch configs continuously
python Cerebric/main.py watch-configs

# Diff config snapshots
python Cerebric/main.py diff-configs
```

---

## Permissions

### journald Access

User must be in `systemd-journal` group:

```bash
sudo usermod -a -G systemd-journal $USER
# Log out and back in
```

### hwmon Access

Most sensors are readable by any user. Some may require:

```bash
sudo chmod a+r /sys/class/hwmon/*/temp*
```

---

## Related

- [architecture/memory-system.md](memory-system.md) - Where ingested data is stored
- [CONFIGURATION.md](../CONFIGURATION.md) - Configuration reference
- [CLI-REFERENCE.md](../CLI-REFERENCE.md) - CLI commands
