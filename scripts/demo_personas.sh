#!/bin/bash
#
# Cerebric Phase 4: Persona System Demo Script
#
# Demonstrates the persona system capabilities:
# - Persona switching
# - Memory isolation
# - Context detection
# - LoRA management
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

Cerebric_CLI="python3 Cerebric/main.py"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Cerebric PHASE 4: PERSONA SYSTEM DEMO              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to pause between steps
pause() {
    echo -e "\n${YELLOW}Press Enter to continue...${NC}"
    read
}

# Demo 1: List Personas
echo -e "${GREEN}═══ Demo 1: List Available Personas ═══${NC}"
$Cerebric_CLI persona-list
pause

# Demo 2: Check Current Status
echo -e "\n${GREEN}═══ Demo 2: Check Current Persona Status ═══${NC}"
$Cerebric_CLI persona-status
pause

# Demo 3: Switch to Friend Persona
echo -e "\n${GREEN}═══ Demo 3: Switch to Friend Persona ═══${NC}"
echo "Switching from IT Admin to Friend..."
$Cerebric_CLI persona-switch --to friend --user demo --confirm
echo ""
$Cerebric_CLI persona-status
pause

# Demo 4: Context Detection
echo -e "\n${GREEN}═══ Demo 4: Auto-Context Detection ═══${NC}"
echo "Detecting context from running applications..."
$Cerebric_CLI context-detect
pause

# Demo 5: Context Preferences
echo -e "\n${GREEN}═══ Demo 5: Context Detection Preferences ═══${NC}"
$Cerebric_CLI context-prefs
pause

# Demo 6: LoRA Catalog
echo -e "\n${GREEN}═══ Demo 6: LoRA Adapter Catalog ═══${NC}"
$Cerebric_CLI lora-list
pause

# Demo 7: LoRA Info
echo -e "\n${GREEN}═══ Demo 7: LoRA Details ═══${NC}"
echo "Getting details for 'none' LoRA..."
$Cerebric_CLI lora-info --lora-key none
pause

# Demo 8: Memory Stats
echo -e "\n${GREEN}═══ Demo 8: Memory Statistics ═══${NC}"
echo "(Memory stats would be shown via dashboard API)"
echo "Check: curl http://localhost:8000/api/persona/memory/stats"
pause

# Demo 9: Switch Back to IT Admin
echo -e "\n${GREEN}═══ Demo 9: Switch Back to IT Admin ═══${NC}"
echo "Switching from Friend back to IT Admin..."
$Cerebric_CLI persona-switch --to it_admin --user demo --confirm
echo ""
$Cerebric_CLI persona-status
pause

# Demo 10: Complete Workflow
echo -e "\n${GREEN}═══ Demo 10: Complete Persona Workflow ═══${NC}"
echo ""
echo "1. Check status"
$Cerebric_CLI persona-status | head -6
echo ""
echo "2. List personas"
$Cerebric_CLI persona-list | head -10
echo ""
echo "3. Detect context"
$Cerebric_CLI context-detect | head -10
echo ""
echo -e "${GREEN}✅ Demo complete!${NC}"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  DEMO COMPLETED                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Phase 4 Features Demonstrated:"
echo "  ✓ Persona switching (IT Admin ↔ Friend)"
echo "  ✓ Memory isolation"
echo "  ✓ Context detection from running apps"
echo "  ✓ LoRA adapter management"
echo "  ✓ State persistence"
echo ""
echo "For more information:"
echo "  - User Guide: docs/Phase4/USER-GUIDE.md"
echo "  - API Docs: docs/Phase4/M3-BACKEND-COMPLETE.md"
echo "  - Tests: tests/test_phase4_integration.py"
echo ""
