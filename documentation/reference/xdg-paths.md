# XDG/FHS Paths

Cerebric follows XDG Base Directory and FHS standards.

---

## User Directories

| Path | Purpose | XDG Variable |
|------|---------|--------------|
| `~/.config/cerebric/` | Configuration | `$XDG_CONFIG_HOME` |
| `~/.local/share/cerebric/` | Application data | `$XDG_DATA_HOME` |
| `~/.local/state/cerebric/` | Runtime state | `$XDG_STATE_HOME` |
| `~/.cache/cerebric/` | Cached data | `$XDG_CACHE_HOME` |

---

## Directory Structure

### Config (`~/.config/cerebric/`)

```
~/.config/cerebric/
├── model.yml           # LLM configuration
├── ingestion.yml       # Data ingestion settings
├── policy.yml          # Action policies
├── autonomy.yml        # Guardrail settings
├── config-registry.yml # Files to track
└── prompts/            # System prompts
    ├── base-safety.txt
    └── identity.txt
```

### Data (`~/.local/share/cerebric/`)

```
~/.local/share/cerebric/
├── index/              # ChromaDB vector database
├── memory/
│   ├── core/           # Core knowledge
│   └── runtime/        # Action history
├── telemetry/
│   ├── journald/       # Log events
│   └── hwmon/          # Sensor data
└── config/
    └── snapshots/      # Config snapshots
```

### State (`~/.local/state/cerebric/`)

```
~/.local/state/cerebric/
├── scheduler.db        # Job queue
├── approval.db         # Approval history
└── safe_mode.lock      # Safe mode indicator
```

### Cache (`~/.cache/cerebric/`)

```
~/.cache/cerebric/
└── models/             # Embedding model cache
```

---

## Environment Overrides

```bash
export XDG_CONFIG_HOME=/custom/config
export XDG_DATA_HOME=/custom/data
export XDG_STATE_HOME=/custom/state
export XDG_CACHE_HOME=/custom/cache
```

Or Cerebric-specific:

```bash
export Cerebric_CONFIG_DIR=/custom/cerebric/config
export Cerebric_DATA_DIR=/custom/cerebric/data
```

---

## Code Reference

Path resolution: `cerebric_core/cerebric_core/utils/paths.py`

```python
from cerebric_core.cerebric_core.utils.paths import config_dir, data_subdir

cfg = config_dir()  # ~/.config/cerebric
data = data_subdir("memory", "core")  # ~/.local/share/cerebric/memory/core
```
