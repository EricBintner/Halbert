#!/bin/bash
# Halbert Dashboard - Development Launcher
# Starts both backend API and Tauri frontend app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_PID=""
FRONTEND_PID=""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cleanup() {
    echo -e "\n${BLUE}Shutting down...${NC}"
    
    # Kill backend
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID $BACKEND_PID)"
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    
    # Kill any remaining process on port 8000
    lsof -t -i:8000 2>/dev/null | xargs -r kill 2>/dev/null || true
    
    echo -e "${GREEN}Goodbye!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Kill any existing server on port 8000
if lsof -i:8000 >/dev/null 2>&1; then
    echo -e "${BLUE}Killing existing process on port 8000...${NC}"
    lsof -t -i:8000 | xargs -r kill 2>/dev/null || true
    sleep 1
fi

# Activate virtual environment
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo -e "${BLUE}Activating virtual environment...${NC}"
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Start backend
echo -e "${GREEN}Starting backend API on http://localhost:8000${NC}"
cd "$PROJECT_ROOT/halbert_core"
python -m uvicorn halbert_core.dashboard.app:app \
    --host 127.0.0.1 \
    --port 8000 \
    --reload \
    --log-level info &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${BLUE}Waiting for backend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/api/persona/status >/dev/null 2>&1; then
        echo -e "${GREEN}Backend ready!${NC}"
        break
    fi
    sleep 0.5
done

# Start Tauri frontend
echo -e "${GREEN}Starting Tauri desktop app...${NC}"
cd "$PROJECT_ROOT/halbert_core/halbert_core/dashboard/frontend"

# Check if npm dependencies are installed
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}Installing npm dependencies...${NC}"
    npm install
fi

# Run Tauri dev (this will block until closed)
npm run tauri dev

# When Tauri closes, cleanup will run
