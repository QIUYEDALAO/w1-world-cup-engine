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
DASHBOARD_HTML="${W1_SCOUT_DASHBOARD_HTML:-reports/dashboard/W1_VISUAL_DASHBOARD.html}"
BUNDLES_JSON="${STATE_DIR}/w1_scout_bundles.json"
SHA_FILE="${STATE_DIR}/.scout_bundles.sha"
STATUS_FILE="${STATE_DIR}/scout_cycle_status.json"
ERROR_LOG="${STATE_DIR}/scout_cycle_errors.log"
MEMORY_FILES=(
  "state/scout_audit.jsonl"
  "state/scout_track_record.json"
  "state/scout_lessons.md"
  "state/scout_lock.jsonl"
)

FETCH_CMD="${W1_SCOUT_FETCH_CMD:-$PYTHON_BIN scripts/w1_scout_fetch_api_football.py}"
BUILD_CMD="${W1_SCOUT_BUILD_CMD:-$PYTHON_BIN scripts/w1_scout_bundle.py}"
ANALYST_CMD="${W1_SCOUT_ANALYST_CMD:-$PYTHON_BIN scripts/w1_scout_analyst.py}"
CHECK_CMD="${W1_SCOUT_CHECK_CMD:-$PYTHON_BIN scripts/check_w1_scout.py}"
EMBED_CMD="${W1_SCOUT_EMBED_CMD:-$PYTHON_BIN scripts/w1_scout_embed.py}"
LOCK_CMD="${W1_SCOUT_LOCK_CMD:-$PYTHON_BIN scripts/w1_scout_ledger.py lock}"
RESULT_SYNC_CMD="${W1_RESULT_SYNC_CMD:-$PYTHON_BIN scripts/w1_result_sync.py}"
AUDIT_CMD="${W1_SCOUT_AUDIT_CMD:-$PYTHON_BIN scripts/w1_scout_ledger.py audit}"
REVIEW_CMD="${W1_SCOUT_REVIEW_CMD:-$PYTHON_BIN scripts/w1_scout_review.py}"
CALIBRATION_CMD="${W1_SCOUT_CALIBRATION_CMD:-$PYTHON_BIN scripts/w1_scout_calibration.py}"
ANALYST_TIMEOUT_SECONDS="${W1_SCOUT_ANALYST_TIMEOUT_SECONDS:-240}"
AUTOPILOT_MAX_FIXTURES_PER_RUN="${W1_SCOUT_AUTOPILOT_MAX_FIXTURES_PER_RUN:-2}"
FETCH_OK=0
FETCH_FAIL=0
GENERATED_COUNT=0
EMBEDDED_COUNT=0
FAILED_COUNT=0
PROCESSED_COUNT=0
FAILED_FIXTURES=""
ORIGINAL_FUTURE_COUNT=0

ts() { date -u +%FT%TZ; }
log() { echo "[$(ts)] $*"; }
persist_memory() {
  [ "$DRY_RUN" = "1" ] && return 0
  [ "${W1_SCOUT_DISABLE_MEMORY_COMMIT:-0}" = "1" ] && return 0
  git add "${MEMORY_FILES[@]}" 2>/dev/null || return 0
  git diff --cached --quiet -- "${MEMORY_FILES[@]}" || \
    git commit -m "scout memory: cycle $(date -u +%FT%TZ)" >/dev/null 2>&1 || true
}
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
  W1_SCOUT_STATUS_FETCH_OK="${FETCH_OK}" \
  W1_SCOUT_STATUS_FETCH_FAIL="${FETCH_FAIL}" \
  W1_SCOUT_STATUS_GENERATED_COUNT="${GENERATED_COUNT}" \
  W1_SCOUT_STATUS_EMBEDDED_COUNT="${EMBEDDED_COUNT}" \
  W1_SCOUT_STATUS_FAILED_COUNT="${FAILED_COUNT}" \
  W1_SCOUT_STATUS_PROCESSED_COUNT="${PROCESSED_COUNT}" \
  W1_SCOUT_STATUS_PENDING_COUNT="$(( ORIGINAL_FUTURE_COUNT > PROCESSED_COUNT ? ORIGINAL_FUTURE_COUNT - PROCESSED_COUNT : 0 ))" \
  W1_SCOUT_STATUS_FAILED_FIXTURES="${FAILED_FIXTURES}" \
  W1_SCOUT_STATUS_FILE="$STATUS_FILE" \
  W1_SCOUT_DASHBOARD_DATA="$DASHBOARD_DATA" \
  "$PYTHON_BIN" - <<'PY'
import json, os
from datetime import datetime, timezone
from pathlib import Path

def odds_move_summary(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"status": "UNKNOWN", "moved_fixtures": [], "message_cn": "暂无盘口异动遥测"}
    try:
        records = json.loads(p.read_text(encoding="utf-8")).get("match_records", [])
    except Exception:
        return {"status": "UNKNOWN", "moved_fixtures": [], "message_cn": "盘口异动遥测读取失败"}
    moved = []
    statuses = []
    stable_like = {"", "STABLE", "UNKNOWN", "DATA_INSUFFICIENT", "SOFT_THIN", "数据不足"}
    for rec in records:
        om = rec.get("odds_movement") or {}
        status = str(om.get("status") or om.get("movement_status") or "").strip()
        if status:
            statuses.append(status)
        if status.upper() not in stable_like and status not in stable_like:
            moved.append(str(rec.get("fixture_id") or rec.get("match") or "unknown"))
    overall = "MOVING" if moved else ("STABLE" if statuses else "UNKNOWN")
    msg = f"{len(moved)} 场出现非稳定盘口状态" if moved else "未发现明确盘口异动"
    return {"status": overall, "moved_fixtures": moved[:8], "message_cn": msg}

path = os.environ["W1_SCOUT_STATUS_FILE"]
prior = {}
try:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            prior = json.load(f)
except Exception:
    prior = {}
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
fetch_ok = os.environ["W1_SCOUT_STATUS_FETCH_OK"] == "1"
fetch_fail = os.environ["W1_SCOUT_STATUS_FETCH_FAIL"] == "1"
cumulative_fetch_ok = int(prior.get("cumulative_fetch_ok") or 0) + (1 if fetch_ok else 0)
payload = {
    "schema_version": "W1_SCOUT_CYCLE_STATUS_G2_V1",
    "updated_at_utc": now,
    "last_run_utc": now,
    "last_fetch_utc": now if fetch_ok else prior.get("last_fetch_utc"),
    "fetch_ok": fetch_ok,
    "fetch_fail": fetch_fail,
    "cumulative_fetch_ok": cumulative_fetch_ok,
    "odds_move_summary": odds_move_summary(os.environ.get("W1_SCOUT_DASHBOARD_DATA", "")),
    "phase": os.environ["W1_SCOUT_STATUS_PHASE"],
    "result": os.environ["W1_SCOUT_STATUS_RESULT"],
    "message_cn": os.environ["W1_SCOUT_STATUS_MESSAGE"],
    "dry_run": os.environ["W1_SCOUT_STATUS_DRY_RUN"] == "1",
    "generated_count": int(os.environ.get("W1_SCOUT_STATUS_GENERATED_COUNT") or 0),
    "embedded_count": int(os.environ.get("W1_SCOUT_STATUS_EMBEDDED_COUNT") or 0),
    "failed_count": int(os.environ.get("W1_SCOUT_STATUS_FAILED_COUNT") or 0),
    "processed_count": int(os.environ.get("W1_SCOUT_STATUS_PROCESSED_COUNT") or 0),
    "pending_count": int(os.environ.get("W1_SCOUT_STATUS_PENDING_COUNT") or 0),
    "failed_fixtures": [x for x in os.environ.get("W1_SCOUT_STATUS_FAILED_FIXTURES", "").split() if x],
    "redlines_cn": "研究用途 · 非推介 · 非独立优势；失败不推进旧 call。",
}

with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift
  W1_SCOUT_TIMEOUT_SECONDS="$timeout_seconds" \
  W1_SCOUT_TIMEOUT_CMD="$*" \
  "$PYTHON_BIN" - <<'PY'
import os, subprocess, sys

timeout = int(float(os.environ.get("W1_SCOUT_TIMEOUT_SECONDS") or "240"))
cmd = os.environ.get("W1_SCOUT_TIMEOUT_CMD") or ""
try:
    proc = subprocess.run(cmd, shell=True, timeout=timeout)
except subprocess.TimeoutExpired:
    print(f"command timed out after {timeout}s: {cmd}", file=sys.stderr)
    raise SystemExit(124)
raise SystemExit(proc.returncode)
PY
}

run_audit_review_calibration() {
  local allow_embed="${1:-0}"
  if ! ${RESULT_SYNC_CMD}; then
    record_error "result sync failed WARN_ONLY; audit/review/calibration continue with local results overlay"
  fi
  ${AUDIT_CMD}
  if [ "${W1_SCOUT_ENABLE_REVIEW:-0}" = "1" ]; then
    if ! ${REVIEW_CMD}; then
      record_error "scout review failed; lock/read advancement remains blocked"
    fi
  fi
  if ! ${CALIBRATION_CMD}; then
    record_error "scout calibration failed"
    return 1
  fi
  if [ "$allow_embed" = "1" ]; then
    ${EMBED_CMD}
  fi
}

future_fixtures() {
  W1_SCOUT_DASHBOARD_DATA="$DASHBOARD_DATA" \
  W1_SCOUT_CALLS_JSON="${STATE_DIR}/w1_scout_calls.json" \
  W1_SCOUT_LOCK_JSONL="${STATE_DIR}/scout_lock.jsonl" \
  W1_SCOUT_DASHBOARD_HTML="$DASHBOARD_HTML" \
  "$PYTHON_BIN" - <<'PY'
import json, os
import re
from datetime import datetime, timedelta, timezone
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
has_call = set()
calls_path = Path(os.environ["W1_SCOUT_CALLS_JSON"])
if calls_path.is_file():
    try:
        for call in json.loads(calls_path.read_text(encoding="utf-8")).get("calls", []):
            if isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                has_call.add(str(call.get("fixture_id") or ""))
    except Exception:
        pass
locked = set()
lock_path = Path(os.environ["W1_SCOUT_LOCK_JSONL"])
if lock_path.is_file():
    try:
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                locked.add(str(json.loads(line).get("fixture_id") or ""))
    except Exception:
        pass
embedded = set()
html_path = Path(os.environ["W1_SCOUT_DASHBOARD_HTML"])
if html_path.is_file():
    try:
        m = re.search(r'<script id="w1-scout-calls" type="application/json">(.*?)</script>', html_path.read_text(encoding="utf-8"), re.S)
        if m:
            for call in json.loads(m.group(1)).get("calls", []):
                if isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                    embedded.add(str(call.get("fixture_id") or ""))
    except Exception:
        pass
now = datetime.now(timezone.utc)
try:
    lookahead_hours = float(os.environ.get("W1_SCOUT_LOOKAHEAD_HOURS", "48"))
except ValueError:
    lookahead_hours = 48.0
force_fixture = os.environ.get("W1_SCOUT_FORCE_FIXTURE", "").strip()
until = now + timedelta(hours=max(1.0, lookahead_hours))
records = json.loads(path.read_text(encoding="utf-8")).get("match_records", [])
pending = []
complete = []
for rec in records:
    kickoff = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
    if kickoff and kickoff > now and (kickoff <= until or str(rec.get("fixture_id")) == force_fixture):
        fid = str(rec.get("fixture_id"))
        if fid not in has_call or fid not in locked or fid not in embedded:
            pending.append(fid)
        else:
            complete.append(fid)
print(" ".join(pending + complete))
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
force = os.environ.get("W1_SCOUT_FORCE_FIXTURE", "").strip()
if dash.is_file():
    now = datetime.now(timezone.utc)
    for rec in json.loads(dash.read_text(encoding="utf-8")).get("match_records", []):
        ko = parse_dt(rec.get("kickoff_utc") or rec.get("kickoff"))
        if ko and ko > now:
            future.add(str(rec.get("fixture_id")))
if force:
    future = {force} if force in future else set()

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
FORCE_FIXTURE="${W1_SCOUT_FORCE_FIXTURE:-}"
if [ -n "$FORCE_FIXTURE" ]; then
  case " $FUTURES " in
    *" $FORCE_FIXTURE "*) FUTURES="$FORCE_FIXTURE"; FUTURE_COUNT=1 ;;
    *)
      log "force fixture ${FORCE_FIXTURE} is not future -> refuse pre-match Scout read; audit/review/calibration only"
      if [ "$DRY_RUN" = "1" ]; then
        log "dry-run: force_fixture=${FORCE_FIXTURE} refused_pre_match=true ai_called_count=0 embedded_count=0 locked_count=0"
        exit 0
      fi
      record_status "force_fixture" "refused" "指定 fixture 已开赛或不在未来赛程内；拒绝生成伪赛前解读，仅允许 audit/review/calibration。"
      run_audit_review_calibration 1
      persist_memory
      exit 0
      ;;
  esac
fi
log "future fixtures selected=${FUTURE_COUNT}"
ORIGINAL_FUTURE_COUNT="$FUTURE_COUNT"
if [ -z "$FORCE_FIXTURE" ] && [ "$FUTURE_COUNT" -gt 0 ]; then
  if ! [[ "$AUTOPILOT_MAX_FIXTURES_PER_RUN" =~ ^[0-9]+$ ]]; then
    AUTOPILOT_MAX_FIXTURES_PER_RUN=2
  fi
  if [ "$AUTOPILOT_MAX_FIXTURES_PER_RUN" -lt 1 ]; then
    AUTOPILOT_MAX_FIXTURES_PER_RUN=1
  fi
  if [ "$FUTURE_COUNT" -gt "$AUTOPILOT_MAX_FIXTURES_PER_RUN" ]; then
    LIMITED_FUTURES=""
    n=0
    for fid in $FUTURES; do
      n=$((n + 1))
      [ "$n" -le "$AUTOPILOT_MAX_FIXTURES_PER_RUN" ] || break
      LIMITED_FUTURES="${LIMITED_FUTURES} ${fid}"
    done
    FUTURES="$(echo "$LIMITED_FUTURES" | awk '{$1=$1; print}')"
    FUTURE_COUNT="$AUTOPILOT_MAX_FIXTURES_PER_RUN"
    log "autopilot max fixtures per run=${AUTOPILOT_MAX_FIXTURES_PER_RUN}; this run fixtures=${FUTURES}; remaining=$((ORIGINAL_FUTURE_COUNT - FUTURE_COUNT))"
  fi
fi

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: no external fetch, no AI call, no state write, no embed, no lock"
  log "dry_run=true force_fixture=${FORCE_FIXTURE:-none} ai_called_count=0 embedded_count=0 locked_count=0 no_old_call_advanced=true"
  exit 0
fi

record_status "start" "running" "Scout 自动周期启动。"

if [ "$FUTURE_COUNT" -gt 0 ]; then
  if [ "${W1_SCOUT_SKIP_FETCH:-0}" = "1" ]; then
    log "Scout factor fetch skipped by W1_SCOUT_SKIP_FETCH=1; use existing local data only"
  else
    FETCH_ARGS=""
    for fid in $FUTURES; do
      FETCH_ARGS="${FETCH_ARGS} --fixture ${fid}"
    done
    # shellcheck disable=SC2086
    if ! ${FETCH_CMD} ${FETCH_ARGS}; then
      FETCH_FAIL=1
      log "fetch failed/partial -> continue with existing local data only; no fake values"
      record_error "fetch failed/partial; continued with existing local data"
    else
      FETCH_OK=1
    fi
  fi
else
  log "no future fixture -> skip factor fetch; audit only"
fi

if ! ${BUILD_CMD}; then
  record_status "bundle" "failed" "bundle 组装失败；不调用 AI、不上屏、不锁定。"
  record_error "bundle build failed"
  exit 1
fi

missing_scout_reads() {
  W1_SCOUT_FUTURES="$FUTURES" \
  W1_SCOUT_CALLS_JSON="${STATE_DIR}/w1_scout_calls.json" \
  W1_SCOUT_LOCK_JSONL="${STATE_DIR}/scout_lock.jsonl" \
  "$PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path

futures = [fid for fid in os.environ.get("W1_SCOUT_FUTURES", "").split() if fid]
if not futures:
    print("")
    raise SystemExit(0)
has_call = set()

calls_path = Path(os.environ["W1_SCOUT_CALLS_JSON"])
if calls_path.is_file():
    try:
        for call in json.loads(calls_path.read_text(encoding="utf-8")).get("calls", []):
            fid = str(call.get("fixture_id") or "")
            if fid in futures and isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                has_call.add(fid)
    except Exception:
        pass

locked = set()
lock_path = Path(os.environ["W1_SCOUT_LOCK_JSONL"])
if lock_path.is_file():
    try:
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            locked.add(str(json.loads(line).get("fixture_id") or ""))
    except Exception:
        pass

missing = {fid for fid in futures if fid not in has_call or fid not in locked}
print(" ".join(fid for fid in futures if fid in missing))
PY
}

dashboard_missing_embeds() {
  W1_SCOUT_FUTURES="$FUTURES" \
  W1_SCOUT_CALLS_JSON="${STATE_DIR}/w1_scout_calls.json" \
  W1_SCOUT_DASHBOARD_HTML="$DASHBOARD_HTML" \
  "$PYTHON_BIN" - <<'PY'
import json, os, re
from pathlib import Path

futures = [fid for fid in os.environ.get("W1_SCOUT_FUTURES", "").split() if fid]
if not futures:
    print("")
    raise SystemExit(0)

has_call = set()
calls_path = Path(os.environ["W1_SCOUT_CALLS_JSON"])
if calls_path.is_file():
    try:
        for call in json.loads(calls_path.read_text(encoding="utf-8")).get("calls", []):
            fid = str(call.get("fixture_id") or "")
            if fid in futures and isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                has_call.add(fid)
    except Exception:
        pass

has_embed = set()
html_path = Path(os.environ["W1_SCOUT_DASHBOARD_HTML"])
if html_path.is_file():
    try:
        m = re.search(r'<script id="w1-scout-calls" type="application/json">(.*?)</script>', html_path.read_text(encoding="utf-8"), re.S)
        if m:
            for call in json.loads(m.group(1)).get("calls", []):
                fid = str(call.get("fixture_id") or "")
                if fid in futures and isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                    has_embed.add(fid)
    except Exception:
        pass

missing = [fid for fid in futures if fid in has_call and fid not in has_embed]
print(" ".join(missing))
PY
}

count_scout_reads_for_futures() {
  W1_SCOUT_FUTURES="$FUTURES" \
  W1_SCOUT_CALLS_JSON="${STATE_DIR}/w1_scout_calls.json" \
  "$PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path

futures = {fid for fid in os.environ.get("W1_SCOUT_FUTURES", "").split() if fid}
if not futures:
    print(0)
    raise SystemExit(0)
count = 0
path = Path(os.environ["W1_SCOUT_CALLS_JSON"])
if path.is_file():
    try:
        for call in json.loads(path.read_text(encoding="utf-8")).get("calls", []):
            if str(call.get("fixture_id") or "") in futures and isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                count += 1
    except Exception:
        pass
print(count)
PY
}

missing_call_fixtures_for_futures() {
  W1_SCOUT_FUTURES="$FUTURES" \
  W1_SCOUT_CALLS_JSON="${STATE_DIR}/w1_scout_calls.json" \
  "$PYTHON_BIN" - <<'PY'
import json, os
from pathlib import Path

futures = [fid for fid in os.environ.get("W1_SCOUT_FUTURES", "").split() if fid]
has_call = set()
path = Path(os.environ["W1_SCOUT_CALLS_JSON"])
if path.is_file():
    try:
        for call in json.loads(path.read_text(encoding="utf-8")).get("calls", []):
            if isinstance(call.get("read"), dict) and call.get("independent_edge") is False:
                has_call.add(str(call.get("fixture_id") or ""))
    except Exception:
        pass
print(" ".join(fid for fid in futures if fid not in has_call))
PY
}

if [ "$FUTURE_COUNT" -eq 0 ]; then
  run_audit_review_calibration 1
  persist_memory
  record_status "audit_only" "ok" "没有未来 fixture；本轮只执行赛后 audit。"
  log "W1_SCOUT cycle done (audit only)"
  exit 0
fi

NEW="$(effective_hash)"
PREV="$(cat "$SHA_FILE" 2>/dev/null || echo "")"
MISSING_READS="$(missing_scout_reads)"
DASHBOARD_MISSING_EMBEDS="$(dashboard_missing_embeds)"
if [ -n "$MISSING_READS" ]; then
  log "存在未生成赛前解读的 fixture，本轮强制生成首版解读: ${MISSING_READS}"
  record_status "missing_read" "running" "存在未生成赛前解读的 fixture，本轮强制生成首版解读。"
fi
if [ "${W1_SCOUT_PREMATCH_ONLY:-0}" = "1" ] && [ -z "$MISSING_READS" ] && [ -n "$DASHBOARD_MISSING_EMBEDS" ]; then
  log "existing Scout read found but dashboard embed missing: ${DASHBOARD_MISSING_EMBEDS}; embedding without AI/lock"
  ${EMBED_CMD}
  record_status "embed_existing" "ok" "已有合法赛前解读；本轮补写 dashboard 上屏，不重复调用 AI、不重新锁定。"
  exit 0
fi
if [ "$NEW" = "$PREV" ] && [ -z "$MISSING_READS" ]; then
  if [ "${W1_SCOUT_PREMATCH_ONLY:-0}" = "1" ]; then
    log "no effective delta -> existing pre-match Scout read/lock is current; skip audit/review/calibration for manual refresh"
    record_status "no_delta" "ok" "已有有效赛前解读；手动强刷不重复调用 AI、不重新锁定。"
    exit 0
  fi
  log "no effective delta -> skip DeepSeek and lock; audit/review/calibration visibility only"
  run_audit_review_calibration 1
  persist_memory
  record_status "no_delta" "ok" "赛前有效因子无变化；未调用 AI、未锁定；仅更新 audit/review/calibration 可见性。"
  log "W1_SCOUT cycle done (no delta)"
  exit 0
fi

log "effective delta -> DeepSeek analyst"
READS_BEFORE="$(count_scout_reads_for_futures)"
ANALYST_ARGS=""
for fid in $FUTURES; do
  ANALYST_ARGS="${ANALYST_ARGS} --fixture ${fid}"
done
if [ -z "$ANALYST_ARGS" ] && [ -n "$FORCE_FIXTURE" ]; then
  ANALYST_ARGS="--fixture ${FORCE_FIXTURE}"
fi
# shellcheck disable=SC2086
W1_SCOUT_ALLOW_PARTIAL_WRITES=1 run_with_timeout "$ANALYST_TIMEOUT_SECONDS" ${ANALYST_CMD} ${ANALYST_ARGS}
ANALYST_RC=$?
PROCESSED_COUNT="$FUTURE_COUNT"
if [ "$ANALYST_RC" -eq 124 ]; then
  FAILED_COUNT="$FUTURE_COUNT"
  FAILED_FIXTURES="$FUTURES"
  log "analyst timeout -> try embedding any previously valid reads, do not overwrite old recommendations"
  record_error "analyst timeout after ${ANALYST_TIMEOUT_SECONDS}s; fixtures=${FUTURES}"
elif [ "$ANALYST_RC" -ne 0 ]; then
  FAILED_COUNT="$FUTURE_COUNT"
  FAILED_FIXTURES="$FUTURES"
  log "analyst failed/partial -> try embedding validated partial reads; do not discard successes"
  record_error "analyst failed/partial rc=${ANALYST_RC}; fixtures=${FUTURES}"
fi
READS_AFTER="$(count_scout_reads_for_futures)"
GENERATED_COUNT="$(( READS_AFTER > READS_BEFORE ? READS_AFTER - READS_BEFORE : 0 ))"
if [ "$ANALYST_RC" -ne 0 ]; then
  FAILED_FIXTURES="$(missing_call_fixtures_for_futures)"
  FAILED_COUNT=0
  if [ -n "$FAILED_FIXTURES" ]; then
    # shellcheck disable=SC2086
    set -- $FAILED_FIXTURES
    FAILED_COUNT=$#
  fi
fi
if [ "$ANALYST_RC" -ne 0 ] && [ "$READS_AFTER" -eq 0 ]; then
  log "analyst failed and produced no valid read -> no embed/lock; audit only"
  record_status "analyst" "failed" "AI 分析师失败；未生成可上屏解读。旧推荐未覆盖，将在下轮自动周期重试。"
  run_audit_review_calibration 0
  persist_memory
  exit 1
fi

if ! ${CHECK_CMD}; then
  log "check_w1_scout failed -> do not update sha, do not embed, do not lock"
  record_status "checker" "failed" "Scout 闸门失败；未更新指纹、未上屏、未锁定。"
  record_error "check_w1_scout failed; sha/embed/lock blocked"
  run_audit_review_calibration 0
  persist_memory
  exit 1
fi

mkdir -p "$STATE_DIR"
echo "$NEW" > "$SHA_FILE"
${EMBED_CMD}
EMBEDDED_COUNT="$READS_AFTER"
${LOCK_CMD}
if [ "$GENERATED_COUNT" -eq 0 ] && [ "$READS_AFTER" -gt 0 ]; then
  GENERATED_COUNT="$READS_AFTER"
fi
if [ "$ANALYST_RC" -ne 0 ]; then
  record_status "analyst" "partial" "Scout 自动周期部分完成：已生成 ${GENERATED_COUNT} 场，已上屏 ${EMBEDDED_COUNT} 场，失败 ${FAILED_COUNT} 场；下轮自动重试剩余 fixture。"
  log "W1_SCOUT cycle partial; generated=${GENERATED_COUNT} embedded=${EMBEDDED_COUNT} failed=${FAILED_COUNT}"
  exit 0
fi
if [ "${W1_SCOUT_PREMATCH_ONLY:-0}" = "1" ]; then
  record_status "complete" "ok" "Scout 单场赛前解读已完成；手动强刷不运行赛后 audit/review/calibration。"
  log "W1_SCOUT G2 cycle done (prematch only)"
  exit 0
fi
run_audit_review_calibration 1
persist_memory
record_status "complete" "ok" "Scout 周期完成；AI call 已过闸门并完成可见性/锁定/audit。"
log "W1_SCOUT G2 cycle done"
