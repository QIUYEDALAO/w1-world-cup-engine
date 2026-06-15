#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/liudehua/.openclaw/workspace/w1_world_cup_engine"
cd "$ROOT"

PORT="${W1_DASHBOARD_PORT:-8787}"
export W1_DASHBOARD_PORT="$PORT"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"
if [ -z "${APIFOOTBALL_KEY:-}" ] && [ -n "${OPENCLAW_APIFOOTBALL_KEY:-}" ]; then
  export APIFOOTBALL_KEY="$OPENCLAW_APIFOOTBALL_KEY"
fi
if [ -n "${APIFOOTBALL_KEY:-}" ]; then
  API_FOOTBALL_STATUS="present"
else
  API_FOOTBALL_STATUS="missing"
fi
URL="http://127.0.0.1:${PORT}/reports/dashboard/W1_VISUAL_DASHBOARD.html"
# Legacy default remains supported by setting W1_DASHBOARD_PORT=8765.

echo "W1 dashboard local server starting..."
echo "APIFOOTBALL_KEY=${API_FOOTBALL_STATUS}"
echo "Open: $URL"

if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "$URL") >/dev/null 2>&1 &
fi

exec python3 scripts/w1_local_predict_server.py
