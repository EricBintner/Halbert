#!/bin/bash
# Halbert Dashboard - Web-only Development Launcher
# Starts backend API only (frontend served from dist/)
# Faster startup - no Tauri compilation needed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

cleanup() {
    echo -e "\n${BLUE}Shutting down...${NC}"
    lsof -t -i:8000 2>/dev/null | xargs -r kill 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill any existing server
if lsof -i:8000 >/dev/null 2>&1; then
    echo -e "${BLUE}Killing existing process on port 8000...${NC}"
    lsof -t -i:8000 | xargs -r kill 2>/dev/null || true
    sleep 1
fi

# Activate venv
[ -f "$PROJECT_ROOT/.venv/bin/activate" ] && source "$PROJECT_ROOT/.venv/bin/activate"

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Halbert Dashboard - http://localhost:8000${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Press Ctrl+C to stop${NC}\n"

cd "$PROJECT_ROOT/halbert_core"
python -m uvicorn halbert_core.dashboard.app:app \
    --host 127.0.0.1 \
    --port 8000 \
    --reload
