# CLI Reference

Complete reference for the Cerebric command-line interface.

---

## Usage

```bash
python Cerebric/main.py [command] [options]
```

Or if installed:

```bash
cerebric [command] [options]
```

---

## Command Categories

| Category | Commands |
|----------|----------|
| [Information](#information) | `info`, `roadmap`, `show`, `show-doc` |
| [Ingestion](#ingestion) | `ingest-journald`, `ingest-hwmon` |
| [Configuration](#configuration-tracking) | `snapshot-configs`, `watch-configs`, `diff-configs`, `index-configs` |
| [Memory & RAG](#memory--rag) | `memory-query`, `memory-stats`, `memory-write`, `index-query`, `ask` |
| [Model](#model-management) | `model-status`, `model-test`, `prompt-show`, `prompt-init` |
| [Policy](#policy) | `policy-show`, `policy-eval` |
| [Scheduler](#scheduler) | `scheduler-add`, `scheduler-list`, `scheduler-cancel` |
| [Executor](#autonomous-executor) | `executor-status`, `executor-schedule`, `executor-list`, `executor-cancel` |
| [Approval](#approval) | `approval-list`, `approval-history` |
| [Autonomy](#autonomy-guardrails) | `autonomy-status`, `autonomy-pause`, `autonomy-resume`, `autonomy-anomalies`, `autonomy-recovery` |
| [Dashboard](#dashboard) | `dashboard`, `build-dashboard` |
| [Runtime](#runtime) | `runtime-tick`, `autonomous-run` |
| [Hardware](#hardware--configuration) | `hardware-detect`, `config-wizard`, `config-validate` |
| [Performance](#performance) | `performance-status`, `performance-alerts`, `performance-reset` |

---

## Information

### `info`

Show product information.

```bash
python Cerebric/main.py info
```

### `roadmap`

Display the development roadmap.

```bash
python Cerebric/main.py roadmap
```

### `show`

Show a project file (relative to `Cerebric/`).

```bash
python Cerebric/main.py show <path>
```

### `show-doc`

Show a docs file (relative to `docs/`).

```bash
python Cerebric/main.py show-doc Phase1/ROADMAP.md
```

---

## Ingestion

### `ingest-journald`

Run journald follower and write events to JSONL.

```bash
python Cerebric/main.py ingest-journald [--config PATH] [--schema PATH]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--config` | Path to ingestion.yml | `~/.config/cerebric/ingestion.yml` |
| `--schema` | Path to schema JSON | `docs/Phase1/schemas/telemetry-event.schema.json` |

### `ingest-hwmon`

Poll hardware sensors and write to JSONL.

```bash
python Cerebric/main.py ingest-hwmon [--config PATH]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--config` | Path to ingestion.yml | `~/.config/cerebric/ingestion.yml` |

---

## Configuration Tracking

### `snapshot-configs`

Take a point-in-time snapshot of tracked configuration files.

```bash
python Cerebric/main.py snapshot-configs [--manifest PATH]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--manifest` | Path to config-registry.yml | `~/.config/cerebric/config-registry.yml` |

### `watch-configs`

Continuously watch configuration files and snapshot on changes.

```bash
python Cerebric/main.py watch-configs [--manifest PATH] [--interval SECONDS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--manifest` | Path to config-registry.yml | `~/.config/cerebric/config-registry.yml` |
| `--interval` | Polling interval (fallback) | 600 |

### `diff-configs`

Compare two configuration snapshots.

```bash
python Cerebric/main.py diff-configs [--prev PATH] [--curr PATH]
```

Without arguments, compares the two most recent snapshots.

### `index-configs`

Index configuration records into the vector database.

```bash
python Cerebric/main.py index-configs
```

---

## Memory & RAG

### `memory-query`

Query the memory system.

```bash
python Cerebric/main.py memory-query --subdir SUBDIR --query "search text" [--limit N] [--json]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--subdir` | Memory subdirectory (`core`, `runtime`) | Required |
| `--query` | Search query | Required |
| `--limit` | Max results | 5 |
| `--json` | Output full JSON | false |

### `memory-stats`

Show memory system statistics.

```bash
python Cerebric/main.py memory-stats
```

### `memory-write`

Write an entry to memory (for testing).

```bash
python Cerebric/main.py memory-write --subdir SUBDIR --entry '{"key": "value"}'
```

### `index-query`

Query the vector index directly.

```bash
python Cerebric/main.py index-query "query text" [-k N]
```

### `ask`

Ask a question using RAG + LLM.

```bash
python Cerebric/main.py ask "How do I fix a broken apt database?"
```

| Option | Description | Default |
|--------|-------------|---------|
| `--model` | Ollama model | `llama3.2:3b` |
| `--no-llm` | Retrieve only, no generation | false |
| `--top-k` | Number of documents to retrieve | 3 |

---

## Model Management

### `model-status`

Show LLM connection and status.

```bash
python Cerebric/main.py model-status
```

### `model-test`

Test the model with a prompt.

```bash
python Cerebric/main.py model-test --prompt "Hello, who are you?" [--max-tokens N]
```

### `prompt-show`

Display the system prompt for a mode.

```bash
python Cerebric/main.py prompt-show [--mode MODE] [--context TEXT]
```

| Mode | Description |
|------|-------------|
| `interactive` | Standard conversation |
| `autonomous` | Background task execution |
| `it_admin` | Technical IT administration |
| `friend` | Casual conversation |
| `custom` | User-defined |

### `prompt-init`

Initialize default prompt configuration files.

```bash
python Cerebric/main.py prompt-init
```

---

## Policy

### `policy-show`

Display the current policy configuration.

```bash
python Cerebric/main.py policy-show
```

### `policy-eval`

Evaluate a policy decision for a tool.

```bash
python Cerebric/main.py policy-eval --tool TOOL_NAME --inputs PATH_TO_JSON
```

---

## Scheduler

### `scheduler-add`

Add a job to the scheduler.

```bash
python Cerebric/main.py scheduler-add \
  --id JOB_ID \
  --task TASK_NAME \
  --schedule "CRON_EXPR" \
  --priority N \
  --inputs PATH_TO_JSON
```

### `scheduler-list`

List scheduled jobs.

```bash
python Cerebric/main.py scheduler-list [--state STATE]
```

States: `pending`, `running`, `completed`, `failed`, `cancelled`

### `scheduler-cancel`

Cancel a pending job.

```bash
python Cerebric/main.py scheduler-cancel --id JOB_ID
```

---

## Autonomous Executor

### `executor-status`

Show executor status.

```bash
python Cerebric/main.py executor-status
```

### `executor-schedule`

Schedule a cron job.

```bash
python Cerebric/main.py executor-schedule \
  --job-id JOB_ID \
  --cron '{"hour": 2, "minute": 0}' \
  [--description TEXT] \
  [--daemon]
```

### `executor-list`

List scheduled jobs.

```bash
python Cerebric/main.py executor-list
```

### `executor-cancel`

Cancel a scheduled job.

```bash
python Cerebric/main.py executor-cancel --job-id JOB_ID
```

---

## Approval

### `approval-list`

List pending approval requests.

```bash
python Cerebric/main.py approval-list
```

### `approval-history`

Show approval history.

```bash
python Cerebric/main.py approval-history [--limit N] [--approved-only]
```

---

## Autonomy Guardrails

### `autonomy-status`

Show guardrail configuration and status.

```bash
python Cerebric/main.py autonomy-status
```

### `autonomy-pause`

Activate safe mode (pause all autonomous operations).

```bash
python Cerebric/main.py autonomy-pause --reason "maintenance"
```

### `autonomy-resume`

Resume autonomous operations.

```bash
python Cerebric/main.py autonomy-resume --user USERNAME
```

### `autonomy-anomalies`

View detected anomalies.

```bash
python Cerebric/main.py autonomy-anomalies [--hours N]
```

### `autonomy-recovery`

View recovery action history.

```bash
python Cerebric/main.py autonomy-recovery [--limit N]
```

---

## Dashboard

### `dashboard`

Start the web dashboard.

```bash
python Cerebric/main.py dashboard [--host HOST] [--port PORT]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Bind address | `127.0.0.1` |
| `--port` | Port number | `8000` |

Access at `http://localhost:8000` after starting.

### `build-dashboard`

Build dashboard JSON artifacts.

```bash
python Cerebric/main.py build-dashboard
```

---

## Runtime

### `runtime-tick`

Run one iteration of the runtime engine.

```bash
python Cerebric/main.py runtime-tick
```

### `autonomous-run`

Run an autonomous task with LLM decision making.

```bash
python Cerebric/main.py autonomous-run \
  --task-type TYPE \
  [--confidence THRESHOLD] \
  [--context JSON] \
  [--no-approval]
```

Task types: `health_check`, `log_cleanup`

---

## Hardware & Configuration

### `hardware-detect`

Detect hardware and show capabilities.

```bash
python Cerebric/main.py hardware-detect [--recommend]
```

### `config-wizard`

Run the interactive configuration wizard.

```bash
python Cerebric/main.py config-wizard [--auto] [--install-help]
```

### `config-validate`

Validate model configuration.

```bash
python Cerebric/main.py config-validate
```

---

## Performance

### `performance-status`

Show model performance metrics.

```bash
python Cerebric/main.py performance-status
```

### `performance-alerts`

Show performance alerts.

```bash
python Cerebric/main.py performance-alerts [--severity LEVEL] [--hours N]
```

### `performance-reset`

Reset performance metrics.

```bash
python Cerebric/main.py performance-reset [--model MODEL_ID]
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `Cerebric_CONFIG_DIR` | Override config directory |
| `Cerebric_DATA_DIR` | Override data directory |
| `OLLAMA_HOST` | Ollama API endpoint |

---

## Examples

### Daily health check

```bash
# Check system status
python Cerebric/main.py model-test --prompt "How are you doing today?"

# View recent anomalies
python Cerebric/main.py autonomy-anomalies --hours 24
```

### Configuration tracking

```bash
# Take a snapshot
python Cerebric/main.py snapshot-configs

# Make a change to /etc/ssh/sshd_config

# Take another snapshot
python Cerebric/main.py snapshot-configs

# See what changed
python Cerebric/main.py diff-configs
```

### Query the knowledge base

```bash
# Ask about systemd
python Cerebric/main.py ask "Why did docker.service fail to start?"

# Query memory directly
python Cerebric/main.py memory-query --subdir core --query "docker errors"
```

### Schedule a maintenance task

```bash
# Schedule nightly health check at 2 AM
python Cerebric/main.py executor-schedule \
  --job-id "nightly-health" \
  --cron '{"hour": 2, "minute": 0}' \
  --description "Nightly system health check" \
  --daemon
```
