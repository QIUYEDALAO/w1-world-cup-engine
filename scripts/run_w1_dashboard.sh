#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/liudehua/.openclaw/workspace/w1_world_cup_engine"
cd "$ROOT"

URL="http://127.0.0.1:8765/reports/dashboard/W1_VISUAL_DASHBOARD.html"

echo "W1 dashboard local server starting..."
echo "Open: $URL"

if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "$URL") >/dev/null 2>&1 &
fi

exec python3 scripts/w1_local_predict_server.py
