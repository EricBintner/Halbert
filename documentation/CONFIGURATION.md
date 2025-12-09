# Configuration Reference

Cerebric uses YAML configuration files following XDG Base Directory standards.

---

## Configuration Paths

| Path | Purpose |
|------|---------|
| `~/.config/cerebric/` | User configuration |
| `~/.local/share/cerebric/` | Application data |
| `~/.local/state/cerebric/` | Runtime state |

---

## Core Configuration Files

### model.yml

LLM configuration.

```yaml
# ~/.config/cerebric/model.yml

# Default model for all operations
default_model: llama3.2:3b

# Ollama connection
ollama_host: http://localhost:11434
ollama_timeout: 120

# Model routing (optional)
routing:
  enabled: false
  quick_tasks: llama3.2:3b
  complex_analysis: llama3.1:70b
  code_generation: deepseek-coder:33b

# Generation defaults
generation:
  max_tokens: 2048
  temperature: 0.7
  top_p: 0.9
```

### ingestion.yml

Data ingestion settings.

```yaml
# ~/.config/cerebric/ingestion.yml

journald:
  enabled: true
  units:
    - docker.service
    - sshd.service
    - nginx.service
    - postgresql.service
  priority_max: 4  # warning and above
  follow: true
  batch_size: 100

hwmon:
  enabled: true
  interval_seconds: 30
  sensors:
    - coretemp
    - nvme
    - acpitz
  alert_thresholds:
    cpu_temp_c: 80
    disk_temp_c: 55
```

### policy.yml

Action policy rules.

```yaml
# ~/.config/cerebric/policy.yml

# Global settings
defaults:
  dry_run: true
  require_approval: true
  log_all: true

# Per-tool rules
rules:
  # Reading is always allowed
  - tool: read_logs
    action: allow
    require_approval: false
    
  - tool: query_memory
    action: allow
    require_approval: false

  # Modifications require approval
  - tool: restart_service
    action: allow
    require_approval: true
    dry_run_first: true
    
  - tool: modify_config
    action: allow
    require_approval: true
    dry_run_first: true
    backup_required: true

  # Dangerous operations blocked
  - tool: delete_file
    action: block
    reason: "File deletion disabled by policy"
```

### autonomy.yml

Autonomy guardrails.

```yaml
# ~/.config/cerebric/autonomy.yml

# Confidence thresholds
confidence:
  min_auto_execute: 0.9     # Auto-execute above this
  min_approval_execute: 0.5  # Allow with approval above this
  block_below: 0.3          # Block below this

# Resource budgets per job
budgets:
  cpu_percent_max: 50
  memory_mb_max: 2048
  time_minutes_max: 30
  frequency_per_hour_max: 10

# Anomaly detection
anomalies:
  cpu_spike_threshold: 90
  memory_leak_mb: 500
  repeated_failures: 3
  error_rate_threshold: 0.5

# Safe mode
safe_mode:
  auto_trigger_on_anomaly: true
  require_user_resume: true
```

### config-registry.yml

Configuration files to track.

```yaml
# ~/.config/cerebric/config-registry.yml

# Files to snapshot and track changes
files:
  - path: /etc/ssh/sshd_config
    description: SSH daemon configuration
    
  - path: /etc/nginx/nginx.conf
    description: Nginx main configuration
    
  - path: /etc/docker/daemon.json
    description: Docker daemon settings
    
  - path: ~/.bashrc
    description: User shell configuration

# Snapshot settings
snapshot:
  directory: ~/.local/share/cerebric/config/snapshots
  keep_count: 50
  on_change: true
```

---

## Prompt Configuration

Located in `~/.config/cerebric/prompts/`.

### base-safety.txt

Core safety instructions included in all prompts.

```text
You are Cerebric, a local-first AI assistant that identifies as this computer.

SAFETY RULES:
1. Never execute destructive commands without approval
2. Always use dry-run mode first
3. Explain what you're about to do before doing it
4. If uncertain, ask for clarification
```

### identity.txt

System identity prompt.

```text
I am this computer. My hostname is {hostname}.
I have been running for {uptime}.
My primary user is {username}.

When I speak about my logs, I mean the system logs.
When I speak about my memory, I mean RAM and the knowledge base.
When I speak about my health, I mean system metrics.
```

---

## Environment Variables

Override configuration with environment variables:

| Variable | Description |
|----------|-------------|
| `Cerebric_CONFIG_DIR` | Config directory |
| `Cerebric_DATA_DIR` | Data directory |
| `Cerebric_STATE_DIR` | State directory |
| `OLLAMA_HOST` | Ollama API endpoint |
| `Cerebric_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) |

---

## Data Directories

### Memory Structure

```
~/.local/share/cerebric/
├── index/              # ChromaDB vector database
├── memory/
│   ├── core/           # Core knowledge
│   └── runtime/        # Action outcomes
├── config/
│   └── snapshots/      # Config snapshots
└── logs/               # Application logs
```

### State Files

```
~/.local/state/cerebric/
├── scheduler.db        # Job queue
├── approval.db         # Approval history
└── safe_mode.lock      # Safe mode indicator
```

---

## Validation

Check configuration validity:

```bash
python Cerebric/main.py config-validate
```

This verifies:
- YAML syntax
- Required fields present
- File paths exist
- Model availability
