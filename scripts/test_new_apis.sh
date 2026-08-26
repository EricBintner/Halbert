#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
#
# Test script for new Halbert APIs
# Run with: ./scripts/test_new_apis.sh
#
# Prerequisites: Dashboard running (make dev), jq installed
#

set -e

API_BASE="http://localhost:8000/api/settings"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "  Halbert API Test Suite"
echo "========================================"
echo ""

# Check if server is running
echo -n "Checking server connectivity... "
if curl -s "$API_BASE/../system/info" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Start the dashboard first: make dev"
    exit 1
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Policy API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Policy API ===${NC}"

echo -n "GET /policy... "
RESULT=$(curl -s "$API_BASE/policy")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  default_allow: $(echo "$RESULT" | jq -r '.policy.default_allow')"
else
    echo -e "${RED}FAILED${NC}"
    echo "$RESULT" | jq .
fi

echo -n "POST /policy/tool (add test_tool)... "
RESULT=$(curl -s -X POST "$API_BASE/policy/tool" \
    -H "Content-Type: application/json" \
    -d '{"tool": "test_tool", "allow": false}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "DELETE /policy/tool/test_tool... "
RESULT=$(curl -s -X DELETE "$API_BASE/policy/tool/test_tool")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Guardrails API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Guardrails API ===${NC}"

echo -n "GET /guardrails/status... "
RESULT=$(curl -s "$API_BASE/guardrails/status")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  safe_mode_active: $(echo "$RESULT" | jq -r '.safe_mode_active')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Anomaly Detection API ===${NC}"

echo -n "GET /anomaly/status... "
RESULT=$(curl -s "$API_BASE/anomaly/status")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  anomalies_24h: $(echo "$RESULT" | jq -r '.summary.total_anomalies_24h')"
    echo "  failure_streak: $(echo "$RESULT" | jq -r '.summary.failure_streak')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /anomaly/check... "
RESULT=$(curl -s -X POST "$API_BASE/anomaly/check")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  cpu_spike: $(echo "$RESULT" | jq -r '.checks.cpu_spike')"
    echo "  error_rate_high: $(echo "$RESULT" | jq -r '.checks.error_rate_high')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Recovery Playbooks API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Recovery Playbooks API ===${NC}"

echo -n "GET /recovery/status... "
RESULT=$(curl -s "$API_BASE/recovery/status")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  total_actions: $(echo "$RESULT" | jq -r '.summary.total_actions')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /recovery/alert (test alert)... "
RESULT=$(curl -s -X POST "$API_BASE/recovery/alert" \
    -H "Content-Type: application/json" \
    -d '{"message": "API test alert", "severity": "info"}')
if echo "$RESULT" | jq -e '.action == "alert_user"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC} (alerts may be disabled)"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Dry-run Simulation API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Dry-run Simulation API ===${NC}"

echo -n "POST /simulate/file-write... "
RESULT=$(curl -s -X POST "$API_BASE/simulate/file-write" \
    -H "Content-Type: application/json" \
    -d '{"path": "/tmp/test-simulation.txt", "content": "Hello from Halbert!"}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  action: $(echo "$RESULT" | jq -r '.simulation.action')"
    echo "  reversible: $(echo "$RESULT" | jq -r '.simulation.reversible')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /simulate/command... "
RESULT=$(curl -s -X POST "$API_BASE/simulate/command" \
    -H "Content-Type: application/json" \
    -d '{"command": "echo hello"}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /simulate/service-restart... "
RESULT=$(curl -s -X POST "$API_BASE/simulate/service-restart" \
    -H "Content-Type: application/json" \
    -d '{"service": "nginx"}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  warnings: $(echo "$RESULT" | jq -r '.simulation.warnings | length') warning(s)"
    echo "  estimated_duration: $(echo "$RESULT" | jq -r '.simulation.estimated_duration_s')s"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /simulate/tool (write_config)... "
RESULT=$(curl -s -X POST "$API_BASE/simulate/tool" \
    -H "Content-Type: application/json" \
    -d '{"tool": "write_config", "args": {"path": "/etc/test.conf", "content": "test=1"}}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "POST /simulate/tool (unknown_tool)... "
RESULT=$(curl -s -X POST "$API_BASE/simulate/tool" \
    -H "Content-Type: application/json" \
    -d '{"tool": "unknown_tool", "args": {"foo": "bar"}}')
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC} (generic fallback)"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Scheduler API
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== Scheduler API ===${NC}"

echo -n "GET /scheduler/status... "
RESULT=$(curl -s "$API_BASE/scheduler/status")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  running: $(echo "$RESULT" | jq -r '.scheduler.running // .scheduler.reason')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo -n "GET /scheduler/jobs... "
RESULT=$(curl -s "$API_BASE/scheduler/jobs")
if echo "$RESULT" | jq -e '.status == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
    echo "  job_count: $(echo "$RESULT" | jq -r '.count // (.jobs | length)')"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket (quick check)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}=== WebSocket ===${NC}"

echo -n "WebSocket endpoint available... "
# Just check the upgrade is offered (won't complete handshake with curl)
RESULT=$(curl -s -I "http://localhost:8000/ws" 2>&1 | head -1)
if [[ "$RESULT" == *"101"* ]] || [[ "$RESULT" == *"426"* ]] || [[ "$RESULT" == *"400"* ]]; then
    echo -e "${GREEN}OK${NC} (endpoint exists)"
else
    echo -e "${YELLOW}SKIP${NC} (use wscat/websocat to test)"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}Test suite complete!${NC}"
echo "========================================"
echo ""
echo "To test WebSocket streaming:"
echo "  npx wscat -c ws://localhost:8000/ws"
echo ""
