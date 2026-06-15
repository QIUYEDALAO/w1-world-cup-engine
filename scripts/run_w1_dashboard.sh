#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/liudehua/.openclaw/workspace/w1_world_cup_engine"
cd "$ROOT"

PORT="${W1_DASHBOARD_PORT:-8787}"
export W1_DASHBOARD_PORT="$PORT"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

load_api_env_key() {
  local env_file="$1"
  local key_name value
  [ -f "$env_file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#export }"
    case "$line" in
      APIFOOTBALL_KEY=*|OPENCLAW_APIFOOTBALL_KEY=*)
        key_name="${line%%=*}"
        value="${line#*=}"
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        if [ "$key_name" = "APIFOOTBALL_KEY" ] && [ -z "${APIFOOTBALL_KEY:-}" ]; then
          export APIFOOTBALL_KEY="$value"
        elif [ "$key_name" = "OPENCLAW_APIFOOTBALL_KEY" ] && [ -z "${OPENCLAW_APIFOOTBALL_KEY:-}" ]; then
          export OPENCLAW_APIFOOTBALL_KEY="$value"
        fi
        ;;
    esac
  done < "$env_file"
}

for env_file in \
  "/Users/liudehua/.openclaw/.env" \
  "/Users/liudehua/.openclaw/service-env/ai.openclaw.gateway.env" \
  "/Users/liudehua/.openclaw/secrets/v4_daily_scan.env" \
  "/Users/liudehua/.openclaw/workspace/v4-football/api_keys.sh"
do
  if [ -f "$env_file" ] && [ -z "${APIFOOTBALL_KEY:-}" ] && [ -z "${OPENCLAW_APIFOOTBALL_KEY:-}" ]; then
    load_api_env_key "$env_file"
  fi
done

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
