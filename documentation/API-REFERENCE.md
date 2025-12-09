# API Reference

REST API for the Cerebric dashboard.

**Code**: `cerebric_core/cerebric_core/dashboard/`

---

## Base URL

```
http://localhost:8000
```

Start with:
```bash
python Cerebric/main.py dashboard
```

---

## Endpoints

### Health

```
GET /health
```

Returns `{"status": "ok"}`.

### System Status

```
GET /api/status
```

Returns system metrics, model status, memory stats.

### Chat

```
POST /api/chat
Content-Type: application/json

{
  "message": "How's my disk space?",
  "context": {}
}
```

### Memory

```
GET /api/memory/stats
GET /api/memory/query?q=docker+errors&limit=10
```

### Approval

```
GET /api/approval/pending
POST /api/approval/{id}/approve
POST /api/approval/{id}/reject
```

### Autonomy

```
GET /api/autonomy/status
POST /api/autonomy/pause
POST /api/autonomy/resume
```

---

## WebSocket

```
ws://localhost:8000/ws
```

Real-time updates for:
- System metrics
- Log events
- Approval requests

---

## OpenAPI Docs

Interactive documentation at:
```
http://localhost:8000/docs
```

---

## Authentication

No authentication by default. Dashboard binds to `127.0.0.1` only.

For network access:
```bash
python Cerebric/main.py dashboard --host 0.0.0.0
```

**Warning**: No auth means anyone on the network can access.
