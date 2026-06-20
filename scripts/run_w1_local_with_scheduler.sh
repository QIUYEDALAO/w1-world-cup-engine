#!/usr/bin/env bash
# Start the local dashboard viewer and the Scout scheduler producer together.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

PORT="${W1_DASHBOARD_PORT:-8765}"
INTERVAL="${W1_SCOUT_SCHEDULER_INTERVAL_SECONDS:-60}"
MAX_FIXTURES="${W1_SCOUT_SCHEDULER_MAX_FIXTURES_PER_RUN:-4}"
LOG_DIR="${W1_LOCAL_LOG_DIR:-logs}"
SERVER_LOG="${LOG_DIR}/w1_local_server.log"        # default: logs/w1_local_server.log
SCHEDULER_LOG="${LOG_DIR}/w1_scout_scheduler.log"  # default: logs/w1_scout_scheduler.log

mkdir -p "$LOG_DIR"

if command -v lsof >/dev/null 2>&1 && lsof -i ":${PORT}" >/dev/null 2>&1; then
  echo "WARN: port ${PORT} is already in use. Stop the existing process before starting this bundle." >&2
  lsof -i ":${PORT}" >&2 || true
  exit 1
fi

server_pid=""
scheduler_pid=""

cleanup() {
  trap - INT TERM EXIT
  if [ -n "$scheduler_pid" ] && kill -0 "$scheduler_pid" 2>/dev/null; then
    kill "$scheduler_pid" 2>/dev/null || true
  fi
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
  fi
  wait "$scheduler_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "starting W1 dashboard viewer on 127.0.0.1:${PORT} -> ${SERVER_LOG}"
W1_SCOUT_AUTOPILOT="${W1_SCOUT_AUTOPILOT:-0}" \
python3 -u scripts/w1_local_predict_server.py >"$SERVER_LOG" 2>&1 &
server_pid="$!"

echo "starting W1 Scout scheduler daemon interval=${INTERVAL}s -> ${SCHEDULER_LOG}"
W1_SCOUT_SCHEDULER_MAX_FIXTURES_PER_RUN="$MAX_FIXTURES" \
W1_SCOUT_SCHEDULER_CONTINUE_UNTIL_EMPTY="${W1_SCOUT_SCHEDULER_CONTINUE_UNTIL_EMPTY:-1}" \
W1_SCOUT_SCHEDULER_MAX_BATCHES="${W1_SCOUT_SCHEDULER_MAX_BATCHES:-4}" \
python3 -u scripts/w1_scout_scheduler.py --daemon --interval "$INTERVAL" >"$SCHEDULER_LOG" 2>&1 &
scheduler_pid="$!"

echo "dashboard: http://127.0.0.1:${PORT}/reports/dashboard/W1_VISUAL_DASHBOARD.html"
echo "server_pid=${server_pid} scheduler_pid=${scheduler_pid}"
echo "Ctrl+C stops both processes."

while kill -0 "$server_pid" 2>/dev/null && kill -0 "$scheduler_pid" 2>/dev/null; do
  sleep 2
done
echo "one process exited; stopping the other..." >&2
cleanup
