# API Reference

REST API for the Halbert dashboard.

**Code**: `halbert_core/halbert_core/dashboard/routes/`

---

## Base URL

```
http://localhost:8000
```

Start with:
```bash
make dev
```

---

## OpenAPI Docs

Interactive documentation at:
```
http://localhost:8000/docs
```

---

## Chat API

### Send Chat Message

```
POST /api/chat/send
Content-Type: application/json
```

**Request:**
```json
{
  "message": "Why is my bcachefs pool failing?",
  "mentions": ["@storage", "@service"],
  "persona": "guide",
  "debug": false,
  "current_page": "storage",
  "page_context": "Viewing failed pool mount-bcachefs",
  "images": [],
  "history": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Previous response"}
  ]
}
```

**Response:**
```json
{
  "response": "Looking at the storage discoveries...",
  "debug": {
    "model_used": "<specialist-model-id>",
    "model_type": "specialist",
    "complexity_score": 0.7,
    "tokens_used": 512
  }
}
```

### Config Editor Chat

```
POST /api/chat/config
Content-Type: application/json
```

**Request:**
```json
{
  "message": "Add a comment at the end",
  "file_path": "/etc/samba/smb.conf",
  "file_content": "# Current file content...",
  "history": [],
  "images": []
}
```

**Response:**
```json
{
  "response": "I'll add the comment...",
  "edit_blocks": [
    {"search": "last line", "replace": "last line\n# Added comment"}
  ],
  "proposed_content": "# Full file with edits applied...",
  "summary": "Added comment at end of file"
}
```

### Model Status

```
GET /api/models/loaded
```

Returns currently loaded models and their status.

---

## Memory API

### Memory Statistics

```
GET /api/chat/memory/stats
```

**Response:**
```json
{
  "status": "ok",
  "chromadb_available": true,
  "memory_events": 150,
  "collections": {
    "self_knowledge_all": 500,
    "self_conversations": 150,
    "self_hwmon": 0,
    "self_journald": 0
  }
}
```

### Query Memory

```
POST /api/chat/memory/query
Content-Type: application/json

{
  "query": "bcachefs mount failure",
  "k": 5,
  "collection": "self_conversations"
}
```

**Response:**
```json
{
  "status": "ok",
  "query": "bcachefs mount failure",
  "results": [
    {
      "content": "The bcachefs pool failed because...",
      "role": "assistant",
      "conversation_id": "conv-123",
      "distance": 0.45
    }
  ],
  "count": 1
}
```

### List Collections

```
GET /api/chat/memory/collections
```

**Response:**
```json
{
  "status": "ok",
  "collections": [
    {"name": "self_conversations", "count": 150, "known": true},
    {"name": "self_knowledge_all", "count": 500, "known": true},
    {"name": "self_journald", "count": 0, "known": true},
    {"name": "self_hwmon", "count": 0, "known": true}
  ]
}
```

### List Entries in Collection

```
GET /api/chat/memory/entries/{collection}?limit=50&offset=0
```

**Response:**
```json
{
  "status": "ok",
  "collection": "self_conversations",
  "entries": [
    {
      "id": "conv:abc123:1702580400000",
      "content": "Why is my bcachefs pool failing?",
      "metadata": {
        "role": "user",
        "conversation_id": "abc123",
        "timestamp": "1702580400",
        "page": "storage"
      }
    }
  ],
  "count": 50
}
```

### Delete Entry

```
DELETE /api/chat/memory/entry/{collection}/{entry_id}
```

**Response:**
```json
{
  "status": "ok",
  "deleted": true
}
```

### Bulk Delete Entries

```
POST /api/chat/memory/delete/{collection}
Content-Type: application/json

{
  "entry_ids": ["id1", "id2", "id3"]
}
```

**Response:**
```json
{
  "status": "ok",
  "deleted": 3
}
```

### Clear Collection

```
POST /api/chat/memory/clear/{collection}
```

⚠️ **Warning**: This permanently deletes ALL entries in the collection.

**Response:**
```json
{
  "status": "ok",
  "cleared": true
}
```

---

## Ingestion API

Telemetry ingestion service for journald and hwmon collection.

### Get Ingestion Status

```
GET /api/settings/ingestion/status
```

**Response:**
```json
{
  "running": true,
  "started_at": "2025-12-14T10:30:00",
  "journald_events": 156,
  "hwmon_events": 42,
  "last_journald_event": "2025-12-14T10:35:22",
  "last_hwmon_event": "2025-12-14T10:35:30",
  "errors": 0,
  "config_path": "/home/user/.config/halbert/ingestion.yml"
}
```

### Start Ingestion

```
POST /api/settings/ingestion/start
```

Starts the background telemetry collection.

### Stop Ingestion

```
POST /api/settings/ingestion/stop
```

Stops the background telemetry collection.

---

## Discovery API

### Get Discoveries by Type

```
GET /api/discovery/{type}
```

Types: `storage`, `service`, `network`, `container`, `gpu`, `sharing`, `security`, `backup`

**Response:**
```json
{
  "discoveries": [
    {
      "id": "disk-nvme0n1",
      "type": "storage",
      "name": "nvme0n1",
      "title": "Samsung 980 PRO",
      "status": "healthy",
      "data": {...}
    }
  ]
}
```

### Trigger Scan

```
POST /api/discovery/scan
```

Triggers a fresh system discovery scan.

---

## Agent API

**Code**: `halbert_core/halbert_core/dashboard/routes/agent.py`

The agent state machine and the one continuous conversation it writes to.
`POST /api/agent/message` is the only way to talk to it and
`GET /api/agent/timeline` the only way to read the history back: there is no
conversations API, because the server chooses which hidden thread a turn
belongs to and the client never names one.

Every thread endpoint degrades rather than fails — with no store, or on a store
error, it answers empty. The one exception is redaction, which must never
report success it did not achieve.

### Send Message

```
POST /api/agent/message
Content-Type: application/json
```

**Request:**
```json
{
  "message": "Why did the media share stop mounting?",
  "session_id": "optional; generated when absent",
  "context": {},
  "images": [],
  "max_tokens": 8192,
  "temperature": 0.7,
  "model": null,
  "tier": null,
  "endpoint_id": null
}
```

`session_id` names one turn, not a conversation. `max_tokens` is bounded to
1–32768. `model` / `tier` / `endpoint_id` carry the in-chat picker's pin for
this turn; `tier` is `guide`, `specialist` or `vision` — anything else,
including `auto`, means "no pin". A second message sent during a live turn
queues on the state machine's turn lock.

**Response:** `text/event-stream`. Each frame is `data: {...}` with
`{"type", "session_id", "timestamp", ...}`. Types include `state_change`,
`plan`, `plan_step_update`, `thinking`, `context_loaded`, `tool_start`,
`tool_complete`, `tool_confirmation_required`, `response_chunk`,
`response_complete`, `response_provenance`, `diff_proposal`, `terminal_spawn`,
`terminal_output`, `terminal_complete`, `model_selected`, `thread_started`,
`thread_recalled`, `turn_persisted`, `conversation_status`, `heartbeat`,
`cancelled` and `error`. The read-only thread id the UI needs arrives on
`turn_persisted`.

### Confirm a High-Risk Action

```
POST /api/agent/confirm/{session_id}
Content-Type: application/json

{"action_id": "exec-123", "confirmed": true}
```

**Response:** `text/event-stream` — the continued turn, same event shapes.

### Session State

```
GET /api/agent/state/{session_id}
```

**Response:**
```json
{
  "session_id": "sess-1",
  "state": "EXECUTING",
  "plan": [],
  "current_step": 0,
  "loop_count": 0,
  "confidence": 0.0,
  "crag_action": "PENDING"
}
```

`404` when the session is not live.

### Cancel

```
POST /api/agent/cancel/{session_id}
```

→ `{"cancelled": true, "session_id": "sess-1"}`, or `404`.

### Health

```
GET /api/agent/health
```

→ `{"status": "healthy", "active_sessions": 0, "current_state": "IDLE"}`, or
`{"status": "unhealthy", "error": "..."}`. Always `200`.

### Intake Classification

```
POST /api/agent/intake
Content-Type: application/json

{"message": "why is my disk failing?"}
```

Read-only: routes the message without running the agent.

**Response:**
```json
{
  "recommended_model": "specialist",
  "complexity_score": 0.72,
  "complexity_level": "high",
  "intent": "troubleshooting",
  "is_greeting": false,
  "is_troubleshooting": true,
  "specialist_enabled": true
}
```

`503` when the build has no intake pipeline.

### Active Sessions

```
GET /api/agent/sessions
```

**Response:**
```json
{
  "sessions": [
    {"session_id": "sess-1", "query": "first 100 chars", "state": "EXECUTING",
     "loop_count": 0, "elapsed_ms": 1240}
  ]
}
```

### Metrics

```
GET /api/agent/metrics                    # collector summary
GET /api/agent/metrics/sessions?limit=10  # {"sessions": [...]} recent completed
```

### Apply / Reject a Proposed File Change

```
POST /api/agent/diff/{session_id}/{diff_id}/apply
POST /api/agent/diff/{session_id}/{diff_id}/reject
```

Resolved from the live session first, then from the store, so a proposal stays
actionable after its turn has ended.

**Response:**
```json
{"applied": true, "diff_id": "d1", "file_path": "/etc/samba/smb.conf"}
```
```json
{"rejected": true, "diff_id": "d1"}
```

`"status_persisted": false` is added when the decision could not be written
back to the store. `404` when there is no such proposal; `400` once it has been
applied or rejected — `new_content` is a whole-file replacement, so a second
apply would silently discard every edit made since.

### Timeline

```
GET /api/agent/timeline?limit=50&before={turn_id}&around={turn_id}
```

One page of the conversation, newest-last, grouped by turn. `before` pages
backwards from a turn; `around` centres a page on one (a recall chip click).
`before` wins when both are given. `limit` is clamped to 1–200.

**Response:**
```json
{
  "turns": [
    {
      "turn_id": "turn-abc",
      "thread_id": "thread-1",
      "timestamp": 1756200000.0,
      "origin": "human",
      "user": {"message_id": 1, "content": "...", "timestamp": 1756200000.0, "status": "complete"},
      "assistant": {"message_id": 2, "content": "...", "timestamp": 1756200001.0, "status": "complete"},
      "blocks": [],
      "terminal_block_ids": [],
      "diff_proposals": []
    }
  ],
  "has_more": false,
  "current_thread": {"thread_id": "thread-1", "title": "", "status": "open"}
}
```

`user` or `assistant` is `null` while a turn is half-written. Always `200`: with
no store, or on any store error, the answer degrades to
`{"turns": [], "has_more": false, "current_thread": null}`.

### Current Thread

```
GET /api/agent/thread/current
```

The open thread, or `null` when nothing is open and when the store is
unavailable. The body is the stored row plus a `thread_id` alias for `id`:

```json
{
  "id": "thread-1",
  "thread_id": "thread-1",
  "title": "Media share stopped mounting",
  "status": "open",
  "receipt": "…summary the recall reads back…",
  "receipt_updated_at": 1756200002.0,
  "topic_domains": [],
  "entities_json": [],
  "recalled_json": [],
  "last_active": 1756200001.0,
  "stale": 0,
  "ephemeral": 0,
  "unread": 0,
  "title_source": "provisional",
  "message_count": 2,
  "turn_count": 1
}
```

### Retract a Recall

```
DELETE /api/agent/thread/{thread_id}/recall/{recalled_thread_id}
```

Marks a thread that was pulled into `thread_id` as retracted, so it stops
feeding later prompts.

→ `{"ok": true}`, or `{"ok": false}` when there was no such recall.

### Redact a Message

```
POST /api/agent/message/{message_id}/redact
```

"Forget this" for one row: its content and tool blocks become
`[redacted by admin]`, and every derived copy goes with it — the FTS index row,
the thread title it founded, the thread's entity sets — before the thread
receipt is regenerated from what is left. Rows are never deleted.

**Response:**
```json
{"ok": true, "thread_id": "thread-1"}
```

`"receipt_refreshed": false` is added when the receipt could not be rebuilt and
was blanked instead. `404` means only "there is no such row"; `503` means the
store is unavailable and `500` means the redaction did not land in full — a
person who asked to forget something is never told "nothing to forget", or
"done", while the words are still readable somewhere.

---

## Settings API

### Endpoints

```
GET /api/settings/endpoints              # List saved endpoints
POST /api/settings/endpoints             # Save/update endpoint
DELETE /api/settings/endpoints/{id}      # Delete endpoint
GET /api/settings/endpoints/{id}/models  # List models from endpoint
POST /api/settings/endpoints/{id}/test   # Test connectivity
```

### Model Assignment

```
POST /api/settings/assign/guide      # Assign guide model
POST /api/settings/assign/specialist # Assign specialist model
POST /api/settings/assign/vision     # Assign vision model
POST /api/settings/guide/clear       # Clear guide assignment
```

**Request:**
```json
{
  "endpoint_id": "local-ollama",
  "model": "<model-id>"
}
```

### AI Rules

```
GET /api/settings/ai-rules           # List rules
POST /api/settings/ai-rules          # Create rule
PUT /api/settings/ai-rules/{id}      # Update rule
DELETE /api/settings/ai-rules/{id}   # Delete rule
```

**Rule Schema:**
```json
{
  "id": "rule-123",
  "text": "bcachefs requires kernel 6.8 or earlier",
  "priority": "high",
  "category": "storage",
  "enabled": true
}
```

---

## Editor API

### Read File

```
GET /api/editor/file?path=/etc/samba/smb.conf
```

### Write File

```
POST /api/editor/file
Content-Type: application/json

{
  "path": "/etc/samba/smb.conf",
  "content": "# New content..."
}
```

### Backups

```
GET /api/editor/backups?path=/etc/samba/smb.conf
POST /api/editor/restore

{"path": "/etc/samba/smb.conf", "backup": "smb.conf.bak.1234567890"}
```

---

## Terminal API

### Execute Command

```
POST /api/terminal/execute
Content-Type: application/json

{"command": "systemctl status nginx"}
```

**Response:**
```json
{
  "output": "● nginx.service - A high performance web server...",
  "error": "",
  "exit_code": 0
}
```

---

## Service API

### Service Actions

```
POST /api/services/{name}/start
POST /api/services/{name}/stop
POST /api/services/{name}/restart
GET /api/services/{name}/logs?lines=100
```

---

## Approval API

### List Pending

```
GET /api/approvals/pending
```

### Approve/Reject

```
POST /api/approvals/{id}/approve
POST /api/approvals/{id}/reject

{"reason": "Approved by admin"}
```

---

## Policy API

### Get Policy

```
GET /api/settings/policy
```

**Response:**
```json
{
  "status": "ok",
  "policy": {
    "default_allow": true,
    "tools": {
      "write_config": {"allow": true},
      "schedule_cron": {"allow": true}
    }
  },
  "path": "/home/user/.config/halbert/policy.yml"
}
```

### Update Policy

```
POST /api/settings/policy
Content-Type: application/json

{
  "policy": {
    "default_allow": true,
    "tools": {"dangerous_tool": {"allow": false}}
  }
}
```

### Set Tool Policy

```
POST /api/settings/policy/tool
Content-Type: application/json

{"tool": "write_config", "allow": true}
```

### Delete Tool Override

```
DELETE /api/settings/policy/tool/{tool_name}
```

---

## Guardrails API

### Get Status

```
GET /api/settings/guardrails/status
```

**Response:**
```json
{
  "status": "ok",
  "safe_mode_active": false,
  "config": {"confidence_threshold": 0.8, "cpu_budget": 80}
}
```

### Enter Safe Mode

```
POST /api/settings/guardrails/safe-mode/enter
Content-Type: application/json

{"reason": "Manual activation"}
```

### Exit Safe Mode

```
POST /api/settings/guardrails/safe-mode/exit
```

---

## Anomaly Detection API

### Get Status

```
GET /api/settings/anomaly/status
```

**Response:**
```json
{
  "status": "ok",
  "summary": {
    "total_anomalies_24h": 2,
    "critical_anomalies_24h": 0,
    "failure_streak": 0,
    "recent_error_rate": 0.0
  },
  "recent_anomalies": [
    {
      "timestamp": "2025-12-14T10:30:00",
      "type": "cpu_spike",
      "severity": "warning",
      "description": "CPU usage 95% above threshold 90%"
    }
  ]
}
```

### Run Check

```
POST /api/settings/anomaly/check
```

Runs anomaly detection checks immediately.

---

## Recovery Playbooks API

### Get Status

```
GET /api/settings/recovery/status
```

### Execute Rollback

```
POST /api/settings/recovery/rollback
Content-Type: application/json

{"file_path": "/etc/myapp/config.yml"}
```

### Restart Service

```
POST /api/settings/recovery/restart-service
Content-Type: application/json

{"service": "nginx"}
```

### Send Alert

```
POST /api/settings/recovery/alert
Content-Type: application/json

{"message": "Recovery alert", "severity": "warning"}
```

---

## Dry-run Simulation API

### Simulate Tool Call

```
POST /api/settings/simulate/tool
Content-Type: application/json

{
  "tool": "write_config",
  "args": {"path": "/etc/app.conf", "content": "new content"}
}
```

**Response:**
```json
{
  "status": "ok",
  "simulation": {
    "success": true,
    "action": "Write file: /etc/app.conf",
    "changes": [{"type": "file_modify", "path": "/etc/app.conf", "diff": "..."}],
    "warnings": [],
    "reversible": true,
    "rollback_strategy": "Restore /etc/app.conf from backup",
    "estimated_duration_s": 0.1
  }
}
```

### Simulate File Write

```
POST /api/settings/simulate/file-write
Content-Type: application/json

{"path": "/etc/app.conf", "content": "new content"}
```

### Simulate Command

```
POST /api/settings/simulate/command
Content-Type: application/json

{"command": "apt update", "dry_run_flag": "--dry-run"}
```

### Simulate Service Restart

```
POST /api/settings/simulate/service-restart
Content-Type: application/json

{"service": "nginx"}
```

---

## WebSocket API

Real-time updates via WebSocket connection.

### Connect

```
ws://localhost:8000/ws
```

### Message Types

| Type | Description |
|------|-------------|
| `system_status` | System metrics every 5s |
| `approval_request` | New approval needed |
| `job_update` | Scheduler job status changed |
| `decision` | LLM decision made |
| `chat_token` | Streaming chat token |
| `chat_complete` | Chat response complete |

**Chat Token Message:**
```json
{
  "type": "chat_token",
  "data": {
    "request_id": "req-123",
    "token": "Hello",
    "done": false
  }
}
```

---

## Scheduler API

### Get Status

```
GET /api/settings/scheduler/status
```

### List Jobs

```
GET /api/settings/scheduler/jobs
```

### Cancel Job

```
POST /api/settings/scheduler/cancel/{job_id}
```

---

## Authentication

No authentication by default. Dashboard binds to `127.0.0.1` only.

For network access, run with `--host 0.0.0.0` but note this exposes the API without auth.
