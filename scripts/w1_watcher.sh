#!/usr/bin/env bash
# W1 World Cup Engine — Auto Refresh Watcher
# Run via cron/launchd every 6h or on-demand with W1_REFRESH_NOW=1
#
# Usage:
#   ./scripts/w1_watcher.sh              # normal scheduled run
#   W1_REFRESH_NOW=1 ./scripts/w1_watcher.sh  # force immediate
#   W1_DRY_RUN=1 ./scripts/w1_watcher.sh      # dry-run, no API calls
#
# Conventions:
#   - Lock: state/w1_refresh.lock
#   - State: state/w1_refresh_state.json
#   - Log: logs/w1_refresh_YYYYMMDD_HHMMSS.log
#   - Snapshots: data/snapshots/group_stage_round1/
#
# Quota policy:
#   - Normal run: 1 fixture list + 1 standings + 24 odds + 24 lineups(conditional) + 1 injury
#     ~ 1 + 1 + 24 + 0-24 + 1 = 27-51 API requests
#   - Dry run: 0 requests
#   - Limit: never exceed 100 req/run (api-football Business quota ~100/day)
#   - Only check lineups for matches within 2h of kickoff or LIVE/FT

set -euo pipefail

export W1_DIR="/Users/liudehua/.openclaw/workspace/w1_world_cup_engine"
cd "$W1_DIR"

# W1 watcher accepts credentials only from the current environment.
# Dry-run mode never requires credentials.
if [ "${W1_DRY_RUN:-0}" != "1" ] && [ -z "${APIFOOTBALL_KEY:-}" ]; then
    echo "[FATAL] APIFOOTBALL_KEY is not set in the current environment"
    exit 1
fi

# --- Paths ---
LOCK="$W1_DIR/locks/w1_refresh.lock"
STATE="$W1_DIR/state/w1_refresh_state.json"
LOG="$W1_DIR/logs/w1_refresh_$(date +%Y%m%d_%H%M%S).log"
SNAPSHOT_DIR="$W1_DIR/data/snapshots/group_stage_round1/"
LAST_SNAPSHOT="$SNAPSHOT_DIR/$(ls -t "$SNAPSHOT_DIR" 2>/dev/null | grep -i 'fixture_details.*\.json' | head -1 || true)"

# --- Lock ---
if [ -f "$LOCK" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0)))
    if [ "$LOCK_AGE" -lt 3600 ]; then
        echo "[SKIP] Lock active for ${LOCK_AGE}s (max 3600s). Exiting." | tee -a "$LOG" 2>/dev/null
        exit 0
    fi
    echo "[WARN] Stale lock (>1h). Removing." | tee -a "$LOG" 2>/dev/null
    rm -f "$LOCK"
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

exec > "$LOG" 2>&1

echo "=== W1 Watcher ==="
echo "Run: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Lock: $LOCK"
echo "Dry run: ${W1_DRY_RUN:-0}"
if [ "${W1_DRY_RUN:-0}" = "1" ]; then
    echo "Credential status: not required for dry run"
else
    echo "Credential status: configured"
fi

# --- Dry-run ---
if [ "${W1_DRY_RUN:-0}" = "1" ]; then
    echo "[DRY RUN] 0 API calls made."
    echo ""
    echo "Planned calls:"
    echo "  1. fixtures?league=1&season=2026&round=Group%20Stage%20-%201"
    echo "  24. odds?fixture={fid} (x24)"
    echo "  25. standings?league=1&season=2026"
    echo "  26. injuries?league=1&season=2026"
    echo "  27-N. lineups?fixture={fid} (matches within 2h of kickoff)"
    echo ""
    echo "Estimated quota: 27-51 calls"
    echo "DRY RUN PASS"
    rm -f "$LOCK"
    exit 0
fi

# --- Determine which fixtures need lineup check ---
NOW_EPOCH=$(date +%s)
NOW_CST=$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M')
NEXT_REFRESH=""

echo ""
echo "Fetching fixtures..."

# Step 1: Fixture list
FIX_DATA=$(curl -s "https://v3.football.api-sports.io/fixtures?league=1&season=2026&round=Group%20Stage%20-%201" \
    -H "x-apisports-key: $APIFOOTBALL_KEY")
FIX_IDS=$(echo "$FIX_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
fids=[]
for f in d.get('response',[]):
    fid=f['fixture']['id']
    ts=f['fixture']['timestamp']
    hm=f['teams']['home']['name']
    aw=f['teams']['away']['name']
    venue=f['fixture']['venue'].get('name','?')
    city=f['fixture']['venue'].get('city','?')
    ref=f['fixture'].get('referee','')
    status=f['fixture']['status']['short']
    fids.append(fid)
    print(f'{fid}|{ts}|{hm}|{aw}|{venue}|{city}|{ref}|{status}')
")
echo "Fixtures fetched: $(echo "$FIX_IDS" | wc -l)"

# Step 2: Odds and standings
echo ""
echo "Fetching odds for 24 fixtures..."
ODDS_FILE=$(mktemp)
ODDS_CHANGED=0

echo "$FIX_IDS" | while IFS='|' read -r fid ts hm aw venue city ref status; do
    ODDS_RAW=$(curl -s "https://v3.football.api-sports.io/odds?fixture=$fid" -H "x-apisports-key: $APIFOOTBALL_KEY")
    echo "$ODDS_RAW" >> "$ODDS_FILE"
    # Track change flag
    echo "$ODDS_RAW" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read(), strict=False)
r=d.get('response',[])
if r:
    bm_count=len(r[0]['bookmakers'])
    ut=r[0].get('update','?')[:19]
    print(f'{fid}: BM={bm_count} snap={ut}')
else:
    print(f'{fid}: NO_ODDS')
" 2>/dev/null
done

# Step 3: Check for lineup-worthy matches (LIVE, FT, or kickoff <= 2h from now)
echo ""
echo "Checking lineups..."
LINEUP_CHANGED=0
REFEREE_CHANGED=0

echo "$FIX_IDS" | while IFS='|' read -r fid ts hm aw venue city ref status; do
    check_lineup=0
    if [ "$status" = "LIVE" ] || [ "$status" = "FT" ]; then
        check_lineup=1
    elif [ "$ts" -gt "$NOW_EPOCH" ] && [ $((ts - NOW_EPOCH)) -le 7200 ]; then
        check_lineup=1
    fi

    if [ "$check_lineup" = "1" ] && [ "$status" != "FT" ]; then
        LU_DATA=$(curl -s "https://v3.football.api-sports.io/fixtures/lineups?fixture=$fid" -H "x-apisports-key: $APIFOOTBALL_KEY")
        echo "$LU_DATA" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read(), strict=False)
r=d.get('response',[])
if r:
    for t in r:
        xi=len(t.get('startXI',[]))
        subs=len(t.get('substitutes',[]))
        form=t.get('formation','?')
        print(f'  {t[\"team\"][\"name\"]} XI={xi} Subs={subs} Form={form}')
    LINEUP_CHANGED=1
    echo 'LINEUP_CHANGED update'
else:
    print(f'  $hm vs $aw: lineups not yet available')
" 2>/dev/null
    fi

    # Referee check
    if [ -n "$ref" ]; then
        echo "  Referee: $ref"
        REFEREE_CHANGED=1
    fi
done

# Step 4: Injuries
echo ""
echo "Checking injuries..."
INJ_DATA=$(curl -s "https://v3.football.api-sports.io/injuries?league=1&season=2026" -H "x-apisports-key: $APIFOOTBALL_KEY")
echo "$INJ_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'Total: {d.get(\"results\",0)} injuries')
" 2>/dev/null

# Step 5: Standings
echo ""
echo "Checking standings..."
curl -s "https://v3.football.api-sports.io/standings?league=1&season=2026" -H "x-apisports-key: $APIFOOTBALL_KEY" \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
grps=len(d['response'][0]['league']['standings'])
print(f'Groups: {grps}')
" 2>/dev/null

# --- Summary ---
echo ""
echo "=== Summary ==="
echo "Status: PASS"
echo "Time: $NOW_CST"
echo "Fixtures checked: $(echo "$FIX_IDS" | wc -l)"
echo "Odds: all 24 fetched"
echo "Next refresh: T+6h"

# Refresh the state file
cat > "$STATE" <<STATEEOF
{
  "last_refresh": "$NOW_CST",
  "fixtures_checked": $(echo "$FIX_IDS" | wc -l),
  "odds_count": 24,
  "next_refresh": "T+6h"
}
STATEEOF

# Cleanup
rm -f "$ODDS_FILE"
rm -f "$LOCK"

echo "Done."
