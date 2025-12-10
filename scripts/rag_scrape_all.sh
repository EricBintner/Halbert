#!/usr/bin/env bash
#
# Comprehensive RAG data scraping script
# Scrapes Arch Wiki, Stack Overflow, and extracts man pages
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DATA_DIR="${DATA_DIR:-data}"
ARCH_WIKI_MAX_PAGES="${ARCH_WIKI_MAX_PAGES:-50}"
STACKOVERFLOW_MAX_QUESTIONS="${STACKOVERFLOW_MAX_QUESTIONS:-100}"
STACKOVERFLOW_MIN_SCORE="${STACKOVERFLOW_MIN_SCORE:-5}"

echo "======================================"
echo "Halbert RAG Data Scraping"
echo "======================================"
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

# Add halbert_core to Python path
export PYTHONPATH="${PWD}/halbert_core:${PYTHONPATH}"

# 1. Scrape Arch Wiki
echo "======================================"
echo "1. Scraping Arch Wiki"
echo "======================================"
python3 -m halbert_core.rag.scrapers.arch_wiki \
    --output-dir "${DATA_DIR}/raw/arch_wiki" \
    --max-pages ${ARCH_WIKI_MAX_PAGES} \
    --rate-limit 1.0

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Arch Wiki scraping complete${NC}"
else
    echo -e "${YELLOW}⚠ Arch Wiki scraping had errors (check logs)${NC}"
fi

echo ""

# 2. Scrape Stack Overflow
echo "======================================"
echo "2. Scraping Stack Overflow"
echo "======================================"

# Check for API key
if [ -n "${STACKOVERFLOW_API_KEY}" ]; then
    API_KEY_ARG="--api-key ${STACKOVERFLOW_API_KEY}"
    echo "Using API key (higher rate limits)"
else
    API_KEY_ARG=""
    echo -e "${YELLOW}No API key set. Using anonymous access (lower rate limits)${NC}"
    echo "Set STACKOVERFLOW_API_KEY environment variable for better performance"
fi

python3 -m halbert_core.rag.scrapers.stackoverflow \
    --output-dir "${DATA_DIR}/raw/stackoverflow" \
    --max-questions ${STACKOVERFLOW_MAX_QUESTIONS} \
    --min-score ${STACKOVERFLOW_MIN_SCORE} \
    ${API_KEY_ARG}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Stack Overflow scraping complete${NC}"
else
    echo -e "${YELLOW}⚠ Stack Overflow scraping had errors (check logs)${NC}"
fi

echo ""

# 3. macOS man pages (if running on macOS)
echo "======================================"
echo "3. macOS Man Pages"
echo "======================================"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Running on macOS - extracting man pages..."
    python3 -m halbert_core.rag.scrapers.macos_man \
        --output-dir "${DATA_DIR}/raw/macos_man" \
        --max-pages 600
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ macOS man pages extraction complete${NC}"
    else
        echo -e "${YELLOW}⚠ macOS man pages extraction had errors${NC}"
    fi
else
    echo -e "${YELLOW}Not running on macOS - skipping${NC}"
    echo "To extract macOS man pages, run this script on a Mac"
fi

echo ""

# 4. Run data pipeline
echo "======================================"
echo "4. Running Data Pipeline"
echo "======================================"

# Determine which sources we have
SOURCES=()
[ -f "${DATA_DIR}/raw/arch_wiki/arch_wiki.jsonl" ] && SOURCES+=(arch_wiki)
[ -f "${DATA_DIR}/raw/stackoverflow/stackoverflow.jsonl" ] && SOURCES+=(stackoverflow)
[ -f "${DATA_DIR}/raw/macos_man/macos_man_pages.jsonl" ] && SOURCES+=(macos_man)

if [ ${#SOURCES[@]} -eq 0 ]; then
    echo -e "${RED}No source files found!${NC}"
    exit 1
fi

echo "Processing sources: ${SOURCES[*]}"

python3 -m halbert_core.rag.data_pipeline \
    --data-dir "${DATA_DIR}" \
    --sources ${SOURCES[*]} \
    --output-name all_sources

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Data pipeline complete${NC}"
else
    echo -e "${RED}✗ Data pipeline failed${NC}"
    exit 1
fi

echo ""

# 5. Summary
echo "======================================"
echo "SUMMARY"
echo "======================================"

# Count documents
if [ -f "${DATA_DIR}/processed/all_sources.jsonl" ]; then
    DOC_COUNT=$(wc -l < "${DATA_DIR}/processed/all_sources.jsonl")
    echo -e "${GREEN}✓ Total documents: ${DOC_COUNT}${NC}"
    echo ""
    echo "Output files:"
    echo "  - ${DATA_DIR}/processed/all_sources.jsonl"
    echo "  - ${DATA_DIR}/processed/all_sources_stats.json"
    echo ""
    echo "Next step: Rebuild RAG index with new data"
    echo "  python3 -m halbert_core.rag.index_builder --test"
else
    echo -e "${RED}✗ Output file not found${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Done!${NC}"
