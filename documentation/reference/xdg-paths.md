# XDG/FHS Paths

Halbert follows XDG Base Directory and FHS standards.

---

## User Directories

| Path | Purpose | XDG Variable |
|------|---------|--------------|
| `~/.config/halbert/` | Configuration | `$XDG_CONFIG_HOME` |
| `~/.local/share/halbert/` | Application data | `$XDG_DATA_HOME` |
| `~/.local/state/halbert/` | Runtime state | `$XDG_STATE_HOME` |
| `~/.cache/halbert/` | Cached data | `$XDG_CACHE_HOME` |

---

## Directory Structure

### Config (`~/.config/halbert/`)

```
~/.config/halbert/
├── model.yml           # LLM configuration
├── ingestion.yml       # Data ingestion settings
├── policy.yml          # Action policies
├── autonomy.yml        # Guardrail settings
├── config-registry.yml # Files to track
└── prompts/            # System prompts
    ├── base-safety.txt
    └── identity.txt
```

### Data (`~/.local/share/halbert/`)

```
~/.local/share/halbert/
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

### State (`~/.local/state/halbert/`)

```
~/.local/state/halbert/
├── scheduler.db        # Job queue
├── approval.db         # Approval history
└── safe_mode.lock      # Safe mode indicator
```

### Cache (`~/.cache/halbert/`)

```
~/.cache/halbert/
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

Or Halbert-specific:

```bash
export Halbert_CONFIG_DIR=/custom/halbert/config
export Halbert_DATA_DIR=/custom/halbert/data
```

---

## Code Reference

Path resolution: `halbert_core/halbert_core/utils/paths.py`

```python
from halbert_core.halbert_core.utils.paths import config_dir, data_subdir

cfg = config_dir()  # ~/.config/halbert
data = data_subdir("memory", "core")  # ~/.local/share/halbert/memory/core
```
