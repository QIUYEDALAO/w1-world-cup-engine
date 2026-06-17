#!/usr/bin/env bash
# W1_SCOUT 自动生产闭环 · G2
# 未来 fixture: 抓赛前因子 → 组装 bundle → effective delta gate → AI 闸门 → embed → 首次赛前锁定。
# 已开赛/完赛 fixture: 只 audit；不补写伪赛前因子。
#
# 用法:
#   bash scripts/run_w1_scout_cycle.sh --dry-run
#   APIFOOTBALL_KEY=... DEEPSEEK_API_KEY=... bash scripts/run_w1_scout_cycle.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

PYTHON_BIN="${PYTHON_BIN:-python3}"
STATE_DIR="${W1_SCOUT_STATE_DIR:-state}"
DASHBOARD_DATA="${W1_SCOUT_DASHBOARD_DATA:-reports/dashboard/assets/w1_dashboard_data.json}"
BUNDLES_JSON="${STATE_DIR}/w1_scout_bundles.json"
SHA_FILE="${STATE_DIR}/.scout_bundles.sha"
STATUS_FILE="${STATE_DIR}/scout_cycle_status.json"
ERROR_LOG="${STATE_DIR}/scout_cycle_errors.log"

FETCH_CMD="${W1_SCOUT_FETCH_CMD:-$PYTHON_BIN scripts/w1_scout_fetch_api_football.py}"
BUILD_CMD="${W1_SCOUT_BUILD_CMD:-$PYTHON_BIN scripts/w1_scout_bundle.py}"
ANALYST_CMD="${W1_SCOUT_ANALYST_CMD:-$PYTHON_BIN scripts/w1_scout_analyst.py}"
CHECK_CMD="${W1_SCOUT_CHECK_CMD:-$PYTHON_BIN scripts/check_w1_scout.py}"
EMBED_CMD="${W1_SCOUT_EMBED_CMD:-$PYTHON_BIN scripts/w1_scout_embed.py}"
LOCK_CMD="${W1_SCOUT_LOCK_CMD:-$PYTHON_BIN scripts/w1_scout_ledger.py lock}"
AUDIT_CMD="${W1_SCOUT_AUDIT_CMD:-$PYTHON_BIN scripts/w1_scout_ledger.py audit}"

ts() { date -u +%FT%TZ; }
log() { echo "[$(ts)] $*"; }
record_error() {
  [ "$DRY_RUN" = "1" ] && return 0
  mkdir -p "$STATE_DIR"
  printf '[%s] %s\n' "$(ts)" "$*" >> "$ERROR_LOG"
}
record_status() {
  [ "$DRY_RUN" = "1" ] && return 0
  mkdir -p "$STATE_DIR"
  W1_SCOUT_STATUS_PHASE="$1" \
  W1_SCOUT_STATUS_RESULT="$2" \
  W1_SCOUT_STATUS_MESSAGE="$3" \
  W1_SCOUT_STATUS_DRY_RUN="$DRY_RUN" \
  W1_SCOUT_STATUS_FILE="$STATUS_FILE" \
  "$PYTHON_BIN" - <<'PY'
import json, os
from datetime import datetime, timezone
path = os.environ["W1_SCOUT_STATUS_FILE"]
payload = {
    "schema_version": "W1_SCOUT_CYCLE_STATUS_G2_V1",
    "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "phase": os.environ["W1_SCOUT_STATUS_PHASE"],
    "result": os.environ["W1_SCOUT_STATUS_RESULT"],
    "message_cn": os.environ["W1_SCOUT_STATUS_MESSAGE"],
    "dry_run": os.environ["W1_SCOUT_STATUS_DRY_RUN"] == "1",
    "redlines_cn": "研究用途 · 非推介 · 非独立优势；失败不推进旧 call。",
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

future_fixtures() {
  W1_SCOUT_DASHBOARD_DATA="$DASHBOARD_DATA" "$PYTHON_BIN" - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

def parse_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

path = Path(os.environ["W1_SCOUT_DASHBOARD_DATA"])
if not path.is_file():
    print("")
    raise SystemExit(0)
now = datetime.now(timezone.utc)
records = json.loads(path.read_text(encoding="utf-8")).get("match_records", [])
ids = []
for rec in records:
    kickoff = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
    if kickoff and kickoff > now:
        ids.append(str(rec.get("fixture_id")))
print(" ".join(ids))
PY
}

effective_hash() {
  if [ -n "${W1_SCOUT_FORCE_HASH:-}" ]; then
    printf '%s\n' "$W1_SCOUT_FORCE_HASH"
    return 0
  fi
  W1_SCOUT_BUNDLES_JSON="$BUNDLES_JSON" \
  W1_SCOUT_DASHBOARD_DATA="$DASHBOARD_DATA" \
  "$PYTHON_BIN" - <<'PY'
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path

VOLATILE = {"fetched_at_utc", "generated_at_utc", "updated_at", "requested_at", "fetched_at"}

def parse_dt(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def scrub(value):
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in sorted(value.items()) if k not in VOLATILE}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value

dash = Path(os.environ["W1_SCOUT_DASHBOARD_DATA"])
future = set()
if dash.is_file():
    now = datetime.now(timezone.utc)
    for rec in json.loads(dash.read_text(encoding="utf-8")).get("match_records", []):
        ko = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
        if ko and ko > now:
            future.add(str(rec.get("fixture_id")))

bundles_path = Path(os.environ["W1_SCOUT_BUNDLES_JSON"])
if not bundles_path.is_file():
    print("missing-bundles")
    raise SystemExit(0)
bundles = json.loads(bundles_path.read_text(encoding="utf-8")).get("bundles", [])
selected = [scrub(b) for b in bundles if str(b.get("fixture_id")) in future]
blob = json.dumps({"future_fixture_effective_bundles": selected}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
print(hashlib.sha1(blob.encode("utf-8")).hexdigest())
PY
}

log "W1_SCOUT G2 cycle start"
FUTURES="$(future_fixtures)"
FUTURE_COUNT=0
if [ -n "$FUTURES" ]; then
  # shellcheck disable=SC2086
  set -- $FUTURES
  FUTURE_COUNT=$#
fi
log "future fixtures selected=${FUTURE_COUNT}"

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: no external fetch, no AI call, no state write, no embed, no lock"
  exit 0
fi

record_status "start" "running" "Scout 自动周期启动。"

if [ "$FUTURE_COUNT" -gt 0 ]; then
  FETCH_ARGS=""
  for fid in $FUTURES; do
    FETCH_ARGS="${FETCH_ARGS} --fixture ${fid}"
  done
  # shellcheck disable=SC2086
  if ! ${FETCH_CMD} ${FETCH_ARGS}; then
    log "fetch failed/partial -> continue with existing local data only; no fake values"
    record_error "fetch failed/partial; continued with existing local data"
  fi
else
  log "no future fixture -> skip factor fetch; audit only"
fi

if ! ${BUILD_CMD}; then
  record_status "bundle" "failed" "bundle 组装失败；不调用 AI、不上屏、不锁定。"
  record_error "bundle build failed"
  exit 1
fi

if [ "$FUTURE_COUNT" -eq 0 ]; then
  ${AUDIT_CMD}
  record_status "audit_only" "ok" "没有未来 fixture；本轮只执行赛后 audit。"
  log "W1_SCOUT cycle done (audit only)"
  exit 0
fi

NEW="$(effective_hash)"
PREV="$(cat "$SHA_FILE" 2>/dev/null || echo "")"
if [ "$NEW" = "$PREV" ]; then
  log "no effective delta -> skip DeepSeek, embed, lock; audit only"
  ${AUDIT_CMD}
  record_status "no_delta" "ok" "赛前有效因子无变化；未调用 AI、未上屏、未锁定，仅 audit。"
  log "W1_SCOUT cycle done (no delta)"
  exit 0
fi

log "effective delta -> DeepSeek analyst"
if ! ${ANALYST_CMD}; then
  log "analyst failed -> do not update sha, do not embed, do not lock; audit only"
  record_status "analyst" "failed" "AI 分析师失败；未更新指纹、未上屏、未锁定。"
  record_error "analyst failed; sha/embed/lock blocked"
  ${AUDIT_CMD}
  exit 1
fi

if ! ${CHECK_CMD}; then
  log "check_w1_scout failed -> do not update sha, do not embed, do not lock"
  record_status "checker" "failed" "Scout 闸门失败；未更新指纹、未上屏、未锁定。"
  record_error "check_w1_scout failed; sha/embed/lock blocked"
  exit 1
fi

mkdir -p "$STATE_DIR"
echo "$NEW" > "$SHA_FILE"
${EMBED_CMD}
${LOCK_CMD}
${AUDIT_CMD}
record_status "complete" "ok" "Scout 周期完成；AI call 已过闸门并完成可见性/锁定/audit。"
log "W1_SCOUT G2 cycle done"
