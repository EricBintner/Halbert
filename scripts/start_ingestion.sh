#!/usr/bin/env bash
# Start Cerebric Phase 1 ingestion processes (journald + hwmon)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

python3 Cerebric/main.py ingest-journald &
JOURNALD_PID=$!
python3 Cerebric/main.py ingest-hwmon &
HWMON_PID=$!

echo "Started ingest-journald (PID $JOURNALD_PID) and ingest-hwmon (PID $HWMON_PID)"
echo "Data under <data>/raw and logs under <logs> (see docs/Phase1/fhs-xdg-paths.md)"
