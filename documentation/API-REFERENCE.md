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
    "model_used": "llama3.1:70b",
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

## Conversations API

### List Conversations

```
GET /api/conversations
```

### Create Conversation

```
POST /api/conversations
Content-Type: application/json

{"name": "Troubleshooting disk", "persona": "guide"}
```

### Get Conversation

```
GET /api/conversations/{id}
```

### Delete Conversation

```
DELETE /api/conversations/{id}
```

### Add Message

```
POST /api/conversations/{id}/messages
Content-Type: application/json

{"role": "user", "content": "Message text", "mentions": []}
```

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
  "model": "llama3.1:8b"
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

## Authentication

No authentication by default. Dashboard binds to `127.0.0.1` only.

For network access, run with `--host 0.0.0.0` but note this exposes the API without auth.
