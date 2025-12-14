# Halbert Features

A comprehensive list of implemented features as of December 2025.

---

## Dashboard Pages

### Dashboard
**Overview of system health at a glance.**
- System metrics (CPU, RAM, disk)
- Quick status indicators
- Navigation to detailed pages

### Services
**Systemd service management.**
- List all services with status (running/stopped/failed)
- Filter by category (system, user, mount, network)
- Service details: status, uptime, logs
- Start/stop/restart controls (with approval)
- Failed service detection and alerts
- AI-assisted troubleshooting via chat

### Storage
**Disk and filesystem management.**
- Disk health monitoring (SMART status)
- Filesystem usage (bcachefs, ZFS, BTRFS, ext4)
- Mount point status
- Pool health for advanced filesystems
- Large directory detection
- AI analysis of storage issues

### Backups
**Backup system detection and monitoring.**
- Timeshift snapshot detection
- Borg repository detection
- Backup schedule status
- Last backup timestamps
- AI-assisted backup recommendations

### Security
**System security overview.**
- SSH configuration audit
- Firewall status (ufw, iptables)
- User account listing
- Sudo configuration
- Failed login detection
- AI security recommendations

### Network
**Network interface management.**
- Interface listing (ethernet, wifi, bridge, bond)
- IP address and MAC display
- Connection status
- Bridge and bond configuration
- VPN status (Tailscale, WireGuard)
- Config editor for netplan/NetworkManager

### Sharing
**File sharing and remote access.**
- **NFS**: Exported shares with client access
- **SMB/Samba**: Share configuration and status
- **Tailscale**: Device listing, drive shares
- **WireGuard**: Peer status
- Config editor for share files

### Containers
**Docker and Podman management.**
- Container listing with status
- Image management
- Log viewing
- Start/stop/restart controls
- Resource usage (CPU, memory)

### GPU
**Graphics card monitoring.**
- NVIDIA GPU detection (nvidia-smi)
- AMD GPU detection (rocm-smi)
- Temperature, memory, utilization
- Ollama model loading status
- CUDA/ROCm version

### Development
**Developer environment status.**
- Git repository detection
- Active development projects
- Language runtime versions
- IDE/editor detection

### Approvals
**Pending action approvals.**
- List pending approvals
- Approve/reject with reason
- Approval history

### Settings
**Application configuration.**

#### AI Models Tab
- **Saved Endpoints**: Configure Ollama instances (local, remote)
- **Model Roles**:
  - **Guide**: Fast model (8B) for simple queries
  - **Specialist**: Large model (70B) for complex reasoning
  - **Vision**: Multimodal model for image analysis
- Test endpoint connectivity
- Per-role endpoint + model selection

#### AI Rules Tab
- Custom guardrails for edge cases
- Priority levels (high/medium/low)
- Categories (storage, kernel, network, security, etc.)
- Enable/disable individual rules
- Example: "bcachefs requires kernel 6.8 - don't recommend upgrades"

#### Data Scan Tab
- Trigger system discovery scan
- View scanner status

---

## Chat System

### AI Assistant (Sidebar)
**Natural language system administration.**

- **Contextual Awareness**: AI knows current page and visible items
- **@Mentions**: Reference specific items (@service, @disk, @interface)
- **Conversation History**: Persistent conversations with search
- **Model Display**: Shows which model is responding

### Smart Model Routing
**Automatic selection between Guide and Specialist.**

- Simple queries → Guide (8B, fast)
- Complex diagnostics → Specialist (70B, thorough)
- Complexity scoring based on keywords and length
- Debug mode shows routing decisions

### Vision Model Support
**Image analysis for troubleshooting.**

- Paste images directly into chat
- Drag-and-drop image files
- Screenshot capture button in sidebar
- Vision model analyzes errors, logs, configurations

### Context Injection
**Automatic relevant context based on query.**

- Storage keywords → inject disk/filesystem discoveries
- Service keywords → inject service status
- Error keywords → inject related failures
- Network keywords → inject interface info
- Failure correlation → link disk failures to mount failures
- **Memory retrieval** → ChromaDB semantic search for past conversations

### Memory System
**Persistent conversation memory using ChromaDB.**

- Conversations stored in `~/.local/share/halbert/chromadb/`
- Semantic search across past conversations
- Auto-inject relevant past context into new queries
- Collections: `self_conversations`, `self_knowledge_all`
- API endpoints: `/api/chat/memory/stats`, `/api/chat/memory/query`

### Self-Knowledge System (Ontology)
**Persistent understanding of itself - WHY things are configured.**

Knowledge Types:
- **Identity**: Hostname, OS, hardware, primary purpose
- **Config Rationale**: WHY something is configured a certain way
- **Roles**: What purpose a component serves
- **Relationships**: Component dependencies and connections
- **User-Taught**: Explicit knowledge from the user

Features:
- Persisted to `~/.local/share/halbert/knowledge/self_knowledge.json`
- ChromaDB semantic search over knowledge
- Auto-bootstraps identity on first run
- **First context injected** into every chat (core identity)

API Endpoints:
- `POST /api/settings/knowledge/teach` — Teach the system something
- `POST /api/settings/knowledge/explain-config` — Record WHY a config exists
- `POST /api/settings/knowledge/assign-role` — Assign purpose to a component
- `GET /api/settings/knowledge/search?q=...` — Semantic search
- `GET /api/settings/knowledge/identity` — Get core identity
- `POST /api/settings/knowledge/bootstrap` — Re-bootstrap identity

### Why Brain UI
**Universal "Why" explanation for any item.**

Visual indicator (Brain icon):
- **Grey**: No explanation defined
- **Pink/Magenta**: User has defined why this exists

Components:
- `WhyBrain` — Clickable brain icon with state
- `WhyOverlay` — Full-screen overlay for editing explanation

Usage:
- Click brain icon on any discovery card
- Type explanation for why the item exists
- Saved to self-knowledge system
- Context injected into future AI responses

### Telemetry Ingestion
**Continuous system event collection.**

- **journald**: System logs (errors, warnings from key services)
- **hwmon**: Temperature sensor readings
- Auto-starts with dashboard, runs in background
- Events indexed in ChromaDB for semantic search
- Telemetry injected into chat when relevant (error keywords → logs, thermal keywords → temps)
- Collections: `self_journald`, `self_hwmon`
- API endpoints: `/api/settings/ingestion/status`, `/start`, `/stop`

### Document RAG
**Linux documentation retrieval for accurate answers.**

- **Sources**: Man pages (7,300+), Arch Wiki, systemd docs, network docs, etc.
- Chunked and indexed in ChromaDB for semantic search
- Auto-injected into chat for how-to and reference questions
- Collection: `linux_docs`
- API endpoints:
  - `GET /api/settings/docs/stats` — Index statistics
  - `POST /api/settings/docs/index` — Trigger indexing
  - `GET /api/settings/docs/query?q=...` — Direct query

### Command Execution
**Run commands suggested by AI.**

- Inline "Run" button on code blocks
- Output displayed inline
- Auto-analyze: AI explains command output
- Output saved to conversation history

---

## Config Editor

### AI-Assisted Editing
**Edit system configuration files with AI help.**

- Open config files from chat or page actions
- Syntax highlighting (Monaco editor)
- AI suggests changes via SEARCH/REPLACE blocks
- Diff view shows proposed changes
- Accept/reject changes
- Backup before save (with restore)

### Supported Config Types
- Netplan (network)
- Samba (sharing)
- NFS exports
- SSH config
- Systemd units
- Any text config file

---

## Terminal

### Integrated Terminal
**Command line access in sidebar.**

- Tab switching between Chat and Terminal
- Command history
- Output display
- Switch to chat to ask about errors

---

## Debug Mode

### Developer Diagnostics
**Verbose debugging for development.**

- Toggle in sidebar footer
- Shows: request count, tokens, response times
- Console logging with color-coded categories
- Model routing decisions visible
- Persists across page reloads

---

## Discovery System

### Automatic System Scanning
**Detect and catalog system components.**

| Scanner | Detects |
|---------|---------|
| `disk_usage.py` | Disks, partitions, filesystems, SMART |
| `network.py` | Interfaces, bridges, bonds, VPN |
| `services.py` | Systemd services, Docker containers |
| `sharing.py` | NFS, SMB, Tailscale, WireGuard |
| `backup.py` | Timeshift, Borg, rsync |
| `security.py` | SSH, firewall, users |
| `gpu.py` | NVIDIA, AMD, Ollama |
| `containers.py` | Docker, Podman |
| `development.py` | Git, dev tools |

---

## Backend API

### Core Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat/send` | POST | Send chat message |
| `/api/chat/config` | POST | Config editor chat |
| `/api/discovery/{type}` | GET | Get discoveries by type |
| `/api/settings/endpoints` | GET/POST/DELETE | Manage Ollama endpoints |
| `/api/settings/assign/{role}` | POST | Assign model to role |
| `/api/settings/ai-rules` | GET/POST/PUT/DELETE | Custom AI rules |
| `/api/conversations` | GET/POST/DELETE | Chat history |
| `/api/terminal/execute` | POST | Run command |
| `/api/editor/file` | GET/POST | Read/write config files |
| `/api/services/{action}` | POST | Service control |

### Chat Request Fields
```json
{
  "message": "Why is my disk failing?",
  "mentions": ["@disk", "@service"],
  "persona": "guide",
  "debug": true,
  "current_page": "storage",
  "page_context": "Viewing disk pool status",
  "images": ["base64..."],
  "history": [{"role": "user", "content": "..."}]
}
```

---

## Configuration

### File Locations
| Path | Purpose |
|------|---------|
| `~/.config/halbert/models.yml` | Model/endpoint configuration |
| `~/.config/halbert/ai_rules.yml` | Custom AI rules |
| `~/.config/halbert/personas/` | Persona definitions |
| `~/.local/share/halbert/conversations/` | Chat history |

### models.yml Example
```yaml
orchestrator:
  endpoint: http://localhost:11434
  model: llama3.1:8b

specialist:
  enabled: true
  endpoint: http://remote-server:11434
  model: llama3.1:70b

vision:
  endpoint: http://localhost:11434
  model: llava:34b
```

---

## Running Halbert

### Development Mode
```bash
make dev
```
Starts FastAPI backend + Vite dev server with hot reload.

### Production Build
```bash
make build
make serve
```

### Access
- Dashboard: http://localhost:8000
- API Docs: http://localhost:8000/docs
