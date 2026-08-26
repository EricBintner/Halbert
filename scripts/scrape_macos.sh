#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
#
# macOS RAG Data Scraping Script
# Phase 25: Build macOS knowledge base
#
# This script can run on ANY platform (Linux or macOS)
# Some scrapers (man pages) require macOS to run locally
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DATA_DIR="${DATA_DIR:-data/macos}"
MAX_FORMULAS="${MAX_FORMULAS:-500}"
RATE_LIMIT="${RATE_LIMIT:-0.5}"

echo -e "${BLUE}======================================"
echo "Halbert macOS RAG Data Scraping"
echo "Phase 25: macOS Knowledge Base"
echo -e "======================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -d "halbert_core" ]; then
    echo -e "${RED}Error: Must be run from LinuxBrain root directory${NC}"
    exit 1
fi

# Check dependencies
echo "Checking dependencies..."
python3 -c "import requests; import bs4" 2>/dev/null || {
    echo -e "${YELLOW}Installing scraping dependencies...${NC}"
    pip install requests beautifulsoup4 html5lib
}
echo -e "${GREEN}✓ Dependencies OK${NC}"
echo ""

# Create output directory
mkdir -p "${DATA_DIR}"

# Add halbert_core to Python path
export PYTHONPATH="${PWD}/halbert_core:${PYTHONPATH}"

# Track stats
TOTAL_DOCS=0

# ============================================
# 1. Homebrew Documentation & Formulas
# ============================================
echo -e "${BLUE}======================================"
echo "1. Scraping Homebrew (docs + formulas)"
echo -e "======================================${NC}"

python3 -m halbert_core.rag.scrapers.homebrew \
    --output-dir "${DATA_DIR}/homebrew" \
    --max-formulas ${MAX_FORMULAS} \
    --rate-limit ${RATE_LIMIT}

if [ $? -eq 0 ]; then
    COUNT=$(wc -l < "${DATA_DIR}/homebrew/homebrew.jsonl" 2>/dev/null || echo 0)
    TOTAL_DOCS=$((TOTAL_DOCS + COUNT))
    echo -e "${GREEN}✓ Homebrew: ${COUNT} documents${NC}"
else
    echo -e "${YELLOW}⚠ Homebrew scraping had errors${NC}"
fi
echo ""

# ============================================
# 2. macOS Command Reference (SS64 + guides)
# ============================================
echo -e "${BLUE}======================================"
echo "2. Scraping macOS Command Reference"
echo -e "======================================${NC}"

python3 -m halbert_core.rag.scrapers.macos_support \
    --output-dir "${DATA_DIR}/support" \
    --rate-limit ${RATE_LIMIT}

if [ $? -eq 0 ]; then
    # The SS64 slice of this scrape is CC BY-NC 4.0 and must not sit in the
    # shippable macOS corpus (LEG-CRIT-01). Split it back out immediately —
    # otherwise every scrape silently undoes the quarantine.
    echo "  Quarantining non-commercial (CC BY-NC) records..."
    python3 "$(dirname "$0")/quarantine_ss64.py" --data-dir "$(dirname "${DATA_DIR}")" || {
        echo -e "${RED}✗ Quarantine step failed — do not build from this corpus${NC}"
        exit 1
    }

    COUNT=$(wc -l < "${DATA_DIR}/support/macos_support.jsonl" 2>/dev/null || echo 0)
    TOTAL_DOCS=$((TOTAL_DOCS + COUNT))
    echo -e "${GREEN}✓ macOS Support: ${COUNT} shippable documents (SS64 quarantined)${NC}"
else
    echo -e "${YELLOW}⚠ macOS support scraping had errors${NC}"
fi
echo ""

# ============================================
# 3. macOS Man Pages (macOS only)
# ============================================
echo -e "${BLUE}======================================"
echo "3. macOS Man Pages"
echo -e "======================================${NC}"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Running on macOS - extracting man pages..."
    
    python3 -m halbert_core.rag.scrapers.macos_man \
        --output-dir "${DATA_DIR}/man-pages" \
        --max-pages 600
    
    if [ $? -eq 0 ]; then
        COUNT=$(wc -l < "${DATA_DIR}/man-pages/macos_man_pages.jsonl" 2>/dev/null || echo 0)
        TOTAL_DOCS=$((TOTAL_DOCS + COUNT))
        echo -e "${GREEN}✓ Man pages: ${COUNT} documents${NC}"
    else
        echo -e "${YELLOW}⚠ Man pages extraction had errors${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Not running on macOS - skipping man pages${NC}"
    echo "To extract macOS man pages, run this script on a Mac"
fi
echo ""

# ============================================
# 4. Merge all sources
# ============================================
echo -e "${BLUE}======================================"
echo "4. Merging Sources"
echo -e "======================================${NC}"

# Combine all JSONL files
MERGED_FILE="${DATA_DIR}/merged/all_macos.jsonl"
mkdir -p "${DATA_DIR}/merged"

# Clear existing merged file
> "${MERGED_FILE}"

# Append all source files
for source_file in "${DATA_DIR}"/*/; do
    # No redirection in a `for ... in` list — the [ -f ] test below already
    # handles the case where the glob matches nothing.
    for jsonl in "${source_file}"*.jsonl; do
        if [ -f "$jsonl" ]; then
            cat "$jsonl" >> "${MERGED_FILE}"
            echo "  Added: $(basename $jsonl)"
        fi
    done
done

MERGED_COUNT=$(wc -l < "${MERGED_FILE}" 2>/dev/null || echo 0)
echo -e "${GREEN}✓ Merged file: ${MERGED_COUNT} documents${NC}"
echo ""

# ============================================
# Summary
# ============================================
echo -e "${BLUE}======================================"
echo "SUMMARY"
echo -e "======================================${NC}"
echo ""
echo -e "${GREEN}Total documents scraped: ${TOTAL_DOCS}${NC}"
echo ""
echo "Output files:"
ls -la "${DATA_DIR}"/*/*.jsonl 2>/dev/null || echo "  (none)"
echo ""
echo "Merged file:"
echo "  ${MERGED_FILE}"
echo ""

if [ "${TOTAL_DOCS}" -gt 0 ]; then
    echo -e "${GREEN}✓ macOS RAG data collection complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review data: head -5 ${MERGED_FILE}"
    echo "  2. Build index: python3 -m halbert_core.rag.index_builder --platform macos"
else
    echo -e "${RED}✗ No documents were scraped${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Done!${NC}"
